"""Behavioral audit against disposable PostgreSQL only, never production.

Runs HTTP routes and command entry handlers with synthetic identities. Telegram
and third-party network transports are denied. This is NOT real-device testing.
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
import hmac
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode, urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/source-audit-runtime')
OUT.mkdir(parents=True,exist_ok=True)
url=os.getenv('SOURCE_AUDIT_DATABASE_URL','')
parsed=urlparse(url)
if parsed.hostname not in {'localhost','127.0.0.1','postgres'} or parsed.path != '/source_audit':
    raise SystemExit('Requires an explicitly named disposable source_audit database on localhost/postgres')
os.environ.update(DATABASE_URL=url, BOT_TOKEN='999999999:synthetic-audit-token-not-valid', BOT_USERNAME='SourceAuditTestBot',
 SOURCE_MINIAPP_URL='https://example.invalid/menu', BASE_URL='https://example.invalid', BOT_OWNER_ID='99000001',
 ADMIN_IDS='99000001', REQUIRED_CHANNEL='', CAKTO_WEBHOOK_SECRET='synthetic-webhook-secret',
 ALLOW_INSECURE_WEBAPP_UID_FALLBACK='false')
import httpx
import requests
async def blocked_async(*args,**kwargs): raise httpx.ConnectError('External service denied in isolated audit')
def blocked_sync(*args,**kwargs): raise httpx.ConnectError('External service denied in isolated audit')
def blocked_requests(*args,**kwargs): raise requests.ConnectionError('External service denied in isolated audit')
httpx.AsyncHTTPTransport.handle_async_request=blocked_async
httpx.HTTPTransport.handle_request=blocked_sync
requests.sessions.Session.send=blocked_requests
from database import create_tables,create_or_get_user
from database_core import run,pool
create_tables()
for uid in [99000001,99000002,99000003]:
 create_or_get_user(uid)
 run("UPDATE users SET coins=100,terms_accepted=TRUE,terms_version='v1' WHERE user_id=%s",(uid,))
import webapp_entrypoint
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from webapp_routes.aninexus_compat import _issue_session

user={'id':99000002,'first_name':'Teste','username':'source_audit_synthetic'}
def signed(u):
 data={'auth_date':str(int(time.time())), 'user':json.dumps(u,separators=(',',':'))}
 secret=hmac.new(b'WebAppData',os.environ['BOT_TOKEN'].encode(),hashlib.sha256).digest()
 data['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(data.items())).encode(),hashlib.sha256).hexdigest()
 return urlencode(data)
headers={'Authorization':'Bearer '+_issue_session(user),'X-Telegram-Init-Data':signed(user)}
http_results=[]
# OpenAPI sees included routers across FastAPI versions; app.routes can be deferred.
route_specs={}
for path, item in webapp_entrypoint.app.openapi().get('paths',{}).items():
 for method, operation in item.items():
  if method.upper() in {'GET','POST','PUT','PATCH','DELETE'}:
   query={p['name']:'invalid' for p in operation.get('parameters',[]) if p.get('in')=='query' and p.get('required')}
   route_specs[(path,method.upper())]=query
# Preserve explicit HTML/internal endpoints deliberately absent from OpenAPI.
for route in webapp_entrypoint.app.routes:
 if not isinstance(route,APIRoute):continue
 for method in route.methods-{'HEAD','OPTIONS'}:
  query={f.alias:'invalid' for f in route.dependant.query_params
         if getattr(f, 'required', None) is True or (hasattr(f, 'field_info') and f.field_info.is_required())}
  route_specs.setdefault((route.path,method),query)
with TestClient(webapp_entrypoint.app,raise_server_exceptions=True) as client:
 for (path,method),query in sorted(route_specs.items()):
  sample=re.sub(r'\{[^}]+\}', '1',path)
  for case,hdr in [('unauthenticated',{}),('malformed_auth',{'Authorization':'Bearer invalid','X-Telegram-Init-Data':'invalid'}),('synthetic_valid',headers)]+([('malformed_fields',headers)] if method in {'POST','PUT','PATCH','DELETE'} else []):
   body={} if method in {'POST','PUT','PATCH','DELETE'} else None
   if case=='malformed_fields': body={key:'not-an-integer' for key in ('character_id','sale_id','user_id','amount','quantity','score','time_ms','moves','target_user_id','from_character_id','to_character_id')}
   t=time.perf_counter()
   try:
    r=client.request(method,sample,params=query,headers=hdr,json=body,follow_redirects=False)
    text=r.text[:300] if r.status_code>=400 else ''
    http_results.append({'method':method,'path':path,'case':case,'status':r.status_code,'ms':round((time.perf_counter()-t)*1000,2),'response':text})
   except Exception as exc:
    http_results.append({'method':method,'path':path,'case':case,'status':500,'error':type(exc).__name__,'trace':traceback.format_exc()[-1600:]})
assert len(http_results)>=438, f'Unexpected route inventory: {len(http_results)}; adapt traversal rather than claim coverage'
(OUT/'http.json').write_text(json.dumps(http_results,ensure_ascii=False,indent=2))

async def commands():
 import bot
 handlers=[]
 bot.register_commands(SimpleNamespace(add_handler=lambda handler:handlers.append(handler)))
 records=[]
 from telegram.ext import CommandHandler
 for handler in handlers:
  if not isinstance(handler, CommandHandler):
   continue  # InlineQueryHandler is tested separately with consent/privacy scenarios.
  name=next(iter(handler.commands))
  # Ordinary-user no-argument checks exercise guards without destructive admin operations.
  for chat_type in ['private','supergroup']:
   uid=99200000+len(records)+1
   create_or_get_user(uid)
   run("UPDATE users SET coins=100,terms_accepted=TRUE,terms_version='v1' WHERE user_id=%s",(uid,))
   who=SimpleNamespace(id=uid,username='source_audit_synthetic',first_name='Teste',last_name='',full_name='Teste <&>',is_bot=False,language_code='pt')
   chat=SimpleNamespace(id=uid if chat_type=='private' else -99000002,type=chat_type,title='Audit',username=None)
   replies=[]
   async def respond(*args,**kw):
    replies.append({'args':[str(a)[:150] for a in args],'kwargs_keys':list(kw)})
    return SimpleNamespace(message_id=1,chat_id=chat.id,delete=AsyncMock(),edit_text=AsyncMock(),edit_caption=AsyncMock(),edit_reply_markup=AsyncMock())
   msg=SimpleNamespace(text='/'+name,caption=None,message_id=1,chat=chat,chat_id=chat.id,from_user=who,reply_to_message=None,
       reply_text=respond,reply_html=respond,reply_photo=respond,reply_document=respond,reply_dice=respond,delete=AsyncMock())
   update=SimpleNamespace(message=msg,effective_message=msg,effective_user=who,effective_chat=chat,callback_query=None,inline_query=None)
   tasks=[]
   def create_task(coro,**kw):
    task=asyncio.create_task(coro);tasks.append(task);return task
   app=SimpleNamespace(bot_data={},create_task=create_task)
   fake_bot=SimpleNamespace(username='SourceAuditTestBot',id=999999999,get_me=AsyncMock(return_value=SimpleNamespace(username='SourceAuditTestBot')),get_chat_member=AsyncMock(return_value=SimpleNamespace(status='member')),send_message=respond,send_photo=respond,send_document=respond,get_user_profile_photos=AsyncMock(return_value=SimpleNamespace(total_count=0,photos=[])))
   update.get_bot = lambda: fake_bot
   context=SimpleNamespace(args=[],bot=fake_bot,application=app,bot_data=app.bot_data,user_data={},chat_data={},job_queue=None)
   start=time.perf_counter()
   try:
    async with asyncio.timeout(6): await handler.callback(update,context)
    result={'command':name,'chat':chat_type,'replies':len(replies),'status':'responded' if replies else 'silent','ms':round((time.perf_counter()-start)*1000,2)}
   except Exception as exc:
    result={'command':name,'chat':chat_type,'status':'error','error':type(exc).__name__,'detail':str(exc)[:200],'trace':traceback.format_exc()[-1000:]}
   if tasks: await asyncio.gather(*tasks,return_exceptions=True)
   records.append(result)
 return records
try: (OUT/'commands.json').write_text(json.dumps(asyncio.run(commands()),ensure_ascii=False,indent=2))
except Exception: (OUT/'commands-init-error.txt').write_text(traceback.format_exc())
pool.close()
print(json.dumps({'http_probes':len(http_results),'http_500':sum(r.get('status',0)>=500 for r in http_results)}))
command_results = json.loads((OUT/'commands.json').read_text())
raise SystemExit(1 if any(r.get('status') == 500 for r in http_results) or any(r.get('status') == 'error' for r in command_results) else 0)
