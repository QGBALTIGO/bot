from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from memory_repository import (
    MemoryProofInvalid,
    MemorySessionInvalid,
    MemoryTooFast,
    finish_memory_session,
    memory_stats,
    start_memory_session,
)
from memory_rules import MEMORY_LEVELS, normalize_level
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page(initial_level: str = "medium") -> str:
    initial = normalize_level(initial_level)
    return f'''<!doctype html>
<html lang="pt-br"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070a14"><title>Memória • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.levels{{display:flex;gap:7px;overflow:auto;margin-top:14px;padding-bottom:2px;scrollbar-width:none}}.levels::-webkit-scrollbar{{display:none}}
.level{{flex:0 0 auto;border:1px solid var(--line);border-radius:999px;padding:9px 12px;background:rgba(255,255,255,.035);font-size:10px;font-weight:900;cursor:pointer}}.level.active{{border-color:rgba(93,230,255,.4);background:rgba(93,230,255,.1)}}
.board{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:14px;perspective:1000px}}
.tile{{position:relative;aspect-ratio:.72;border:0;background:transparent;padding:0;cursor:pointer;transform-style:preserve-3d;transition:transform .36s cubic-bezier(.2,.8,.2,1)}}
.tile.open,.tile.matched{{transform:rotateY(180deg)}}.tile.matched{{opacity:.62;cursor:default}}
.face{{position:absolute;inset:0;overflow:hidden;border:1px solid var(--line);border-radius:17px;backface-visibility:hidden;box-shadow:var(--shadow-soft)}}
.back{{display:grid;place-items:center;background:linear-gradient(145deg,rgba(93,230,255,.16),rgba(157,115,255,.19),rgba(255,95,158,.16));font-size:24px;font-weight:950}}
.front{{transform:rotateY(180deg);background:#09101e}}.front img{{width:100%;height:100%;object-fit:cover;display:block}}
.hud{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}}
.start{{margin-top:13px}}.result{{margin-top:14px;padding:16px;border:1px solid rgba(114,241,189,.25);border-radius:18px;background:rgba(114,241,189,.06);display:none}}
@media(min-width:700px){{.board{{grid-template-columns:repeat(5,minmax(0,1fr))}}}}
</style></head><body>
<div class="v2-shell">
<section class="v2-hero"><div class="v2-eyebrow">Source Baltigo • MiniGame V2</div><h1 class="v2-title">Memória<br>Anime.</h1><p class="v2-copy">Encontre todos os pares. O servidor mede a partida e valida os pares antes de aceitar qualquer recorde.</p>
<div class="hud"><div class="v2-metric"><span class="v2-metric-label">Tempo</span><span class="v2-metric-value" id="time">0:00</span></div><div class="v2-metric"><span class="v2-metric-label">Jogadas</span><span class="v2-metric-value" id="moves">0</span></div><div class="v2-metric"><span class="v2-metric-label">Pares</span><span class="v2-metric-value" id="pairs">0/0</span></div></div></section>
<section class="v2-panel"><h2 class="v2-section-title">Escolha a dificuldade</h2><div class="levels" id="levels">
<button class="level" data-level="easy">Fácil • 4</button><button class="level" data-level="medium">Médio • 6</button><button class="level" data-level="hard">Difícil • 8</button><button class="level" data-level="extreme">Muito difícil • 10</button></div>
<button class="v2-btn start" id="start">Iniciar nova partida</button><div class="board" id="board"></div><div class="v2-empty" id="empty" style="margin-top:14px">Escolha a dificuldade e inicie.</div><div class="result" id="result"></div></section>
</div><div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let level={initial!r}, session=null, opened=[], matched=new Set(), proof=[], moves=0, busy=false, timer=null, visualStarted=0;
const esc=s=>String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function setLevel(next){{if(session)return;level=next;document.querySelectorAll('.level').forEach(b=>b.classList.toggle('active',b.dataset.level===level))}}
function fmt(ms){{const s=Math.floor(ms/1000),m=Math.floor(s/60);return `${{m}}:${{String(s%60).padStart(2,'0')}}`}}
function sync(){{document.getElementById('moves').textContent=moves;document.getElementById('pairs').textContent=`${{matched.size}}/${{session?.pairs||0}}`}}
function startTimer(){{clearInterval(timer);visualStarted=Date.now();timer=setInterval(()=>document.getElementById('time').textContent=fmt(Date.now()-visualStarted),250)}}
function renderBoard(){{const root=document.getElementById('board');root.innerHTML='';(session?.board||[]).forEach(item=>{{const b=document.createElement('button');b.className='tile';b.dataset.pos=item.position;b.innerHTML=`<div class="face back">✦</div><div class="face front"><img draggable="false" src="${{esc(item.image)}}" alt="${{esc(item.title)}}"></div>`;b.onclick=()=>flip(b,Number(item.position));root.appendChild(b)}});document.getElementById('empty').style.display=session?'none':'block'}}
function tile(pos){{return document.querySelector(`.tile[data-pos="${{pos}}"]`)}}
async function flip(el,pos){{if(!session||busy||matched.has(pos)||opened.includes(pos))return;el.classList.add('open');opened.push(pos);if(opened.length<2)return;moves++;sync();busy=true;const [a,b]=opened;const ia=session.board[a],ib=session.board[b];await new Promise(r=>setTimeout(r,560));if(ia.title===ib.title&&ia.image===ib.image){{matched.add(a);matched.add(b);proof.push([a,b]);tile(a)?.classList.add('matched');tile(b)?.classList.add('matched');v2Haptic('light')}}else{{tile(a)?.classList.remove('open');tile(b)?.classList.remove('open')}}opened=[];busy=false;sync();if(matched.size===session.board.length)await finish()}}
async function start(){{try{{document.getElementById('start').disabled=true;const data=await v2Api('/api/v2/memory/start',{{method:'POST',body:JSON.stringify({{level}})}});session=data.session;opened=[];matched=new Set();proof=[];moves=0;busy=false;document.getElementById('result').style.display='none';document.getElementById('time').textContent='0:00';renderBoard();sync();startTimer();document.getElementById('start').textContent='Reiniciar partida';document.getElementById('start').disabled=false}}catch(e){{v2Toast(e.message);document.getElementById('start').disabled=false}}}}
async function finish(){{clearInterval(timer);busy=true;try{{const data=await v2Api('/api/v2/memory/finish',{{method:'POST',body:JSON.stringify({{session_token:session.session_token,moves,proof}})}});const r=data.result;document.getElementById('time').textContent=fmt(r.elapsed_ms);const box=document.getElementById('result');box.style.display='block';box.innerHTML=`🏁 <b>Partida concluída</b><br><br>Tempo validado: <b>${{fmt(r.elapsed_ms)}}</b><br>Jogadas: <b>${{r.moves}}</b><br>Melhor: <b>${{fmt(r.best_elapsed_ms)}}</b> • ${{r.best_moves}} jogadas${{r.new_best?'<br><br>✨ Novo recorde pessoal!':''}}`;v2Haptic('medium');session=null;document.getElementById('start').textContent='Jogar novamente'}}catch(e){{v2Toast(e.message)}}finally{{busy=false}}}}
document.querySelectorAll('.level').forEach(b=>b.onclick=()=>setLevel(b.dataset.level));document.getElementById('start').onclick=start;setLevel(level);
</script></body></html>'''


