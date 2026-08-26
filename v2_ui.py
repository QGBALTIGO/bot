from __future__ import annotations


def base_css() -> str:
    return r"""
:root{
  --bg:#050711;
  --bg-soft:#08101d;
  --surface:rgba(13,18,34,.91);
  --surface-2:rgba(18,26,46,.88);
  --surface-soft:rgba(255,255,255,.045);
  --line:rgba(255,255,255,.09);
  --line-strong:rgba(255,255,255,.17);
  --text:#f7f8ff;
  --muted:#9ca8c3;
  --muted-strong:#cad3e6;
  --pink:#ff5f9e;
  --violet:#9d73ff;
  --cyan:#5de6ff;
  --gold:#ffd36c;
  --green:#72f1bd;
  --danger:#ff6f86;
  --shadow:0 24px 70px rgba(0,0,0,.46);
  --shadow-soft:0 16px 42px rgba(0,0,0,.28);
  --r-xl:30px;
  --r-lg:24px;
  --r-md:18px;
  --safe-top:env(safe-area-inset-top,0px);
  --safe-bottom:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  min-height:100vh;
  color:var(--text);
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  background:
    radial-gradient(900px 520px at 0 -10%,rgba(93,230,255,.14),transparent 55%),
    radial-gradient(780px 520px at 110% 10%,rgba(255,95,158,.16),transparent 54%),
    linear-gradient(180deg,#050711 0%,#07101c 50%,#050812 100%);
  overflow-x:hidden;
  -webkit-font-smoothing:antialiased;
}
body:before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  opacity:.25;
  background-image:
    linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);
  background-size:34px 34px;
  mask-image:linear-gradient(#000,transparent 95%);
}
a{color:inherit;text-decoration:none}
button,input,select{font:inherit;color:inherit}
button{-webkit-tap-highlight-color:transparent}
.v2-shell{position:relative;z-index:1;width:min(1080px,100%);margin:auto;padding:calc(16px + var(--safe-top)) 14px calc(40px + var(--safe-bottom))}
.v2-hero{position:relative;overflow:hidden;padding:22px;border:1px solid var(--line);border-radius:var(--r-xl);background:linear-gradient(145deg,rgba(18,28,53,.94),rgba(8,12,25,.96));box-shadow:var(--shadow)}
.v2-hero:before{content:"";position:absolute;width:260px;height:260px;border-radius:50%;right:-60px;top:-100px;background:radial-gradient(circle,rgba(255,95,158,.34),transparent 68%)}
.v2-eyebrow{position:relative;color:var(--cyan);font-size:11px;font-weight:900;letter-spacing:.18em;text-transform:uppercase}
.v2-title{position:relative;margin:7px 0 8px;font-size:clamp(30px,8vw,52px);line-height:.96;letter-spacing:-.05em}
.v2-copy{position:relative;margin:0;color:var(--muted-strong);font-size:14px;line-height:1.55;max-width:62ch}
.v2-panel{margin-top:14px;padding:17px;border:1px solid var(--line);border-radius:var(--r-lg);background:linear-gradient(180deg,var(--surface),rgba(8,13,27,.95));box-shadow:var(--shadow-soft)}
.v2-section-title{margin:0;font-size:23px;letter-spacing:-.035em}
.v2-section-copy{margin:6px 0 0;color:var(--muted);font-size:13px;line-height:1.5}
.v2-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}
.v2-metric{padding:13px 11px;border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface-soft)}
.v2-metric-label{display:block;color:var(--muted);font-size:9px;font-weight:900;letter-spacing:.12em;text-transform:uppercase}
.v2-metric-value{display:block;margin-top:6px;font-size:20px;font-weight:950;letter-spacing:-.04em}
.v2-search{display:flex;align-items:center;gap:10px;margin-top:13px;padding:0 14px;border:1px solid var(--line);border-radius:17px;background:rgba(255,255,255,.04)}
.v2-search input{width:100%;min-height:50px;border:0;outline:0;background:transparent}
.v2-search input::placeholder{color:rgba(202,211,230,.45)}
.v2-btn{width:100%;min-height:50px;border:0;border-radius:17px;background:linear-gradient(135deg,var(--pink),var(--violet));font-weight:900;box-shadow:0 12px 30px rgba(157,115,255,.22);cursor:pointer;transition:transform .16s,filter .16s}
.v2-btn:active{transform:scale(.985)}
.v2-btn:disabled{opacity:.45;filter:grayscale(.45)}
.v2-chip{display:inline-flex;align-items:center;gap:6px;padding:8px 10px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.04);font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}
.v2-empty{padding:28px 18px;text-align:center;border:1px dashed var(--line-strong);border-radius:var(--r-lg);color:var(--muted);line-height:1.6}
.v2-skeleton{position:relative;overflow:hidden;background:rgba(255,255,255,.055)}
.v2-skeleton:after{content:"";position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent);animation:v2Shimmer 1.25s infinite}
@keyframes v2Shimmer{100%{transform:translateX(100%)}}
.v2-toast{position:fixed;z-index:100;left:50%;bottom:calc(18px + var(--safe-bottom));width:min(420px,calc(100% - 28px));transform:translate(-50%,20px);padding:13px 15px;border:1px solid var(--line);border-radius:17px;background:rgba(8,13,27,.96);box-shadow:var(--shadow);opacity:0;pointer-events:none;transition:.24s;text-align:center;font-size:13px}.v2-toast.show{opacity:1;transform:translate(-50%,0)}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
"""


def telegram_bootstrap_js() -> str:
    return r"""
const tg = window.Telegram?.WebApp || null;
if (tg) { try { tg.ready(); tg.expand(); } catch (_) {} }
async function v2Api(path, opts={}) {
  const headers = new Headers(opts.headers || {});
  if (tg?.initData) headers.set('X-Telegram-Init-Data', tg.initData);
  if (opts.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
  const response = await fetch(path, {...opts, headers});
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok || data.ok === false) {
    const error = new Error(data.message || 'Não foi possível concluir.');
    error.code = data.code || 'request_failed';
    error.status = response.status;
    throw error;
  }
  return data;
}
function v2Haptic(kind='light') { try { tg?.HapticFeedback?.impactOccurred(kind); } catch (_) {} }
function v2Toast(message) {
  const el = document.getElementById('v2Toast');
  if (!el) return;
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(v2Toast.timer);
  v2Toast.timer = setTimeout(() => el.classList.remove('show'), 2600);
}
"""
