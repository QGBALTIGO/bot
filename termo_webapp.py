from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from termo_repository import (
    TermoDuplicateGuess,
    TermoHintAlreadyUsed,
    TermoInsufficientCoins,
    TermoInvalidGuess,
    TermoInvalidState,
    buy_hint,
    get_active_or_today,
    start_daily_game,
    start_train_game,
    submit_guess,
)
from termo_rules import HINT_COST_COINS
from termo_service import get_termo_dashboard
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page() -> str:
    return f'''<!doctype html>
<html lang="pt-br"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070a14"><title>Termo Anime • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.mode-row{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}}
.secondary{{min-height:48px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.045);font-weight:900;cursor:pointer}}
.board{{display:grid;gap:7px;margin-top:16px}}
.guess-row{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}}
.letter{{aspect-ratio:1;border:1px solid var(--line);border-radius:13px;background:rgba(255,255,255,.035);display:grid;place-items:center;font-size:clamp(18px,6vw,28px);font-weight:950;text-transform:uppercase;transition:transform .22s,background .22s,border-color .22s}}
.letter.correct{{background:rgba(114,241,189,.22);border-color:rgba(114,241,189,.52)}}
.letter.present{{background:rgba(255,211,108,.2);border-color:rgba(255,211,108,.48)}}
.letter.absent{{background:rgba(255,255,255,.065);color:rgba(255,255,255,.5)}}
.controls{{display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:14px}}
.controls input{{min-width:0;height:52px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.045);padding:0 15px;text-transform:lowercase;font-size:18px;font-weight:900;outline:0}}
.controls button{{min-width:86px;border:0;border-radius:16px;background:linear-gradient(135deg,var(--cyan),var(--violet));color:#07101a;font-weight:950;cursor:pointer}}
.info-row{{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}}
.hint{{margin-top:12px;padding:13px;border:1px solid rgba(255,211,108,.25);border-radius:16px;background:rgba(255,211,108,.07);display:none;line-height:1.5;font-size:13px}}
.end{{margin-top:14px;padding:15px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.04);display:none;line-height:1.55}}
.stats-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:12px}}
.rank{{display:grid;grid-template-columns:36px 1fr auto;gap:8px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}}.rank:last-child{{border-bottom:0}}
.rank strong{{font-size:13px}}.muted{{color:var(--muted)}}
@media(min-width:700px){{.board{{width:min(500px,100%);margin-left:auto;margin-right:auto}}}}
</style></head><body>
<div class="v2-shell">
<section class="v2-hero"><div class="v2-eyebrow">Source Baltigo • Palavra diária</div><h1 class="v2-title">Termo<br>Anime.</h1><p class="v2-copy">Descubra a palavra de 6 letras em até 6 tentativas. O jogo diário recompensa coins e XP; treino é livre e não altera o ranking.</p>
<div class="v2-metrics"><div class="v2-metric"><span class="v2-metric-label">Tentativas</span><span class="v2-metric-value" id="attempts">0/6</span></div><div class="v2-metric"><span class="v2-metric-label">Streak</span><span class="v2-metric-value" id="streak">0</span></div><div class="v2-metric"><span class="v2-metric-label">Vitórias</span><span class="v2-metric-value" id="wins">0</span></div></div></section>
<section class="v2-panel"><h2 class="v2-section-title">Partida</h2><p class="v2-section-copy" id="gameCopy">Abra a palavra diária ou entre no treino.</p>
<div class="mode-row"><button class="v2-btn" id="dailyBtn">🎌 Palavra diária</button><button class="secondary" id="trainBtn">🧪 Treino</button></div>
<div class="info-row"><span class="v2-chip" id="modeChip">sem partida</span><span class="v2-chip" id="timerChip">5:00</span><button class="v2-chip" id="hintBtn" style="cursor:pointer">💡 Dica • {HINT_COST_COINS} coins</button></div>
<div class="board" id="board"></div><div class="controls" id="controls"><input id="guess" maxlength="6" autocomplete="off" placeholder="palavra"><button id="send">Enviar</button></div><div class="hint" id="hint"></div><div class="end" id="end"></div></section>
<section class="v2-panel"><h2 class="v2-section-title">Seu desempenho</h2><div class="stats-grid"><div class="v2-metric"><span class="v2-metric-label">Jogos</span><span class="v2-metric-value" id="games">0</span></div><div class="v2-metric"><span class="v2-metric-label">Acerto</span><span class="v2-metric-value" id="rate">0%</span></div><div class="v2-metric"><span class="v2-metric-label">Melhor</span><span class="v2-metric-value" id="best">—</span></div></div></section>
<section class="v2-panel"><h2 class="v2-section-title">Ranking diário</h2><p class="v2-section-copy">Mais vitórias; em empate, menor média de tentativas.</p><div id="ranking"></div></section>
</div><div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let game=null,dashboard={{stats:{{}},ranking:[]}},timer=null;
const esc=s=>String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function blankRow(){{return `<div class="guess-row">${{Array.from({{length:6}},()=>'<div class="letter"></div>').join('')}}</div>`}}
function renderBoard(){{const root=document.getElementById('board');const guesses=game?.guesses||[];let html='';for(const item of guesses){{const chars=Array.from(String(item.guess||'').toUpperCase());const result=item.result||[];html+=`<div class="guess-row">${{chars.map((c,i)=>`<div class="letter ${{esc(result[i]||'absent')}}">${{esc(c)}}</div>`).join('')}}</div>`}}for(let i=guesses.length;i<6;i++)html+=blankRow();root.innerHTML=html}}
function syncGame(){{const status=game?.status||'none',mode=game?.mode||'';document.getElementById('attempts').textContent=`${{game?.attempts||0}}/6`;document.getElementById('modeChip').textContent=mode==='daily'?'🎌 diário':mode==='train'?'🧪 treino':'sem partida';document.getElementById('gameCopy').textContent=!game?'Inicie uma partida.':status==='playing'?`Categoria: ${{game.category}} • dificuldade ${{'★'.repeat(Number(game.difficulty||1))}}`:`Partida encerrada: ${{status}}`;const playing=status==='playing';document.getElementById('controls').style.display=playing?'grid':'none';document.getElementById('hintBtn').style.display=playing?'inline-flex':'none';const hint=document.getElementById('hint');if(game?.hint_used&&game?.hint){{hint.style.display='block';hint.innerHTML=`💡 <b>Dica:</b> ${{esc(game.hint)}}`}}else hint.style.display='none';const end=document.getElementById('end');if(game&&status!=='playing'){{end.style.display='block';const won=status==='win';end.innerHTML=`${{won?'🏆 <b>Você acertou!</b>':'🔎 <b>Partida encerrada.</b>'}}<br><br>Palavra: <b>${{esc(String(game.secret_word||'').toUpperCase())}}</b>${{won&&game.mode==='daily'?`<br>Recompensa: <b>+${{game.reward_coins}} coins</b> • <b>+${{game.reward_xp}} XP</b><br>🔥 sequência: <b>${{game.streak}}</b>`:''}}`}}else end.style.display='none';renderBoard();runTimer()}}
function runTimer(){{clearInterval(timer);const chip=document.getElementById('timerChip');function tick(){{if(!game||game.status!=='playing'||!game.expires_at){{chip.textContent='—';return}}const left=Math.max(0,Math.floor((new Date(game.expires_at).getTime()-Date.now())/1000));chip.textContent=`${{Math.floor(left/60)}}:${{String(left%60).padStart(2,'0')}}`;if(left<=0)load()}}tick();timer=setInterval(tick,1000)}}
function syncDashboard(){{const s=dashboard.stats||{{}};document.getElementById('streak').textContent=s.current_streak||0;document.getElementById('wins').textContent=s.wins||0;document.getElementById('games').textContent=s.games||0;document.getElementById('rate').textContent=`${{Number(s.win_rate||0).toFixed(0)}}%`;document.getElementById('best').textContent=s.best_attempts?`${{s.best_attempts}}/6`:'—';document.getElementById('ranking').innerHTML=(dashboard.ranking||[]).map(r=>`<div class="rank"><span>${{r.position<=3?['🥇','🥈','🥉'][r.position-1]:r.position}}</span><strong>${{esc(r.display_name)}}</strong><span><b>${{r.wins}}</b> vitórias<br><span class="muted">${{r.avg_attempts?`${{r.avg_attempts}} tent.`:'—'}}</span></span></div>`).join('')||'<div class="v2-empty" style="margin-top:12px">Ainda não há ranking.</div>'}}
async function load(){{try{{const data=await v2Api('/api/v2/termo/state');game=data.game||null;dashboard=data.dashboard||dashboard;syncGame();syncDashboard()}}catch(e){{v2Toast(e.message)}}}}
async function start(mode){{try{{const data=await v2Api(mode==='daily'?'/api/v2/termo/start':'/api/v2/termo/train',{{method:'POST'}});game=data.game;document.getElementById('guess').value='';syncGame();v2Haptic('light')}}catch(e){{v2Toast(e.message)}}}}
async function sendGuess(){{if(!game||game.status!=='playing')return;const input=document.getElementById('guess');const guess=input.value.trim().toLowerCase();if(Array.from(guess).length!==6){{v2Toast('Digite uma palavra de 6 letras.');return}}try{{document.getElementById('send').disabled=true;const data=await v2Api('/api/v2/termo/guess',{{method:'POST',body:JSON.stringify({{session_token:game.session_token,guess}})}});game=data.game;input.value='';syncGame();if(game.status!=='playing'){{dashboard=(await v2Api('/api/v2/termo/state')).dashboard||dashboard;syncDashboard();v2Haptic('medium')}}}}catch(e){{v2Toast(e.message)}}finally{{document.getElementById('send').disabled=false}}}}
async function hint(){{if(!game||game.status!=='playing')return;if(game.hint_used){{v2Toast('A dica desta partida já foi usada.');return}}const text=game.mode==='daily'?`Usar dica por {HINT_COST_COINS} coins?`:'Usar dica gratuita no treino?';if(!confirm(text))return;try{{const data=await v2Api('/api/v2/termo/hint',{{method:'POST',body:JSON.stringify({{session_token:game.session_token}})}});game.hint_used=true;game.hint=data.hint;syncGame();v2Haptic('light')}}catch(e){{v2Toast(e.message)}}}}
document.getElementById('dailyBtn').onclick=()=>start('daily');document.getElementById('trainBtn').onclick=()=>start('train');document.getElementById('send').onclick=sendGuess;document.getElementById('guess').addEventListener('keydown',e=>{{if(e.key==='Enter')sendGuess()}});document.getElementById('hintBtn').onclick=hint;load();
</script></body></html>'''


