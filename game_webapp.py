from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from game_rules import SPIN_REWARDS
from game_service import GameServiceError, claim_daily_reward, get_state, pick_dice_anime, roll_dice, spin
from utils.runtime_guard import rate_limiter

logger = logging.getLogger(__name__)


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


async def _limited(user_id: int, action: str, limit: int, window: float) -> bool:
    return await rate_limiter.allow(
        f"webapp:game:{action}:{int(user_id)}",
        limit=limit,
        window_seconds=window,
    )


def _error(exc: GameServiceError, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "code": exc.code, "message": exc.message},
        status_code=status,
    )


def _page() -> str:
    spin_labels = [item.label for item in SPIN_REWARDS]
    spin_labels_js = "[" + ",".join(repr(label) for label in spin_labels) + "]"

    return f'''<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070a14">
<title>Baltigo Game Center</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{{
  --bg:#050711;--panel:#0d1222;--panel2:#121a2e;--line:rgba(255,255,255,.09);
  --text:#f7f8ff;--muted:#9ca8c3;--pink:#ff5f9e;--violet:#9d73ff;--cyan:#5de6ff;
  --gold:#ffd36c;--green:#72f1bd;--danger:#ff6f86;--shadow:0 24px 70px rgba(0,0,0,.46);
  --radius:26px;--safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px)
}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;min-height:100vh;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;background:
radial-gradient(900px 520px at 0 -10%,rgba(93,230,255,.14),transparent 55%),
radial-gradient(780px 520px at 110% 10%,rgba(255,95,158,.16),transparent 54%),
linear-gradient(180deg,#050711 0%,#07101c 50%,#050812 100%);overflow-x:hidden}}
body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.25;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:34px 34px;mask-image:linear-gradient(#000,transparent 95%)}}
button{{font:inherit;color:inherit}}.shell{{width:min(960px,100%);margin:auto;padding:calc(16px + var(--safe-top)) 14px calc(44px + var(--safe-bottom))}}
.hero{{position:relative;overflow:hidden;padding:22px;border:1px solid var(--line);border-radius:32px;background:linear-gradient(145deg,rgba(18,28,53,.94),rgba(8,12,25,.96));box-shadow:var(--shadow)}}
.hero:before{{content:"";position:absolute;width:230px;height:230px;border-radius:50%;right:-50px;top:-80px;background:radial-gradient(circle,rgba(255,95,158,.36),transparent 68%);filter:blur(3px)}}
.eyebrow{{position:relative;color:var(--cyan);font-size:11px;font-weight:900;letter-spacing:.18em;text-transform:uppercase}}h1{{position:relative;margin:7px 0 8px;font-size:clamp(31px,9vw,54px);line-height:.94;letter-spacing:-.055em}}.lead{{position:relative;margin:0;color:#c7d0e4;line-height:1.55;font-size:14px;max-width:58ch}}
.wallet{{position:relative;display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:18px}}.wallet-card{{padding:13px 12px;border:1px solid var(--line);border-radius:19px;background:rgba(255,255,255,.045);backdrop-filter:blur(14px)}}.wallet-label{{display:block;color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.12em;text-transform:uppercase}}.wallet-value{{display:block;margin-top:6px;font-size:21px;font-weight:900;letter-spacing:-.04em}}.wallet-value.pulse{{animation:countPulse .42s ease}}@keyframes countPulse{{50%{{transform:scale(1.14);color:var(--gold)}}}}
.tabs{{position:sticky;z-index:20;top:8px;display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:14px 0;padding:6px;border:1px solid var(--line);border-radius:20px;background:rgba(7,11,22,.78);backdrop-filter:blur(18px)}}.tab{{border:0;border-radius:15px;padding:11px 7px;background:transparent;color:var(--muted);font-size:12px;font-weight:900;cursor:pointer;transition:.2s}}.tab.active{{color:#fff;background:linear-gradient(135deg,rgba(157,115,255,.28),rgba(93,230,255,.16));box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}}
.section{{display:none;animation:sectionIn .36s cubic-bezier(.2,.8,.2,1)}}.section.active{{display:block}}@keyframes sectionIn{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}.panel{{padding:18px;border:1px solid var(--line);border-radius:var(--radius);background:linear-gradient(180deg,rgba(14,21,40,.91),rgba(8,13,27,.95));box-shadow:0 18px 44px rgba(0,0,0,.28)}}.section-title{{margin:0;font-size:25px;letter-spacing:-.04em}}.section-copy{{color:var(--muted);font-size:13px;line-height:1.55;margin:7px 0 0}}.cta{{width:100%;min-height:52px;margin-top:15px;border:0;border-radius:17px;background:linear-gradient(135deg,var(--pink),var(--violet));box-shadow:0 12px 30px rgba(157,115,255,.22);font-weight:900;cursor:pointer;transition:transform .15s,filter .15s}}.cta:active{{transform:scale(.985)}}.cta:disabled{{opacity:.45;filter:grayscale(.5);cursor:default}}
.toast{{position:fixed;z-index:90;left:50%;bottom:calc(18px + var(--safe-bottom));width:min(420px,calc(100% - 28px));transform:translate(-50%,20px);padding:13px 15px;border:1px solid var(--line);border-radius:17px;background:rgba(8,13,27,.95);box-shadow:var(--shadow);opacity:0;pointer-events:none;transition:.24s;color:#e8edfa;font-size:13px;text-align:center}}.toast.show{{opacity:1;transform:translate(-50%,0)}}
/* Daily */.streak{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:16px}}.day{{aspect-ratio:1;border-radius:15px;display:grid;place-items:center;border:1px solid var(--line);background:rgba(255,255,255,.035);font-size:11px;font-weight:900;color:var(--muted);position:relative;overflow:hidden}}.day.done{{color:#fff;border-color:rgba(114,241,189,.35);background:rgba(114,241,189,.10)}}.day.current{{color:#fff;border-color:rgba(255,211,108,.45);background:rgba(255,211,108,.13);box-shadow:0 0 24px rgba(255,211,108,.12)}}.reward-list{{display:flex;gap:8px;flex-wrap:wrap;margin-top:13px}}.reward-chip{{padding:9px 11px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.04);font-size:12px;font-weight:800}}
/* Dice */.dice-stage{{position:relative;height:260px;display:grid;place-items:center;perspective:850px;margin:8px 0 2px;overflow:hidden}}.dice-stage:before{{content:"";position:absolute;width:210px;height:68px;border-radius:50%;background:rgba(93,230,255,.12);filter:blur(18px);bottom:26px;transform:rotateX(68deg)}}.dice{{position:relative;width:112px;height:112px;transform-style:preserve-3d;transform:rotateX(-18deg) rotateY(28deg);transition:transform 1.05s cubic-bezier(.16,.84,.25,1.1)}}.dice.rolling{{animation:diceRoll 1.35s cubic-bezier(.18,.72,.18,1)}}@keyframes diceRoll{{0%{{transform:rotateX(-18deg) rotateY(28deg) scale(.9)}}30%{{transform:rotateX(380deg) rotateY(520deg) translateY(-12px) scale(1.13)}}70%{{transform:rotateX(800deg) rotateY(900deg) translateY(6px) scale(.98)}}100%{{transform:rotateX(1062deg) rotateY(1110deg)}}}}.face{{position:absolute;width:112px;height:112px;border-radius:25px;border:1px solid rgba(255,255,255,.24);background:linear-gradient(145deg,rgba(255,255,255,.98),rgba(205,216,242,.92));box-shadow:inset 0 0 22px rgba(34,45,86,.18),0 9px 24px rgba(0,0,0,.18);display:grid;grid-template:repeat(3,1fr)/repeat(3,1fr);padding:16px}}.face.front{{transform:translateZ(56px)}}.face.back{{transform:rotateY(180deg) translateZ(56px)}}.face.right{{transform:rotateY(90deg) translateZ(56px)}}.face.left{{transform:rotateY(-90deg) translateZ(56px)}}.face.top{{transform:rotateX(90deg) translateZ(56px)}}.face.bottom{{transform:rotateX(-90deg) translateZ(56px)}}.pip{{width:13px;height:13px;border-radius:50%;background:#11172b;align-self:center;justify-self:center;box-shadow:inset 0 2px 2px rgba(0,0,0,.35)}}.p1{{grid-area:1/1}}.p2{{grid-area:1/3}}.p3{{grid-area:2/1}}.p4{{grid-area:2/2}}.p5{{grid-area:2/3}}.p6{{grid-area:3/1}}.p7{{grid-area:3/3}}.anime-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}}.anime-option{{overflow:hidden;border:1px solid var(--line);border-radius:20px;background:rgba(255,255,255,.04);cursor:pointer;text-align:left;padding:0;transition:.18s}}.anime-option:active{{transform:scale(.98)}}.anime-option img{{display:block;width:100%;aspect-ratio:1.58;object-fit:cover;background:#0a0e1a}}.anime-option span{{display:block;padding:10px 11px;font-size:12px;font-weight:900}}.reveal{{display:none;margin-top:14px;overflow:hidden;border:1px solid rgba(255,211,108,.25);border-radius:24px;background:linear-gradient(145deg,rgba(255,211,108,.08),rgba(157,115,255,.08))}}.reveal.show{{display:grid;grid-template-columns:112px 1fr;animation:reveal .65s cubic-bezier(.15,.8,.22,1)}}@keyframes reveal{{from{{opacity:0;transform:scale(.94) rotateX(8deg)}}to{{opacity:1;transform:none}}}}.reveal img{{width:112px;height:150px;object-fit:cover}}.reveal-copy{{padding:15px}}.reveal-kicker{{font-size:10px;color:var(--gold);font-weight:900;letter-spacing:.15em;text-transform:uppercase}}.reveal-name{{font-size:20px;font-weight:950;margin-top:5px;letter-spacing:-.03em}}.reveal-anime{{font-size:12px;color:var(--muted);margin-top:5px}}
/* Wheel */.wheel-wrap{{position:relative;width:min(330px,86vw);aspect-ratio:1;margin:24px auto 8px;display:grid;place-items:center}}.pointer{{position:absolute;z-index:4;top:-7px;width:0;height:0;border-left:16px solid transparent;border-right:16px solid transparent;border-top:30px solid var(--gold);filter:drop-shadow(0 5px 6px rgba(0,0,0,.35))}}.wheel{{position:absolute;inset:0;border-radius:50%;border:7px solid rgba(255,255,255,.12);background:conic-gradient(from -22.5deg,#ff5f9e 0 45deg,#815cff 45deg 90deg,#28bdd5 90deg 135deg,#ffba4a 135deg 180deg,#6c74ff 180deg 225deg,#ed6dff 225deg 270deg,#39dca2 270deg 315deg,#ff785c 315deg 360deg);box-shadow:0 22px 55px rgba(0,0,0,.4),inset 0 0 0 7px rgba(5,7,17,.42);transition:transform 4.2s cubic-bezier(.12,.72,.08,1)}}.wheel:after{{content:"B";position:absolute;inset:35%;display:grid;place-items:center;border-radius:50%;background:#0b1020;border:5px solid rgba(255,255,255,.13);font-size:42px;font-weight:1000;box-shadow:0 8px 30px rgba(0,0,0,.35)}}.wheel-label{{position:absolute;z-index:2;left:50%;top:50%;width:44%;transform-origin:0 0;font-size:10px;font-weight:950;text-shadow:0 1px 3px rgba(0,0,0,.45);pointer-events:none}}.wheel-result{{min-height:28px;text-align:center;color:#dce4f6;font-size:14px;font-weight:850}}
.status{{margin-top:13px;padding:11px 12px;border-radius:15px;background:rgba(255,255,255,.035);border:1px solid var(--line);color:var(--muted);font-size:12px;line-height:1.45}}@media(min-width:700px){{.game-grid{{display:grid;grid-template-columns:1.05fr .95fr;gap:14px}}.anime-grid{{grid-template-columns:repeat(3,1fr)}}}}
@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}}}
</style>
</head>
<body>
<div class="shell">
  <section class="hero">
    <div class="eyebrow">Source Baltigo • Game Center V2</div>
    <h1>Um jogo só.<br>Todos os sistemas.</h1>
    <p class="lead">Daily, dados, giros e coleção agora usam a mesma economia. Nada de recompensa fantasma: tudo que aparece aqui existe de verdade na sua conta.</p>
    <div class="wallet">
      <div class="wallet-card"><span class="wallet-label">Coins</span><span class="wallet-value" id="coins">—</span></div>
      <div class="wallet-card"><span class="wallet-label">Dados</span><span class="wallet-value" id="diceBalance">—</span></div>
      <div class="wallet-card"><span class="wallet-label">Giros</span><span class="wallet-value" id="spins">—</span></div>
    </div>
  </section>

  <nav class="tabs">
    <button class="tab" data-tab="daily">🎁 Daily</button>
    <button class="tab" data-tab="dice">🎲 Dado</button>
    <button class="tab" data-tab="spin">🎡 Giro</button>
  </nav>

  <section id="daily" class="section">
    <div class="panel">
      <h2 class="section-title">Daily que vale alguma coisa</h2>
      <p class="section-copy">Todo dia você recebe coins, dado e giro. A sequência de 7 dias aumenta o pacote — sem prometer recurso que não existe.</p>
      <div class="streak" id="streak"></div>
      <div class="reward-list" id="dailyRewards"></div>
      <button class="cta" id="dailyBtn">Resgatar recompensa</button>
      <div class="status" id="dailyStatus">Carregando sua sequência…</div>
    </div>
  </section>

  <section id="dice" class="section">
    <div class="panel">
      <h2 class="section-title">Dado de descoberta</h2>
      <p class="section-copy">Um dado consumido = uma rolagem. O número define quantas obras aparecem; você escolhe uma e recebe um personagem real na coleção.</p>
      <div class="dice-stage">
        <div class="dice" id="dice3d">
          <div class="face front" data-face="1"></div><div class="face back" data-face="6"></div>
          <div class="face right" data-face="3"></div><div class="face left" data-face="4"></div>
          <div class="face top" data-face="2"></div><div class="face bottom" data-face="5"></div>
        </div>
      </div>
      <button class="cta" id="rollBtn">Rolar dado</button>
      <div class="status" id="diceStatus">Próxima recarga: <b id="nextDice">—</b></div>
      <div class="anime-grid" id="animeGrid"></div>
      <div class="reveal" id="reveal"><img id="revealImg" alt=""><div class="reveal-copy"><div class="reveal-kicker">Novo personagem</div><div class="reveal-name" id="revealName"></div><div class="reveal-anime" id="revealAnime"></div></div></div>
    </div>
  </section>

  <section id="spin" class="section">
    <div class="panel">
      <h2 class="section-title">Roleta Baltigo</h2>
      <p class="section-copy">Agora o giro existe de verdade. Cada tentativa consome 1 giro e credita imediatamente a recompensa sorteada.</p>
      <div class="wheel-wrap"><div class="pointer"></div><div class="wheel" id="wheel"></div><div id="wheelLabels"></div></div>
      <div class="wheel-result" id="wheelResult">Pronto para girar.</div>
      <button class="cta" id="spinBtn">Girar roleta</button>
      <div class="status">Você consegue novos giros principalmente no Daily. O histórico fica registrado no servidor.</div>
    </div>
  </section>
</div>
<div class="toast" id="toast"></div>
<script>
const tg = window.Telegram?.WebApp || null;
if (tg) {{ try {{ tg.ready(); tg.expand(); }} catch (_) {{}} }}
const spinLabels = {spin_labels_js};
const $ = (id) => document.getElementById(id);
const state = {{ wallet:null, activeRoll:null, wheelTurns:0, busy:false }};

function toast(message) {{ const el=$('toast'); el.textContent=message; el.classList.add('show'); clearTimeout(toast.t); toast.t=setTimeout(()=>el.classList.remove('show'),2600); }}
function haptic(kind='light') {{ try {{ tg?.HapticFeedback?.impactOccurred(kind); }} catch (_) {{}} }}
async function api(path, opts={{}}) {{
  const headers = new Headers(opts.headers || {{}});
  if (tg?.initData) headers.set('X-Telegram-Init-Data', tg.initData);
  if (opts.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
  const res = await fetch(path, {{...opts, headers}});
  let data={{}}; try {{ data=await res.json(); }} catch (_) {{}}
  if (!res.ok || data.ok===false) throw Object.assign(new Error(data.message || 'Não foi possível concluir.'), {{code:data.code || 'request_failed', status:res.status}});
  return data;
}}
function pulse(el) {{ el.classList.remove('pulse'); void el.offsetWidth; el.classList.add('pulse'); }}
function setWallet(w) {{
  if (!w) return; state.wallet=w;
  [['coins',w.coins],['diceBalance',w.dice],['spins',w.spins]].forEach(([id,val])=>{{ const el=$(id); if(el.textContent!==String(val)){{el.textContent=val;pulse(el)}} }});
  $('nextDice').textContent=w.next_dice_recharge_hhmm || '—';
  $('rollBtn').disabled=Number(w.dice||0)<=0 || !!state.activeRoll;
  $('spinBtn').disabled=Number(w.spins||0)<=0;
}}
function renderStreak(d) {{
  const streak=Math.max(0,Number(d?.streak||0)); const cycle=Number(d?.cycle_day||0); const root=$('streak'); root.innerHTML='';
  for(let i=1;i<=7;i++){{ const x=document.createElement('div'); x.className='day'+(i<=cycle?' done':'')+(i===Math.min(7,cycle+1)&&!d?.claimed_today?' current':''); x.textContent='D'+i; root.appendChild(x); }}
  $('dailyStatus').innerHTML=d?.claimed_today ? `✅ Daily de hoje resgatado • sequência <b>${{streak}} dia(s)</b>` : `🔥 Sequência atual: <b>${{streak}} dia(s)</b>`;
  $('dailyBtn').disabled=!!d?.claimed_today;
  $('dailyBtn').textContent=d?.claimed_today?'Resgatado hoje':'Resgatar recompensa';
}}
function showDailyReward(r) {{ const root=$('dailyRewards'); root.innerHTML=''; [['🪙',r.coins,'coins'],['🎲',r.dice,'dado(s)'],['🎡',r.spins,'giro(s)']].forEach(([ico,n,label])=>{{if(Number(n)>0){{const e=document.createElement('span');e.className='reward-chip';e.textContent=`${{ico}} +${{n}} ${{label}}`;root.appendChild(e)}}}}); }}
function dots(face, positions) {{ const f=document.querySelector(`[data-face="${{face}}"]`); positions.forEach(p=>{{const d=document.createElement('i');d.className='pip p'+p;f.appendChild(d)}}); }}
dots(1,[4]); dots(2,[1,7]); dots(3,[1,4,7]); dots(4,[1,2,6,7]); dots(5,[1,2,4,6,7]); dots(6,[1,2,3,5,6,7]);
const finalTransforms={{1:'rotateX(0deg) rotateY(0deg)',2:'rotateX(-90deg) rotateY(0deg)',3:'rotateX(0deg) rotateY(-90deg)',4:'rotateX(0deg) rotateY(90deg)',5:'rotateX(90deg) rotateY(0deg)',6:'rotateX(0deg) rotateY(180deg)'}};
function animateDice(value) {{ const d=$('dice3d'); d.classList.remove('rolling'); d.style.transform=''; void d.offsetWidth; d.classList.add('rolling'); setTimeout(()=>{{d.classList.remove('rolling');d.style.transform=finalTransforms[value]||finalTransforms[1]}},1320); }}
function renderRoll(roll) {{
  state.activeRoll=roll || null; const grid=$('animeGrid'); grid.innerHTML=''; $('reveal').classList.remove('show');
  if(!roll){{setWallet(state.wallet);return}};
  if(roll.dice_value) animateDice(Number(roll.dice_value));
  (roll.options||[]).forEach(opt=>{{const b=document.createElement('button');b.className='anime-option';b.innerHTML=`<img src="${{String(opt.cover||'').replace(/"/g,'&quot;')}}" alt=""><span></span>`;b.querySelector('span').textContent=opt.title||'Obra';b.onclick=()=>pickAnime(opt,b);grid.appendChild(b)}});
  $('diceStatus').innerHTML=`🎲 Você tirou <b>${{roll.dice_value}}</b>. Escolha uma das obras abaixo.`; setWallet(state.wallet);
}}
async function loadState() {{
  try {{ const data=await api('/api/v2/game/state'); state.activeRoll=data.state.active_dice_roll; setWallet(data.state.wallet); renderStreak(data.state.daily); renderRoll(state.activeRoll); }}
  catch(e) {{ toast(e.message); $('dailyStatus').textContent='Abra esta MiniApp pelo Telegram para carregar sua conta.'; }}
}}
$('dailyBtn').onclick=async()=>{{
  if(state.busy)return; state.busy=true; $('dailyBtn').disabled=true;
  try{{const data=await api('/api/v2/game/daily/claim',{{method:'POST',body:'{{}}'}}); haptic('medium'); if(data.reward){{showDailyReward(data.reward);toast(`Daily: +${{data.reward.coins}} coins, +${{data.reward.dice}} dado(s), +${{data.reward.spins}} giro(s)`);}} setWallet(data.wallet); await loadState();}}
  catch(e){{toast(e.message)}}finally{{state.busy=false}}
}};
$('rollBtn').onclick=async()=>{{
  if(state.busy)return; state.busy=true; $('rollBtn').disabled=true; $('animeGrid').innerHTML=''; $('reveal').classList.remove('show'); $('diceStatus').textContent='Rolando…'; haptic('medium');
  const d=$('dice3d'); d.classList.remove('rolling'); void d.offsetWidth; d.classList.add('rolling');
  try{{const data=await api('/api/v2/game/dice/roll',{{method:'POST',body:'{{}}'}}); setWallet(data.wallet); setTimeout(()=>renderRoll(data.roll),120);}}
  catch(e){{d.classList.remove('rolling');toast(e.message);$('diceStatus').textContent=e.message; await loadState();}}finally{{state.busy=false}}
}};
async function pickAnime(opt,button){{
  if(state.busy||!state.activeRoll)return; state.busy=true; document.querySelectorAll('.anime-option').forEach(x=>x.disabled=true); button.style.boxShadow='0 0 0 2px rgba(255,211,108,.55)'; $('diceStatus').textContent='Revelando personagem…';
  try{{const data=await api('/api/v2/game/dice/pick',{{method:'POST',body:JSON.stringify({{roll_token:state.activeRoll.roll_token,anime_id:opt.id}})}}); const c=data.character; $('revealImg').src=c.image||'';$('revealName').textContent=c.name;$('revealAnime').textContent=c.anime+` • agora você tem ${{data.quantity}} cópia(s)`;$('reveal').classList.add('show');haptic('heavy');state.activeRoll=null;setWallet(data.state.wallet);$('animeGrid').innerHTML='';$('diceStatus').textContent='Carta adicionada à coleção.';}}
  catch(e){{toast(e.message);await loadState();}}finally{{state.busy=false}}
}}
function renderWheelLabels(){{const root=$('wheelLabels');root.innerHTML='';spinLabels.forEach((label,i)=>{{const e=document.createElement('div');e.className='wheel-label';e.textContent=label;e.style.transform=`rotate(${{i*45}}deg) translate(58px,-50%) rotate(10deg)`;root.appendChild(e)}})}}renderWheelLabels();
$('spinBtn').onclick=async()=>{{
  if(state.busy)return; state.busy=true; $('spinBtn').disabled=true; $('wheelResult').textContent='Girando…'; haptic('medium');
  try{{const data=await api('/api/v2/game/spin',{{method:'POST',body:'{{}}'}}); const idx=Number(data.segment_index||0); state.wheelTurns+=5; const center=idx*45; const target=state.wheelTurns*360 - center; $('wheel').style.transform=`rotate(${{target}}deg)`; setTimeout(()=>{{ $('wheelResult').textContent=`✨ ${{data.reward.label}}`; setWallet(data.wallet); haptic('heavy'); toast(`Você ganhou ${{data.reward.label}}`); state.busy=false; }},4200);}}
  catch(e){{toast(e.message);$('wheelResult').textContent=e.message;state.busy=false;await loadState();}}
}};
function activateTab(name){{document.querySelectorAll('.section').forEach(e=>e.classList.toggle('active',e.id===name));document.querySelectorAll('.tab').forEach(e=>e.classList.toggle('active',e.dataset.tab===name));history.replaceState(null,'','#'+name)}}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>activateTab(b.dataset.tab)); const first=['daily','dice','spin'].includes(location.hash.slice(1))?location.hash.slice(1):'daily';activateTab(first);loadState();
</script>
</body></html>'''


