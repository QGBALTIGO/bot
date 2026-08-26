from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from ranking_service import get_ranking_state
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page() -> str:
    return f'''<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070a14">
<title>Ranking • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.rank-tabs{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:14px;padding:5px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.035)}}
.rank-tab{{min-height:43px;border:0;border-radius:13px;background:transparent;color:var(--muted);font-size:11px;font-weight:900;cursor:pointer;transition:.18s}}
.rank-tab.active{{color:#fff;background:linear-gradient(135deg,rgba(157,115,255,.26),rgba(93,230,255,.13));box-shadow:inset 0 0 0 1px rgba(255,255,255,.07)}}
.podium{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;align-items:end;margin-top:16px}}
.podium-card{{position:relative;min-height:145px;padding:14px 10px;border:1px solid var(--line);border-radius:21px;background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.025));text-align:center;overflow:hidden}}
.podium-card.first{{min-height:174px;border-color:rgba(255,211,108,.30);background:linear-gradient(180deg,rgba(255,211,108,.12),rgba(255,255,255,.025))}}
.podium-medal{{font-size:25px}}.podium-name{{margin-top:8px;font-size:12px;font-weight:950;line-height:1.2;word-break:break-word}}.podium-value{{margin-top:7px;color:var(--gold);font-size:12px;font-weight:900}}.podium-flag{{font-size:16px;margin-top:5px}}
.rank-list{{display:grid;gap:8px;margin-top:12px}}.rank-row{{display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:10px;align-items:center;padding:12px;border:1px solid var(--line);border-radius:17px;background:rgba(255,255,255,.035)}}.rank-row.me{{border-color:rgba(93,230,255,.32);background:linear-gradient(90deg,rgba(93,230,255,.09),rgba(157,115,255,.06))}}.rank-pos{{font-size:13px;font-weight:1000;color:var(--muted)}}.rank-name{{font-size:12px;font-weight:950;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.rank-sub{{margin-top:3px;color:var(--muted);font-size:10px}}.rank-score{{text-align:right;font-size:12px;font-weight:950;color:var(--gold)}}
.viewer-card{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:13px}}.viewer-pos{{padding:11px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.035);text-align:center}}.viewer-pos b{{display:block;font-size:17px}}.viewer-pos span{{display:block;margin-top:3px;color:var(--muted);font-size:9px;text-transform:uppercase;font-weight:900;letter-spacing:.09em}}
.rule{{margin-top:12px;padding:12px;border-left:2px solid var(--cyan);border-radius:0 13px 13px 0;background:rgba(93,230,255,.055);color:var(--muted-strong);font-size:11px;line-height:1.5}}
@media(max-width:420px){{.rank-tab{{font-size:10px;padding:0 4px}}.podium-card{{padding:12px 6px}}}}
</style>
</head>
<body>
<div class="v2-shell">
  <section class="v2-hero">
    <div class="v2-eyebrow">Source Baltigo • Ranking V2</div>
    <h1 class="v2-title">Quem está no topo?</h1>
    <p class="v2-copy">Progressão, coleção e economia agora usam fontes únicas. O placar geral não usa coins, evitando que saldo ou compras virem vantagem competitiva.</p>
    <div class="viewer-card">
      <div class="viewer-pos"><b id="myLevel">—</b><span>Nível</span></div>
      <div class="viewer-pos"><b id="myCollection">—</b><span>Coleção</span></div>
      <div class="viewer-pos"><b id="myCoins">—</b><span>Fortuna</span></div>
    </div>
  </section>

  <section class="v2-panel">
    <div class="rank-tabs">
      <button class="rank-tab active" data-tab="general">🏆 Geral</button>
      <button class="rank-tab" data-tab="level">⭐ Nível</button>
      <button class="rank-tab" data-tab="collection">📚 Coleção</button>
      <button class="rank-tab" data-tab="coins">🪙 Coins</button>
    </div>
    <div class="podium" id="podium"></div>
    <div class="rank-list" id="rankList"><div class="v2-empty">Carregando ranking…</div></div>
    <div class="rule" id="rule"></div>
  </section>
</div>
<div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let state=null; let active='general';
const medal=p=>p===1?'🥇':p===2?'🥈':p===3?'🥉':'#'+p;
const fmt=n=>new Intl.NumberFormat('pt-BR').format(Number(n||0));
function valueFor(item,kind){{
  if(kind==='general') return `${{Number(item.score||0).toFixed(1)}} pts`;
  if(kind==='level') return `Nv. ${{fmt(item.level)}}`;
  if(kind==='collection') return `${{fmt(item.unique_cards)}} únicas`;
  return `${{fmt(item.coins)}} coins`;
}}
function subFor(item,kind){{
  if(kind==='general') return `Nv. ${{fmt(item.level)}} • ${{fmt(item.unique_cards)}} cartas`;
  if(kind==='level') return `${{fmt(item.xp)}} XP • ${{fmt(item.total_actions)}} ações`;
  if(kind==='collection') return `${{fmt(item.total_copies)}} cópias totais`;
  return 'Saldo atual da wallet V2';
}}
function makePodium(item,slot){{
  const el=document.createElement('div');el.className='podium-card '+(item.position===1?'first':'');
  const medalEl=document.createElement('div');medalEl.className='podium-medal';medalEl.textContent=medal(item.position);
  const name=document.createElement('div');name.className='podium-name';name.textContent=item.display_name||'Jogador';
  const flag=document.createElement('div');flag.className='podium-flag';flag.textContent=item.flag||' ';
  const val=document.createElement('div');val.className='podium-value';val.textContent=valueFor(item,active);
  el.append(medalEl,name,flag,val);return el;
}}
function render(kind){{
  active=kind;document.querySelectorAll('.rank-tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===kind));
  const rows=state?.leaderboards?.[kind]||[];const podium=document.getElementById('podium');const list=document.getElementById('rankList');podium.innerHTML='';list.innerHTML='';
  const top=rows.slice(0,3);[top[1],top[0],top[2]].filter(Boolean).forEach(item=>podium.appendChild(makePodium(item)));
  rows.slice(3).forEach(item=>{{const row=document.createElement('div');row.className='rank-row'+(item.is_viewer?' me':'');const pos=document.createElement('div');pos.className='rank-pos';pos.textContent='#'+item.position;const main=document.createElement('div');const name=document.createElement('div');name.className='rank-name';name.textContent=(item.flag?item.flag+' ':'')+(item.display_name||'Jogador');const sub=document.createElement('div');sub.className='rank-sub';sub.textContent=subFor(item,kind);main.append(name,sub);const score=document.createElement('div');score.className='rank-score';score.textContent=valueFor(item,kind);row.append(pos,main,score);list.appendChild(row)}});
  if(!rows.length) list.innerHTML='<div class="v2-empty">Ainda não há dados suficientes para este ranking.</div>';
  document.getElementById('rule').textContent=kind==='general'?(state?.rules?.general||''):(kind==='coins'?'Coins aparecem apenas como ranking de fortuna e não alteram o placar geral.':'Desempates usam a métrica secundária do próprio sistema.');
}}
function pos(v){{return Number(v||0)>0?'#'+v:'—'}}
async function load(){{try{{const data=await v2Api('/api/v2/ranking');state=data.ranking;const p=state.viewer?.positions||{{}};document.getElementById('myLevel').textContent=pos(p.level);document.getElementById('myCollection').textContent=pos(p.collection);document.getElementById('myCoins').textContent=pos(p.coins);if(state.viewer?.public===false){{v2Toast('Seu perfil está privado e não aparece nos rankings públicos.')}}render(active)}}catch(e){{v2Toast(e.message);document.getElementById('rankList').innerHTML='<div class="v2-empty">Não foi possível carregar o ranking.</div>'}}}}
document.querySelectorAll('.rank-tab').forEach(btn=>btn.onclick=()=>{{render(btn.dataset.tab);v2Haptic('light')}});load();
</script>
</body></html>'''


def register_ranking_routes(app) -> None:
    @app.get("/ranking", response_class=HTMLResponse)
    async def ranking_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/ranking")
    async def ranking_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse(
                {"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."},
                status_code=401,
            )
        if not await rate_limiter.allow(
            f"webapp:ranking:get:{user_id}", limit=20, window_seconds=60
        ):
            return JSONResponse(
                {"ok": False, "code": "rate_limited", "message": "Muitas atualizações em sequência."},
                status_code=429,
            )
        return JSONResponse({"ok": True, "ranking": get_ranking_state(user_id)})
