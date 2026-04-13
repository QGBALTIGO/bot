import html
import json
from typing import Any


def _h(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _font_links() -> str:
    return """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
"""


def _base_css() -> str:
    return (
        r"""
:root{
  --bg:#060914;
  --bg-2:#0b1224;
  --surface:rgba(10,16,34,.82);
  --surface-2:rgba(17,26,47,.88);
  --surface-soft:rgba(255,255,255,.045);
  --border:rgba(169,184,206,.18);
  --border-strong:rgba(255,255,255,.26);
  --text:#f6f8fd;
  --muted:rgba(226,232,244,.66);
  --muted-strong:rgba(234,239,248,.82);
  --accent:#ff6f94;
  --accent-cool:#7ad5ff;
  --ok:#51deb5;
  --danger:#ff6a7f;
  --shadow-lg:0 24px 60px rgba(0,0,0,.42);
  --shadow-md:0 18px 36px rgba(0,0,0,.30);
  --radius-xl:30px;
  --radius-lg:24px;
  --radius-md:18px;
  --safe-top:env(safe-area-inset-top, 0px);
  --safe-bottom:env(safe-area-inset-bottom, 0px);
}
*{ box-sizing:border-box; }
html,body{ min-height:100%; }
body{
  margin:0;
  color:var(--text);
  font-family:"Plus Jakarta Sans", "Segoe UI", sans-serif;
  background:
    radial-gradient(920px 420px at 12% -8%, rgba(122,213,255,.16), transparent 58%),
    radial-gradient(780px 460px at 100% 0%, rgba(255,111,148,.16), transparent 50%),
    linear-gradient(180deg, #040711 0%, #08101f 38%, #070d18 100%);
  overflow-x:hidden;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
}
body::before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  background:
    linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0) 18%),
    radial-gradient(rgba(255,255,255,.05) 1px, transparent 1px);
  background-size:auto, 34px 34px;
  opacity:.24;
  mask-image:linear-gradient(180deg, rgba(0,0,0,.9), transparent 92%);
}
body::after{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  background:linear-gradient(180deg, rgba(2,5,12,.08), rgba(2,5,12,.42));
}
a{ color:inherit; text-decoration:none; }
img{ max-width:100%; }
button,input,select{ font:inherit; color:inherit; }
button{ appearance:none; -webkit-tap-highlight-color:transparent; }
.app-shell{
  position:relative;
  z-index:1;
  width:min(1120px, 100%);
  margin:0 auto;
  padding:calc(16px + var(--safe-top)) 14px calc(28px + var(--safe-bottom));
}
.hero-card{
  position:relative;
  overflow:hidden;
  border-radius:var(--radius-xl);
  border:1px solid var(--border);
  background:linear-gradient(180deg, rgba(16,24,46,.88), rgba(7,12,24,.94));
  box-shadow:var(--shadow-lg);
  min-height:260px;
}
.hero-card.hero-card--compact{ min-height:224px; }
.hero-media{ position:absolute; inset:0; }
.hero-media img{ width:100%; height:100%; object-fit:cover; display:block; opacity:.94; }
.hero-overlay{
  position:absolute;
  inset:0;
  background:
    linear-gradient(180deg, rgba(7,11,22,.22), rgba(7,11,22,.82)),
    linear-gradient(115deg, rgba(4,8,18,.36), rgba(4,8,18,.08) 34%, rgba(255,111,148,.12) 80%, rgba(122,213,255,.18));
}
.hero-content{
  position:relative;
  z-index:1;
  display:flex;
  flex-direction:column;
  justify-content:flex-end;
  gap:12px;
  min-height:inherit;
  padding:20px;
}
.eyebrow-chip{
  width:max-content;
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:9px 14px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.16);
  background:rgba(8,14,28,.50);
  backdrop-filter:blur(16px);
  font-size:11px;
  font-weight:800;
  letter-spacing:.18em;
  text-transform:uppercase;
  color:var(--muted-strong);
}
.hero-title,
.section-title,
.card-title,
.profile-name,
.sheet-title,
.hub-title,
.hero-value{
  font-family:"Space Grotesk", "Plus Jakarta Sans", sans-serif;
}
.hero-title{
  margin:0;
  max-width:14ch;
  font-size:clamp(30px, 8vw, 52px);
  line-height:.98;
  letter-spacing:-.04em;
}
.hero-subtitle{
  margin:0;
  max-width:54ch;
  color:var(--muted-strong);
  font-size:14px;
  line-height:1.55;
}
.hero-metrics{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  margin-top:4px;
}
.metric-card{
  padding:14px;
  border-radius:20px;
  border:1px solid rgba(255,255,255,.12);
  background:linear-gradient(180deg, rgba(255,255,255,.07), rgba(255,255,255,.03));
  backdrop-filter:blur(18px);
}
.metric-label{
  display:block;
  color:var(--muted);
  font-size:11px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
.metric-value{
  display:block;
  margin-top:8px;
  font-size:18px;
  font-weight:800;
  line-height:1.1;
}
.metric-value.hero-value{ font-size:20px; }
.hero-actions{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
}
.action-btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  min-height:46px;
  padding:12px 16px;
  border-radius:16px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.06);
  box-shadow:var(--shadow-md);
  font-size:13px;
  font-weight:800;
  letter-spacing:.06em;
  text-transform:uppercase;
  transition:transform .18s ease, border-color .18s ease, background .18s ease;
}
.action-btn:active{ transform:scale(.98); }
.action-btn--primary{
  border-color:rgba(255,111,148,.44);
  background:linear-gradient(180deg, rgba(255,111,148,.28), rgba(255,111,148,.16));
}
.action-btn--cool{
  border-color:rgba(122,213,255,.36);
  background:linear-gradient(180deg, rgba(122,213,255,.24), rgba(122,213,255,.14));
}
.panel{
  margin-top:16px;
  padding:16px;
  border-radius:var(--radius-lg);
  border:1px solid var(--border);
  background:linear-gradient(180deg, rgba(12,18,36,.86), rgba(9,14,29,.92));
  box-shadow:var(--shadow-md);
}
.panel.panel--soft{
  background:linear-gradient(180deg, rgba(12,18,36,.68), rgba(9,14,29,.80));
}
.section-head{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:12px;
  flex-wrap:wrap;
}
.section-kicker{
  color:var(--accent-cool);
  font-size:11px;
  font-weight:800;
  letter-spacing:.18em;
  text-transform:uppercase;
}
.section-title{
  margin:4px 0 0;
  font-size:24px;
  line-height:1.02;
  letter-spacing:-.03em;
}
.section-meta{
  color:var(--muted);
  font-size:13px;
  line-height:1.5;
}
.searchbar{
  display:flex;
  align-items:center;
  gap:12px;
  min-height:58px;
  padding:0 16px;
  border-radius:18px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.05);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03);
}
.searchbar input,
.searchbar select{
  width:100%;
  min-height:52px;
  padding:0;
  border:0;
  outline:none;
  background:transparent;
}
.searchbar input::placeholder{
  color:rgba(230,236,246,.42);
  font-weight:700;
}
.input-icon{
  flex:0 0 auto;
  color:var(--muted);
  font-weight:800;
  letter-spacing:.10em;
  text-transform:uppercase;
  font-size:12px;
}
.scroll-x{
  overflow-x:auto;
  overflow-y:hidden;
  -ms-overflow-style:none;
  scrollbar-width:none;
}
.scroll-x::-webkit-scrollbar{ display:none; }
.chip-row{
  display:flex;
  gap:10px;
  min-width:max-content;
  padding-bottom:2px;
}
.chip{
  display:inline-flex;
  align-items:center;
  gap:8px;
  min-height:42px;
  padding:10px 14px;
  border-radius:999px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.05);
  font-size:12px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  white-space:nowrap;
}
.chip.active,
.chip:hover{
  border-color:rgba(122,213,255,.34);
  background:linear-gradient(180deg, rgba(122,213,255,.18), rgba(122,213,255,.10));
}
.chip--accent{
  border-color:rgba(255,111,148,.34);
  background:linear-gradient(180deg, rgba(255,111,148,.18), rgba(255,111,148,.10));
}
.stack{ display:grid; gap:14px; }
.media-grid{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:14px;
}
.media-card{
  position:relative;
  overflow:hidden;
  border-radius:22px;
  border:1px solid var(--border);
  background:linear-gradient(180deg, rgba(14,21,40,.94), rgba(10,15,28,.96));
  box-shadow:var(--shadow-md);
  transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.media-card:active{ transform:scale(.985); }
.media-card:hover{
  transform:translateY(-2px);
  border-color:var(--border-strong);
  box-shadow:0 26px 52px rgba(0,0,0,.40);
}
.media-cover{
  position:relative;
  width:100%;
  aspect-ratio:0.76;
  background:
    radial-gradient(circle at 20% 10%, rgba(122,213,255,.26), transparent 38%),
    linear-gradient(180deg, rgba(18,27,50,.96), rgba(12,18,34,.96));
}
.media-cover img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}
.media-cover::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(2,5,12,.00) 42%, rgba(2,5,12,.66) 100%);
}
.media-badge{
  position:absolute;
  top:12px;
  left:12px;
  z-index:1;
  display:inline-flex;
  align-items:center;
  gap:6px;
  min-height:32px;
  padding:8px 10px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.14);
  background:rgba(8,14,28,.48);
  backdrop-filter:blur(16px);
  font-size:10px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
"""
        r"""
.media-badge--accent{
  border-color:rgba(255,111,148,.28);
  background:rgba(255,111,148,.16);
}
.media-badge--cool{
  border-color:rgba(122,213,255,.28);
  background:rgba(122,213,255,.14);
}
.media-count{
  position:absolute;
  right:12px;
  bottom:12px;
  z-index:1;
  display:inline-flex;
  align-items:center;
  min-height:34px;
  padding:9px 11px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.16);
  background:rgba(8,14,28,.48);
  backdrop-filter:blur(18px);
  font-size:11px;
  font-weight:800;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.media-body{ padding:14px; }
.card-title{
  margin:0;
  font-size:16px;
  line-height:1.12;
  letter-spacing:-.03em;
}
.pill-row{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:10px;
}
.soft-pill{
  display:inline-flex;
  align-items:center;
  gap:6px;
  min-height:30px;
  padding:7px 10px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(255,255,255,.045);
  color:var(--muted-strong);
  font-size:11px;
  font-weight:800;
  letter-spacing:.10em;
  text-transform:uppercase;
}
.soft-pill--accent{
  border-color:rgba(255,111,148,.26);
  background:rgba(255,111,148,.10);
}
.soft-pill--cool{
  border-color:rgba(122,213,255,.28);
  background:rgba(122,213,255,.10);
}
.grid-tiles{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:12px;
}
.hub-tile,
.buy-tile,
.setting-row,
.stat-tile{
  border-radius:22px;
  border:1px solid var(--border);
  background:linear-gradient(180deg, rgba(15,22,42,.92), rgba(10,16,30,.96));
  box-shadow:var(--shadow-md);
}
.hub-tile{
  position:relative;
  overflow:hidden;
  min-height:200px;
}
.hub-tile-media{ position:absolute; inset:0; }
.hub-tile-media img{ width:100%; height:100%; object-fit:cover; display:block; }
.hub-tile-overlay{
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(8,12,23,.18), rgba(8,12,23,.82));
}
.hub-tile-content{
  position:relative;
  z-index:1;
  display:flex;
  flex-direction:column;
  justify-content:flex-end;
  gap:10px;
  min-height:200px;
  padding:16px;
}
.hub-title{
  margin:0;
  font-size:22px;
  line-height:1.02;
  letter-spacing:-.04em;
}
.hub-copy{
  margin:0;
  color:var(--muted-strong);
  font-size:13px;
  line-height:1.55;
}
.stat-grid{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:12px;
}
.stat-tile{ padding:16px; }
.stat-label{
  color:var(--muted);
  font-size:11px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
.stat-value{
  margin-top:8px;
  font-size:24px;
  font-weight:800;
  line-height:1.05;
}
.profile-card{
  display:flex;
  align-items:center;
  gap:14px;
  padding:18px;
  margin-top:-52px;
  position:relative;
  z-index:2;
}
.profile-avatar{
  width:88px;
  height:88px;
  border-radius:28px;
  overflow:hidden;
  flex:0 0 auto;
  display:flex;
  align-items:center;
  justify-content:center;
  border:1px solid rgba(255,255,255,.10);
  background:linear-gradient(180deg, rgba(255,111,148,.22), rgba(122,213,255,.18));
  box-shadow:var(--shadow-md);
  font-size:28px;
  font-weight:800;
  letter-spacing:-.04em;
}
.profile-avatar img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}
.profile-copy{
  min-width:0;
  flex:1;
}
.profile-name{
  margin:0;
  font-size:28px;
  line-height:1.02;
  letter-spacing:-.04em;
}
.profile-sub{
  margin:6px 0 0;
  color:var(--muted);
  font-size:13px;
  line-height:1.45;
}
.setting-group{
  display:grid;
  gap:12px;
}
.setting-row{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:16px;
}
"""
        r"""
.setting-copy{
  min-width:0;
  flex:1;
}
.setting-title{
  margin:0;
  font-size:16px;
  font-weight:800;
  letter-spacing:-.02em;
}
.setting-sub{
  margin:6px 0 0;
  color:var(--muted);
  font-size:13px;
  line-height:1.5;
}
.form-stack,
.inline-controls{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
}
.field{
  display:flex;
  align-items:center;
  min-width:0;
  min-height:50px;
  padding:0 14px;
  border-radius:16px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.05);
}
.field input,
.field select{
  width:100%;
  min-height:48px;
  border:0;
  outline:none;
  background:transparent;
}
.control-btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:48px;
  padding:12px 16px;
  border-radius:16px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.06);
  font-size:12px;
  font-weight:800;
  letter-spacing:.12em;
  text-transform:uppercase;
}
.control-btn--accent{
  border-color:rgba(122,213,255,.34);
  background:linear-gradient(180deg, rgba(122,213,255,.20), rgba(122,213,255,.10));
}
.control-btn--danger{
  border-color:rgba(255,106,127,.32);
  background:linear-gradient(180deg, rgba(255,106,127,.20), rgba(255,106,127,.10));
}
.segmented{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
}
.segmented-btn{
  min-height:52px;
  padding:12px 14px;
  border-radius:18px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.05);
  font-size:13px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
}
.segmented-btn.active{
  border-color:rgba(255,111,148,.34);
  background:linear-gradient(180deg, rgba(255,111,148,.20), rgba(255,111,148,.10));
}
.buy-grid{
  display:grid;
  grid-template-columns:1fr;
  gap:12px;
}
.buy-tile{ padding:18px; }
.buy-title{
  margin:0;
  font-size:20px;
  font-weight:800;
  line-height:1.1;
  letter-spacing:-.03em;
}
.buy-copy{
  margin:10px 0 0;
  color:var(--muted);
  font-size:13px;
  line-height:1.55;
}
.buy-price{
  margin-top:14px;
  color:var(--muted-strong);
  font-size:11px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
.floating-note{
  margin-top:16px;
  min-height:52px;
  padding:14px 16px;
  border-radius:18px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.05);
  color:var(--muted-strong);
  font-size:13px;
  font-weight:700;
  line-height:1.45;
}
.floating-note[data-tone="error"]{
  border-color:rgba(255,106,127,.28);
  background:rgba(255,106,127,.10);
}
.floating-note[data-tone="success"]{
  border-color:rgba(81,222,181,.28);
  background:rgba(81,222,181,.10);
}
.empty-state{
  padding:22px 18px;
  border-radius:22px;
  border:1px dashed rgba(255,255,255,.14);
  background:rgba(255,255,255,.03);
  color:var(--muted);
  text-align:center;
}
.empty-state strong{
  display:block;
  margin-bottom:6px;
  color:var(--text);
  font-size:16px;
  letter-spacing:-.02em;
}
.loadmore-btn{
  width:100%;
  min-height:52px;
  border-radius:18px;
  border:1px solid var(--border);
  background:rgba(255,255,255,.05);
  font-size:12px;
  font-weight:800;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.sheet-backdrop{
  position:fixed;
  inset:0;
  display:none;
  align-items:flex-end;
  justify-content:center;
  padding:16px;
  background:rgba(3,6,14,.68);
  backdrop-filter:blur(14px);
  z-index:9999;
}
.sheet{
  width:min(760px, 100%);
  max-height:min(82vh, 760px);
  display:flex;
  flex-direction:column;
  overflow:hidden;
  border-radius:28px;
  border:1px solid var(--border);
  background:linear-gradient(180deg, rgba(11,17,34,.96), rgba(8,13,25,.98));
  box-shadow:0 34px 70px rgba(0,0,0,.56);
}
.sheet-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:16px;
  border-bottom:1px solid rgba(255,255,255,.08);
}
.sheet-title{
  margin:0;
  font-size:20px;
  letter-spacing:-.03em;
}
.sheet-body{
  padding:16px;
  overflow:auto;
}
.list-stack{ display:grid; gap:10px; }
.footer-note{
  margin-top:18px;
  color:rgba(255,255,255,.42);
  text-align:center;
  font-size:12px;
  font-weight:700;
  letter-spacing:.10em;
  text-transform:uppercase;
}
.skeleton-card{
  overflow:hidden;
  border-radius:22px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(255,255,255,.03);
}
.skeleton-cover{
  aspect-ratio:0.76;
  background:linear-gradient(90deg, rgba(255,255,255,.04) 20%, rgba(255,255,255,.11) 50%, rgba(255,255,255,.04) 80%);
  background-size:200% 100%;
  animation:shimmer 1.2s linear infinite;
}
"""
        r"""
.skeleton-body{
  padding:14px;
  display:grid;
  gap:10px;
}
.skeleton-line{
  height:11px;
  border-radius:999px;
  background:linear-gradient(90deg, rgba(255,255,255,.04) 20%, rgba(255,255,255,.11) 50%, rgba(255,255,255,.04) 80%);
  background-size:200% 100%;
  animation:shimmer 1.2s linear infinite;
}
.pulse-dot{
  display:inline-block;
  width:8px;
  height:8px;
  border-radius:50%;
  background:var(--ok);
  box-shadow:0 0 0 0 rgba(81,222,181,.44);
  animation:pulse 1.8s ease infinite;
}
@keyframes shimmer{
  0%{ background-position:200% 0; }
  100%{ background-position:-200% 0; }
}
@keyframes pulse{
  0%{ box-shadow:0 0 0 0 rgba(81,222,181,.44); }
  70%{ box-shadow:0 0 0 10px rgba(81,222,181,0); }
  100%{ box-shadow:0 0 0 0 rgba(81,222,181,0); }
}
@media (min-width:740px){
  .app-shell{
    padding-left:20px;
    padding-right:20px;
  }
  .hero-content{ padding:26px; }
  .hero-metrics{ grid-template-columns:repeat(4, minmax(0, 1fr)); }
  .grid-tiles{ grid-template-columns:repeat(3, minmax(0, 1fr)); }
  .media-grid{ grid-template-columns:repeat(3, minmax(0, 1fr)); }
  .buy-grid{ grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .setting-row{ padding:18px; }
}
@media (prefers-reduced-motion: reduce){
  *,
  *::before,
  *::after{
    animation:none !important;
    transition:none !important;
    scroll-behavior:auto !important;
  }
}
"""
    )


def _page_template(
    title: str,
    body: str,
    *,
    extra_css: str = "",
    extra_js: str = "",
    include_tg: bool = False,
) -> str:
    tg_script = '<script src="https://telegram.org/js/telegram-web-app.js"></script>' if include_tg else ""
    return f"""<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{_h(title)}</title>
  {_font_links()}
  {tg_script}
  <style>{_base_css()}{extra_css}</style>
</head>
<body>
  <main class="app-shell">
    {body}
  </main>
  <script>{_shared_js()}{extra_js}</script>
</body>
</html>"""


def _shared_js() -> str:
    return r"""
function esc(value){
  return String(value || "").replace(/[&<>"']/g, function(ch){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch];
  });
}

function debounce(fn, wait){
  let timer = null;
  return function(){
    const args = arguments;
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(function(){ fn.apply(null, args); }, wait);
  };
}

function tgOpenLink(url){
  try{
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openTelegramLink){
      Telegram.WebApp.openTelegramLink(url);
      return;
    }
  }catch(err){}
  window.open(url, "_blank", "noopener,noreferrer");
}

function setSkeleton(container, count){
  const root = typeof container === "string" ? document.getElementById(container) : container;
  if (!root) return;
  let html = "";
  for (let i = 0; i < count; i += 1){
    html += '<div class="skeleton-card"><div class="skeleton-cover"></div><div class="skeleton-body"><div class="skeleton-line" style="width:78%;"></div><div class="skeleton-line" style="width:54%;"></div></div></div>';
  }
  root.innerHTML = html;
}

function setImageFallback(img, label){
  try{
    const parent = img && img.parentElement;
    if (!parent) return;
    if (parent.querySelector(".media-fallback")) return;
    const div = document.createElement("div");
    div.className = "media-fallback";
    div.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:16px;text-align:center;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:rgba(255,255,255,.72);background:linear-gradient(180deg, rgba(18,28,52,.92), rgba(12,18,34,.96));";
    div.textContent = label || "NO IMAGE";
    parent.appendChild(div);
    img.remove();
  }catch(err){}
}

function humanClock(){
  try{
    return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }catch(err){
    return "--:--";
  }
}

function createLiveRefresh(task, intervalMs){
  let working = false;
  async function run(opts){
    const options = opts || {};
    if (working) return;
    if (document.hidden && !options.force) return;
    working = true;
    try{
      await task(options);
    }catch(err){
      console.error(err);
    }finally{
      working = false;
    }
  }
  const timer = window.setInterval(function(){ run({ silent: true }); }, intervalMs);
  document.addEventListener("visibilitychange", function(){
    if (!document.hidden) run({ force: true, silent: true });
  });
  window.addEventListener("focus", function(){ run({ force: true, silent: true }); });
  window.addEventListener("pageshow", function(){ run({ force: true, silent: true }); });
  return {
    run: run,
    stop: function(){ window.clearInterval(timer); }
  };
}
"""


def build_home_page(
    *,
    top_banner_url: str,
    catalog_banner_url: str,
    manga_banner_url: str,
    cards_banner_url: str,
    shop_banner_url: str,
) -> str:
    body = f"""
<section class="hero-card">
  <div class="hero-media"><img src="{_h(top_banner_url)}" alt="Source Baltigo"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Source Baltigo MiniApp</div>
    <h1 class="hero-title">Anime, manga e cards com cara de produto premium.</h1>
    <p class="hero-subtitle">Um hub mobile-first para descoberta, colecao e navegacao rapida dentro do ecossistema Baltigo no Telegram.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Experiencia</span><span class="metric-value hero-value">Mobile first</span></div>
      <div class="metric-card"><span class="metric-label">Visual</span><span class="metric-value hero-value">Cinematografico</span></div>
      <div class="metric-card"><span class="metric-label">Fluxo</span><span class="metric-value hero-value">Rapido e vivo</span></div>
      <div class="metric-card"><span class="metric-label">MiniApp</span><span class="metric-value hero-value">Telegram native</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div>
      <div class="section-kicker">Entrada principal</div>
      <h2 class="section-title">Explore o ecossistema</h2>
    </div>
    <div class="section-meta">Tudo organizado para abrir rapido, parecer produto de verdade e dar contexto imediato logo nos primeiros segundos.</div>
  </div>
  <div class="grid-tiles" style="margin-top:14px;">
    <a class="hub-tile" href="/catalogo">
      <div class="hub-tile-media"><img src="{_h(catalog_banner_url)}" alt="Catalogo"></div>
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill soft-pill--cool">Anime catalog</div>
        <h3 class="hub-title">Catalogo</h3>
        <p class="hub-copy">Biblioteca com busca, navegacao por letra e cards de conteudo com cara de streaming.</p>
      </div>
    </a>
    <a class="hub-tile" href="/mangas">
      <div class="hub-tile-media"><img src="{_h(manga_banner_url)}" alt="Mangas"></div>
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill soft-pill--accent">Manga library</div>
        <h3 class="hub-title">Mangas</h3>
        <p class="hub-copy">Uma vitrine mais limpa, mais legivel e mais marcante para descobrir colecoes do canal.</p>
      </div>
    </a>
    <a class="hub-tile" href="/cards">
      <div class="hub-tile-media"><img src="{_h(cards_banner_url)}" alt="Cards"></div>
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill">Cards live</div>
        <h3 class="hub-title">Cards</h3>
        <p class="hub-copy">Colecao de personagens com atualizacao silenciosa para refletir fotos trocadas e exclusoes.</p>
      </div>
    </a>
    <a class="hub-tile" href="/shop">
      <div class="hub-tile-media"><img src="{_h(shop_banner_url)}" alt="Shop"></div>
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill soft-pill--accent">Economy</div>
        <h3 class="hub-title">Shop</h3>
        <p class="hub-copy">Venda personagens, compre recursos e acompanhe seu saldo em uma interface mais forte e consistente.</p>
      </div>
    </a>
    <a class="hub-tile" href="/pedido">
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill soft-pill--cool">Requests</div>
        <h3 class="hub-title">Pedidos</h3>
        <p class="hub-copy">Fluxo para solicitar novos titulos com a mesma linguagem visual do resto do produto.</p>
      </div>
    </a>
    <a class="hub-tile" href="/dado">
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill">Dice system</div>
        <h3 class="hub-title">Dado</h3>
        <p class="hub-copy">Area do sistema com contraste melhor, mais profundidade visual e toque mais premium.</p>
      </div>
    </a>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Direcao visual</div>
      <h2 class="section-title">Dark theme mais cinematografico</h2>
    </div>
    <div class="section-meta">Paleta mais rica, hierarquia tipografica mais clara, superficies com profundidade e movimentos discretos para aumentar a percepcao de qualidade.</div>
  </div>
  <div class="chip-row scroll-x" style="margin-top:14px;">
    <div class="chip chip--accent">Contraste premium</div>
    <div class="chip">Animacao leve</div>
    <div class="chip">Touch friendly</div>
    <div class="chip">Cards mais fortes</div>
    <div class="chip">Busca melhor</div>
    <div class="chip">Layout mais respirado</div>
    <div class="chip">Cara de produto real</div>
  </div>
</section>

<div class="footer-note">Source Baltigo . Premium web experience</div>
"""
    return _page_template("Source Baltigo", body)


def build_media_catalog_page(
    *,
    page_title: str,
    hero_tag: str,
    hero_title: str,
    hero_copy: str,
    banner_url: str,
    api_letters: str,
    api_catalog: str,
    search_placeholder: str,
    footer_label: str,
    default_badge: str,
) -> str:
    config = {
        "apiLetters": api_letters,
        "apiCatalog": api_catalog,
        "searchPlaceholder": search_placeholder,
        "footerLabel": footer_label,
        "defaultBadge": default_badge,
    }
    body = f"""
<section class="hero-card">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="{_h(hero_title)}"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">{_h(hero_tag)}</div>
    <h1 class="hero-title">{_h(hero_title)}</h1>
    <p class="hero-subtitle">{_h(hero_copy)}</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Total</span><span class="metric-value" id="heroTotal">...</span></div>
      <div class="metric-card"><span class="metric-label">Busca</span><span class="metric-value">Instantanea</span></div>
      <div class="metric-card"><span class="metric-label">Filtro</span><span class="metric-value">Por letra</span></div>
      <div class="metric-card"><span class="metric-label">Estilo</span><span class="metric-value">Streaming feel</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="stack">
    <div class="section-head">
      <div>
        <div class="section-kicker">Descoberta</div>
        <h2 class="section-title">Busque e explore</h2>
      </div>
      <div class="section-meta" id="metaTxt">Carregando catalogo...</div>
    </div>
    <label class="searchbar">
      <span class="input-icon">Busca</span>
      <input id="searchInput" type="text" placeholder="{_h(search_placeholder)}">
    </label>
    <div class="scroll-x">
      <div class="chip-row" id="lettersRail"></div>
    </div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Resultado</div>
      <h2 class="section-title">Selecao disponivel</h2>
    </div>
    <div class="section-meta" id="resultTxt">Preparando vitrine...</div>
  </div>
  <div class="media-grid" id="cards" style="margin-top:14px;"></div>
  <div id="emptyBox" class="empty-state" style="display:none; margin-top:14px;">
    <strong>Nada encontrado</strong>
    Ajuste a busca ou troque a letra para ver mais opcoes.
  </div>
  <button id="btnMore" class="loadmore-btn" style="margin-top:14px;">Carregar mais</button>
</section>

<div class="footer-note">{_h(footer_label)}</div>
"""
    js = f"""
const CATALOG_CONFIG = {_j(config)};
const catalogState = {{ letter: "ALL", q: "", limit: 60, offset: 0, total: 0, loading: false, letters: null }};

function catalogBadge(item){{
  const raw = String(item.badge || item.format || CATALOG_CONFIG.defaultBadge || "").trim();
  return raw ? raw.toUpperCase() : "MEDIA";
}}

function catalogMetaParts(item){{
  const parts = [];
  if (item.year) parts.push(String(item.year));
  if (item.score) parts.push("Score " + String(item.score));
  if (item.format) parts.push(String(item.format).toUpperCase().replace(/_/g, " "));
  return parts;
}}

function makeLetterChip(key, count){{
  const button = document.createElement("button");
  button.type = "button";
  button.className = "chip" + (catalogState.letter === key ? " active" : "");
  const label = key === "ALL" ? "Todos" : key;
  button.innerHTML = '<span>' + esc(label) + '</span><span class="soft-pill">' + esc(count) + '</span>';
  button.onclick = function(){{
    if (catalogState.letter === key) return;
    catalogState.letter = key;
    loadCatalog({{ reset: true }});
    renderLetters();
  }};
  return button;
}}

async function renderLetters(){{
  const root = document.getElementById("lettersRail");
  if (!catalogState.letters){{
    const res = await fetch(CATALOG_CONFIG.apiLetters + "?_ts=" + Date.now());
    catalogState.letters = await res.json();
  }}
  const data = catalogState.letters || {{}};
  document.getElementById("heroTotal").textContent = String(data.total || 0);
  root.innerHTML = "";
  root.appendChild(makeLetterChip("ALL", data.all_count || data.total || 0));
  root.appendChild(makeLetterChip("#", (data.counts && data.counts["#"]) || 0));
  for (let code = 65; code <= 90; code += 1){{
    const key = String.fromCharCode(code);
    root.appendChild(makeLetterChip(key, (data.counts && data.counts[key]) || 0));
  }}
}}

function buildCatalogCard(item){{
  const cover = item.cover_url ? '<img src="' + esc(item.cover_url) + '" alt="' + esc(item.titulo) + '" loading="lazy" onerror="setImageFallback(this, \\'No image\\')">' : '';
  const pills = catalogMetaParts(item).map(function(part){{ return '<span class="soft-pill">' + esc(part) + '</span>'; }}).join("");
  return ''
    + '<article class="media-card" onclick="tgOpenLink(' + JSON.stringify(String(item.link_post || "")) + ')">'
    + '<div class="media-cover">' + cover + '<div class="media-badge media-badge--cool">' + esc(catalogBadge(item)) + '</div></div>'
    + '<div class="media-body"><h3 class="card-title">' + esc(item.titulo) + '</h3><div class="pill-row"><span class="soft-pill soft-pill--accent">Canal</span>' + pills + '</div></div>'
    + '</article>';
}}

function renderCatalog(items){{
  const root = document.getElementById("cards");
  const empty = document.getElementById("emptyBox");
  document.getElementById("metaTxt").textContent = "Total carregado: " + String(catalogState.total || 0) + " . Atualizado " + humanClock();
  document.getElementById("resultTxt").textContent = "Mostrando " + String(items.length) + " de " + String(catalogState.total || 0);
  if (!items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = items.map(buildCatalogCard).join("");
}}

async function loadCatalog(options){{
  const opts = options || {{}};
  if (catalogState.loading) return;
  catalogState.loading = true;
  const root = document.getElementById("cards");
  const btn = document.getElementById("btnMore");
  if (opts.reset) {{
    catalogState.offset = 0;
    setSkeleton(root, 6);
  }}
  btn.disabled = true;
  btn.textContent = "Carregando";
  const params = new URLSearchParams();
  params.set("letter", catalogState.letter);
  params.set("q", catalogState.q);
  params.set("limit", String(catalogState.limit));
  params.set("offset", String(catalogState.offset));
  params.set("_ts", String(Date.now()));
  const res = await fetch(CATALOG_CONFIG.apiCatalog + "?" + params.toString());
  const data = await res.json();
  const items = Array.isArray(data.items) ? data.items : [];
  catalogState.total = Number(data.total || 0);
  if (opts.reset) {{
    renderCatalog(items);
  }} else {{
    root.innerHTML += items.map(buildCatalogCard).join("");
  }}
  catalogState.offset += items.length;
  if (catalogState.offset >= catalogState.total) {{
    btn.disabled = true;
    btn.textContent = "Fim da lista";
  }} else {{
    btn.disabled = false;
    btn.textContent = "Carregar mais";
  }}
  catalogState.loading = false;
}}

document.getElementById("searchInput").addEventListener("input", debounce(function(event){{
  catalogState.q = String(event.target.value || "").trim();
  loadCatalog({{ reset: true }});
}}, 220));

document.getElementById("btnMore").addEventListener("click", function(){{
  loadCatalog({{ reset: false }});
}});

(async function(){{
  await renderLetters();
  await loadCatalog({{ reset: true }});
}})();
"""
    return _page_template(page_title, body, extra_js=js)


def build_cards_home_page(*, top_banner_url: str) -> str:
    body = f"""
<section class="hero-card">
  <div class="hero-media"><img src="{_h(top_banner_url)}" alt="Cards"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Cards collection</div>
    <h1 class="hero-title">Personagens, subcategorias e busca viva.</h1>
    <p class="hero-subtitle">A home de cards agora fica mais forte visualmente e se atualiza sozinha para refletir novas fotos e exclusoes sem depender de reload manual.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Obras</span><span class="metric-value" id="animeCountHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Subcategorias</span><span class="metric-value" id="subCountHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Status</span><span class="metric-value"><span class="pulse-dot"></span> Live sync</span></div>
      <div class="metric-card"><span class="metric-label">Refresh</span><span class="metric-value">5s visivel</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="stack">
    <div class="section-head">
      <div>
        <div class="section-kicker">Descoberta</div>
        <h2 class="section-title">Encontre rapido</h2>
      </div>
      <div class="section-meta" id="cardsMeta">Carregando home de cards...</div>
    </div>
    <label class="searchbar">
      <span class="input-icon">Anime</span>
      <input id="animeSearchInput" type="text" placeholder="Buscar obra da colecao...">
    </label>
    <label class="searchbar">
      <span class="input-icon">Char</span>
      <input id="charSearchInput" type="text" placeholder="Buscar personagem e apertar Enter...">
    </label>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Subcategorias</div>
      <h2 class="section-title">Atalhos inteligentes</h2>
    </div>
    <div class="section-meta">Os chips abaixo tambem entram no refresh automatico.</div>
  </div>
  <div class="scroll-x" style="margin-top:14px;">
    <div class="chip-row" id="subcategoriesRail"></div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Obras</div>
      <h2 class="section-title">Vitrine principal</h2>
    </div>
    <div class="section-meta" id="animeResultMeta">Preparando grid...</div>
  </div>
  <div class="media-grid" id="animeGrid" style="margin-top:14px;"></div>
  <div id="animeEmpty" class="empty-state" style="display:none; margin-top:14px;">
    <strong>Nenhuma obra encontrada</strong>
    Tente outro termo ou explore as subcategorias.
  </div>
</section>

<div class="footer-note">Source Baltigo . Cards hub</div>
"""
    js = f"""
const cardsHomeState = {{ allAnimes: [], filteredAnimes: [], subcategories: [] }};
function cardsHomeCover(item){{
  if (item.cover_image) return item.cover_image;
  if (item.banner_image) return item.banner_image;
  return {_j(top_banner_url)};
}}
function cardsHomeApplyFilter(){{
  const q = String(document.getElementById("animeSearchInput").value || "").trim().toLowerCase();
  cardsHomeState.filteredAnimes = !q ? cardsHomeState.allAnimes.slice() : cardsHomeState.allAnimes.filter(function(item){{
    return String(item.anime || "").toLowerCase().includes(q);
  }});
  renderCardsHome();
}}
function renderCardsHome(){{
  const root = document.getElementById("animeGrid");
  const empty = document.getElementById("animeEmpty");
  document.getElementById("animeCountHero").textContent = String(cardsHomeState.allAnimes.length);
  document.getElementById("subCountHero").textContent = String(cardsHomeState.subcategories.length);
  document.getElementById("cardsMeta").textContent = "Atualizado " + humanClock() + " . Obras " + String(cardsHomeState.allAnimes.length) + " . Subcategorias " + String(cardsHomeState.subcategories.length);
  document.getElementById("animeResultMeta").textContent = "Mostrando " + String(cardsHomeState.filteredAnimes.length) + " obras";
  if (!cardsHomeState.filteredAnimes.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = cardsHomeState.filteredAnimes.map(function(item){{
    return ''
      + '<article class="media-card" onclick="window.location.href=\\'/cards/anime?anime_id=' + encodeURIComponent(item.anime_id) + '\\'">'
      + '<div class="media-cover"><img src="' + esc(cardsHomeCover(item)) + '" alt="' + esc(item.anime) + '" loading="lazy" onerror="setImageFallback(this, \\'No image\\')"><div class="media-badge media-badge--cool">Cards</div><div class="media-count">' + esc((item.characters_count || 0) + ' chars') + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.anime) + '</h3><div class="pill-row"><span class="soft-pill">ID ' + esc(item.anime_id) + '</span><span class="soft-pill soft-pill--accent">Obra</span></div></div>'
      + '</article>';
  }}).join("");
}}
function renderSubcategories(){{
  const root = document.getElementById("subcategoriesRail");
  root.innerHTML = cardsHomeState.subcategories.length ? cardsHomeState.subcategories.map(function(item){{
    const href = "/cards/subcategory?name=" + encodeURIComponent(String(item.name || ""));
    return '<button type="button" class="chip chip--accent" onclick="window.location.href=' + JSON.stringify(href) + '">' + esc(String(item.name || "")) + ' <span class="soft-pill">' + esc(item.count || 0) + '</span></button>';
  }}).join("") : '<div class="chip">Nenhuma subcategoria</div>';
}}
async function refreshCardsHome(options){{
  const opts = options || {{}};
  if (!opts.silent && !cardsHomeState.allAnimes.length) setSkeleton("animeGrid", 6);
  const results = await Promise.all([fetch("/api/cards/animes?limit=5000&_ts=" + Date.now()), fetch("/api/cards/subcategories?_ts=" + Date.now())]);
  const animeData = await results[0].json();
  const subData = await results[1].json();
  cardsHomeState.allAnimes = Array.isArray(animeData.items) ? animeData.items.slice().sort(function(a, b){{ return String(a.anime || "").localeCompare(String(b.anime || "")); }}) : [];
  cardsHomeState.subcategories = Array.isArray(subData.items) ? subData.items : [];
  renderSubcategories();
  cardsHomeApplyFilter();
}}
document.getElementById("animeSearchInput").addEventListener("input", debounce(cardsHomeApplyFilter, 180));
document.getElementById("charSearchInput").addEventListener("keydown", function(event){{
  if (event.key !== "Enter") return;
  const value = String(event.target.value || "").trim();
  if (!value) return;
  window.location.href = "/cards/search?q=" + encodeURIComponent(value);
}});
(async function(){{
  await refreshCardsHome({{ silent: false }});
  createLiveRefresh(refreshCardsHome, 5000);
}})();
"""
    return _page_template("Cards - Source Baltigo", body, extra_js=js)


def build_cards_anime_page(*, anime_id: int, top_banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img id="animeHeroImage" src="{_h(top_banner_url)}" alt="Anime"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="hero-actions">
      <a class="action-btn" href="/cards">Voltar</a>
      <div class="action-btn action-btn--cool">Anime ID {_h(anime_id)}</div>
    </div>
    <h1 class="hero-title" id="animeHeroTitle">Carregando...</h1>
    <p class="hero-subtitle" id="animeHeroSubtitle">Atualizando personagens...</p>
  </div>
</section>

<section class="panel">
  <div class="stack">
    <div class="section-head">
      <div>
        <div class="section-kicker">Personagens</div>
        <h2 class="section-title">Busca local com sync automatico</h2>
      </div>
      <div class="section-meta" id="animeMeta">Buscando dados...</div>
    </div>
    <label class="searchbar">
      <span class="input-icon">Busca</span>
      <input id="animeCharSearchInput" type="text" placeholder="Buscar personagem neste anime...">
    </label>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Grid</div>
      <h2 class="section-title">Cards do anime</h2>
    </div>
    <div class="section-meta" id="animeCountMeta">Carregando...</div>
  </div>
  <div class="media-grid" id="animeCharGrid" style="margin-top:14px;"></div>
  <div id="animeCharEmpty" class="empty-state" style="display:none; margin-top:14px;">
    <strong>Nenhum personagem encontrado</strong>
    Isso pode acontecer se o card foi removido ou se o filtro nao encontrou resultado.
  </div>
</section>

<div class="footer-note">Source Baltigo . Anime cards</div>
"""
    js = f"""
const animeCardsState = {{ animeId: {int(anime_id)}, anime: null, items: [], filteredItems: [] }};
function animeHeroImage(meta){{
  if (meta && meta.banner_image) return meta.banner_image;
  if (meta && meta.cover_image) return meta.cover_image;
  return {_j(top_banner_url)};
}}
function animeCardImage(item){{ return item && item.image ? item.image : {_j(top_banner_url)}; }}
function applyAnimeCardFilter(){{
  const q = String(document.getElementById("animeCharSearchInput").value || "").trim().toLowerCase();
  animeCardsState.filteredItems = !q ? animeCardsState.items.slice() : animeCardsState.items.filter(function(item){{ return String(item.name || "").toLowerCase().includes(q); }});
  renderAnimeCards();
}}
function renderAnimeCards(){{
  const root = document.getElementById("animeCharGrid");
  const empty = document.getElementById("animeCharEmpty");
  const anime = animeCardsState.anime;
  if (anime){{
    document.getElementById("animeHeroTitle").textContent = anime.anime || "Anime";
    document.getElementById("animeHeroSubtitle").textContent = "Colecao sincronizada em tempo real";
    document.getElementById("animeHeroImage").src = animeHeroImage(anime);
    document.getElementById("animeMeta").textContent = "Atualizado " + humanClock() + " . ID " + String(anime.anime_id) + " . " + String(anime.characters_count || animeCardsState.items.length) + " personagens";
  }} else {{
    document.getElementById("animeHeroTitle").textContent = "Anime nao encontrado";
    document.getElementById("animeHeroSubtitle").textContent = "Verifique se os cards ainda existem";
    document.getElementById("animeHeroImage").src = {_j(top_banner_url)};
    document.getElementById("animeMeta").textContent = "Sem dados para este anime";
  }}
  document.getElementById("animeCountMeta").textContent = "Mostrando " + String(animeCardsState.filteredItems.length) + " personagens";
  if (!animeCardsState.filteredItems.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = animeCardsState.filteredItems.map(function(item){{
    const badge = item.subcategory ? String(item.subcategory) : "Card";
    return ''
      + '<article class="media-card"><div class="media-cover"><img src="' + esc(animeCardImage(item)) + '" alt="' + esc(item.name) + '" loading="lazy" onerror="setImageFallback(this, \\'No image\\')"><div class="media-badge">' + esc(badge) + '</div><div class="media-count">ID ' + esc(item.id) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.name) + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(item.anime || "") + '</span><span class="soft-pill">Card</span></div></div></article>';
  }}).join("");
}}
async function refreshAnimeCards(options){{
  const opts = options || {{}};
  if (!opts.silent && !animeCardsState.items.length) setSkeleton("animeCharGrid", 6);
  const res = await fetch("/api/cards/characters?anime_id=" + encodeURIComponent(animeCardsState.animeId) + "&limit=5000&_ts=" + Date.now());
  const data = await res.json();
  animeCardsState.anime = data.anime || null;
  animeCardsState.items = Array.isArray(data.items) ? data.items.slice().sort(function(a, b){{ return String(a.name || "").localeCompare(String(b.name || "")); }}) : [];
  applyAnimeCardFilter();
}}
document.getElementById("animeCharSearchInput").addEventListener("input", debounce(applyAnimeCardFilter, 180));
(async function(){{
  await refreshAnimeCards({{ silent: false }});
  createLiveRefresh(refreshAnimeCards, 5000);
}})();
"""
    return _page_template("Cards anime", body, extra_js=js)


def build_cards_subcategory_page(*, name: str, top_banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(top_banner_url)}" alt="{_h(name)}"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="hero-actions">
      <a class="action-btn" href="/cards">Voltar</a>
      <div class="action-btn action-btn--accent">Subcategoria</div>
    </div>
    <h1 class="hero-title">{_h(name)}</h1>
    <p class="hero-subtitle">Lista viva com refresh automatico para acompanhar mudancas na colecao.</p>
  </div>
</section>

<section class="panel">
  <div class="stack">
    <div class="section-head">
      <div>
        <div class="section-kicker">Filtro local</div>
        <h2 class="section-title">Encontrar personagem</h2>
      </div>
      <div class="section-meta" id="subcategoryMeta">Carregando...</div>
    </div>
    <label class="searchbar">
      <span class="input-icon">Busca</span>
      <input id="subcategorySearchInput" type="text" placeholder="Filtrar por nome do personagem...">
    </label>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Resultado</div>
      <h2 class="section-title">Cards da subcategoria</h2>
    </div>
    <div class="section-meta" id="subcategoryResultMeta">Preparando grid...</div>
  </div>
  <div class="media-grid" id="subcategoryGrid" style="margin-top:14px;"></div>
  <div id="subcategoryEmpty" class="empty-state" style="display:none; margin-top:14px;">
    <strong>Nenhum card encontrado</strong>
    Pode ser um filtro sem resultado ou itens removidos da subcategoria.
  </div>
</section>

<div class="footer-note">Source Baltigo . Subcategoria</div>
"""
    js = f"""
const subcategoryState = {{ name: {_j(name)}, items: [], filteredItems: [] }};
function applySubcategoryFilter(){{
  const q = String(document.getElementById("subcategorySearchInput").value || "").trim().toLowerCase();
  subcategoryState.filteredItems = !q ? subcategoryState.items.slice() : subcategoryState.items.filter(function(item){{ return String(item.name || "").toLowerCase().includes(q); }});
  renderSubcategory();
}}
function renderSubcategory(){{
  const root = document.getElementById("subcategoryGrid");
  const empty = document.getElementById("subcategoryEmpty");
  document.getElementById("subcategoryMeta").textContent = "Atualizado " + humanClock() + " . " + String(subcategoryState.items.length) + " itens na subcategoria";
  document.getElementById("subcategoryResultMeta").textContent = "Mostrando " + String(subcategoryState.filteredItems.length) + " personagens";
  if (!subcategoryState.filteredItems.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = subcategoryState.filteredItems.map(function(item){{
    return ''
      + '<article class="media-card"><div class="media-cover"><img src="' + esc(item.image || {_j(top_banner_url)}) + '" alt="' + esc(item.name) + '" loading="lazy" onerror="setImageFallback(this, \\'No image\\')"><div class="media-badge media-badge--accent">' + esc(subcategoryState.name) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.name) + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(item.anime || "") + '</span><span class="soft-pill">Card</span></div></div></article>';
  }}).join("");
}}
async function refreshSubcategory(options){{
  const opts = options || {{}};
  if (!opts.silent && !subcategoryState.items.length) setSkeleton("subcategoryGrid", 6);
  const res = await fetch("/api/cards/subcategory?name=" + encodeURIComponent(subcategoryState.name) + "&limit=5000&_ts=" + Date.now());
  const data = await res.json();
  subcategoryState.items = Array.isArray(data.items) ? data.items.slice().sort(function(a, b){{ return String(a.name || "").localeCompare(String(b.name || "")); }}) : [];
  applySubcategoryFilter();
}}
document.getElementById("subcategorySearchInput").addEventListener("input", debounce(applySubcategoryFilter, 180));
(async function(){{
  await refreshSubcategory({{ silent: false }});
  createLiveRefresh(refreshSubcategory, 5000);
}})();
"""
    return _page_template("Cards subcategory", body, extra_js=js)


def build_cards_search_page(*, query: str, top_banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(top_banner_url)}" alt="Busca"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="hero-actions">
      <a class="action-btn" href="/cards">Voltar</a>
      <div class="action-btn action-btn--cool">Busca cards</div>
    </div>
    <h1 class="hero-title">Resultado para "{_h(query)}"</h1>
    <p class="hero-subtitle">Pesquisa dedicada com refresh silencioso para refletir fotos novas e cards removidos.</p>
  </div>
</section>

<section class="panel">
  <div class="stack">
    <div class="section-head">
      <div>
        <div class="section-kicker">Nova busca</div>
        <h2 class="section-title">Troque o termo quando quiser</h2>
      </div>
      <div class="section-meta" id="searchMeta">Carregando resultados...</div>
    </div>
    <label class="searchbar">
      <span class="input-icon">Busca</span>
      <input id="searchQueryInput" type="text" value="{_h(query)}" placeholder="Digite um personagem e aperte Enter">
    </label>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Resultados</div>
      <h2 class="section-title">Personagens encontrados</h2>
    </div>
    <div class="section-meta" id="searchResultMeta">Preparando grid...</div>
  </div>
  <div class="media-grid" id="searchGrid" style="margin-top:14px;"></div>
  <div id="searchEmpty" class="empty-state" style="display:none; margin-top:14px;">
    <strong>Nenhum resultado</strong>
    Tente outro nome para buscar novamente.
  </div>
</section>

<div class="footer-note">Source Baltigo . Search</div>
"""
    js = f"""
const searchPageState = {{ query: {_j(query)}, items: [] }};
function renderSearchResults(){{
  const root = document.getElementById("searchGrid");
  const empty = document.getElementById("searchEmpty");
  document.getElementById("searchMeta").textContent = "Atualizado " + humanClock() + " . Termo atual: " + searchPageState.query;
  document.getElementById("searchResultMeta").textContent = "Total de resultados: " + String(searchPageState.items.length);
  if (!searchPageState.items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = searchPageState.items.map(function(item){{
    return ''
      + '<article class="media-card"><div class="media-cover"><img src="' + esc(item.image || {_j(top_banner_url)}) + '" alt="' + esc(item.name) + '" loading="lazy" onerror="setImageFallback(this, \\'No image\\')"><div class="media-badge">Search</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.name) + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(item.anime || "") + '</span><span class="soft-pill">Card</span></div></div></article>';
  }}).join("");
}}
async function refreshSearchPage(options){{
  const opts = options || {{}};
  if (!opts.silent && !searchPageState.items.length) setSkeleton("searchGrid", 6);
  const res = await fetch("/api/cards/search?q=" + encodeURIComponent(searchPageState.query) + "&limit=500&_ts=" + Date.now());
  const data = await res.json();
  searchPageState.items = Array.isArray(data.items) ? data.items.slice().sort(function(a, b){{ return String(a.name || "").localeCompare(String(b.name || "")); }}) : [];
  renderSearchResults();
}}
document.getElementById("searchQueryInput").addEventListener("keydown", function(event){{
  if (event.key !== "Enter") return;
  const q = String(event.target.value || "").trim();
  if (!q || q === searchPageState.query) return;
  window.location.href = "/cards/search?q=" + encodeURIComponent(q);
}});
(async function(){{
  await refreshSearchPage({{ silent: false }});
  createLiveRefresh(refreshSearchPage, 5000);
}})();
"""
    return _page_template("Cards search", body, extra_js=js)


def build_menu_page(*, uid: int, menu_banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(menu_banner_url)}" alt="Menu"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">User center</div>
    <h1 class="hero-title">Perfil Baltigo</h1>
    <p class="hero-subtitle">Configuracoes, favorito, colecao e status em uma interface mais organizada, mais elegante e com refresh automatico quando houver mudanca nos cards.</p>
  </div>
</section>

<section class="panel profile-card">
  <div class="profile-avatar" id="profileAvatar">SB</div>
  <div class="profile-copy">
    <h2 class="profile-name" id="profileName">Carregando...</h2>
    <p class="profile-sub" id="profileSub">Atualizando dados do usuario...</p>
    <div class="pill-row">
      <span class="soft-pill soft-pill--cool" id="favoritePill">Favorito: --</span>
      <span class="soft-pill"><span class="pulse-dot"></span> Sync automatico</span>
    </div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div>
      <div class="section-kicker">Status</div>
      <h2 class="section-title">Resumo da conta</h2>
    </div>
    <div class="section-meta" id="menuMeta">Carregando perfil...</div>
  </div>
  <div class="stat-grid" style="margin-top:14px;">
    <div class="stat-tile"><div class="stat-label">Colecao</div><div class="stat-value" id="menuCollection">0</div></div>
    <div class="stat-tile"><div class="stat-label">Coins</div><div class="stat-value" id="menuCoins">0</div></div>
    <div class="stat-tile"><div class="stat-label">Nivel</div><div class="stat-value" id="menuLevel">1</div></div>
    <div class="stat-tile"><div class="stat-label">Idioma</div><div class="stat-value" id="menuLanguage">PT</div></div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Perfil</div><h2 class="section-title">Identidade do usuario</h2></div>
    <div class="section-meta">Sem alterar regras de negocio. So uma camada visual melhor e mais consistente.</div>
  </div>
  <div class="setting-group" style="margin-top:14px;">
    <div class="setting-row">
      <div class="setting-copy"><h3 class="setting-title">Nickname</h3><p class="setting-sub">Unico, comecando em maiuscula, e travado depois do primeiro salvamento.</p></div>
      <div class="form-stack" style="width:min(100%, 360px);">
        <label class="field"><input id="nicknameInput" maxlength="17" placeholder="Ex: Zoro"></label>
        <button class="control-btn control-btn--accent" id="saveNicknameBtn">Salvar nickname</button>
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-copy"><h3 class="setting-title">Favoritar personagem</h3><p class="setting-sub">Somente personagens da sua colecao. A lista atualiza sozinha se algum card mudar ou sumir.</p></div>
      <div class="inline-controls"><button class="control-btn" id="favoriteBtn">Escolher favorito</button></div>
    </div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Preferencias</div><h2 class="section-title">Seu jeito de usar</h2></div>
  </div>
  <div class="setting-group" style="margin-top:14px;">
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Pais</h3><p class="setting-sub">Escolha a bandeira exibida no seu perfil.</p></div><label class="field" style="width:min(100%, 240px);"><select id="countrySelect"></select></label></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Idioma</h3><p class="setting-sub">Idioma principal da sua conta.</p></div><label class="field" style="width:min(100%, 240px);"><select id="languageSelect"></select></label></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Perfil privado</h3><p class="setting-sub">Controla a visibilidade do seu perfil para outros usuarios.</p></div><button class="control-btn" id="privacyBtn">Desativado</button></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Notificacoes</h3><p class="setting-sub">Aviso quando os dados acumularem totalmente.</p></div><button class="control-btn" id="notificationsBtn">Ativado</button></div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Conta</div><h2 class="section-title">Acoes sensiveis</h2></div>
  </div>
  <div class="setting-group" style="margin-top:14px;">
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Excluir conta</h3><p class="setting-sub">Remove nickname, colecao, nivel, coins e preferencias.</p></div><button class="control-btn control-btn--danger" id="deleteBtn">Excluir conta</button></div>
  </div>
</section>

<div id="menuNote" class="floating-note">Perfil sendo carregado...</div>
<div class="footer-note">Source Baltigo . User menu</div>

<div class="sheet-backdrop" id="favoriteSheetBackdrop">
  <div class="sheet">
    <div class="sheet-head">
      <h3 class="sheet-title">Escolher favorito</h3>
      <button class="control-btn" id="closeFavoriteSheetBtn">Fechar</button>
    </div>
    <div class="sheet-body">
      <label class="searchbar">
        <span class="input-icon">Busca</span>
        <input id="favoriteSearchInput" type="text" placeholder="Filtrar sua colecao...">
      </label>
      <div class="list-stack" id="favoriteList" style="margin-top:14px;"></div>
    </div>
  </div>
</div>
"""
    js = f"""
const MENU_UID = {int(uid)};
const menuNote = document.getElementById("menuNote");
const menuState = {{ profile: null, favoriteItems: [] }};
const tgMenu = (window.Telegram && Telegram.WebApp) ? Telegram.WebApp : null;
if (tgMenu) {{ try {{ tgMenu.ready(); tgMenu.expand(); }} catch(err) {{}} }}
function setMenuNote(message, tone){{ menuNote.textContent = message || ""; menuNote.dataset.tone = tone || ""; }}
async function menuGet(url){{ const res = await fetch(url + (url.includes("?") ? "&" : "?") + "_ts=" + Date.now()); const data = await res.json(); if (!res.ok || !data.ok) throw new Error((data && data.message) || "Erro"); return data; }}
async function menuPost(url, payload){{ const res = await fetch(url + "?_ts=" + Date.now(), {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(payload) }}); const data = await res.json(); if (!res.ok || !data.ok) throw new Error((data && data.message) || "Erro"); return data; }}
function renderMenuAvatar(profile){{ const avatar = document.getElementById("profileAvatar"); if (profile.favorite && profile.favorite.image) {{ avatar.innerHTML = '<img src="' + esc(profile.favorite.image) + '" alt="avatar" onerror="setImageFallback(this, \\'Avatar\\')">'; return; }} avatar.textContent = (String(profile.display_name || "SB").trim().slice(0, 2).toUpperCase() || "SB"); }}
function renderMenuProfile(data){{ const p = data.profile || {{}}; menuState.profile = p; document.getElementById("profileName").textContent = p.display_name || "User"; document.getElementById("profileSub").textContent = p.nickname ? ("@" + p.nickname) : "Sem nickname"; document.getElementById("favoritePill").textContent = "Favorito: " + (p.favorite ? p.favorite.name : "--"); document.getElementById("menuCollection").textContent = String(p.collection_total || 0); document.getElementById("menuCoins").textContent = String(p.coins || 0); document.getElementById("menuLevel").textContent = String(p.level || 1); document.getElementById("menuLanguage").textContent = String((p.language || "pt")).toUpperCase(); document.getElementById("menuMeta").textContent = "Atualizado " + humanClock() + " . UID " + String(p.user_id || MENU_UID); renderMenuAvatar(p); document.getElementById("nicknameInput").value = p.nickname || ""; document.getElementById("nicknameInput").disabled = !!p.nickname; document.getElementById("saveNicknameBtn").disabled = !!p.nickname; const country = document.getElementById("countrySelect"); country.innerHTML = ""; (data.countries || []).forEach(function(item){{ const opt = document.createElement("option"); opt.value = item.code; opt.textContent = String(item.flag || "") + " " + String(item.name || ""); if (item.code === p.country_code) opt.selected = true; country.appendChild(opt); }}); const language = document.getElementById("languageSelect"); language.innerHTML = ""; (data.languages || []).forEach(function(item){{ const opt = document.createElement("option"); opt.value = item.code; opt.textContent = item.name; if (item.code === p.language) opt.selected = true; language.appendChild(opt); }}); document.getElementById("privacyBtn").textContent = p.private_profile ? "Ativado" : "Desativado"; document.getElementById("notificationsBtn").textContent = p.notifications_enabled ? "Ativado" : "Desativado"; }}
async function loadMenuProfile(options){{ const opts = options || {{}}; const data = await menuGet("/api/menu/profile?uid=" + MENU_UID); renderMenuProfile(data); if (!opts.silent) setMenuNote("Perfil carregado com sucesso.", "success"); }}
function favoriteSheetOpen(){{ document.getElementById("favoriteSheetBackdrop").style.display = "flex"; }}
function favoriteSheetClose(){{ document.getElementById("favoriteSheetBackdrop").style.display = "none"; }}
function favoriteSheetIsOpen(){{ return document.getElementById("favoriteSheetBackdrop").style.display === "flex"; }}
function renderFavoriteItems(items){{ const root = document.getElementById("favoriteList"); if (!items.length){{ root.innerHTML = '<div class="empty-state"><strong>Sua colecao esta vazia</strong>Voce so pode favoritar personagens da sua colecao.</div>'; return; }} root.innerHTML = items.map(function(item){{ return '<div class="setting-row"><div style="display:flex; align-items:center; gap:12px; min-width:0; flex:1;"><div class="profile-avatar" style="width:64px;height:64px;border-radius:18px;font-size:18px;">' + (item.image ? '<img src="' + esc(item.image) + '" alt="" onerror="setImageFallback(this, \\'No image\\')">' : esc(String(item.name || "").slice(0, 2).toUpperCase())) + '</div><div class="setting-copy"><h3 class="setting-title">' + esc(item.name) + '</h3><p class="setting-sub">' + esc(item.anime || "") + ' . Quantidade ' + esc(item.quantity || 0) + '</p></div></div><button class="control-btn control-btn--accent" data-favorite="' + esc(item.id) + '">Favoritar</button></div>'; }}).join(""); root.querySelectorAll("[data-favorite]").forEach(function(button){{ button.onclick = async function(){{ try{{ setMenuNote("Salvando favorito...", ""); await menuPost("/api/menu/favorite", {{ uid: MENU_UID, character_id: Number(button.getAttribute("data-favorite") || 0) }}); await loadMenuProfile({{ silent: true }}); if (favoriteSheetIsOpen()) await loadFavoriteCharacters({{ silent: true }}); favoriteSheetClose(); setMenuNote("Favorito atualizado com sucesso.", "success"); }}catch(err){{ setMenuNote("Erro ao salvar favorito: " + err.message, "error"); }} }}; }}); }}
function applyFavoriteFilter(){{ const q = String(document.getElementById("favoriteSearchInput").value || "").trim().toLowerCase(); const filtered = menuState.favoriteItems.filter(function(item){{ const hay = (String(item.name || "") + " " + String(item.anime || "")).toLowerCase(); return hay.includes(q); }}); renderFavoriteItems(filtered); }}
async function loadFavoriteCharacters(options){{ const data = await menuGet("/api/menu/collection-characters?uid=" + MENU_UID); menuState.favoriteItems = Array.isArray(data.items) ? data.items : []; applyFavoriteFilter(); if (!(options && options.silent)) setMenuNote("Colecao carregada para escolha do favorito.", "success"); }}
document.getElementById("favoriteBtn").onclick = async function(){{ try{{ await loadFavoriteCharacters({{ silent: false }}); favoriteSheetOpen(); }}catch(err){{ setMenuNote("Erro ao carregar colecao: " + err.message, "error"); }} }};
document.getElementById("favoriteSearchInput").addEventListener("input", debounce(applyFavoriteFilter, 120));
document.getElementById("closeFavoriteSheetBtn").onclick = favoriteSheetClose;
document.getElementById("favoriteSheetBackdrop").onclick = function(event){{ if (event.target.id === "favoriteSheetBackdrop") favoriteSheetClose(); }};
document.getElementById("saveNicknameBtn").onclick = async function(){{ try{{ setMenuNote("Salvando nickname...", ""); await menuPost("/api/menu/nickname", {{ uid: MENU_UID, nickname: document.getElementById("nicknameInput").value.trim() }}); await loadMenuProfile({{ silent: true }}); setMenuNote("Nickname salvo com sucesso.", "success"); }}catch(err){{ setMenuNote("Erro ao salvar nickname: " + err.message, "error"); }} }};
document.getElementById("countrySelect").onchange = async function(event){{ try{{ await menuPost("/api/menu/country", {{ uid: MENU_UID, country_code: event.target.value }}); setMenuNote("Pais atualizado.", "success"); }}catch(err){{ setMenuNote("Erro ao atualizar pais: " + err.message, "error"); }} }};
document.getElementById("languageSelect").onchange = async function(event){{ try{{ await menuPost("/api/menu/language", {{ uid: MENU_UID, language: event.target.value }}); await loadMenuProfile({{ silent: true }}); setMenuNote("Idioma atualizado.", "success"); }}catch(err){{ setMenuNote("Erro ao atualizar idioma: " + err.message, "error"); }} }};
document.getElementById("privacyBtn").onclick = async function(){{ try{{ const current = document.getElementById("privacyBtn").textContent === "Ativado"; await menuPost("/api/menu/privacy", {{ uid: MENU_UID, value: !current }}); await loadMenuProfile({{ silent: true }}); setMenuNote("Privacidade atualizada.", "success"); }}catch(err){{ setMenuNote("Erro ao atualizar privacidade: " + err.message, "error"); }} }};
document.getElementById("notificationsBtn").onclick = async function(){{ try{{ const current = document.getElementById("notificationsBtn").textContent === "Ativado"; await menuPost("/api/menu/notifications", {{ uid: MENU_UID, value: !current }}); await loadMenuProfile({{ silent: true }}); setMenuNote("Notificacoes atualizadas.", "success"); }}catch(err){{ setMenuNote("Erro ao atualizar notificacoes: " + err.message, "error"); }} }};
document.getElementById("deleteBtn").onclick = async function(){{ if (!window.confirm("Tem certeza que deseja excluir sua conta? Essa acao e irreversivel.")) return; try{{ setMenuNote("Excluindo conta...", ""); await menuPost("/api/menu/delete-account", {{ uid: MENU_UID }}); setMenuNote("Conta excluida com sucesso.", "success"); if (tgMenu) {{ try {{ tgMenu.close(); }} catch(err) {{}} }} }}catch(err){{ setMenuNote("Erro ao excluir conta: " + err.message, "error"); }} }};
(async function(){{ try{{ await loadMenuProfile({{ silent: false }}); createLiveRefresh(async function(){{ await loadMenuProfile({{ silent: true }}); if (favoriteSheetIsOpen()) await loadFavoriteCharacters({{ silent: true }}); }}, 6000); }}catch(err){{ setMenuNote("Erro ao carregar perfil: " + err.message, "error"); }} }})();
"""
    return _page_template("Menu", body, extra_js=js, include_tg=True)


def build_shop_page(*, shop_banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(shop_banner_url)}" alt="Shop"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Baltigo economy</div>
    <h1 class="hero-title">Loja Baltigo</h1>
    <p class="hero-subtitle">Uma experiencia mais forte visualmente para vender cards, comprar recursos e acompanhar tudo com atualizacao automatica.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Coins</span><span class="metric-value" id="shopCoinsHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Dados</span><span class="metric-value" id="shopDadoHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Estado</span><span class="metric-value"><span class="pulse-dot"></span> Live sync</span></div>
      <div class="metric-card"><span class="metric-label">Refresh</span><span class="metric-value">5s visivel</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Economia</div><h2 class="section-title">Compra e venda</h2></div>
    <div class="section-meta" id="shopMeta">Carregando loja...</div>
  </div>
  <div class="segmented" style="margin-top:14px;">
    <button type="button" class="segmented-btn active" id="tabSellBtn">Vender</button>
    <button type="button" class="segmented-btn" id="tabBuyBtn">Comprar</button>
  </div>
</section>

<section class="panel panel--soft" id="sellView">
  <div class="stack">
    <div class="section-head">
      <div><div class="section-kicker">Colecao</div><h2 class="section-title">Vender personagens</h2></div>
      <div class="section-meta" id="sellMeta">Carregando colecao...</div>
    </div>
    <label class="searchbar"><span class="input-icon">Busca</span><input id="sellSearchInput" type="text" placeholder="Buscar personagem ou anime..."></label>
    <div class="media-grid" id="sellGrid"></div>
    <div id="sellEmpty" class="empty-state" style="display:none;"><strong>Nada para vender</strong>Sua busca nao encontrou cards ou a colecao esta vazia.</div>
  </div>
</section>

<section class="panel panel--soft" id="buyView" style="display:none;">
  <div class="section-head">
    <div><div class="section-kicker">Loja</div><h2 class="section-title">Recursos disponiveis</h2></div>
    <div class="section-meta">A mesma linguagem visual da colecao, so que agora com foco em decisao rapida.</div>
  </div>
  <div class="buy-grid" style="margin-top:14px;">
    <article class="buy-tile"><h3 class="buy-title">Comprar dado</h3><p class="buy-copy">Adiciona mais um dado ao seu saldo atual para continuar usando o sistema sem esperar.</p><div class="buy-price">Preco: 2 coins</div><button class="action-btn action-btn--cool" id="buyDadoBtn" style="margin-top:14px; width:100%;">Comprar dado</button></article>
    <article class="buy-tile"><h3 class="buy-title">Alterar nickname</h3><p class="buy-copy">Libera uma nova troca de nickname no seu perfil. Ideal para quem quer mudar a identidade visual da conta.</p><div class="buy-price">Preco: 3 coins</div><button class="action-btn action-btn--primary" id="buyNickBtn" style="margin-top:14px; width:100%;">Comprar nickname</button></article>
  </div>
</section>

<div id="shopNote" class="floating-note">Loja sendo carregada...</div>
<div class="footer-note">Source Baltigo . Shop</div>
"""
    js = r"""
const tgShop = (window.Telegram && Telegram.WebApp) ? Telegram.WebApp : null;
if (tgShop) { try { tgShop.ready(); tgShop.expand(); } catch(err) {} }
const shopNote = document.getElementById("shopNote");
const shopState = { items: [], coins: 0, dado_balance: 0, q: "" };
function setShopNote(message, tone){ shopNote.textContent = message || ""; shopNote.dataset.tone = tone || ""; }
async function shopFetch(url, options){ const opts = options || {}; const headers = Object.assign({}, opts.headers || {}); try { const initData = tgShop && tgShop.initData ? tgShop.initData : ""; if (initData) headers["x-telegram-init-data"] = initData; } catch(err) {} const res = await fetch(url, Object.assign({}, opts, { headers })); const data = await res.json(); return { ok: res.ok, data: data }; }
function syncShopHero(){ document.getElementById("shopCoinsHero").textContent = String(shopState.coins || 0); document.getElementById("shopDadoHero").textContent = String(shopState.dado_balance || 0); document.getElementById("shopMeta").textContent = "Atualizado " + humanClock() + " . Coins " + String(shopState.coins || 0) + " . Dados " + String(shopState.dado_balance || 0); }
function renderSellGrid(){ const root = document.getElementById("sellGrid"); const empty = document.getElementById("sellEmpty"); const q = String(shopState.q || "").trim().toLowerCase(); const items = shopState.items.filter(function(item){ if (!q) return true; const hay = (String(item.character_id || "") + " " + String(item.character_name || "") + " " + String(item.anime_title || "")).toLowerCase(); return hay.includes(q); }); document.getElementById("sellMeta").textContent = "Mostrando " + String(items.length) + " cards disponiveis para venda"; if (!items.length){ root.innerHTML = ""; empty.style.display = ""; return; } empty.style.display = "none"; root.innerHTML = items.map(function(item){ const rarity = item.rarity ? '<span class="soft-pill soft-pill--accent">' + esc(item.rarity) + '</span>' : ""; return '<article class="media-card"><div class="media-cover">' + (item.image ? '<img src="' + esc(item.image) + '" alt="' + esc(item.character_name) + '" loading="lazy" onerror="setImageFallback(this, \\'No image\\')">' : '') + '<div class="media-badge media-badge--cool">Sell</div><div class="media-count">x' + esc(item.quantity || 0) + '</div></div><div class="media-body"><h3 class="card-title">' + esc(item.character_name) + '</h3><div class="pill-row"><span class="soft-pill">' + esc(item.anime_title || "") + '</span>' + rarity + '</div><button class="action-btn action-btn--primary" style="width:100%; margin-top:14px;" data-sell="' + esc(item.character_id) + '">Vender +1 coin</button></div></article>'; }).join(""); root.querySelectorAll("[data-sell]").forEach(function(button){ button.onclick = async function(){ const characterId = Number(button.getAttribute("data-sell") || 0); button.disabled = true; setShopNote("Vendendo personagem...", ""); const response = await shopFetch("/api/shop/sell/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ character_id: characterId }) }); if (!response.ok || !response.data.ok){ setShopNote("Erro ao vender: " + ((response.data && response.data.error) || "Nao foi possivel vender."), "error"); button.disabled = false; return; } shopState.coins = Number(response.data.coins || shopState.coins || 0); syncShopHero(); await loadShopCollection({ silent: true }); setShopNote("Personagem vendido com sucesso.", "success"); }; }); }
async function loadShopState(options){ const response = await shopFetch("/api/shop/state"); if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar estado da loja."); shopState.coins = Number(response.data.coins || 0); shopState.dado_balance = Number(response.data.dado_balance || 0); syncShopHero(); if (!(options && options.silent)) setShopNote("Estado da loja carregado.", "success"); }
async function loadShopCollection(options){ const opts = options || {}; if (!opts.silent && !shopState.items.length) setSkeleton("sellGrid", 6); const response = await shopFetch("/api/shop/sell/all?q=" + encodeURIComponent(shopState.q || "")); if (!response.ok || !response.data.ok){ shopState.items = []; renderSellGrid(); throw new Error("Falha ao carregar personagens da colecao."); } shopState.items = Array.isArray(response.data.items) ? response.data.items : []; renderSellGrid(); if (!opts.silent) setShopNote("Colecao carregada para venda.", "success"); }
async function refreshShop(){ await loadShopState({ silent: true }); await loadShopCollection({ silent: true }); }
document.getElementById("sellSearchInput").addEventListener("input", debounce(function(event){ shopState.q = String(event.target.value || ""); renderSellGrid(); }, 120));
document.getElementById("tabSellBtn").onclick = function(){ document.getElementById("tabSellBtn").classList.add("active"); document.getElementById("tabBuyBtn").classList.remove("active"); document.getElementById("sellView").style.display = ""; document.getElementById("buyView").style.display = "none"; };
document.getElementById("tabBuyBtn").onclick = function(){ document.getElementById("tabBuyBtn").classList.add("active"); document.getElementById("tabSellBtn").classList.remove("active"); document.getElementById("buyView").style.display = ""; document.getElementById("sellView").style.display = "none"; };
document.getElementById("buyDadoBtn").onclick = async function(){ setShopNote("Comprando dado...", ""); const response = await shopFetch("/api/shop/buy/dado", { method: "POST" }); if (!response.ok || !response.data.ok){ setShopNote("Erro ao comprar dado: " + ((response.data && response.data.error) || "Coins insuficientes."), "error"); return; } shopState.coins = Number(response.data.coins || shopState.coins || 0); shopState.dado_balance = Number(response.data.dado_balance || shopState.dado_balance || 0); syncShopHero(); setShopNote("Dado comprado com sucesso.", "success"); };
document.getElementById("buyNickBtn").onclick = async function(){ setShopNote("Comprando alteracao de nickname...", ""); const response = await shopFetch("/api/shop/buy/nickname", { method: "POST" }); if (!response.ok || !response.data.ok){ setShopNote("Erro ao comprar alteracao: " + ((response.data && response.data.error) || "Coins insuficientes."), "error"); return; } shopState.coins = Number(response.data.coins || shopState.coins || 0); syncShopHero(); setShopNote("Alteracao de nickname liberada.", "success"); };
(async function(){ try { await loadShopState({ silent: false }); await loadShopCollection({ silent: false }); createLiveRefresh(refreshShop, 5000); } catch(err) { setShopNote(err.message, "error"); } })();
"""
    return _page_template("Shop", body, extra_js=js, include_tg=True)
