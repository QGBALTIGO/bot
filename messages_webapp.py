from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from identity_repository import find_identity_by_nickname
from messages_repository import MessageError, message_center_state, report_message, set_message_block, update_message_settings
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state,"telegram_user_id",0) or 0)


def _page() -> str:
    return f'''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#070a14"><title>Mensagens • Baltigo</title><script src="https://telegram.org/js/telegram-web-app.js"></script><style>{base_css()}
.tabs{{display:flex;gap:8px;overflow:auto;margin-top:14px}}.tab{{padding:9px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface-soft);font-size:10px;font-weight:950;text-transform:uppercase;letter-spacing:.08em}}.tab.active{{background:rgba(93,230,255,.1);border-color:rgba(93,230,255,.4)}}.view{{display:none}}.view.active{{display:block}}.list{{display:grid;gap:9px;margin-top:13px}}.msg{{padding:13px;border:1px solid var(--line);border-radius:17px;background:var(--surface-soft)}}.msg .meta{{font-size:10px;color:var(--muted);margin-bottom:7px}}.msg .text{{white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.45}}.switch{{display:flex;align-items:center;justify-content:space-between;padding:13px 0;border-bottom:1px solid var(--line)}}.switch input{{width:22px;height:22px}}.field{{margin-top:12px}}.field input{{width:100%;padding:13px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.04);outline:0}}
</style></head><body><div class="v2-shell"><section class="v2-hero"><div class="v2-eyebrow">Social • Mensagens V2</div><h1 class="v2-title">Converse sem<br>perder o controle.</h1><p class="v2-copy">Histórico, mensagens anônimas, bloqueios e denúncias usam regras persistentes. A identidade anônima nunca é enviada ao destinatário.</p><div class="tabs"><button class="tab active" data-v="inbox">Recebidas</button><button class="tab" data-v="sent">Enviadas</button><button class="tab" data-v="settings">Privacidade</button></div></section><section class="v2-panel view active" id="inbox"><h2 class="v2-section-title">Recebidas</h2><div class="list" id="inboxList"></div></section><section class="v2-panel view" id="sent"><h2 class="v2-section-title">Enviadas</h2><div class="list" id="sentList"></div></section><section class="v2-panel view" id="settings"><h2 class="v2-section-title">Privacidade</h2><div class="switch"><span>Receber mensagens</span><input id="allow" type="checkbox"></div><div class="switch"><span>Permitir anônimas</span><input id="anon" type="checkbox"></div><h3>Bloquear por nickname</h3><div class="field"><input id="blockNick" placeholder="nickname"></div><button class="v2-btn" id="blockBtn" style="margin-top:10px">Bloquear</button><div class="list" id="blocks"></div></section></div><div class="v2-toast" id="v2Toast"></div><script>{telegram_bootstrap_js()}
let state={{inbox:[],sent:[],blocks:[],settings:{{}}}};const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===b.dataset.v))}});
function render(){{$('inboxList').innerHTML=state.inbox.length?state.inbox.map(x=>`<div class="msg"><div class="meta">#${{x.message_id}} • ${{esc(x.from)}}${{x.is_anonymous?' • anônima':''}}</div><div class="text">${{esc(x.text)}}</div><button class="tab report" data-id="${{x.message_id}}" style="margin-top:9px">Denunciar</button></div>`).join(''):'<div class="v2-empty">Nenhuma mensagem recebida.</div>';$('sentList').innerHTML=state.sent.length?state.sent.map(x=>`<div class="msg"><div class="meta">#${{x.message_id}} • para ${{esc(x.to)}} • ${{esc(x.status)}}${{x.is_anonymous?' • anônima':''}}</div><div class="text">${{esc(x.text)}}</div></div>`).join(''):'<div class="v2-empty">Nenhuma mensagem enviada.</div>';$('allow').checked=!!state.settings.allow_messages;$('anon').checked=!!state.settings.allow_anonymous;$('blocks').innerHTML=state.blocks.length?state.blocks.map(x=>`<div class="msg"><b>${{esc(x.display_name)}}</b><button class="tab unblock" data-id="${{x.blocked_user_id}}" style="margin-left:8px">Desbloquear</button></div>`).join(''):'<div class="v2-empty">Nenhum bloqueio.</div>';document.querySelectorAll('.report').forEach(b=>b.onclick=async()=>{{const reason=prompt('Motivo da denúncia:')||'';try{{await v2Api('/api/v2/messages/report',{{method:'POST',body:JSON.stringify({{message_id:Number(b.dataset.id),reason}})}});v2Toast('Denúncia registrada.')}}catch(e){{v2Toast(e.message)}}}});document.querySelectorAll('.unblock').forEach(b=>b.onclick=async()=>{{try{{await v2Api('/api/v2/messages/block',{{method:'POST',body:JSON.stringify({{user_id:Number(b.dataset.id),blocked:false}})}});await load()}}catch(e){{v2Toast(e.message)}}}})}}
async function load(){{try{{const d=await v2Api('/api/v2/messages/state');state=d.state;render()}}catch(e){{v2Toast(e.message)}}}};$('allow').onchange=$('anon').onchange=async()=>{{try{{await v2Api('/api/v2/messages/settings',{{method:'POST',body:JSON.stringify({{allow_messages:$('allow').checked,allow_anonymous:$('anon').checked}})}});v2Toast('Preferências salvas.')}}catch(e){{v2Toast(e.message);load()}}}};$('blockBtn').onclick=async()=>{{try{{await v2Api('/api/v2/messages/block',{{method:'POST',body:JSON.stringify({{nickname:$('blockNick').value,blocked:true}})}});$('blockNick').value='';v2Toast('Bloqueado.');load()}}catch(e){{v2Toast(e.message)}}}};load();</script></body></html>'''


def register_message_routes(app) -> None:
    @app.get('/messages',response_class=HTMLResponse)
    async def messages_page(): return HTMLResponse(_page())

    @app.get('/api/v2/messages/state')
    async def messages_state(request:Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f'messages:web:state:{uid}',limit=50,window_seconds=60): return JSONResponse({'ok':False,'message':'Muitas atualizações.'},status_code=429)
        return JSONResponse({'ok':True,'state':message_center_state(uid)})

    @app.post('/api/v2/messages/settings')
    async def messages_settings(request:Request):
        uid=_uid(request);p=await request.json();return JSONResponse({'ok':True,'settings':update_message_settings(uid,allow_messages=p.get('allow_messages'),allow_anonymous=p.get('allow_anonymous'))})

    @app.post('/api/v2/messages/block')
    async def messages_block(request:Request):
        uid=_uid(request);p=await request.json();target_id=0
        if p.get('nickname'):
            target=find_identity_by_nickname(str(p.get('nickname') or ''))
            if not target:return JSONResponse({'ok':False,'message':'Nickname não encontrado.'},status_code=404)
            target_id=int(target['user_id'])
        else:
            try:target_id=int(p.get('user_id') or 0)
            except Exception:target_id=0
        try:set_message_block(uid,target_id,bool(p.get('blocked',True)))
        except MessageError as exc:return JSONResponse({'ok':False,'message':exc.message},status_code=400)
        return JSONResponse({'ok':True})

    @app.post('/api/v2/messages/report')
    async def messages_report(request:Request):
        uid=_uid(request);p=await request.json()
        try:row=report_message(uid,int(p.get('message_id') or 0),str(p.get('reason') or ''))
        except (MessageError,ValueError) as exc:return JSONResponse({'ok':False,'message':getattr(exc,'message',str(exc))},status_code=400)
        return JSONResponse({'ok':True,'report_id':int(row.get('id') or 0)})
