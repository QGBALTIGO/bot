from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from profile_service import ProfileServiceError, sync_and_get_profile, update_profile
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
<title>Perfil • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.profile-head{{display:grid;grid-template-columns:82px 1fr;gap:14px;align-items:center;margin-top:17px}}.avatar{{width:82px;height:82px;border-radius:26px;border:1px solid var(--line-strong);display:grid;place-items:center;overflow:hidden;background:linear-gradient(145deg,rgba(157,115,255,.28),rgba(93,230,255,.16));font-size:34px;font-weight:1000;box-shadow:var(--shadow-soft)}}.avatar img{{width:100%;height:100%;object-fit:cover}}.display-name{{font-size:23px;font-weight:950;letter-spacing:-.04em;line-height:1.08}}.rank{{margin-top:5px;color:var(--gold);font-size:12px;font-weight:900}}.handle{{margin-top:5px;color:var(--muted);font-size:11px}}
.form-grid{{display:grid;gap:12px;margin-top:15px}}.field label{{display:block;margin:0 0 6px;color:var(--muted);font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.12em}}.field input,.field select{{width:100%;min-height:50px;padding:0 13px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.04);outline:0}}.toggle{{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:13px;border:1px solid var(--line);border-radius:17px;background:rgba(255,255,255,.035)}}.toggle-copy strong{{font-size:13px}}.toggle-copy span{{display:block;margin-top:4px;color:var(--muted);font-size:11px;line-height:1.4}}.switch{{position:relative;width:48px;height:28px;flex:0 0 auto}}.switch input{{display:none}}.switch span{{position:absolute;inset:0;border-radius:999px;background:rgba(255,255,255,.10);border:1px solid var(--line);transition:.2s}}.switch span:after{{content:"";position:absolute;width:20px;height:20px;left:3px;top:3px;border-radius:50%;background:#fff;transition:.2s}}.switch input:checked+span{{background:linear-gradient(90deg,var(--violet),var(--pink))}}.switch input:checked+span:after{{transform:translateX(20px)}}
.favorite{{display:grid;grid-template-columns:72px 1fr auto;gap:11px;align-items:center;margin-top:11px;padding:10px;border:1px solid var(--line);border-radius:20px;background:rgba(255,255,255,.035)}}.favorite img{{width:72px;height:86px;object-fit:cover;border-radius:14px;background:#0b1020}}.favorite-name{{font-size:13px;font-weight:950}}.favorite-anime{{margin-top:4px;color:var(--muted);font-size:10px}}.small-btn{{border:1px solid var(--line);border-radius:13px;background:rgba(255,255,255,.055);padding:9px;font-size:11px;font-weight:900;cursor:pointer}}.results{{display:grid;gap:7px;margin-top:8px;max-height:260px;overflow:auto}}.result{{display:grid;grid-template-columns:45px 1fr;gap:9px;align-items:center;padding:7px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.035);cursor:pointer}}.result img{{width:45px;height:54px;object-fit:cover;border-radius:10px}}.result b{{font-size:12px}}.result span{{display:block;color:var(--muted);font-size:10px;margin-top:2px}}
@media(min-width:700px){{.form-grid{{grid-template-columns:1fr 1fr}}.form-grid .wide{{grid-column:1/-1}}}}
</style>
</head>
<body>
<div class="v2-shell">
  <section class="v2-hero">
    <div class="v2-eyebrow">Source Baltigo • Perfil V2</div>
    <div class="profile-head"><div class="avatar" id="avatar">B</div><div><div class="display-name" id="displayName">Carregando…</div><div class="rank" id="rank">—</div><div class="handle" id="handle"></div></div></div>
    <div class="v2-metrics">
      <div class="v2-metric"><span class="v2-metric-label">Nível</span><span class="v2-metric-value" id="level">—</span></div>
      <div class="v2-metric"><span class="v2-metric-label">Coleção</span><span class="v2-metric-value" id="collection">—</span></div>
      <div class="v2-metric"><span class="v2-metric-label">Coins</span><span class="v2-metric-value" id="coins">—</span></div>
    </div>
  </section>

  <section class="v2-panel">
    <h2 class="v2-section-title">Sua identidade</h2><p class="v2-section-copy">Uma configuração só para perfil, ranking e futuros sistemas sociais.</p>
    <div class="form-grid">
      <div class="field"><label>Nickname</label><input id="nickname" maxlength="24" placeholder="Como você quer aparecer"></div>
      <div class="field"><label>País</label><select id="country"><option value="">Sem bandeira</option><option value="BR">🇧🇷 Brasil</option><option value="PT">🇵🇹 Portugal</option><option value="US">🇺🇸 Estados Unidos</option><option value="ES">🇪🇸 Espanha</option><option value="MX">🇲🇽 México</option><option value="AR">🇦🇷 Argentina</option><option value="CL">🇨🇱 Chile</option><option value="CO">🇨🇴 Colômbia</option><option value="JP">🇯🇵 Japão</option></select></div>
      <div class="toggle wide"><div class="toggle-copy"><strong>Perfil privado</strong><span>Quando os perfis públicos forem liberados, estatísticas detalhadas ficam ocultas para outras pessoas.</span></div><label class="switch"><input type="checkbox" id="privateProfile"><span></span></label></div>
    </div>
  </section>

  <section class="v2-panel">
    <h2 class="v2-section-title">Personagem favorito</h2><p class="v2-section-copy">O favorito será reutilizado no perfil, coleção e futuras telas sociais.</p>
    <div id="favorite"></div>
    <div class="v2-search"><span>⌕</span><input id="favoriteSearch" placeholder="Buscar personagem…" autocomplete="off"></div>
    <div class="results" id="results"></div>
  </section>

  <section class="v2-panel"><button class="v2-btn" id="saveBtn">Salvar perfil</button></section>
</div>
<div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let profile=null; let favoriteId=null; let searchTimer=null;
const esc=(s)=>String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function renderFavorite(f){{const root=document.getElementById('favorite');if(!f){{root.innerHTML='<div class="v2-empty">Nenhum favorito definido.</div>';return}};root.innerHTML=`<div class="favorite"><img src="${{esc(f.image)}}" alt=""><div><div class="favorite-name">${{esc(f.name)}}</div><div class="favorite-anime">${{esc(f.anime)}}</div></div><button class="small-btn" id="removeFav">Remover</button></div>`;document.getElementById('removeFav').onclick=()=>{{favoriteId=0;renderFavorite(null)}}}}
function renderProfile(p){{profile=p;favoriteId=p.favorite?.id||0;document.getElementById('displayName').textContent=p.display_name||'Usuário';document.getElementById('rank').textContent=p.progress?.rank||'—';document.getElementById('handle').textContent=p.telegram_username?'@'+p.telegram_username:'';document.getElementById('level').textContent=p.progress?.level??1;document.getElementById('collection').textContent=p.collection?.unique??0;document.getElementById('coins').textContent=p.wallet?.coins??0;document.getElementById('nickname').value=p.nickname||'';document.getElementById('country').value=p.country_code||'';document.getElementById('privateProfile').checked=!!p.private_profile;renderFavorite(p.favorite);const avatar=document.getElementById('avatar');avatar.textContent=(p.display_name||'B').trim().charAt(0).toUpperCase()||'B'}}
async function load(){{try{{const data=await v2Api('/api/v2/profile');renderProfile(data.profile)}}catch(e){{v2Toast(e.message)}}}}
async function searchFavorite(q){{const root=document.getElementById('results');if(q.trim().length<2){{root.innerHTML='';return}};try{{const res=await fetch('/api/cards/search?q='+encodeURIComponent(q.trim())+'&limit=12');const data=await res.json();root.innerHTML='';(data.items||[]).forEach(c=>{{const el=document.createElement('div');el.className='result';el.innerHTML=`<img src="${{esc(c.image)}}" alt=""><div><b>${{esc(c.name)}}</b><span>${{esc(c.anime)}}</span></div>`;el.onclick=()=>{{favoriteId=Number(c.id);renderFavorite({{id:c.id,name:c.name,anime:c.anime,image:c.image}});root.innerHTML='';document.getElementById('favoriteSearch').value='';v2Haptic('light')}};root.appendChild(el)}})}}catch(e){{root.innerHTML=''}}}}
document.getElementById('favoriteSearch').addEventListener('input',e=>{{clearTimeout(searchTimer);searchTimer=setTimeout(()=>searchFavorite(e.target.value),220)}});
document.getElementById('saveBtn').onclick=async()=>{{const btn=document.getElementById('saveBtn');btn.disabled=true;try{{const payload={{nickname:document.getElementById('nickname').value,private_profile:document.getElementById('privateProfile').checked,country_code:document.getElementById('country').value,favorite_character_id:favoriteId}};const data=await v2Api('/api/v2/profile',{{method:'POST',body:JSON.stringify(payload)}});renderProfile(data.profile);v2Haptic('medium');v2Toast('Perfil salvo.')}}catch(e){{v2Toast(e.message)}}finally{{btn.disabled=false}}}};load();
</script>
</body></html>'''


def register_profile_routes(app) -> None:
    @app.get("/profile", response_class=HTMLResponse)
    async def profile_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/profile")
    async def profile_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        if not await rate_limiter.allow(f"webapp:profile:get:{user_id}", limit=30, window_seconds=60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas atualizações em sequência."}, status_code=429)
        username = str(getattr(request.state, "telegram_username", "") or "")
        full_name = str(getattr(request.state, "telegram_full_name", "") or "")
        return JSONResponse({"ok": True, "profile": sync_and_get_profile(user_id, username=username, full_name=full_name)})

    @app.post("/api/v2/profile")
    async def profile_update_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        if not await rate_limiter.allow(f"webapp:profile:update:{user_id}", limit=10, window_seconds=60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Você está salvando rápido demais."}, status_code=429)
        try:
            payload: Dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "code": "invalid_json", "message": "Dados inválidos."}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"ok": False, "code": "invalid_payload", "message": "Dados inválidos."}, status_code=400)
        try:
            profile = update_profile(user_id, payload)
        except ProfileServiceError as exc:
            return JSONResponse({"ok": False, "code": exc.code, "message": exc.message}, status_code=409 if exc.code == "nickname_taken" else 400)
        return JSONResponse({"ok": True, "profile": profile})
