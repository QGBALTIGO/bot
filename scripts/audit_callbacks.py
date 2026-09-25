"""Exercise all registered callback entrypoints with synthetic users and messages.

Only a disposable PostgreSQL database is permitted. External transports are denied.
Read-only pagination, malformed data, and wrong-owner cases are not real Telegram UX tests.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
url=os.environ.get('SOURCE_AUDIT_DATABASE_URL','');parsed=urlparse(url)
if parsed.hostname not in {'127.0.0.1','localhost','postgres'} or parsed.path!='/source_audit':
    raise SystemExit('Requires disposable localhost/source_audit')
os.environ.update(DATABASE_URL=url,BOT_TOKEN='999999999:synthetic-audit-invalid-token',BOT_USERNAME='SourceAuditTestBot',BOT_OWNER_ID='99000001',ADMIN_IDS='99000001',SOURCE_MINIAPP_URL='https://example.invalid/menu',REQUIRED_CHANNEL='')
import httpx
import requests
async def denied_async(*args,**kwargs): raise httpx.ConnectError('External transport denied in isolated audit')
def denied_sync(*args,**kwargs): raise requests.ConnectionError('External transport denied in isolated audit')
httpx.AsyncHTTPTransport.handle_async_request=denied_async
requests.sessions.Session.send=denied_sync
import bot
from database import create_or_get_user
from database_core import run,pool
handlers=[]
bot.register_callbacks(SimpleNamespace(add_handler=lambda h:handlers.append(h)))

async def audit():
    result=[]
    for h in handlers:
        pat=h.pattern.pattern
        base=pat.lstrip('^').rstrip('$')
        for case in ['malformed','unknown_or_wrong_owner']:
            uid=99300000+len(result)+1;create_or_get_user(uid)
            run("UPDATE users SET terms_accepted=TRUE,terms_version='v1' WHERE user_id=%s",(uid,))
            who=SimpleNamespace(id=uid,username='audit_callback',first_name='Teste',last_name='',full_name='Teste',is_bot=False)
            chat=SimpleNamespace(id=uid,type='private',username=None)
            actions=[]
            async def respond(*args,**kwargs): actions.append({'args':str(args)[:200],'keys':list(kwargs)});return SimpleNamespace(message_id=1,chat_id=uid)
            message=SimpleNamespace(message_id=1,chat_id=uid,chat=chat,from_user=who,text=None,caption='Teste',photo=[],reply_to_message=None,
                edit_caption=respond,edit_text=respond,edit_media=respond,edit_reply_markup=respond,delete=respond,reply_text=respond,reply_html=respond,reply_photo=respond)
            prefix=base.split(':')[0]
            if prefix=='imgrev': data='imgrev:a:999999999'
            elif prefix in {'xcardnoop','xcolecao_noop'}: data=prefix
            elif case=='malformed':
                data=prefix+(':bad:20:bad' if prefix.startswith(('colecao_','xcolecao','xcardnav')) else ':bad:bad' if prefix=='colecao' else ':bad')
            else:
                if prefix=='colecao': data=f'{prefix}:99000003:1'
                elif prefix.startswith(('colecao_','xcolecao','xcardnav')):data=f'{prefix}:99000003:20:1'
                elif prefix=='rank':data='rank:level:99000003'
                elif prefix=='termo':data='termo:invalid:99000003'
                elif prefix=='capturebuy':data='capturebuy:999999999:99000003'
                elif prefix=='duel':data='duel:accept:999999999'
                else:data=f'{prefix}:999999999'
            query=SimpleNamespace(id='synthetic',data=data,from_user=who,message=message,answer=respond,edit_message_caption=respond,edit_message_text=respond,edit_message_reply_markup=respond)
            update=SimpleNamespace(callback_query=query,message=None,effective_message=message,effective_user=who,effective_chat=chat)
            tasks=[]
            def create_task(coro,**kw): t=asyncio.create_task(coro);tasks.append(t);return t
            fakebot=SimpleNamespace(id=999999999,username='SourceAuditTestBot',get_chat_member=AsyncMock(return_value=SimpleNamespace(status='member')),send_message=respond,send_photo=respond,edit_message_caption=respond,answer_callback_query=respond)
            ctx=SimpleNamespace(bot=fakebot,args=[],user_data={},chat_data={},bot_data={},application=SimpleNamespace(bot=fakebot,bot_data={},create_task=create_task),job_queue=None)
            try:
                async with asyncio.timeout(5): await h.callback(update,ctx)
                row={'handler':h.callback.__name__,'pattern':pat,'case':case,'status':'acknowledged' if actions else 'silent','responses':len(actions)}
            except Exception as e:row={'handler':h.callback.__name__,'pattern':pat,'case':case,'status':'error','error':type(e).__name__,'detail':str(e),'trace':traceback.format_exc()}
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            result.append(row)
    return result

rows=asyncio.run(audit())
out=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/callback-audit.json');out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'registrations':len(handlers),'checks':rows},ensure_ascii=False,indent=2))
pool.close()
print(json.dumps({'registrations':len(handlers),'checks':len(rows),'errors':sum(r['status']=='error' for r in rows)}))
raise SystemExit(1 if any(r['status']=='error' for r in rows) else 0)
