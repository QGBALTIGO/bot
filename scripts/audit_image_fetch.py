"""Read-only TLS/DNS-pinning compatibility smoke using a public official test image."""
from __future__ import annotations
import asyncio
import io
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from utils.image_proxy import fetch_public_image, _urlopen_public_image
URL='https://www.python.org/static/community_logos/python-logo.png'
async def run():
    results=[]
    for name in ['pinned_httpx','pinned_http_1_1_fallback']:
        t=time.perf_counter()
        try:
            async with asyncio.timeout(30):
                data,kind,final=await (fetch_public_image(URL) if name=='pinned_httpx' else asyncio.to_thread(_urlopen_public_image,URL,{}))
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            assert kind=='image/png' and len(data)>100
            results.append({'case':name,'passed':True,'bytes':len(data),'media_type':kind,'ms':round((time.perf_counter()-t)*1000,2)})
        except Exception as e:
            results.append({'case':name,'passed':False,'error':type(e).__name__,'detail':str(e)})
    out=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/source-image-compatibility.json')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'url':URL,'checks':results},indent=2))
    print(json.dumps(results))
    if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':asyncio.run(run())