def register_game_routes(app) -> None:
    @app.get("/game", response_class=HTMLResponse)
    async def game_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/game/state")
    async def game_state_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        if not await _limited(user_id, "state", 60, 60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas atualizações. Tente de novo em instantes."}, status_code=429)
        return JSONResponse({"ok": True, "state": get_state(user_id)})

    @app.post("/api/v2/game/daily/claim")
    async def daily_claim_api(request: Request):
        user_id = _uid(request)
        if not await _limited(user_id, "daily", 4, 60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Espere um pouco antes de tentar novamente."}, status_code=429)
        result = claim_daily_reward(user_id)
        if not result.get("claimed"):
            return JSONResponse({"ok": False, "code": "already_claimed", "message": "Você já resgatou o Daily de hoje."}, status_code=409)
        return JSONResponse({"ok": True, **result})

    @app.post("/api/v2/game/dice/roll")
    async def dice_roll_api(request: Request):
        user_id = _uid(request)
        if not await _limited(user_id, "dice_roll", 10, 60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Você está rolando rápido demais."}, status_code=429)
        try:
            result = roll_dice(user_id)
        except GameServiceError as exc:
            return _error(exc, 409 if exc.code in {"active_roll", "no_dice"} else 400)
        return JSONResponse({"ok": True, **result})

    @app.post("/api/v2/game/dice/pick")
    async def dice_pick_api(request: Request):
        user_id = _uid(request)
        if not await _limited(user_id, "dice_pick", 16, 60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas escolhas em sequência."}, status_code=429)
        try:
            payload: Dict[str, Any] = await request.json()
        except Exception:
            payload = {{}}
        try:
            result = pick_dice_anime(
                user_id,
                str(payload.get("roll_token") or ""),
                int(payload.get("anime_id") or 0),
            )
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "code": "invalid_payload", "message": "Escolha inválida."}, status_code=400)
        except GameServiceError as exc:
            return _error(exc, 409 if exc.code in {"roll_expired", "roll_not_found"} else 400)
        return JSONResponse({"ok": True, **result})

    @app.post("/api/v2/game/spin")
    async def spin_api(request: Request):
        user_id = _uid(request)
        if not await _limited(user_id, "spin", 14, 60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Você está girando rápido demais."}, status_code=429)
        try:
            result = spin(user_id)
        except GameServiceError as exc:
            return _error(exc, 409 if exc.code == "no_spins" else 400)
        return JSONResponse({"ok": True, **result})