def register_memory_routes(app) -> None:
    @app.get("/memory", response_class=HTMLResponse)
    async def memory_page(level: str = "medium"):
        return HTMLResponse(_page(level))

    @app.get("/api/v2/memory/stats")
    async def stats_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        return JSONResponse({"ok": True, "stats": memory_stats(user_id)})

    @app.post("/api/v2/memory/start")
    async def start_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"memory:start:{user_id}", limit=6, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas partidas iniciadas em sequência."}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        level = normalize_level(str((payload or {}).get("level") or "medium"))
        return JSONResponse({"ok": True, "session": start_memory_session(user_id, level)})

    @app.post("/api/v2/memory/finish")
    async def finish_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"memory:finish:{user_id}", limit=10, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas tentativas em sequência."}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            result = finish_memory_session(
                user_id,
                str((payload or {}).get("session_token") or ""),
                int((payload or {}).get("moves") or 0),
                (payload or {}).get("proof"),
            )
        except MemoryTooFast:
            return JSONResponse({"ok": False, "code": "implausible_time", "message": "A conclusão foi rápida demais para ser validada."}, status_code=409)
        except MemoryProofInvalid:
            return JSONResponse({"ok": False, "code": "invalid_proof", "message": "A sequência de pares não corresponde a esta partida."}, status_code=400)
        except MemorySessionInvalid:
            return JSONResponse({"ok": False, "code": "invalid_session", "message": "Essa partida expirou ou já foi concluída."}, status_code=409)
        return JSONResponse({"ok": True, "result": result})