def register_termo_routes(app) -> None:
    @app.get("/termo", response_class=HTMLResponse)
    async def termo_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/termo/state")
    async def state_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        return JSONResponse({"ok": True, "game": get_active_or_today(user_id), "dashboard": get_termo_dashboard(user_id)})

    @app.post("/api/v2/termo/start")
    async def start_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"termo:start:{user_id}", limit=5, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas tentativas em sequência."}, status_code=429)
        return JSONResponse({"ok": True, "game": start_daily_game(user_id)})

    @app.post("/api/v2/termo/train")
    async def train_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"termo:train:{user_id}", limit=8, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitos treinos iniciados."}, status_code=429)
        return JSONResponse({"ok": True, "game": start_train_game(user_id)})

    @app.post("/api/v2/termo/guess")
    async def guess_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"termo:guess:{user_id}", limit=10, window_seconds=15)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Aguarde antes de tentar novamente."}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            game = submit_guess(user_id, str((payload or {}).get("session_token") or ""), str((payload or {}).get("guess") or ""))
        except TermoInvalidGuess:
            return JSONResponse({"ok": False, "code": "invalid_word", "message": "Essa palavra não está na lista do jogo."}, status_code=400)
        except TermoDuplicateGuess:
            return JSONResponse({"ok": False, "code": "duplicate_guess", "message": "Você já tentou essa palavra."}, status_code=409)
        except TermoInvalidState:
            return JSONResponse({"ok": False, "code": "invalid_state", "message": "Essa partida terminou ou expirou."}, status_code=409)
        return JSONResponse({"ok": True, "game": game})

    @app.post("/api/v2/termo/hint")
    async def hint_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"termo:hint:{user_id}", limit=4, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Aguarde antes de tentar novamente."}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            result = buy_hint(user_id, str((payload or {}).get("session_token") or ""))
        except TermoHintAlreadyUsed:
            return JSONResponse({"ok": False, "code": "hint_used", "message": "A dica desta partida já foi usada."}, status_code=409)
        except TermoInsufficientCoins:
            return JSONResponse({"ok": False, "code": "insufficient_coins", "message": f"Você precisa de {HINT_COST_COINS} coins para a dica."}, status_code=409)
        except TermoInvalidState:
            return JSONResponse({"ok": False, "code": "invalid_state", "message": "Essa partida não está mais ativa."}, status_code=409)
        return JSONResponse({"ok": True, **result})
