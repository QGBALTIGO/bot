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
  flex-direction:column;
  align-items:flex-start;
  gap:14px;
  padding:18px;
  margin-top:-28px;
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
  flex-direction:column;
  align-items:stretch;
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
  width:100%;
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
  width:100%;
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
  .profile-card{
    flex-direction:row;
    align-items:center;
    margin-top:-52px;
  }
  .setting-row{
    flex-direction:row;
    align-items:center;
  }
  .inline-controls,
  .form-stack{
    width:auto;
  }
  .control-btn{
    width:auto;
  }
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

function getTelegramWebApp(){
  try{
    return (window.Telegram && Telegram.WebApp) ? Telegram.WebApp : null;
  }catch(err){
    return null;
  }
}

function resolveWebappUid(fallback){
  const base = Number(fallback || 0);
  try{
    const params = new URLSearchParams(window.location.search || "");
    const raw = params.get("uid") || params.get("user_id") || "";
    const parsed = Number(raw || 0);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }catch(err){}
  return Number.isFinite(base) && base > 0 ? base : 0;
}

function withAuthQuery(url, uid){
  const target = new URL(url, window.location.origin);
  const safeUid = Number(uid || 0);
  if (safeUid > 0 && !target.searchParams.has("uid")){
    target.searchParams.set("uid", String(safeUid));
  }
  return target.pathname + target.search;
}

async function authJson(url, options){
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {});
  const uid = Number(opts.uid || 0);
  const tg = getTelegramWebApp();

  try{
    const initData = tg && tg.initData ? tg.initData : "";
    if (initData){
      headers["x-telegram-init-data"] = initData;
    }
  }catch(err){}

  if (uid > 0){
    headers["x-webapp-uid"] = String(uid);
  }

  let body = opts.body;
  if (Object.prototype.hasOwnProperty.call(opts, "json")){
    const payload = Object.assign({}, opts.json || {});
    if (uid > 0 && !payload.uid){
      payload.uid = uid;
    }
    body = JSON.stringify(payload);
    headers["Content-Type"] = "application/json";
  }

  const finalUrl = withAuthQuery(url, uid);
  const res = await fetch(finalUrl, Object.assign({}, opts, { headers: headers, body: body }));
  let data = null;
  try{
    data = await res.json();
  }catch(err){
    data = { ok: false, message: "Resposta invalida do servidor." };
  }
  return { ok: res.ok, data: data };
}

function openExternalLink(url){
  const tg = getTelegramWebApp();
  try{
    if (tg && tg.openLink){
      tg.openLink(url);
      return;
    }
  }catch(err){}
  window.open(url, "_blank", "noopener,noreferrer");
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
  const cover = item.cover_url ? '<img src="' + esc(item.cover_url) + '" alt="' + esc(item.titulo) + '" loading="lazy">' : '';
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
      + '<div class="media-cover"><img src="' + esc(cardsHomeCover(item)) + '" alt="' + esc(item.anime) + '" loading="lazy"><div class="media-badge media-badge--cool">Cards</div><div class="media-count">' + esc((item.characters_count || 0) + ' chars') + '</div></div>'
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
      + '<article class="media-card"><div class="media-cover"><img src="' + esc(animeCardImage(item)) + '" alt="' + esc(item.name) + '" loading="lazy"><div class="media-badge">' + esc(badge) + '</div><div class="media-count">ID ' + esc(item.id) + '</div></div>'
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
      + '<article class="media-card"><div class="media-cover"><img src="' + esc(item.image || {_j(top_banner_url)}) + '" alt="' + esc(item.name) + '" loading="lazy"><div class="media-badge media-badge--accent">' + esc(subcategoryState.name) + '</div></div>'
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
      + '<article class="media-card"><div class="media-cover"><img src="' + esc(item.image || {_j(top_banner_url)}) + '" alt="' + esc(item.name) + '" loading="lazy"><div class="media-badge">Search</div></div>'
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
function renderMenuAvatar(profile){{ const avatar = document.getElementById("profileAvatar"); if (profile.favorite && profile.favorite.image) {{ avatar.innerHTML = '<img src="' + esc(profile.favorite.image) + '" alt="avatar">'; return; }} avatar.textContent = (String(profile.display_name || "SB").trim().slice(0, 2).toUpperCase() || "SB"); }}
function renderMenuProfile(data){{ const p = data.profile || {{}}; menuState.profile = p; document.getElementById("profileName").textContent = p.display_name || "User"; document.getElementById("profileSub").textContent = p.nickname ? ("@" + p.nickname) : "Sem nickname"; document.getElementById("favoritePill").textContent = "Favorito: " + (p.favorite ? p.favorite.name : "--"); document.getElementById("menuCollection").textContent = String(p.collection_total || 0); document.getElementById("menuCoins").textContent = String(p.coins || 0); document.getElementById("menuLevel").textContent = String(p.level || 1); document.getElementById("menuLanguage").textContent = String((p.language || "pt")).toUpperCase(); document.getElementById("menuMeta").textContent = "Atualizado " + humanClock() + " . UID " + String(p.user_id || MENU_UID); renderMenuAvatar(p); document.getElementById("nicknameInput").value = p.nickname || ""; document.getElementById("nicknameInput").disabled = !!p.nickname; document.getElementById("saveNicknameBtn").disabled = !!p.nickname; const country = document.getElementById("countrySelect"); country.innerHTML = ""; (data.countries || []).forEach(function(item){{ const opt = document.createElement("option"); opt.value = item.code; opt.textContent = String(item.flag || "") + " " + String(item.name || ""); if (item.code === p.country_code) opt.selected = true; country.appendChild(opt); }}); const language = document.getElementById("languageSelect"); language.innerHTML = ""; (data.languages || []).forEach(function(item){{ const opt = document.createElement("option"); opt.value = item.code; opt.textContent = item.name; if (item.code === p.language) opt.selected = true; language.appendChild(opt); }}); document.getElementById("privacyBtn").textContent = p.private_profile ? "Ativado" : "Desativado"; document.getElementById("notificationsBtn").textContent = p.notifications_enabled ? "Ativado" : "Desativado"; }}
async function loadMenuProfile(options){{ const opts = options || {{}}; const data = await menuGet("/api/menu/profile?uid=" + MENU_UID); renderMenuProfile(data); if (!opts.silent) setMenuNote("Perfil carregado com sucesso.", "success"); }}
function favoriteSheetOpen(){{ document.getElementById("favoriteSheetBackdrop").style.display = "flex"; }}
function favoriteSheetClose(){{ document.getElementById("favoriteSheetBackdrop").style.display = "none"; }}
function favoriteSheetIsOpen(){{ return document.getElementById("favoriteSheetBackdrop").style.display === "flex"; }}
function renderFavoriteItems(items){{ const root = document.getElementById("favoriteList"); if (!items.length){{ root.innerHTML = '<div class="empty-state"><strong>Sua colecao esta vazia</strong>Voce so pode favoritar personagens da sua colecao.</div>'; return; }} root.innerHTML = items.map(function(item){{ return '<div class="setting-row"><div style="display:flex; align-items:center; gap:12px; min-width:0; flex:1;"><div class="profile-avatar" style="width:64px;height:64px;border-radius:18px;font-size:18px;">' + (item.image ? '<img src="' + esc(item.image) + '" alt="">' : esc(String(item.name || "").slice(0, 2).toUpperCase())) + '</div><div class="setting-copy"><h3 class="setting-title">' + esc(item.name) + '</h3><p class="setting-sub">' + esc(item.anime || "") + ' . Quantidade ' + esc(item.quantity || 0) + '</p></div></div><button class="control-btn control-btn--accent" data-favorite="' + esc(item.id) + '">Favoritar</button></div>'; }}).join(""); root.querySelectorAll("[data-favorite]").forEach(function(button){{ button.onclick = async function(){{ try{{ setMenuNote("Salvando favorito...", ""); await menuPost("/api/menu/favorite", {{ uid: MENU_UID, character_id: Number(button.getAttribute("data-favorite") || 0) }}); await loadMenuProfile({{ silent: true }}); if (favoriteSheetIsOpen()) await loadFavoriteCharacters({{ silent: true }}); favoriteSheetClose(); setMenuNote("Favorito atualizado com sucesso.", "success"); }}catch(err){{ setMenuNote("Erro ao salvar favorito: " + err.message, "error"); }} }}; }}); }}
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


def build_shop_page(*, uid: int, shop_banner_url: str) -> str:
    extra_css = r"""
.shop-inline-note{
  margin-top:14px;
  padding:14px 16px;
  border-radius:18px;
  border:1px solid rgba(122,213,255,.20);
  background:linear-gradient(180deg, rgba(122,213,255,.10), rgba(122,213,255,.04));
  color:var(--muted-strong);
  font-size:13px;
  line-height:1.55;
}
.shop-inline-note strong{
  display:block;
  margin-bottom:4px;
  color:var(--text);
  font-size:13px;
}
.xshop-strip{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:14px;
}
.xmini-card{
  overflow:hidden;
  border-color:rgba(255,255,255,.10);
  background:linear-gradient(180deg, rgba(12,18,36,.82), rgba(8,13,24,.94));
}
.xmini-card--rare{
  border-color:rgba(122,213,255,.24);
}
.xmini-card--special{
  border-color:rgba(255,111,148,.28);
  box-shadow:0 18px 42px rgba(255,111,148,.08), var(--shadow-md);
}
.xmini-card .media-cover{
  aspect-ratio:.72;
  background:
    radial-gradient(circle at 20% 10%, rgba(122,213,255,.18), transparent 36%),
    radial-gradient(circle at 85% 0%, rgba(255,111,148,.18), transparent 24%),
    linear-gradient(180deg, rgba(15,22,43,.98), rgba(8,12,22,.98));
}
.xmini-card .media-cover img{
  object-fit:contain;
  padding:16px;
  position:relative;
  z-index:0;
}
.xmini-card .media-cover::after{
  background:linear-gradient(180deg, rgba(2,5,12,.00) 36%, rgba(2,5,12,.74) 100%);
}
.xmini-price{
  position:absolute;
  top:12px;
  right:12px;
  z-index:1;
  min-height:34px;
  padding:9px 11px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.14);
  background:rgba(8,14,28,.54);
  backdrop-filter:blur(18px);
  font-size:11px;
  font-weight:800;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.xmini-anime{
  margin-top:8px;
  color:var(--muted);
  font-size:12px;
  line-height:1.5;
  min-height:36px;
}
.xmini-status{
  margin-top:12px;
  color:var(--muted-strong);
  font-size:12px;
  line-height:1.5;
  min-height:36px;
}
.xmini-open{
  width:100%;
  margin-top:14px;
}
.xdetail-sheet{
  width:min(940px, 100%);
}
.xdetail-sheet .control-btn{
  width:auto;
}
.xdetail-layout{
  display:grid;
  gap:16px;
}
.xdetail-preview,
.xdetail-content{
  border-radius:24px;
  border:1px solid rgba(255,255,255,.08);
  background:linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
  padding:16px;
}
.xdetail-image-shell{
  position:relative;
  overflow:hidden;
  aspect-ratio:.72;
  border-radius:24px;
  border:1px solid rgba(255,255,255,.10);
  background:
    radial-gradient(circle at 18% 12%, rgba(122,213,255,.22), transparent 34%),
    radial-gradient(circle at 84% 0%, rgba(255,111,148,.20), transparent 24%),
    linear-gradient(180deg, rgba(13,20,39,.98), rgba(8,12,22,.98));
}
.xdetail-image-shell img{
  width:100%;
  height:100%;
  object-fit:contain;
  padding:22px;
  display:block;
}
.xdetail-image-shell::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(2,5,12,.02) 40%, rgba(2,5,12,.58) 100%);
  pointer-events:none;
}
.xdetail-preview-copy{
  margin-top:14px;
}
.xdetail-preview-copy .card-title{
  font-size:26px;
}
.xdetail-preview-copy .section-meta{
  margin-top:8px;
}
.xdetail-table{
  display:grid;
  gap:10px;
}
.xdetail-row{
  display:grid;
  grid-template-columns:150px minmax(0, 1fr);
  gap:10px;
}
.xdetail-label{
  display:flex;
  align-items:center;
  padding:14px;
  border-radius:16px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(255,255,255,.06);
  color:var(--muted);
  font-size:11px;
  font-weight:800;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.xdetail-value{
  display:flex;
  align-items:center;
  padding:14px;
  border-radius:16px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(6,10,20,.72);
  color:var(--text);
  font-size:14px;
  font-weight:700;
  line-height:1.55;
  word-break:break-word;
}
.xdetail-section{
  margin-top:14px;
  overflow:hidden;
  border-radius:20px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(255,255,255,.03);
}
.xdetail-section-title{
  padding:12px 14px;
  border-bottom:1px solid rgba(255,255,255,.06);
  color:var(--muted-strong);
  font-size:11px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
.xdetail-section-body{
  padding:16px;
  color:var(--muted-strong);
  font-size:14px;
  line-height:1.7;
  white-space:pre-wrap;
}
.xdetail-buybar{
  margin-top:14px;
  padding:16px;
  border-radius:20px;
  border:1px solid rgba(255,255,255,.08);
  background:linear-gradient(180deg, rgba(122,213,255,.08), rgba(255,255,255,.02));
}
.xdetail-buyhint{
  margin-top:10px;
  color:var(--muted);
  font-size:12px;
  line-height:1.55;
}
.xdetail-buybtn{
  width:100%;
  margin-top:14px;
}
@media (min-width:860px){
  .xdetail-layout{
    grid-template-columns:minmax(280px, 340px) minmax(0, 1fr);
  }
}
@media (max-width:680px){
  .xdetail-row{
    grid-template-columns:1fr;
  }
}
"""
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(shop_banner_url)}" alt="Loja"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Baltigo Economy</div>
    <h1 class="hero-title">Loja Baltigo</h1>
    <p class="hero-subtitle">Venda cards normais, compre recursos da conta e descubra a vitrine di&aacute;ria de XCARDS sem poluir a tela.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Jogador</span><span class="metric-value" id="shopPlayerHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Coins</span><span class="metric-value" id="shopCoinsHero">0</span></div>
      <div class="metric-card"><span class="metric-label">Dados</span><span class="metric-value" id="shopDadoHero">0</span></div>
      <div class="metric-card"><span class="metric-label">N&iacute;vel</span><span class="metric-value" id="shopLevelHero">1</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Economia</div><h2 class="section-title">Compra, venda e rota&ccedil;&atilde;o di&aacute;ria</h2></div>
    <div class="section-meta" id="shopMeta">Preparando a loja...</div>
  </div>
  <div class="pill-row" style="margin-top:14px;">
    <span class="soft-pill soft-pill--cool" id="shopNicknamePill">Conta: ...</span>
    <span class="soft-pill" id="shopCollectionPill">Cole&ccedil;&atilde;o: ...</span>
    <span class="soft-pill" id="shopXCollectionPill">XCards: ...</span>
    <span class="soft-pill" id="shopRefreshPill">Renova&ccedil;&atilde;o: ...</span>
    <span class="soft-pill">UID {_h(uid) if int(uid) > 0 else "--"}</span>
  </div>
  <div class="segmented" style="margin-top:14px;">
    <button type="button" class="segmented-btn active" id="tabSellBtn">Vender</button>
    <button type="button" class="segmented-btn" id="tabBuyBtn">Comprar</button>
    <button type="button" class="segmented-btn" id="tabXcardsBtn">XCARDS</button>
  </div>
</section>

<section class="panel panel--soft" id="sellView">
  <div class="stack">
    <div class="section-head">
      <div><div class="section-kicker">Cole&ccedil;&atilde;o</div><h2 class="section-title">Vender personagens normais</h2></div>
      <div class="section-meta" id="sellMeta">Carregando cards da sua cole&ccedil;&atilde;o...</div>
    </div>
    <label class="searchbar"><span class="input-icon">Busca</span><input id="sellSearchInput" type="text" placeholder="Buscar personagem ou anime..."></label>
    <div class="media-grid" id="sellGrid"></div>
    <div id="sellEmpty" class="empty-state" style="display:none;"><strong>Nada para vender</strong>Sua busca n&atilde;o encontrou cards ou a cole&ccedil;&atilde;o est&aacute; vazia.</div>
  </div>
</section>

<section class="panel panel--soft" id="buyView" style="display:none;">
  <div class="section-head">
    <div><div class="section-kicker">Conta</div><h2 class="section-title">Compras r&aacute;pidas</h2></div>
    <div class="section-meta">Toda compra pede confirma&ccedil;&atilde;o antes de gastar suas coins.</div>
  </div>
  <div class="shop-inline-note">
    <strong>Compras simples, sem polui&ccedil;&atilde;o visual.</strong>
    O foco aqui &eacute; resolver r&aacute;pido: mais um dado para continuar usando o sistema ou uma nova altera&ccedil;&atilde;o de nickname quando voc&ecirc; quiser mudar a identidade da conta.
  </div>
  <div class="buy-grid" style="margin-top:14px;">
    <article class="buy-tile">
      <h3 class="buy-title">Comprar dado</h3>
      <p class="buy-copy">Adiciona mais um dado ao seu saldo atual para continuar usando o sistema sem esperar a recarga natural.</p>
      <div class="buy-price">Pre&ccedil;o: 2 coins</div>
      <button class="action-btn action-btn--cool" id="buyDadoBtn" style="margin-top:14px; width:100%;">Comprar dado</button>
    </article>
    <article class="buy-tile">
      <h3 class="buy-title">Alterar nickname</h3>
      <p class="buy-copy">Libera uma nova troca de nickname no seu perfil para quando voc&ecirc; quiser renovar o nome exibido no bot.</p>
      <div class="buy-price">Pre&ccedil;o: 3 coins</div>
      <button class="action-btn action-btn--primary" id="buyNickBtn" style="margin-top:14px; width:100%;">Comprar altera&ccedil;&atilde;o</button>
    </article>
  </div>
</section>

<section class="panel panel--soft" id="xcardsView" style="display:none;">
  <div class="section-head">
    <div><div class="section-kicker">XCARDS</div><h2 class="section-title">Vitrine di&aacute;ria</h2></div>
    <div class="section-meta" id="xcardsMeta">Preparando a sele&ccedil;&atilde;o do dia...</div>
  </div>
  <div class="xshop-strip">
    <span class="soft-pill soft-pill--cool" id="xshopCompactRefresh">Renova&ccedil;&atilde;o: --</span>
    <span class="soft-pill" id="xshopCompactLevel">N&iacute;vel: --</span>
    <span class="soft-pill" id="xshopCompactCollection">XCards: --</span>
  </div>
  <div class="media-grid" id="xcardsGrid" style="margin-top:14px;"></div>
  <div id="xcardsGridEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nenhum XCARD hoje</strong>A vitrine do dia ainda n&atilde;o foi preparada.</div>
</section>

<div class="sheet-backdrop" id="xcardDetailBackdrop">
  <div class="sheet xdetail-sheet">
    <div class="sheet-head">
      <div>
        <h3 class="sheet-title" id="xcardDetailTitle">Detalhes do card</h3>
        <div class="section-meta" id="xcardDetailMeta">Carregando...</div>
      </div>
      <button class="control-btn" id="closeXcardDetailBtn">Fechar</button>
    </div>
    <div class="sheet-body">
      <div class="xdetail-layout">
        <div class="xdetail-preview">
          <div class="xdetail-image-shell" id="xcardDetailImageShell"></div>
          <div class="xdetail-preview-copy">
            <h3 class="card-title" id="xcardDetailName">XCard</h3>
            <div class="section-meta" id="xcardDetailAnime">--</div>
            <div class="pill-row" id="xcardDetailPills" style="margin-top:12px;"></div>
          </div>
        </div>
        <div class="xdetail-content">
          <div class="xdetail-table" id="xcardDetailTable"></div>
          <section class="xdetail-section">
            <div class="xdetail-section-title">Efeito</div>
            <div class="xdetail-section-body" id="xcardDetailEffect">--</div>
          </section>
          <section class="xdetail-section">
            <div class="xdetail-section-title">Acionar</div>
            <div class="xdetail-section-body" id="xcardDetailTrigger">--</div>
          </section>
          <div class="xdetail-buybar">
            <div class="pill-row" id="xcardDetailBuyPills"></div>
            <div class="xdetail-buyhint" id="xcardDetailBuyHint">Selecione o card para ver as condi&ccedil;&otilde;es de compra.</div>
            <button class="action-btn action-btn--cool xdetail-buybtn" id="xcardDetailBuyBtn">Comprar</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="shopNote" class="floating-note">Loja sendo carregada...</div>
<div class="footer-note">Baltigo . Loja</div>
"""
    js = f"""
const SHOP_UID = resolveWebappUid({int(uid)});
const tgShop = getTelegramWebApp();
if (tgShop) {{ try {{ tgShop.ready(); tgShop.expand(); }} catch(err) {{}} }}

const shopNote = document.getElementById("shopNote");
const xcardDetailBackdrop = document.getElementById("xcardDetailBackdrop");
const shopState = {{
  tab: "sell",
  items: [],
  coins: 0,
  dado_balance: 0,
  q: "",
  profile: null,
  refresh: null,
  xcards: {{ normal: [], rare: [], special: [], all: [] }},
  selectedOffer: null
}};

function setShopNote(message, tone){{
  shopNote.textContent = message || "";
  shopNote.dataset.tone = tone || "";
}}

function userDisplayName(){{
  const profile = shopState.profile || {{}};
  const nickname = String(profile.nickname || "").trim();
  const displayName = String(profile.display_name || profile.full_name || (SHOP_UID > 0 ? ("UID " + SHOP_UID) : "Jogador"));
  return nickname || displayName;
}}

function setShopTab(tab){{
  shopState.tab = String(tab || "sell");
  if (shopState.tab !== "xcards") closeXcardDetail();
  document.getElementById("tabSellBtn").classList.toggle("active", shopState.tab === "sell");
  document.getElementById("tabBuyBtn").classList.toggle("active", shopState.tab === "buy");
  document.getElementById("tabXcardsBtn").classList.toggle("active", shopState.tab === "xcards");
  document.getElementById("sellView").style.display = shopState.tab === "sell" ? "" : "none";
  document.getElementById("buyView").style.display = shopState.tab === "buy" ? "" : "none";
  document.getElementById("xcardsView").style.display = shopState.tab === "xcards" ? "" : "none";
}}

function syncShopHero(){{
  const profile = shopState.profile || {{}};
  const nickname = String(profile.nickname || "").trim();
  const displayName = userDisplayName();
  const level = Number((profile.level != null ? profile.level : 1) || 1);
  const collectionTotal = Number(profile.collection_total || 0);
  const xcollectionTotal = Number(profile.xcollection_total || 0);
  const refresh = shopState.refresh || {{}};
  const refreshCountdown = String(refresh.countdown_label || "--");
  const refreshClock = String(refresh.next_refresh_hhmm || "--:--");

  document.getElementById("shopPlayerHero").textContent = displayName;
  document.getElementById("shopCoinsHero").textContent = String(shopState.coins || 0);
  document.getElementById("shopDadoHero").textContent = String(shopState.dado_balance || 0);
  document.getElementById("shopLevelHero").textContent = String(level || 1);
  document.getElementById("shopNicknamePill").textContent = nickname ? ("Conta: @" + nickname) : ("Conta: " + displayName);
  document.getElementById("shopCollectionPill").textContent = "Cole\\u00e7\\u00e3o: " + String(collectionTotal || 0);
  document.getElementById("shopXCollectionPill").textContent = "XCards: " + String(xcollectionTotal || 0);
  document.getElementById("shopRefreshPill").textContent = "Renova\\u00e7\\u00e3o: " + refreshCountdown;
  document.getElementById("shopMeta").textContent = "Atualizado " + humanClock() + " . Coins " + String(shopState.coins || 0) + " . Dados " + String(shopState.dado_balance || 0) + " . XCARDS " + refreshCountdown + " at\\u00e9 " + refreshClock;
  document.getElementById("xshopCompactRefresh").textContent = "Renova\\u00e7\\u00e3o: " + refreshCountdown;
  document.getElementById("xshopCompactLevel").textContent = "N\\u00edvel: " + String(level || 1);
  document.getElementById("xshopCompactCollection").textContent = "XCards: " + String(xcollectionTotal || 0);
}}

function renderSellGrid(){{
  const root = document.getElementById("sellGrid");
  const empty = document.getElementById("sellEmpty");
  const q = String(shopState.q || "").trim().toLowerCase();
  const items = shopState.items.filter(function(item){{
    if (!q) return true;
    const hay = (String(item.character_id || "") + " " + String(item.character_name || "") + " " + String(item.anime_title || "")).toLowerCase();
    return hay.includes(q);
  }});
  document.getElementById("sellMeta").textContent = "Mostrando " + String(items.length) + " cards dispon\\u00edveis para venda";
  if (!items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = items.map(function(item){{
    const rarity = item.rarity ? '<span class="soft-pill soft-pill--accent">' + esc(item.rarity) + '</span>' : "";
    const img = item.image ? '<img src="' + esc(item.image) + '" alt="' + esc(item.character_name) + '" loading="lazy" onerror="setImageFallback(this,\\'CARD\\')">' : "";
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge media-badge--cool">Venda</div><div class="media-count">x' + esc(item.quantity || 0) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.character_name) + '</h3><div class="pill-row"><span class="soft-pill">' + esc(item.anime_title || "") + '</span>' + rarity + '</div><button class="action-btn action-btn--primary" style="width:100%; margin-top:14px;" data-sell="' + esc(item.character_id) + '">Vender +1 coin</button></div>'
      + '</article>';
  }}).join("");
  root.querySelectorAll("[data-sell]").forEach(function(button){{
    button.onclick = async function(){{
      const characterId = Number(button.getAttribute("data-sell") || 0);
      const item = shopState.items.find(function(entry){{ return Number(entry.character_id || 0) === characterId; }}) || {{}};
      const targetName = String(item.character_name || "este personagem");
      if (!window.confirm('Tem certeza que deseja vender "' + targetName + '" por 1 coin?')) return;
      button.disabled = true;
      setShopNote("Vendendo personagem...", "");
      const response = await authJson("/api/shop/sell/confirm", {{ uid: SHOP_UID, method: "POST", json: {{ character_id: characterId }} }});
      if (!response.ok || !response.data.ok){{
        setShopNote("Erro ao vender: " + ((response.data && response.data.error) || "N\\u00e3o foi poss\\u00edvel vender."), "error");
        button.disabled = false;
        return;
      }}
      shopState.coins = Number(response.data.coins || shopState.coins || 0);
      await loadShopCollection({{ silent: true }});
      await loadShopContext({{ silent: true }});
      await loadShopState({{ silent: true }});
      syncShopHero();
      setShopNote("Personagem vendido com sucesso.", "success");
    }};
  }});
}}

function xcardGroupTone(group){{
  if (group === "special") return "accent";
  if (group === "rare") return "cool";
  return "";
}}

function xcardActionState(item){{
  const price = Number(item.price || 0);
  const coins = Number(shopState.coins || 0);
  if (item.purchased) return {{ disabled: true, label: "Comprado hoje", tone: "cool", status: "Este slot j\\u00e1 foi comprado hoje." }};
  if (item.locked) return {{ disabled: true, label: "N\\u00edvel " + String(item.level_required || 1), tone: "", status: "Dispon\\u00edvel a partir do n\\u00edvel " + String(item.level_required || 1) + "." }};
  if (coins < price) return {{ disabled: true, label: "Coins insuficientes", tone: "", status: "Faltam " + String(price - coins) + " coins para comprar." }};
  if (item.slot_group === "special") return {{ disabled: false, label: "Comprar por " + String(price) + " coins", tone: "primary", status: "Slot especial dispon\\u00edvel hoje." }};
  if (item.slot_group === "rare") return {{ disabled: false, label: "Comprar por " + String(price) + " coins", tone: "cool", status: "Card raro pronto para compra." }};
  return {{ disabled: false, label: "Comprar por " + String(price) + " coins", tone: "cool", status: "Card dispon\\u00edvel agora." }};
}}

function xcardActionClass(action){{
  return action.tone === "primary"
    ? "action-btn action-btn--primary"
    : action.tone === "cool"
      ? "action-btn action-btn--cool"
      : "action-btn";
}}

function xcardAllOffers(){{
  return Array.isArray((shopState.xcards || {{}}).all) ? shopState.xcards.all : [];
}}

function getXcardOfferBySlot(slotCode){{
  return xcardAllOffers().find(function(item){{
    return String(item.slot_code || "") === String(slotCode || "");
  }}) || null;
}}

function xcardDetailOpen(){{
  return xcardDetailBackdrop && xcardDetailBackdrop.style.display === "flex";
}}

function closeXcardDetail(){{
  if (xcardDetailBackdrop) xcardDetailBackdrop.style.display = "none";
}}

function openXcardDetail(item){{
  shopState.selectedOffer = item || null;
  renderXcardDetail();
  if (xcardDetailBackdrop) xcardDetailBackdrop.style.display = "flex";
}}

function xcardDisplayText(value, fallback){{
  const text = String(value || "").trim();
  return text && text !== "-" ? text : (fallback || "--");
}}

function xcardJoinList(listValue, fallback){{
  const items = Array.isArray(listValue)
    ? listValue.map(function(entry){{ return String(entry || "").trim(); }}).filter(Boolean)
    : [];
  return items.length ? items.join(" . ") : (fallback || "--");
}}

function renderXcardOffer(item){{
  const card = item.card || {{}};
  const action = xcardActionState(item);
  const image = card.image ? '<img src="' + esc(card.image) + '" alt="' + esc(card.name || "XCard") + '" loading="lazy" onerror="setImageFallback(this,\\'XCARD\\')">' : "";
  const pills = []
    .concat(item.locked ? ['<span class="soft-pill">Nv. ' + esc(item.level_required || 1) + '</span>'] : [])
    .concat(card.alt_art ? ['<span class="soft-pill soft-pill--accent">Alt-Art</span>'] : [])
    .concat(item.purchased ? ['<span class="soft-pill">Comprado</span>'] : [])
    .join("");
  return ''
    + '<article class="media-card xmini-card xmini-card--' + esc(item.slot_group || "normal") + '">'
    +   '<div class="media-cover">' + image + '<div class="media-badge' + (xcardGroupTone(item.slot_group) ? (' media-badge--' + xcardGroupTone(item.slot_group)) : '') + '">' + esc(item.slot_group_label || "Normal") + '</div><div class="xmini-price">' + esc(item.price || 0) + ' coins</div></div>'
    +   '<div class="media-body">'
    +     '<h3 class="card-title">' + esc(card.name || "XCard") + '</h3>'
    +     '<div class="xmini-anime">' + esc(card.anime || "Obra n\\u00e3o registrada") + '</div>'
    +     '<div class="pill-row">' + pills + '</div>'
    +     '<div class="xmini-status">' + esc(action.status) + '</div>'
    +     '<button class="action-btn action-btn--cool xmini-open" data-xopen="' + esc(item.slot_code || "") + '">Abrir card</button>'
    +   '</div>'
    + '</article>';
}}

function renderXcardDetail(){{
  const item = shopState.selectedOffer;
  if (!item) return;
  const card = item.card || {{}};
  const action = xcardActionState(item);
  const imageHtml = card.image
    ? '<img src="' + esc(card.image) + '" alt="' + esc(card.name || "XCard") + '" loading="lazy" onerror="setImageFallback(this,\\'XCARD\\')">'
    : '<div class="media-fallback" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;">XCARD</div>';
  const detailRows = [
    ["Energia necess\\u00e1ria", xcardDisplayText(card.required_energy, "--")],
    ["Custo AP", xcardDisplayText(card.ap_cost, "--")],
    ["Tipo do cart\\u00e3o", xcardDisplayText(card.card_type, "--")],
    ["PA", xcardDisplayText(card.bp, "--")],
    ["Afinidade", xcardDisplayText(card.affinity, "--")],
    ["Energia gerada", xcardJoinList(card.generated_energy, "--")]
  ];
  const pills = []
    .concat(card.anime ? ['<span class="soft-pill soft-pill--cool">' + esc(card.anime) + '</span>'] : [])
    .concat(card.card_no ? ['<span class="soft-pill">ID ' + esc(card.card_no) + '</span>'] : [])
    .concat(card.rarity_label ? ['<span class="soft-pill' + (item.slot_group === "special" ? ' soft-pill--accent' : '') + '">' + esc(card.rarity_label) + '</span>'] : [])
    .concat(item.slot_group_label ? ['<span class="soft-pill">' + esc(item.slot_group_label) + '</span>'] : [])
    .concat(card.alt_art ? ['<span class="soft-pill soft-pill--accent">Alt-Art</span>'] : [])
    .join("");
  document.getElementById("xcardDetailTitle").textContent = String(card.name || "Detalhes do card");
  document.getElementById("xcardDetailMeta").textContent = item.purchased
    ? "Card j\\u00e1 comprado hoje."
    : "Toque em comprar quando decidir levar este card.";
  document.getElementById("xcardDetailImageShell").innerHTML = imageHtml;
  document.getElementById("xcardDetailName").textContent = String(card.name || "XCard");
  document.getElementById("xcardDetailAnime").textContent = String(card.anime || "Obra n\\u00e3o registrada");
  document.getElementById("xcardDetailPills").innerHTML = pills;
  document.getElementById("xcardDetailTable").innerHTML = detailRows.map(function(row){{
    return '<div class="xdetail-row"><div class="xdetail-label">' + esc(row[0]) + '</div><div class="xdetail-value">' + esc(row[1]) + '</div></div>';
  }}).join("");
  document.getElementById("xcardDetailEffect").textContent = xcardDisplayText(card.effect, "Sem efeito registrado.");
  document.getElementById("xcardDetailTrigger").textContent = xcardDisplayText(card.trigger, "Acionar n\\u00e3o registrado.");
  document.getElementById("xcardDetailBuyPills").innerHTML = ''
    + '<span class="soft-pill soft-pill--cool">Pre\\u00e7o: ' + esc(item.price || 0) + ' coins</span>'
    + '<span class="soft-pill">N\\u00edvel: ' + esc(item.level_required || 1) + '</span>'
    + '<span class="soft-pill' + (item.purchased ? '' : (item.slot_group === "special" ? ' soft-pill--accent' : '')) + '">' + esc(card.rarity_label || card.rarity || "--") + '</span>';
  document.getElementById("xcardDetailBuyHint").textContent = action.status + (card.product_name ? (" Produto: " + String(card.product_name)) : "");
  const buyBtn = document.getElementById("xcardDetailBuyBtn");
  buyBtn.className = xcardActionClass(action) + " xdetail-buybtn";
  buyBtn.textContent = action.label;
  buyBtn.disabled = !!action.disabled;
}}

async function buySelectedXcard(){{
  const item = shopState.selectedOffer;
  if (!item) return;
  const action = xcardActionState(item);
  if (action.disabled) return;
  const buyBtn = document.getElementById("xcardDetailBuyBtn");
  buyBtn.disabled = true;
  setShopNote("Comprando XCARD...", "");
  const response = await authJson("/api/shop/xcards/buy", {{ uid: SHOP_UID, method: "POST", json: {{ slot_code: item.slot_code }} }});
  if (!response.ok || !response.data.ok){{
    setShopNote("Erro ao comprar XCARD: " + ((response.data && response.data.error) || "N\\u00e3o foi poss\\u00edvel concluir a compra."), "error");
    await loadShopState({{ silent: true }});
    await loadXcardDailyShop({{ silent: true }});
    syncShopHero();
    renderXcardDetail();
    return;
  }}
  shopState.coins = Number(response.data.coins || shopState.coins || 0);
  await loadShopContext({{ silent: true }});
  await loadShopState({{ silent: true }});
  await loadXcardDailyShop({{ silent: true }});
  syncShopHero();
  closeXcardDetail();
  const purchase = (response.data && response.data.purchase) || {{}};
  setShopNote("XCARD comprado: " + String(purchase.card_name || (item.card || {{}}).name || "Card") + ".", "success");
}}

function syncSelectedOfferFromState(){{
  if (!shopState.selectedOffer || !shopState.selectedOffer.slot_code) return;
  const latest = getXcardOfferBySlot(shopState.selectedOffer.slot_code);
  if (!latest) return;
  shopState.selectedOffer = latest;
  if (xcardDetailOpen()) renderXcardDetail();
}}

function renderXcards(){{
  const root = document.getElementById("xcardsGrid");
  const empty = document.getElementById("xcardsGridEmpty");
  const items = xcardAllOffers();
  document.getElementById("xcardsMeta").textContent = items.length
    ? "Toque em um card para abrir a ficha completa."
    : "Nenhuma oferta dispon\\u00edvel agora.";
  if (!items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = items.map(renderXcardOffer).join("");
  root.querySelectorAll("[data-xopen]").forEach(function(button){{
    button.onclick = async function(){{
      const slotCode = String(button.getAttribute("data-xopen") || "");
      const item = getXcardOfferBySlot(slotCode);
      if (!item) return;
      openXcardDetail(item);
    }};
  }});
}}

async function loadShopContext(options){{
  const response = await authJson("/api/webapp/context", {{ uid: SHOP_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao identificar o jogador da loja.");
  shopState.profile = response.data.profile || null;
  if (shopState.profile){{
    shopState.coins = Number(shopState.profile.coins || shopState.coins || 0);
    shopState.dado_balance = Number(shopState.profile.dado_balance || shopState.dado_balance || 0);
  }}
  syncShopHero();
  if (!(options && options.silent)) setShopNote("Jogador identificado com sucesso.", "success");
}}

async function loadShopState(options){{
  const response = await authJson("/api/shop/state", {{ uid: SHOP_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar o estado da loja.");
  shopState.coins = Number(response.data.coins || 0);
  shopState.dado_balance = Number(response.data.dado_balance || 0);
  if (response.data.refresh) shopState.refresh = response.data.refresh;
  if (shopState.profile && response.data.level != null) shopState.profile.level = Number(response.data.level || 1);
  if (shopState.profile && response.data.xcollection_total != null) shopState.profile.xcollection_total = Number(response.data.xcollection_total || 0);
  syncShopHero();
  if (!(options && options.silent)) setShopNote("Estado da loja atualizado.", "success");
}}

async function loadShopCollection(options){{
  const opts = options || {{}};
  if (!opts.silent && !shopState.items.length) setSkeleton("sellGrid", 6);
  const response = await authJson("/api/shop/sell/all?q=" + encodeURIComponent(shopState.q || ""), {{ uid: SHOP_UID }});
  if (!response.ok || !response.data.ok){{
    shopState.items = [];
    renderSellGrid();
    throw new Error("Falha ao carregar personagens da cole\\u00e7\\u00e3o.");
  }}
  shopState.items = Array.isArray(response.data.items) ? response.data.items : [];
  renderSellGrid();
  if (!opts.silent) setShopNote("Cole\\u00e7\\u00e3o pronta para venda.", "success");
}}

async function loadXcardDailyShop(options){{
  const opts = options || {{}};
  if (!opts.silent){{
    setSkeleton("xcardsGrid", 6);
  }}
  const response = await authJson("/api/shop/xcards/daily", {{ uid: SHOP_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar a loja di\\u00e1ria de XCARDS.");
  const groups = response.data.groups || {{}};
  shopState.xcards = {{
    normal: Array.isArray(groups.normal) ? groups.normal : [],
    rare: Array.isArray(groups.rare) ? groups.rare : [],
    special: Array.isArray(groups.special) ? groups.special : [],
    all: Array.isArray(response.data.offers) ? response.data.offers : []
  }};
  if (response.data.refresh) shopState.refresh = response.data.refresh;
  shopState.coins = Number(response.data.coins || shopState.coins || 0);
  if (shopState.profile){{
    shopState.profile.level = Number(response.data.level || shopState.profile.level || 1);
    shopState.profile.xcollection_total = Number(response.data.xcollection_total || shopState.profile.xcollection_total || 0);
  }}
  renderXcards();
  syncShopHero();
  syncSelectedOfferFromState();
  if (!opts.silent) setShopNote("Loja di\\u00e1ria de XCARDS carregada.", "success");
}}

async function refreshShop(){{
  await loadShopContext({{ silent: true }});
  await loadShopState({{ silent: true }});
  await loadShopCollection({{ silent: true }});
  await loadXcardDailyShop({{ silent: true }});
}}

document.getElementById("sellSearchInput").addEventListener("input", debounce(function(event){{
  shopState.q = String(event.target.value || "");
  renderSellGrid();
}}, 120));

document.getElementById("tabSellBtn").onclick = function(){{ setShopTab("sell"); }};
document.getElementById("tabBuyBtn").onclick = function(){{ setShopTab("buy"); }};
document.getElementById("tabXcardsBtn").onclick = function(){{ setShopTab("xcards"); }};
document.getElementById("closeXcardDetailBtn").onclick = closeXcardDetail;
document.getElementById("xcardDetailBackdrop").onclick = function(event){{ if (event.target.id === "xcardDetailBackdrop") closeXcardDetail(); }};
document.getElementById("xcardDetailBuyBtn").onclick = buySelectedXcard;

document.getElementById("buyDadoBtn").onclick = async function(){{
  if (!window.confirm("Tem certeza que deseja comprar 1 dado por 2 coins?")) return;
  setShopNote("Comprando dado...", "");
  const response = await authJson("/api/shop/buy/dado", {{ uid: SHOP_UID, method: "POST", json: {{}} }});
  if (!response.ok || !response.data.ok){{
    setShopNote("Erro ao comprar dado: " + ((response.data && response.data.error) || "Coins insuficientes."), "error");
    return;
  }}
  shopState.coins = Number(response.data.coins || shopState.coins || 0);
  shopState.dado_balance = Number(response.data.dado_balance || shopState.dado_balance || 0);
  await loadShopContext({{ silent: true }});
  await loadShopState({{ silent: true }});
  syncShopHero();
  setShopNote("Dado comprado com sucesso.", "success");
}};

document.getElementById("buyNickBtn").onclick = async function(){{
  if (!window.confirm("Tem certeza que deseja comprar uma nova altera\\u00e7\\u00e3o de nickname por 3 coins?")) return;
  setShopNote("Comprando altera\\u00e7\\u00e3o de nickname...", "");
  const response = await authJson("/api/shop/buy/nickname", {{ uid: SHOP_UID, method: "POST", json: {{}} }});
  if (!response.ok || !response.data.ok){{
    setShopNote("Erro ao comprar altera\\u00e7\\u00e3o: " + ((response.data && response.data.error) || "Coins insuficientes."), "error");
    return;
  }}
  shopState.coins = Number(response.data.coins || shopState.coins || 0);
  await loadShopContext({{ silent: true }});
  await loadShopState({{ silent: true }});
  syncShopHero();
  setShopNote("Altera\\u00e7\\u00e3o de nickname liberada.", "success");
}};

(async function(){{
  try {{
    setShopTab("sell");
    await loadShopContext({{ silent: true }});
    await loadShopState({{ silent: true }});
    await loadShopCollection({{ silent: false }});
    await loadXcardDailyShop({{ silent: false }});
    createLiveRefresh(refreshShop, 30000);
  }} catch(err) {{
    setShopNote(err.message, "error");
  }}
}})();
"""
    return _page_template("Loja", body, extra_css=extra_css, extra_js=js, include_tg=True)


def _uid_query(uid: int) -> str:
    return f"?uid={int(uid)}" if int(uid) > 0 else ""


def build_collection_page(*, uid: int, banner_url: str) -> str:
    uid_q = _uid_query(uid)
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Colecao"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Collection center</div>
    <h1 class="hero-title">Colecao Baltigo</h1>
    <p class="hero-subtitle">Uma colecao viva, sincronizada com a loja e com o comando tradicional, pronta para refletir novas fotos, cards removidos e mudancas na conta sem poluir a tela.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Jogador</span><span class="metric-value" id="collectionPlayerHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Unicos</span><span class="metric-value" id="collectionUniqueHero">0</span></div>
      <div class="metric-card"><span class="metric-label">Copias</span><span class="metric-value" id="collectionCopiesHero">0</span></div>
      <div class="metric-card"><span class="metric-label">Completas</span><span class="metric-value" id="collectionCompletedHero">0</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Visao geral</div><h2 class="section-title">Sua estante pessoal</h2></div>
    <div class="section-meta" id="collectionMeta">Carregando colecao...</div>
  </div>
  <div class="pill-row" style="margin-top:14px;">
    <span class="soft-pill soft-pill--cool" id="collectionNicknamePill">Conta: ...</span>
    <span class="soft-pill" id="collectionFavoritePill">Favorito: --</span>
    <span class="soft-pill">Live sync 5s</span>
  </div>
  <div class="segmented" style="margin-top:14px;">
    <button type="button" class="segmented-btn active" id="collectionTabCards">Cards</button>
    <button type="button" class="segmented-btn" id="collectionTabAnimes">Obras</button>
    <button type="button" class="segmented-btn" id="collectionTabMissing">Faltantes</button>
  </div>
  <label class="searchbar" style="margin-top:14px;">
    <span class="input-icon">Busca</span>
    <input id="collectionSearchInput" type="text" placeholder="Buscar personagem ou anime...">
  </label>
</section>

<section class="panel panel--soft" id="collectionCardsView">
  <div class="section-head">
    <div><div class="section-kicker">Cards</div><h2 class="section-title">Personagens que ja sao seus</h2></div>
    <div class="section-meta" id="collectionCardsMeta">Preparando grid...</div>
  </div>
  <div class="media-grid" id="collectionCardsGrid" style="margin-top:14px;"></div>
  <div id="collectionCardsEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Colecao vazia</strong>Quando voce receber personagens, eles aparecem aqui automaticamente.</div>
</section>

<section class="panel panel--soft" id="collectionAnimesView" style="display:none;">
  <div class="section-head">
    <div><div class="section-kicker">Obras</div><h2 class="section-title">Progresso por anime</h2></div>
    <div class="section-meta" id="collectionAnimesMeta">Preparando obras...</div>
  </div>
  <div class="media-grid" id="collectionAnimesGrid" style="margin-top:14px;"></div>
  <div id="collectionAnimesEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nenhuma obra iniciada</strong>Assim que voce tiver algum card, a obra correspondente aparece aqui.</div>
</section>

<section class="panel panel--soft" id="collectionMissingView" style="display:none;">
  <div class="section-head">
    <div><div class="section-kicker">Faltantes</div><h2 class="section-title">Obras para completar</h2></div>
    <div class="section-meta" id="collectionMissingMeta">Preparando faltantes...</div>
  </div>
  <div class="media-grid" id="collectionMissingGrid" style="margin-top:14px;"></div>
  <div id="collectionMissingEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nada faltando</strong>As obras completas ficam aqui marcadas como finalizadas.</div>
</section>

<div id="collectionNote" class="floating-note">Colecao sendo carregada...</div>
<div class="footer-note">Source Baltigo . Collection</div>

<div class="sheet-backdrop" id="collectionDetailBackdrop">
  <div class="sheet">
    <div class="sheet-head">
      <div>
        <h3 class="sheet-title" id="collectionDetailTitle">Detalhes da obra</h3>
        <div class="section-meta" id="collectionDetailMeta">Carregando...</div>
      </div>
      <button class="control-btn" id="closeCollectionDetailBtn">Fechar</button>
    </div>
    <div class="sheet-body">
      <div class="segmented">
        <button type="button" class="segmented-btn active" id="collectionDetailOwnedBtn">Meus cards</button>
        <button type="button" class="segmented-btn" id="collectionDetailMissingBtn">Faltam</button>
      </div>
      <div class="segmented" style="margin-top:10px;">
        <button type="button" class="segmented-btn" id="collectionDetailGalleryBtn">Galeria</button>
        <a class="segmented-btn" id="collectionDetailShopLink" href="/shop{uid_q}">Abrir loja</a>
      </div>
      <div class="media-grid" id="collectionDetailGrid" style="margin-top:14px;"></div>
      <div id="collectionDetailEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nada para mostrar</strong>Troque o modo ou espere a colecao sincronizar.</div>
    </div>
  </div>
</div>
"""
    js = f"""
const COLLECTION_UID = resolveWebappUid({int(uid)});
const collectionNote = document.getElementById("collectionNote");
const collectionState = {{
  profile: null,
  stats: null,
  cards: [],
  animes: [],
  tab: "cards",
  q: "",
  detailAnimeId: 0,
  detailMode: "owned"
}};
const tgCollection = getTelegramWebApp();
if (tgCollection) {{ try {{ tgCollection.ready(); tgCollection.expand(); }} catch(err) {{}} }}
function setCollectionNote(message, tone){{ collectionNote.textContent = message || ""; collectionNote.dataset.tone = tone || ""; }}
function collectionDisplayName(){{
  const profile = collectionState.profile || {{}};
  return String(profile.nickname || profile.display_name || profile.full_name || (COLLECTION_UID > 0 ? ("UID " + COLLECTION_UID) : "Jogador"));
}}
function syncCollectionHero(){{
  const profile = collectionState.profile || {{}};
  const stats = collectionState.stats || {{}};
  document.getElementById("collectionPlayerHero").textContent = collectionDisplayName();
  document.getElementById("collectionUniqueHero").textContent = String(stats.unique_cards || 0);
  document.getElementById("collectionCopiesHero").textContent = String(stats.total_copies || 0);
  document.getElementById("collectionCompletedHero").textContent = String(stats.completed_animes || 0);
  document.getElementById("collectionNicknamePill").textContent = profile.nickname ? ("@" + profile.nickname) : (profile.display_name || "Conta sem nickname");
  document.getElementById("collectionFavoritePill").textContent = "Favorito: " + String(stats.favorite_name || "--");
  document.getElementById("collectionMeta").textContent = "Atualizado " + humanClock() + " . Unicos " + String(stats.unique_cards || 0) + " . Copias " + String(stats.total_copies || 0);
}}
function filterCollectionCards(){{
  const q = String(collectionState.q || "").trim().toLowerCase();
  return collectionState.cards.filter(function(item){{
    if (!q) return true;
    const hay = (String(item.name || "") + " " + String(item.anime || "") + " " + String(item.character_id || "")).toLowerCase();
    return hay.includes(q);
  }});
}}
function filterCollectionAnimes(mode){{
  const q = String(collectionState.q || "").trim().toLowerCase();
  return collectionState.animes.filter(function(item){{
    if (mode === "missing" && !(Number(item.missing_count || 0) > 0)) return false;
    if (!q) return true;
    return String(item.anime || "").toLowerCase().includes(q);
  }});
}}
function renderCollectionCards(){{
  const items = filterCollectionCards();
  const root = document.getElementById("collectionCardsGrid");
  const empty = document.getElementById("collectionCardsEmpty");
  document.getElementById("collectionCardsMeta").textContent = "Mostrando " + String(items.length) + " personagens da sua conta";
  if (!items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = items.map(function(item){{
    const badge = item.subcategory ? String(item.subcategory) : "Card";
    const img = item.image ? '<img src="' + esc(item.image) + '" alt="' + esc(item.name) + '" loading="lazy" onerror="setImageFallback(this,\\'CARD\\')">' : "";
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge">' + esc(badge) + '</div><div class="media-count">x' + esc(item.quantity || 0) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.name) + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(item.anime || "") + '</span><span class="soft-pill">ID ' + esc(item.character_id || 0) + '</span></div></div>'
      + '</article>';
  }}).join("");
}}
function renderCollectionAnimeSummary(targetId, emptyId, metaId, mode){{
  const items = filterCollectionAnimes(mode);
  const root = document.getElementById(targetId);
  const empty = document.getElementById(emptyId);
  const meta = document.getElementById(metaId);
  meta.textContent = "Mostrando " + String(items.length) + " obras";
  if (!items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = items.map(function(item){{
    const img = item.cover_image ? '<img src="' + esc(item.cover_image) + '" alt="' + esc(item.anime) + '" loading="lazy" onerror="setImageFallback(this,\\'ANIME\\')">' : '';
    const pct = String(item.completion_pct || 0) + "%";
    const actionMode = mode === "missing" ? "missing" : "owned";
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge media-badge--cool">' + esc(pct) + '</div><div class="media-count">' + esc(item.owned_count || 0) + '/' + esc(item.total_count || 0) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.anime) + '</h3><div class="pill-row"><span class="soft-pill">Faltam ' + esc(item.missing_count || 0) + '</span><span class="soft-pill soft-pill--accent">Obra</span></div><button class="action-btn action-btn--cool" style="width:100%; margin-top:14px;" data-open-anime="' + esc(item.anime_id) + '" data-open-mode="' + esc(actionMode) + '">Abrir detalhes</button></div>'
      + '</article>';
  }}).join("");
  root.querySelectorAll("[data-open-anime]").forEach(function(button){{
    button.onclick = function(){{
      openCollectionDetail(Number(button.getAttribute("data-open-anime") || 0), String(button.getAttribute("data-open-mode") || "owned"));
    }};
  }});
}}
function applyCollectionView(){{
  document.getElementById("collectionTabCards").classList.toggle("active", collectionState.tab === "cards");
  document.getElementById("collectionTabAnimes").classList.toggle("active", collectionState.tab === "animes");
  document.getElementById("collectionTabMissing").classList.toggle("active", collectionState.tab === "missing");
  document.getElementById("collectionCardsView").style.display = collectionState.tab === "cards" ? "" : "none";
  document.getElementById("collectionAnimesView").style.display = collectionState.tab === "animes" ? "" : "none";
  document.getElementById("collectionMissingView").style.display = collectionState.tab === "missing" ? "" : "none";
  document.getElementById("collectionSearchInput").placeholder = collectionState.tab === "cards" ? "Buscar personagem ou anime..." : "Buscar obra...";
  renderCollectionCards();
  renderCollectionAnimeSummary("collectionAnimesGrid", "collectionAnimesEmpty", "collectionAnimesMeta", "animes");
  renderCollectionAnimeSummary("collectionMissingGrid", "collectionMissingEmpty", "collectionMissingMeta", "missing");
}}
function collectionDetailOpen(){{
  return document.getElementById("collectionDetailBackdrop").style.display === "flex";
}}
function closeCollectionDetail(){{
  document.getElementById("collectionDetailBackdrop").style.display = "none";
}}
async function loadCollectionDetail(options){{
  if (!collectionState.detailAnimeId) return;
  const response = await authJson("/api/collection/anime?anime_id=" + encodeURIComponent(collectionState.detailAnimeId) + "&mode=" + encodeURIComponent(collectionState.detailMode), {{ uid: COLLECTION_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar detalhes da obra.");
  const data = response.data;
  const anime = data.anime || {{}};
  const items = Array.isArray(data.items) ? data.items : [];
  document.getElementById("collectionDetailTitle").textContent = anime.anime || "Detalhes da obra";
  document.getElementById("collectionDetailMeta").textContent = "Modo " + String(collectionState.detailMode).toUpperCase() + " . " + String(data.owned_count || 0) + "/" + String(data.total_count || 0) + " coletados";
  document.getElementById("collectionDetailOwnedBtn").classList.toggle("active", collectionState.detailMode === "owned");
  document.getElementById("collectionDetailMissingBtn").classList.toggle("active", collectionState.detailMode === "missing");
  document.getElementById("collectionDetailGalleryBtn").classList.toggle("active", collectionState.detailMode === "gallery");
  document.getElementById("collectionDetailShopLink").href = "/shop" + ({_j(uid_q)} || ("?uid=" + COLLECTION_UID));
  const root = document.getElementById("collectionDetailGrid");
  const empty = document.getElementById("collectionDetailEmpty");
  if (!items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = items.map(function(item){{
    const badge = collectionState.detailMode === "missing" ? "Falta" : (item.subcategory || (item.owned ? "Card" : "Galeria"));
    const countLabel = item.owned ? ("x" + String(item.quantity || 0)) : "ID " + String(item.id || 0);
    const img = item.image ? '<img src="' + esc(item.image) + '" alt="' + esc(item.name) + '" loading="lazy" onerror="setImageFallback(this,\\'CARD\\')">' : '';
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge">' + esc(badge) + '</div><div class="media-count">' + esc(countLabel) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.name || "Personagem") + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(item.anime || anime.anime || "") + '</span>' + (item.owned ? '<span class="soft-pill">Seu</span>' : '<span class="soft-pill soft-pill--accent">Falta</span>') + '</div></div>'
      + '</article>';
  }}).join("");
}}
async function openCollectionDetail(animeId, mode){{
  collectionState.detailAnimeId = Number(animeId || 0);
  collectionState.detailMode = String(mode || "owned");
  document.getElementById("collectionDetailBackdrop").style.display = "flex";
  setSkeleton("collectionDetailGrid", 4);
  try {{
    await loadCollectionDetail({{ silent: false }});
  }} catch(err) {{
    setCollectionNote(err.message, "error");
  }}
}}
async function loadCollectionState(options){{
  const response = await authJson("/api/collection/state", {{ uid: COLLECTION_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar resumo da colecao.");
  collectionState.profile = response.data.profile || null;
  collectionState.stats = response.data.stats || null;
  syncCollectionHero();
  if (!(options && options.silent)) setCollectionNote("Resumo da colecao atualizado.", "success");
}}
async function loadCollectionCards(options){{
  const opts = options || {{}};
  if (!opts.silent && !collectionState.cards.length) setSkeleton("collectionCardsGrid", 6);
  const response = await authJson("/api/collection/cards", {{ uid: COLLECTION_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar cards da colecao.");
  collectionState.cards = Array.isArray(response.data.items) ? response.data.items : [];
  renderCollectionCards();
}}
async function loadCollectionAnimes(options){{
  const opts = options || {{}};
  if (!opts.silent && !collectionState.animes.length) {{
    setSkeleton("collectionAnimesGrid", 4);
    setSkeleton("collectionMissingGrid", 4);
  }}
  const response = await authJson("/api/collection/animes", {{ uid: COLLECTION_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar obras da colecao.");
  collectionState.animes = Array.isArray(response.data.items) ? response.data.items : [];
  renderCollectionAnimeSummary("collectionAnimesGrid", "collectionAnimesEmpty", "collectionAnimesMeta", "animes");
  renderCollectionAnimeSummary("collectionMissingGrid", "collectionMissingEmpty", "collectionMissingMeta", "missing");
}}
async function refreshCollection(){{
  await loadCollectionState({{ silent: true }});
  await loadCollectionCards({{ silent: true }});
  await loadCollectionAnimes({{ silent: true }});
  if (collectionDetailOpen()) await loadCollectionDetail({{ silent: true }});
}}
document.getElementById("collectionSearchInput").addEventListener("input", debounce(function(event){{
  collectionState.q = String(event.target.value || "");
  applyCollectionView();
}}, 140));
document.getElementById("collectionTabCards").onclick = function(){{ collectionState.tab = "cards"; applyCollectionView(); }};
document.getElementById("collectionTabAnimes").onclick = function(){{ collectionState.tab = "animes"; applyCollectionView(); }};
document.getElementById("collectionTabMissing").onclick = function(){{ collectionState.tab = "missing"; applyCollectionView(); }};
document.getElementById("closeCollectionDetailBtn").onclick = closeCollectionDetail;
document.getElementById("collectionDetailBackdrop").onclick = function(event){{ if (event.target.id === "collectionDetailBackdrop") closeCollectionDetail(); }};
document.getElementById("collectionDetailOwnedBtn").onclick = async function(){{ collectionState.detailMode = "owned"; await loadCollectionDetail({{ silent: false }}); }};
document.getElementById("collectionDetailMissingBtn").onclick = async function(){{ collectionState.detailMode = "missing"; await loadCollectionDetail({{ silent: false }}); }};
document.getElementById("collectionDetailGalleryBtn").onclick = async function(){{ collectionState.detailMode = "gallery"; await loadCollectionDetail({{ silent: false }}); }};
(async function(){{
  try {{
    await loadCollectionState({{ silent: true }});
    await loadCollectionCards({{ silent: false }});
    await loadCollectionAnimes({{ silent: false }});
    applyCollectionView();
    createLiveRefresh(refreshCollection, 5000);
  }} catch(err) {{
    setCollectionNote(err.message, "error");
  }}
}})();
"""
    return _page_template("Colecao", body, extra_js=js, include_tg=True)


def build_memory_page(*, uid: int = 0, banner_url: str, default_level: str = "medium") -> str:
    safe_level = str(default_level or "medium").strip().lower()
    if safe_level not in {"easy", "medium", "hard", "extreme"}:
        safe_level = "medium"

    extra_css = r"""
.memory-shell{
  display:grid;
  gap:14px;
}
.memory-top{
  overflow:hidden;
  padding:0;
}
.memory-banner{
  position:relative;
  overflow:hidden;
  aspect-ratio:16 / 8;
  border-bottom:1px solid rgba(255,255,255,.06);
  background:
    radial-gradient(circle at 20% 18%, rgba(122,213,255,.16), transparent 34%),
    linear-gradient(180deg, rgba(12,18,36,.98), rgba(7,10,20,.98));
}
.memory-banner img{
  width:100%;
  height:100%;
  object-fit:cover;
  object-position:center;
  display:block;
}
.memory-banner::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(5,8,16,.08), rgba(5,8,16,.68));
}
.memory-top-body{
  padding:16px;
}
.memory-head{
  display:grid;
  gap:6px;
}
.memory-title{
  margin:0;
  font-family:"Space Grotesk", "Plus Jakarta Sans", sans-serif;
  font-size:32px;
  line-height:.96;
  letter-spacing:-.05em;
}
.memory-sub{
  margin:0;
  color:var(--muted-strong);
  font-size:13px;
  line-height:1.45;
}
.memory-status{
  color:var(--muted);
  font-size:12px;
  line-height:1.45;
}
.memory-difficulty{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  margin-top:14px;
}
.memory-difficulty .segmented-btn{
  min-height:52px;
  font-size:13px;
  letter-spacing:.08em;
}
.memory-toolbar{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  margin-top:14px;
}
.memory-stat{
  padding:14px;
  border-radius:18px;
  border:1px solid rgba(255,255,255,.10);
  background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.025));
}
.memory-stat-label{
  display:block;
  color:var(--muted);
  font-size:10px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
.memory-stat-value{
  display:block;
  margin-top:6px;
  font-family:"Space Grotesk", "Plus Jakarta Sans", sans-serif;
  font-size:22px;
  font-weight:800;
  line-height:1.02;
}
.memory-actions{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  margin-top:14px;
}
.memory-actions .action-btn{
  width:100%;
  min-height:50px;
}
.memory-board-panel{
  padding-top:16px;
}
.memory-board-head{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:10px;
}
.memory-board-head .section-meta{
  flex-shrink:0;
}
.memory-board{
  display:grid;
  gap:10px;
  margin-top:14px;
  grid-template-columns:repeat(2, minmax(0, 1fr));
}
.memory-board.level-medium{
  grid-template-columns:repeat(4, minmax(0, 1fr));
}
.memory-board.level-hard,
.memory-board.level-extreme{
  grid-template-columns:repeat(4, minmax(0, 1fr));
}
.memory-card{
  position:relative;
  width:100%;
  aspect-ratio:.72;
  border:0;
  padding:0;
  background:none;
  cursor:pointer;
  -webkit-tap-highlight-color:transparent;
}
.memory-card:disabled{
  cursor:default;
}
.memory-card__face{
  position:absolute;
  inset:0;
  overflow:hidden;
  border-radius:18px;
  border:1px solid rgba(255,255,255,.10);
  box-shadow:0 14px 28px rgba(0,0,0,.24);
  transition:opacity .24s ease, transform .24s ease, box-shadow .24s ease, border-color .24s ease;
}
.memory-card__back{
  background:
    radial-gradient(circle at 20% 18%, rgba(122,213,255,.16), transparent 30%),
    radial-gradient(circle at 84% 0%, rgba(255,111,148,.14), transparent 24%),
    linear-gradient(180deg, rgba(14,21,40,.98), rgba(8,11,20,.98));
}
.memory-card__back::before,
.memory-card__back::after{
  content:"";
  position:absolute;
  left:50%;
  top:50%;
  transform:translate(-50%, -50%);
  border-radius:18px;
}
.memory-card__back::before{
  width:54%;
  height:54%;
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.02);
  box-shadow:inset 0 0 0 1px rgba(122,213,255,.08);
}
.memory-card__back::after{
  width:22%;
  height:22%;
  border-radius:999px;
  background:linear-gradient(180deg, rgba(122,213,255,.42), rgba(255,111,148,.34));
  box-shadow:0 0 0 8px rgba(255,255,255,.03);
}
.memory-card__front{
  opacity:0;
  transform:scale(.96);
  background:linear-gradient(180deg, rgba(12,18,34,.22), rgba(6,10,20,.80));
}
.memory-card__front img{
  width:100%;
  height:100%;
  object-fit:cover;
  object-position:center;
  display:block;
}
.memory-card.is-open .memory-card__back,
.memory-card.is-matched .memory-card__back{
  opacity:0;
  transform:scale(.94);
}
.memory-card.is-open .memory-card__front,
.memory-card.is-matched .memory-card__front{
  opacity:1;
  transform:scale(1);
}
.memory-card.is-matched .memory-card__front{
  border-color:rgba(81,222,181,.38);
  box-shadow:0 16px 30px rgba(81,222,181,.16), 0 10px 20px rgba(0,0,0,.22);
}
.memory-card.is-locked{
  pointer-events:none;
}
.memory-result{
  display:grid;
  gap:14px;
}
.memory-result-grid{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:12px;
}
.memory-record{
  margin-top:12px;
  color:var(--muted-strong);
  font-size:13px;
  line-height:1.6;
}
.memory-record strong{
  color:var(--text);
}
.memory-foot{
  color:var(--muted);
  font-size:12px;
  line-height:1.55;
}
@keyframes memoryCardIn{
  from{ opacity:0; transform:translateY(14px) scale(.96); }
  to{ opacity:1; transform:translateY(0) scale(1); }
}
@media (max-width:560px){
  .memory-title{
    font-size:26px;
  }
  .memory-banner{
    aspect-ratio:16 / 9;
  }
  .memory-toolbar,
  .memory-actions,
  .memory-difficulty{
    gap:9px;
  }
  .memory-stat{
    padding:13px;
  }
  .memory-stat-value{
    font-size:20px;
  }
  .memory-board{
    gap:8px;
  }
  .memory-card__face{
    border-radius:16px;
  }
  .memory-result-grid{
    grid-template-columns:1fr;
  }
}
@media (min-width:720px){
  .memory-toolbar{
    grid-template-columns:repeat(4, minmax(0, 1fr));
  }
  .memory-difficulty{
    grid-template-columns:repeat(4, minmax(0, 1fr));
  }
  .memory-board.level-easy{
    grid-template-columns:repeat(4, minmax(0, 1fr));
  }
  .memory-board.level-medium{
    grid-template-columns:repeat(4, minmax(0, 1fr));
  }
  .memory-board.level-hard{
    grid-template-columns:repeat(6, minmax(0, 1fr));
  }
  .memory-board.level-extreme{
    grid-template-columns:repeat(6, minmax(0, 1fr));
  }
}
"""

    body = f"""
<div class="memory-shell">
  <section class="panel panel--soft memory-top">
    <div class="memory-banner"><img id="memoryHeroImage" src="{_h(banner_url)}" alt="Memory anime"></div>
    <div class="memory-top-body">
      <div class="memory-head">
        <h1 class="memory-title">Memoria anime</h1>
        <p class="memory-sub">Forme pares usando capas e banners do catalogo de /cards.</p>
        <div class="memory-status" id="memoryStatus">Preparando as obras...</div>
      </div>
      <div class="memory-difficulty" id="memoryLevelTabs">
        <button type="button" class="segmented-btn" data-level="easy">Facil</button>
        <button type="button" class="segmented-btn" data-level="medium">Medio</button>
        <button type="button" class="segmented-btn" data-level="hard">Dificil</button>
        <button type="button" class="segmented-btn" data-level="extreme">Muito dificil</button>
      </div>
      <div class="memory-toolbar">
        <article class="memory-stat"><span class="memory-stat-label">Jogadas</span><span class="memory-stat-value" id="memoryMovesValue">0</span></article>
        <article class="memory-stat"><span class="memory-stat-label">Pares</span><span class="memory-stat-value" id="memoryPairsValue">0/0</span></article>
        <article class="memory-stat"><span class="memory-stat-label">Tempo</span><span class="memory-stat-value" id="memoryTimerValue">00:00</span></article>
        <article class="memory-stat"><span class="memory-stat-label">Recorde</span><span class="memory-stat-value" id="memoryBestValue">--</span></article>
      </div>
      <div class="memory-actions">
        <button type="button" class="action-btn action-btn--cool" id="memoryNewBoardBtn">Novo</button>
        <button type="button" class="action-btn" id="memoryRestartBtn">Reiniciar</button>
      </div>
    </div>
  </section>

  <section class="panel panel--soft memory-board-panel">
    <div class="memory-board-head">
      <div>
        <div class="section-kicker">Tabuleiro</div>
        <h2 class="section-title">Encontre todos os pares</h2>
      </div>
      <div class="section-meta" id="memoryBoardMeta">Carregando...</div>
    </div>
    <div id="memoryBoard" class="memory-board level-medium"></div>
    <div id="memoryEmpty" class="empty-state" style="display:none; margin-top:14px;">
      <strong>Sem imagens suficientes</strong>
      O jogo precisa de obras com imagem valida no catalogo.
    </div>
  </section>

  <section class="panel panel--soft" id="memoryResultPanel" style="display:none;">
    <div class="memory-result">
      <div class="section-head">
        <div><div class="section-kicker">Resultado</div><h2 class="section-title">Voce fechou o tabuleiro</h2></div>
        <div class="section-meta" id="memoryResultMeta">Fim de partida</div>
      </div>
      <div class="memory-result-grid">
        <article class="memory-stat"><span class="memory-stat-label">Tempo</span><span class="memory-stat-value" id="memoryResultTime">00:00</span></article>
        <article class="memory-stat"><span class="memory-stat-label">Jogadas</span><span class="memory-stat-value" id="memoryResultMoves">0</span></article>
      </div>
      <div class="memory-record" id="memoryRecordText">Seu melhor tempo aparece aqui.</div>
      <div class="memory-actions">
        <button type="button" class="action-btn action-btn--primary" id="memoryPlayAgainBtn">Novo sorteio</button>
        <button type="button" class="action-btn action-btn--cool" id="memoryKeepLevelBtn">Mesmo nivel</button>
      </div>
      <div class="memory-foot">As cartas usam imagens reais do catalogo, entao cada partida pode puxar obras diferentes.</div>
    </div>
  </section>
</div>
"""

    js = f"""
const MEMORY_DEFAULT_LEVEL = {_j(safe_level)};
const MEMORY_HERO_FALLBACK = {_j(banner_url)};
const MEMORY_UID = resolveWebappUid({int(uid)});
const tgMemory = getTelegramWebApp();
if (tgMemory) {{ try {{ tgMemory.ready(); tgMemory.expand(); }} catch(err) {{}} }}

const memoryLevels = {{
  easy: {{
    label: "F\\u00e1cil",
    pairs: 6,
    helper: "Entrada suave para partidas curtinhas e leitura f\\u00e1cil do tabuleiro."
  }},
  medium: {{
    label: "M\\u00e9dio",
    pairs: 8,
    helper: "Boa medida para uma rodada r\\u00e1pida sem ficar trivial."
  }},
  hard: {{
    label: "Dif\\u00edcil",
    pairs: 12,
    helper: "Mais animes em campo e menos espa\\u00e7o para erro."
  }},
  extreme: {{
    label: "Muito dif\\u00edcil",
    pairs: 18,
    helper: "Grade grande para quem quer se testar de verdade."
  }}
}};

const memoryEls = {{
  heroImage: document.getElementById("memoryHeroImage"),
  status: document.getElementById("memoryStatus"),
  boardMeta: document.getElementById("memoryBoardMeta"),
  board: document.getElementById("memoryBoard"),
  empty: document.getElementById("memoryEmpty"),
  moves: document.getElementById("memoryMovesValue"),
  pairs: document.getElementById("memoryPairsValue"),
  timer: document.getElementById("memoryTimerValue"),
  best: document.getElementById("memoryBestValue"),
  resultPanel: document.getElementById("memoryResultPanel"),
  resultMeta: document.getElementById("memoryResultMeta"),
  resultTime: document.getElementById("memoryResultTime"),
  resultMoves: document.getElementById("memoryResultMoves"),
  recordText: document.getElementById("memoryRecordText"),
  tabs: Array.from(document.querySelectorAll("[data-level]"))
}};

const memoryState = {{
  catalog: [],
  level: MEMORY_DEFAULT_LEVEL,
  deck: [],
  flippedIds: [],
  busy: false,
  moves: 0,
  matches: 0,
  totalPairs: 0,
  elapsedMs: 0,
  startedAt: 0,
  timerHandle: null,
  best: loadMemoryBest(),
  currentSelection: []
}};

if (memoryEls.heroImage) {{
  memoryEls.heroImage.onerror = function(){{
    this.src = MEMORY_HERO_FALLBACK;
  }};
}}

function setMemoryNote(message, tone){{
  memoryEls.status.textContent = String(message || "");
  memoryEls.status.dataset.tone = tone || "";
}}

function normalizeMemoryLevel(level){{
  const raw = String(level || "").trim().toLowerCase();
  if (memoryLevels[raw]) return raw;
  if (raw === "facil") return "easy";
  if (raw === "medio") return "medium";
  if (raw === "dificil") return "hard";
  if (raw === "muito-dificil" || raw === "muito_dificil" || raw === "muitodificil") return "extreme";
  return "medium";
}}

function loadMemoryBest(){{
  try{{
    const raw = localStorage.getItem("source-baltigo-memory-best-v1");
    const data = raw ? JSON.parse(raw) : {{}};
    return data && typeof data === "object" ? data : {{}};
  }}catch(err){{
    return {{}};
  }}
}}

function saveMemoryBest(){{
  try{{
    localStorage.setItem("source-baltigo-memory-best-v1", JSON.stringify(memoryState.best || {{}}));
  }}catch(err){{}}
}}

function applyMemoryBest(level, timeMs, moves){{
  const safeLevel = normalizeMemoryLevel(level);
  const safeTimeMs = Number(timeMs || 0);
  const safeMoves = Number(moves || 0);
  if (!safeLevel || !safeTimeMs || !safeMoves) return;
  memoryState.best[safeLevel] = {{
    timeMs: safeTimeMs,
    moves: safeMoves
  }};
  saveMemoryBest();
}}

function formatMemoryDuration(ms){{
  const totalSeconds = Math.max(0, Math.floor(Number(ms || 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
}}

function memoryBestLabel(level){{
  const entry = (memoryState.best || {{}})[String(level || "")] || null;
  if (!entry || !entry.timeMs) return "--";
  return formatMemoryDuration(entry.timeMs) + " . " + String(entry.moves || 0) + " jog.";
}}

function renderMemoryResultState(level, current, isBest, metaText){{
  const best = (memoryState.best || {{}})[level] || current;
  memoryEls.resultMeta.textContent = metaText || (isBest ? "Novo recorde salvo neste n\\u00edvel." : "Partida conclu\\u00edda com sucesso.");
  memoryEls.resultTime.textContent = formatMemoryDuration(current.timeMs || 0);
  memoryEls.resultMoves.textContent = String(current.moves || 0);
  memoryEls.recordText.innerHTML = isBest
    ? "<strong>Recorde novo.</strong> Tempo " + esc(formatMemoryDuration(best.timeMs || 0)) + " com " + esc(best.moves || 0) + " jogadas."
    : "Seu melhor neste n\\u00edvel est\\u00e1 em <strong>" + esc(formatMemoryDuration(best.timeMs || 0)) + "</strong> com <strong>" + esc(best.moves || 0) + "</strong> jogadas.";
  memoryEls.resultPanel.style.display = "";
}}

async function loadMemoryRemoteBest(){{
  try{{
    const response = await authJson("/api/memory/best", {{ uid: MEMORY_UID }});
    if (!response.ok || !response.data || !response.data.ok) return;
    const byLevel = response.data.by_level || {{}};
    Object.keys(byLevel).forEach(function(level){{
      const entry = byLevel[level] || {{}};
      applyMemoryBest(level, Number(entry.time_ms || 0), Number(entry.moves || 0));
    }});
    syncMemoryChrome();
  }}catch(err){{
    console.warn("memory best sync failed", err);
  }}
}}

async function persistMemoryResult(level, current){{
  const response = await authJson("/api/memory/finish", {{
    uid: MEMORY_UID,
    method: "POST",
    json: {{
      level: level,
      time_ms: Number(current.timeMs || 0),
      moves: Number(current.moves || 0)
    }}
  }});
  if (!response.ok || !response.data || !response.data.ok){{
    throw new Error((response.data && response.data.message) ? response.data.message : "Nao consegui salvar o resultado.");
  }}
  const best = response.data.best || {{}};
  return {{
    newRecord: !!response.data.new_record,
    best: {{
      timeMs: Number(best.time_ms || 0),
      moves: Number(best.moves || 0)
    }}
  }};
}}

function updateMemoryHeroBanner(){{
  const featured = Array.isArray(memoryState.currentSelection) && memoryState.currentSelection.length
    ? memoryState.currentSelection[Math.floor(Math.random() * memoryState.currentSelection.length)]
    : null;
  const image = featured && (featured.hero || featured.image) ? (featured.hero || featured.image) : MEMORY_HERO_FALLBACK;
  if (memoryEls.heroImage) memoryEls.heroImage.src = image || MEMORY_HERO_FALLBACK;
}}

function syncMemoryChrome(){{
  const level = memoryLevels[memoryState.level] || memoryLevels.medium;
  const catalogTotal = Array.isArray(memoryState.catalog) ? memoryState.catalog.length : 0;
  memoryEls.moves.textContent = String(memoryState.moves || 0);
  memoryEls.pairs.textContent = String(memoryState.matches || 0) + "/" + String(memoryState.totalPairs || 0);
  memoryEls.timer.textContent = formatMemoryDuration(memoryState.elapsedMs);
  memoryEls.best.textContent = memoryBestLabel(memoryState.level);
  memoryEls.status.textContent = String(catalogTotal || 0) + " obras prontas . Nivel " + String(level.label);
  memoryEls.tabs.forEach(function(button){{
    const active = String(button.getAttribute("data-level") || "") === memoryState.level;
    button.classList.toggle("active", active);
  }});
}}

function stopMemoryTimer(){{
  if (memoryState.timerHandle) {{
    window.clearInterval(memoryState.timerHandle);
    memoryState.timerHandle = null;
  }}
}}

function startMemoryTimer(){{
  if (memoryState.timerHandle) return;
  memoryState.startedAt = Date.now() - Number(memoryState.elapsedMs || 0);
  memoryState.timerHandle = window.setInterval(function(){{
    memoryState.elapsedMs = Math.max(0, Date.now() - Number(memoryState.startedAt || Date.now()));
    syncMemoryChrome();
  }}, 250);
}}

function shuffleMemoryItems(items){{
  const clone = Array.isArray(items) ? items.slice() : [];
  for (let index = clone.length - 1; index > 0; index -= 1){{
    const other = Math.floor(Math.random() * (index + 1));
    const tmp = clone[index];
    clone[index] = clone[other];
    clone[other] = tmp;
  }}
  return clone;
}}

function parseMemoryLevelFromQuery(){{
  try{{
    const params = new URLSearchParams(window.location.search || "");
    return normalizeMemoryLevel(params.get("level") || MEMORY_DEFAULT_LEVEL);
  }}catch(err){{
    return normalizeMemoryLevel(MEMORY_DEFAULT_LEVEL);
  }}
}}

function updateMemoryUrlLevel(){{
  try{{
    const url = new URL(window.location.href);
    url.searchParams.set("level", memoryState.level);
    window.history.replaceState({{}}, "", url.pathname + url.search);
  }}catch(err){{}}
}}

function memoryCardClass(card){{
  const flipped = !!card.revealed || !!card.matched;
  const matched = !!card.matched;
  const disabled = matched || memoryState.busy || memoryState.flippedIds.length >= 2;
  return [
    "memory-card",
    flipped ? "is-open" : "",
    matched ? "is-matched" : "",
    disabled && !flipped ? "is-locked" : ""
  ].filter(Boolean).join(" ");
}}

function buildMemoryCardMarkup(card, index){{
  const classes = memoryCardClass(card);
  const badge = "Par " + String(card.position || 0);
  const safeImage = esc(card.image || "");
  return ''
    + '<button type="button" class="' + classes + '" data-cardid="' + esc(card.id) + '" data-entry style="animation-delay:' + String(index * 24) + 'ms;">'
    +   '<span class="memory-card__face memory-card__back" aria-hidden="true"></span>'
    +   '<span class="memory-card__face memory-card__front">' + (safeImage ? '<img src="' + safeImage + '" alt="' + esc(badge) + '" loading="lazy" onerror="this.remove()">' : '') + '</span>'
    + '</button>';
}}

function syncMemoryBoardNodes(){{
  const nodes = Array.from(memoryEls.board.querySelectorAll("[data-cardid]"));
  memoryState.deck.forEach(function(card, index){{
    const node = nodes[index];
    if (!node) return;
    node.className = memoryCardClass(card);
    node.disabled = !!card.matched || !!memoryState.busy || (memoryState.flippedIds.length >= 2 && !card.revealed);
  }});
}}

function renderMemoryBoard(forceRebuild){{
  const root = memoryEls.board;
  const config = memoryLevels[memoryState.level] || memoryLevels.medium;
  root.className = "memory-board level-" + String(memoryState.level || "medium");
  if (!memoryState.deck.length){{
    root.innerHTML = "";
    memoryEls.empty.style.display = "";
    memoryEls.boardMeta.textContent = "Sem pares suficientes para montar o tabuleiro.";
    return;
  }}
  memoryEls.empty.style.display = "none";
  if (forceRebuild || root.childElementCount !== memoryState.deck.length){{
    root.innerHTML = memoryState.deck.map(function(card, index){{
      return buildMemoryCardMarkup(card, index);
    }}).join("");
    root.querySelectorAll("[data-cardid]").forEach(function(button){{
      button.onclick = function(){{
        handleMemoryFlip(button.getAttribute("data-cardid") || "");
      }};
    }});
  }} else {{
    syncMemoryBoardNodes();
  }}
  memoryEls.boardMeta.textContent = "N\\u00edvel " + config.label + " . " + String(memoryState.totalPairs || 0) + " pares . " + String(memoryState.deck.length || 0) + " cartas";
}}

function findMemoryCard(cardId){{
  return memoryState.deck.find(function(card){{ return String(card.id) === String(cardId); }}) || null;
}}

function resetMemoryState(){{
  stopMemoryTimer();
  memoryState.flippedIds = [];
  memoryState.busy = false;
  memoryState.moves = 0;
  memoryState.matches = 0;
  memoryState.totalPairs = 0;
  memoryState.elapsedMs = 0;
  memoryState.startedAt = 0;
  memoryEls.resultPanel.style.display = "none";
}}

function buildMemoryDeck(selection){{
  const deck = [];
  (selection || []).forEach(function(item, pairIndex){{
    for (let copy = 0; copy < 2; copy += 1){{
      deck.push({{
        id: String(item.anime_id) + "-" + String(pairIndex) + "-" + String(copy) + "-" + String(Math.random().toString(36).slice(2, 8)),
        pairId: String(item.anime_id),
        title: String(item.anime || "Anime"),
        image: String(item.image || ""),
        revealed: false,
        matched: false,
        position: pairIndex + 1
      }});
    }}
  }});
  return shuffleMemoryItems(deck);
}}

function pickMemorySelection(level, keepCurrent){{
  const config = memoryLevels[level] || memoryLevels.medium;
  const requiredPairs = Number(config.pairs || 0);
  if (keepCurrent && Array.isArray(memoryState.currentSelection) && memoryState.currentSelection.length === requiredPairs){{
    return memoryState.currentSelection.slice();
  }}
  const source = shuffleMemoryItems(memoryState.catalog).slice(0, requiredPairs);
  memoryState.currentSelection = source;
  return source;
}}

function openMemoryLevel(level, options){{
  const nextLevel = normalizeMemoryLevel(level);
  const config = memoryLevels[nextLevel] || memoryLevels.medium;
  const selection = pickMemorySelection(nextLevel, !!(options && options.keepSelection));
  resetMemoryState();
  memoryState.level = nextLevel;
  memoryState.totalPairs = selection.length;
  memoryState.deck = buildMemoryDeck(selection);
  updateMemoryUrlLevel();
  updateMemoryHeroBanner();
  syncMemoryChrome();
  renderMemoryBoard(true);
  setMemoryNote("Tabuleiro pronto . " + String(config.label) + " . " + String(config.pairs) + " pares.", "success");
}}

async function completeMemoryGame(){{
  stopMemoryTimer();
  const level = memoryState.level;
  const previous = (memoryState.best || {{}})[level] || null;
  const current = {{ timeMs: Number(memoryState.elapsedMs || 0), moves: Number(memoryState.moves || 0) }};
  let isBest = false;
  if (!previous || !previous.timeMs || current.timeMs < previous.timeMs || (current.timeMs === previous.timeMs && current.moves < (previous.moves || 0))){{
    applyMemoryBest(level, current.timeMs, current.moves);
    isBest = true;
  }}
  syncMemoryChrome();
  renderMemoryResultState(level, current, isBest, isBest ? "Novo recorde salvo neste n\\u00edvel." : "Partida conclu\\u00edda com sucesso.");
  setMemoryNote("Partida concluida.", "success");
  try{{
    const saved = await persistMemoryResult(level, current);
    if (saved && saved.best && saved.best.timeMs && saved.best.moves){{
      applyMemoryBest(level, saved.best.timeMs, saved.best.moves);
      syncMemoryChrome();
      renderMemoryResultState(
        level,
        current,
        !!saved.newRecord,
        saved.newRecord ? "Novo recorde salvo no ranking." : "Resultado sincronizado com o ranking."
      );
    }}
  }}catch(err){{
    console.warn("memory result sync failed", err);
    setMemoryNote("Partida concluida. O ranking nao sincronizou agora.", "");
  }}
}}

function resolveMemoryPair(){{
  const opened = memoryState.flippedIds.map(findMemoryCard).filter(Boolean);
  if (opened.length < 2){{
    memoryState.flippedIds = [];
    memoryState.busy = false;
    renderMemoryBoard();
    return;
  }}
  const first = opened[0];
  const second = opened[1];
  if (String(first.pairId) === String(second.pairId)){{
    first.matched = true;
    second.matched = true;
    memoryState.matches += 1;
    setMemoryNote("Par encontrado.", "success");
  }} else {{
    first.revealed = false;
    second.revealed = false;
    setMemoryNote("Nao foi par.", "");
  }}
  memoryState.flippedIds = [];
  memoryState.busy = false;
  renderMemoryBoard(false);
  syncMemoryChrome();
  if (memoryState.matches >= memoryState.totalPairs && memoryState.totalPairs > 0){{
    completeMemoryGame().catch(function(err){{
      console.error(err);
      setMemoryNote("Partida concluida, mas houve uma falha ao finalizar.", "error");
    }});
  }}
}}

function handleMemoryFlip(cardId){{
  if (!cardId || memoryState.busy) return;
  const card = findMemoryCard(cardId);
  if (!card || card.matched || card.revealed) return;
  if (!memoryState.startedAt) startMemoryTimer();
  card.revealed = true;
  memoryState.flippedIds.push(String(cardId));
  renderMemoryBoard(false);
  if (memoryState.flippedIds.length >= 2){{
    memoryState.moves += 1;
    memoryState.busy = true;
    syncMemoryBoardNodes();
    syncMemoryChrome();
    window.setTimeout(resolveMemoryPair, 760);
  }} else {{
    syncMemoryChrome();
  }}
}}

async function fetchMemoryCatalog(){{
  memoryEls.status.textContent = "Carregando obras do catalogo...";
  const response = await fetch("/api/cards/animes?limit=5000&_ts=" + Date.now());
  const data = await response.json();
  const items = Array.isArray(data.items) ? data.items : [];
  memoryState.catalog = items.map(function(item){{
    const cover = String(item.cover_image || "").trim();
    const banner = String(item.banner_image || "").trim();
    return {{
      anime_id: Number(item.anime_id || 0),
      anime: String(item.anime || "").trim(),
      image: cover || banner,
      hero: banner || cover
    }};
  }}).filter(function(item){{
    return item.anime_id > 0 && item.anime && item.image;
  }});
  if (!memoryState.catalog.length){{
    throw new Error("Nenhuma obra com banner dispon\\u00edvel.");
  }}
  memoryEls.status.textContent = String(memoryState.catalog.length) + " obras prontas para jogar.";
}}

document.getElementById("memoryNewBoardBtn").onclick = function(){{
  openMemoryLevel(memoryState.level, {{ keepSelection: false }});
}};

document.getElementById("memoryRestartBtn").onclick = function(){{
  openMemoryLevel(memoryState.level, {{ keepSelection: true }});
}};

document.getElementById("memoryPlayAgainBtn").onclick = function(){{
  openMemoryLevel(memoryState.level, {{ keepSelection: false }});
}};

document.getElementById("memoryKeepLevelBtn").onclick = function(){{
  openMemoryLevel(memoryState.level, {{ keepSelection: true }});
}};

memoryEls.tabs.forEach(function(button){{
  button.onclick = function(){{
    const level = button.getAttribute("data-level") || "medium";
    openMemoryLevel(level, {{ keepSelection: false }});
  }};
}});

(async function initMemoryGame(){{
  try{{
    const initialLevel = parseMemoryLevelFromQuery();
    memoryState.level = initialLevel;
    syncMemoryChrome();
    await loadMemoryRemoteBest();
    await fetchMemoryCatalog();
    openMemoryLevel(initialLevel, {{ keepSelection: false }});
  }}catch(err){{
    console.error(err);
    memoryState.deck = [];
    renderMemoryBoard();
    memoryEls.status.textContent = "Nao foi possivel carregar o jogo.";
    memoryEls.boardMeta.textContent = "Revise o catalogo de cards.";
    setMemoryNote("Erro ao carregar o jogo: " + (err && err.message ? err.message : "falha inesperada"), "error");
  }}
}})();
"""

    return _page_template("Jogo da Memoria", body, extra_css=extra_css, extra_js=js, include_tg=True)


def build_request_center_page(*, uid: int, banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Pedidos"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Request center</div>
    <h1 class="hero-title">Central de pedidos</h1>
    <p class="hero-subtitle">Peca animes, mangas e envie reports com a mesma identidade premium do resto do app, sem misturar informacao demais e com resposta rapida para toque mobile.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Jogador</span><span class="metric-value" id="requestPlayerHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Restantes</span><span class="metric-value" id="requestRemainingHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Fluxo</span><span class="metric-value">Anime . Manga . Report</span></div>
      <div class="metric-card"><span class="metric-label">Status</span><span class="metric-value"><span class="pulse-dot"></span> Pronto</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Pedidos</div><h2 class="section-title">Escolha o que voce quer fazer</h2></div>
    <div class="section-meta" id="requestMeta">Carregando limites...</div>
  </div>
  <div class="segmented" style="margin-top:14px;">
    <button type="button" class="segmented-btn active" id="requestTabAnime">Anime</button>
    <button type="button" class="segmented-btn" id="requestTabManga">Manga</button>
    <button type="button" class="segmented-btn" id="requestTabReport">Report</button>
  </div>
</section>

<section class="panel panel--soft" id="requestSearchView">
  <div class="section-head">
    <div><div class="section-kicker">Busca</div><h2 class="section-title" id="requestSearchTitle">Procure um anime</h2></div>
    <div class="section-meta" id="requestSearchMeta">Digite pelo menos 2 letras para comecar.</div>
  </div>
  <label class="searchbar" style="margin-top:14px;">
    <span class="input-icon">Busca</span>
    <input id="requestSearchInput" type="text" placeholder="Buscar titulo para pedir...">
  </label>
  <div class="media-grid" id="requestResultsGrid" style="margin-top:14px;"></div>
  <div id="requestResultsEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nenhum resultado ainda</strong>Pesquise um titulo para pedir ou troque para o modo report.</div>
</section>

<section class="panel panel--soft" id="requestReportView" style="display:none;">
  <div class="section-head">
    <div><div class="section-kicker">Report</div><h2 class="section-title">Conte o problema com clareza</h2></div>
    <div class="section-meta">Use essa area para bugs, links quebrados ou problemas na experiencia.</div>
  </div>
  <div class="setting-group" style="margin-top:14px;">
    <div class="setting-row">
      <div class="setting-copy"><h3 class="setting-title">Tipo</h3><p class="setting-sub">Ajuda a triagem a ficar mais rapida.</p></div>
      <label class="field" style="width:min(100%, 280px);"><select id="requestReportType"><option>Bug</option><option>Legenda</option><option>Link quebrado</option><option>Player</option><option>Outro</option></select></label>
    </div>
    <div class="setting-row">
      <div class="setting-copy"><h3 class="setting-title">Mensagem</h3><p class="setting-sub">Explique o problema com o maximo de contexto util.</p></div>
      <label class="field" style="width:100%; min-height:150px; align-items:flex-start; padding:14px;"><textarea id="requestReportMessage" style="width:100%; min-height:120px; resize:vertical; border:0; outline:none; background:transparent; color:inherit;" placeholder="Descreva o erro, a pagina e o que aconteceu."></textarea></label>
    </div>
    <button class="action-btn action-btn--primary" id="sendReportBtn" style="width:100%;">Enviar report</button>
  </div>
</section>

<div id="requestNote" class="floating-note">Central sendo carregada...</div>
<div class="footer-note">Source Baltigo . Requests</div>
"""
    js = f"""
const REQUEST_UID = resolveWebappUid({int(uid)});
const requestNote = document.getElementById("requestNote");
const requestState = {{ tab: "anime", user: null, remaining: 0, used: 0, limit: 3, items: [], loading: false }};
const tgRequest = getTelegramWebApp();
if (tgRequest) {{ try {{ tgRequest.ready(); tgRequest.expand(); }} catch(err) {{}} }}
function setRequestNote(message, tone){{ requestNote.textContent = message || ""; requestNote.dataset.tone = tone || ""; }}
function requestUserLabel(){{
  const user = requestState.user || {{}};
  return String(user.nickname || user.display_name || user.full_name || (REQUEST_UID > 0 ? ("UID " + REQUEST_UID) : "Jogador"));
}}
function syncRequestHero(){{
  document.getElementById("requestPlayerHero").textContent = requestUserLabel();
  document.getElementById("requestRemainingHero").textContent = String(requestState.remaining || 0);
  document.getElementById("requestMeta").textContent = "Limite " + String(requestState.limit || 3) + " por 24h . Restam " + String(requestState.remaining || 0);
}}
function applyRequestTab(){{
  document.getElementById("requestTabAnime").classList.toggle("active", requestState.tab === "anime");
  document.getElementById("requestTabManga").classList.toggle("active", requestState.tab === "manga");
  document.getElementById("requestTabReport").classList.toggle("active", requestState.tab === "report");
  document.getElementById("requestSearchView").style.display = requestState.tab === "report" ? "none" : "";
  document.getElementById("requestReportView").style.display = requestState.tab === "report" ? "" : "none";
  document.getElementById("requestSearchTitle").textContent = requestState.tab === "anime" ? "Procure um anime" : "Procure um manga";
  document.getElementById("requestSearchInput").placeholder = requestState.tab === "anime" ? "Buscar anime para pedir..." : "Buscar manga para pedir...";
}}
function renderRequestResults(){{
  const root = document.getElementById("requestResultsGrid");
  const empty = document.getElementById("requestResultsEmpty");
  document.getElementById("requestSearchMeta").textContent = requestState.items.length ? ("Resultados: " + String(requestState.items.length)) : "Digite pelo menos 2 letras para comecar.";
  if (!requestState.items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = requestState.items.map(function(item){{
    const disabled = item.already_exists || item.already_requested || requestState.remaining <= 0;
    const statePill = item.already_exists
      ? '<span class="soft-pill">Ja existe</span>'
      : (item.already_requested ? '<span class="soft-pill soft-pill--accent">Ja pedido</span>' : '<span class="soft-pill soft-pill--cool">Disponivel</span>');
    const img = item.cover ? '<img src="' + esc(item.cover) + '" alt="' + esc(item.title) + '" loading="lazy" onerror="setImageFallback(this,\\'MEDIA\\')">' : '';
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge">' + esc(requestState.tab) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.title) + '</h3><div class="pill-row">' + statePill + (item.year ? '<span class="soft-pill">' + esc(item.year) + '</span>' : '') + '</div><button class="action-btn action-btn--primary" style="width:100%; margin-top:14px;" data-request-item="' + esc(item.id || 0) + '"' + (disabled ? ' disabled' : '') + '>' + (disabled ? 'Indisponivel' : 'Enviar pedido') + '</button></div>'
      + '</article>';
  }}).join("");
  root.querySelectorAll("[data-request-item]").forEach(function(button){{
    button.onclick = async function(){{
      const targetId = Number(button.getAttribute("data-request-item") || 0);
      const item = requestState.items.find(function(entry){{ return Number(entry.id || 0) === targetId; }});
      if (!item) return;
      button.disabled = true;
      try {{
        setRequestNote("Enviando pedido...", "");
        const payload = {{
          user_id: Number((requestState.user || {{}}).user_id || REQUEST_UID || 0),
          username: String((requestState.user || {{}}).username || ""),
          full_name: String((requestState.user || {{}}).full_name || (requestState.user || {{}}).display_name || ""),
          media_type: requestState.tab,
          anilist_id: Number(item.id || 0),
          title: String(item.title || ""),
          cover: String(item.cover || "")
        }};
        const response = await authJson("/api/pedido/send", {{ uid: REQUEST_UID, method: "POST", json: payload }});
        if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.message) || "Nao foi possivel enviar o pedido.");
        item.already_requested = true;
        await loadRequestLimit({{ silent: true }});
        renderRequestResults();
        setRequestNote("Pedido enviado com sucesso.", "success");
      }} catch(err) {{
        button.disabled = false;
        setRequestNote(err.message, "error");
      }}
    }};
  }});
}}
async function loadRequestUser(){{
  const response = await authJson("/api/webapp/context", {{ uid: REQUEST_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao identificar o jogador.");
  requestState.user = response.data.profile || null;
  syncRequestHero();
}}
async function loadRequestLimit(options){{
  const response = await authJson("/api/pedido/limit", {{ uid: REQUEST_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar limite de pedidos.");
  requestState.used = Number(response.data.used || 0);
  requestState.remaining = Number(response.data.remaining || 0);
  requestState.limit = Number(response.data.limit || 3);
  syncRequestHero();
  if (!(options && options.silent)) setRequestNote("Limites atualizados.", "success");
}}
async function searchRequestTitles(query){{
  const q = String(query || "").trim();
  if (q.length < 2){{
    requestState.items = [];
    renderRequestResults();
    return;
  }}
  requestState.loading = true;
  setSkeleton("requestResultsGrid", 4);
  const res = await fetch("/api/pedido/search?q=" + encodeURIComponent(q) + "&media_type=" + encodeURIComponent(requestState.tab));
  const data = await res.json();
  requestState.loading = false;
  if (!res.ok || !data.ok) throw new Error((data && data.message) || "Nao foi possivel buscar agora.");
  requestState.items = Array.isArray(data.items) ? data.items : [];
  renderRequestResults();
}}
async function sendReport(){{
  const message = String(document.getElementById("requestReportMessage").value || "").trim();
  if (!message) throw new Error("Escreva uma mensagem antes de enviar.");
  const payload = {{
    user_id: Number((requestState.user || {{}}).user_id || REQUEST_UID || 0),
    username: String((requestState.user || {{}}).username || ""),
    full_name: String((requestState.user || {{}}).full_name || (requestState.user || {{}}).display_name || ""),
    report_type: String(document.getElementById("requestReportType").value || "Outro"),
    message: message
  }};
  const response = await authJson("/api/pedido/report", {{ uid: REQUEST_UID, method: "POST", json: payload }});
  if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.message) || "Nao foi possivel enviar o report.");
  document.getElementById("requestReportMessage").value = "";
  setRequestNote("Report enviado com sucesso.", "success");
}}
document.getElementById("requestTabAnime").onclick = function(){{ requestState.tab = "anime"; requestState.items = []; applyRequestTab(); renderRequestResults(); }};
document.getElementById("requestTabManga").onclick = function(){{ requestState.tab = "manga"; requestState.items = []; applyRequestTab(); renderRequestResults(); }};
document.getElementById("requestTabReport").onclick = function(){{ requestState.tab = "report"; applyRequestTab(); }};
document.getElementById("requestSearchInput").addEventListener("input", debounce(async function(event){{
  try {{
    await searchRequestTitles(event.target.value || "");
  }} catch(err) {{
    requestState.items = [];
    renderRequestResults();
    setRequestNote(err.message, "error");
  }}
}}, 320));
document.getElementById("sendReportBtn").onclick = async function(){{
  try {{
    setRequestNote("Enviando report...", "");
    await sendReport();
  }} catch(err) {{
    setRequestNote(err.message, "error");
  }}
}};
(async function(){{
  try {{
    applyRequestTab();
    await loadRequestUser();
    await loadRequestLimit({{ silent: false }});
    renderRequestResults();
  }} catch(err) {{
    setRequestNote(err.message, "error");
  }}
}})();
"""
    return _page_template("Pedidos", body, extra_js=js, include_tg=True)


def build_dado_page(*, uid: int, banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Dado"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Dice system</div>
    <h1 class="hero-title">Sistema de dados</h1>
    <p class="hero-subtitle">Role, escolha o anime e revele o personagem em uma experiencia mais limpa, mais forte visualmente e adaptada para mobile e desktop sem perder a sincronia do sistema.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Jogador</span><span class="metric-value" id="dadoPlayerHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Saldo</span><span class="metric-value" id="dadoBalanceHero">0</span></div>
      <div class="metric-card"><span class="metric-label">Proximo</span><span class="metric-value" id="dadoNextHero">--:--</span></div>
      <div class="metric-card"><span class="metric-label">Status</span><span class="metric-value"><span class="pulse-dot"></span> Live</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Rolagem</div><h2 class="section-title">Seu painel de sorte</h2></div>
    <div class="section-meta" id="dadoMeta">Carregando estado...</div>
  </div>
  <div class="stack" style="margin-top:14px;">
    <div class="panel panel--soft" style="margin-top:0;">
      <div style="display:grid; gap:14px;">
        <div id="diceFace" style="min-height:180px; border-radius:28px; border:1px solid rgba(122,213,255,.24); background:radial-gradient(circle at 20% 10%, rgba(122,213,255,.18), transparent 44%), linear-gradient(180deg, rgba(12,19,39,.94), rgba(8,13,25,.96)); display:flex; align-items:center; justify-content:center; font-family:'Space Grotesk','Plus Jakarta Sans',sans-serif; font-size:82px; font-weight:800; letter-spacing:-.06em; box-shadow:var(--shadow-md);">?</div>
        <div class="pill-row">
          <span class="soft-pill soft-pill--cool" id="dadoHud">Pronto para rolar</span>
          <span class="soft-pill" id="dadoIdentityPill">Conta: ...</span>
        </div>
        <div class="segmented">
          <button type="button" class="segmented-btn active" id="rollDiceBtn">Rolar dado</button>
          <button type="button" class="segmented-btn" id="resetDiceBtn">Limpar tela</button>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Escolha</div><h2 class="section-title">Animes da rodada</h2></div>
    <div class="section-meta" id="dadoOptionsMeta">Role o dado para gerar as opcoes.</div>
  </div>
  <div class="media-grid" id="dadoOptionsGrid" style="margin-top:14px;"></div>
  <div id="dadoOptionsEmpty" class="empty-state" style="margin-top:14px;"><strong>Nenhuma rolagem ativa</strong>Quando a rolagem acontecer, as opcoes aparecem aqui para voce escolher.</div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Revelacao</div><h2 class="section-title">Personagem obtido</h2></div>
    <div class="section-meta" id="dadoRewardMeta">Nenhum personagem revelado ainda.</div>
  </div>
  <div id="dadoRewardRoot" class="empty-state" style="margin-top:14px;"><strong>Sem premio ainda</strong>Escolha um anime da rodada para revelar o personagem.</div>
</section>

<div id="dadoNote" class="floating-note">Sistema de dados sendo carregado...</div>
<div class="footer-note">Source Baltigo . Dice</div>
"""
    js = f"""
const DADO_UID = resolveWebappUid({int(uid)});
const dadoNote = document.getElementById("dadoNote");
const dadoState = {{
  user: null,
  balance: 0,
  next: "--:--",
  rollId: 0,
  diceValue: 0,
  options: [],
  rolling: false,
  picking: false
}};
const tgDado = getTelegramWebApp();
if (tgDado) {{ try {{ tgDado.ready(); tgDado.expand(); }} catch(err) {{}} }}
function setDadoNote(message, tone){{ dadoNote.textContent = message || ""; dadoNote.dataset.tone = tone || ""; }}
function dadoUserLabel(){{
  const user = dadoState.user || {{}};
  return String(user.nickname || user.display_name || user.full_name || (DADO_UID > 0 ? ("UID " + DADO_UID) : "Jogador"));
}}
function syncDadoHero(){{
  document.getElementById("dadoPlayerHero").textContent = dadoUserLabel();
  document.getElementById("dadoBalanceHero").textContent = String(dadoState.balance || 0);
  document.getElementById("dadoNextHero").textContent = String(dadoState.next || "--:--");
  document.getElementById("dadoIdentityPill").textContent = dadoUserLabel();
  document.getElementById("dadoMeta").textContent = "Atualizado " + humanClock() + " . Saldo " + String(dadoState.balance || 0) + " . Proximo " + String(dadoState.next || "--:--");
}}
function setDiceFace(value, label){{
  document.getElementById("diceFace").textContent = String(value || "?");
  document.getElementById("dadoHud").textContent = label || "Pronto";
}}
async function animateDiceFace(finalValue){{
  const face = document.getElementById("diceFace");
  face.style.transform = "scale(0.96)";
  for (let i = 0; i < 10; i += 1){{
    setDiceFace(1 + Math.floor(Math.random() * 6), "Rolando...");
    await new Promise(function(resolve){{ window.setTimeout(resolve, 80); }});
  }}
  face.style.transform = "scale(1)";
  setDiceFace(finalValue || "?", "Resultado: " + String(finalValue || "?"));
}}
function clearReward(){{
  document.getElementById("dadoRewardRoot").className = "empty-state";
  document.getElementById("dadoRewardRoot").innerHTML = "<strong>Sem premio ainda</strong>Escolha um anime da rodada para revelar o personagem.";
  document.getElementById("dadoRewardMeta").textContent = "Nenhum personagem revelado ainda.";
}}
function renderReward(character){{
  const root = document.getElementById("dadoRewardRoot");
  const stars = "★".repeat(Number(character.stars || 1));
  const img = character.image ? '<img src="' + esc(character.image) + '" alt="' + esc(character.name || "Personagem") + '" loading="lazy" onerror="setImageFallback(this,\\'WIN\\')">' : "";
  root.className = "";
  root.innerHTML = ''
    + '<article class="media-card">'
    + '<div class="media-cover">' + img + '<div class="media-badge media-badge--accent">' + esc(character.tier || "COMMON") + '</div><div class="media-count">' + esc(stars) + '</div></div>'
    + '<div class="media-body"><h3 class="card-title">' + esc(character.name || "Personagem") + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(character.anime_title || "Anime") + '</span><span class="soft-pill">' + esc(character.id || 0) + '</span></div></div>'
    + '</article>';
  document.getElementById("dadoRewardMeta").textContent = "Premio revelado com sucesso.";
}}
function renderDadoOptions(){{
  const root = document.getElementById("dadoOptionsGrid");
  const empty = document.getElementById("dadoOptionsEmpty");
  if (!dadoState.options.length){{
    root.innerHTML = "";
    empty.style.display = "";
    document.getElementById("dadoOptionsMeta").textContent = "Role o dado para gerar as opcoes.";
    return;
  }}
  empty.style.display = "none";
  document.getElementById("dadoOptionsMeta").textContent = "Escolha um anime para revelar o personagem.";
  root.innerHTML = dadoState.options.map(function(opt){{
    const img = opt.cover ? '<img src="' + esc(opt.cover) + '" alt="' + esc(opt.title || "Anime") + '" loading="lazy" onerror="setImageFallback(this,\\'ANIME\\')">' : '';
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge media-badge--cool">Anime</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(opt.title || "Anime") + '</h3><button class="action-btn action-btn--primary" style="width:100%; margin-top:14px;" data-pick-anime="' + esc(opt.id || 0) + '">Escolher este anime</button></div>'
      + '</article>';
  }}).join("");
  root.querySelectorAll("[data-pick-anime]").forEach(function(button){{
    button.onclick = async function(){{
      const animeId = Number(button.getAttribute("data-pick-anime") || 0);
      if (!animeId || !dadoState.rollId || dadoState.picking) return;
      dadoState.picking = true;
      button.disabled = true;
      try {{
        setDadoNote("Revelando personagem...", "");
        const response = await authJson("/api/dado/pick", {{ uid: DADO_UID, method: "POST", json: {{ roll_id: dadoState.rollId, anime_id: animeId }} }});
        if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.error) || "Falha ao revelar personagem.");
        dadoState.balance = Number(response.data.balance || dadoState.balance || 0);
        dadoState.rollId = 0;
        dadoState.options = [];
        syncDadoHero();
        renderDadoOptions();
        renderReward(response.data.character || {{}});
        setDadoNote("Personagem obtido com sucesso.", "success");
      }} catch(err) {{
        button.disabled = false;
        setDadoNote(err.message, "error");
      }} finally {{
        dadoState.picking = false;
      }}
    }};
  }});
}}
async function loadDadoUser(){{
  const response = await authJson("/api/webapp/context", {{ uid: DADO_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao identificar o jogador.");
  dadoState.user = response.data.profile || null;
  syncDadoHero();
}}
async function loadDadoState(options){{
  const response = await authJson("/api/dado/state", {{ uid: DADO_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar o estado dos dados.");
  dadoState.balance = Number(response.data.balance || 0);
  dadoState.next = String(response.data.next_recharge_hhmm || "--:--");
  if (response.data.active_roll && response.data.active_roll.roll_id){{
    dadoState.rollId = Number(response.data.active_roll.roll_id || 0);
    dadoState.diceValue = Number(response.data.active_roll.dice_value || 0);
    dadoState.options = Array.isArray(response.data.active_roll.options) ? response.data.active_roll.options : [];
    if (dadoState.diceValue > 0) await animateDiceFace(dadoState.diceValue);
  }} else {{
    dadoState.rollId = 0;
    dadoState.diceValue = 0;
    dadoState.options = [];
    setDiceFace("?", "Pronto para rolar");
  }}
  syncDadoHero();
  renderDadoOptions();
  if (!(options && options.silent)) setDadoNote("Estado do sistema de dados atualizado.", "success");
}}
async function rollDice(){{
  if (dadoState.rolling || dadoState.picking) return;
  dadoState.rolling = true;
  document.getElementById("rollDiceBtn").disabled = true;
  clearReward();
  try {{
    setDadoNote("Rolando dado...", "");
    const response = await authJson("/api/dado/roll", {{ uid: DADO_UID, method: "POST", json: {{}} }});
    if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.error) || "Falha ao rolar.");
    dadoState.rollId = Number(response.data.roll_id || 0);
    dadoState.diceValue = Number(response.data.dice_value || 0);
    dadoState.options = Array.isArray(response.data.options) ? response.data.options : [];
    dadoState.balance = Number(response.data.balance || dadoState.balance || 0);
    syncDadoHero();
    await animateDiceFace(dadoState.diceValue || "?");
    renderDadoOptions();
    setDadoNote("Escolha um anime para revelar o personagem.", "success");
  }} catch(err) {{
    setDadoNote(err.message, "error");
  }} finally {{
    dadoState.rolling = false;
    document.getElementById("rollDiceBtn").disabled = false;
  }}
}}
document.getElementById("rollDiceBtn").onclick = rollDice;
document.getElementById("resetDiceBtn").onclick = function(){{
  dadoState.rollId = 0;
  dadoState.diceValue = 0;
  dadoState.options = [];
  setDiceFace("?", "Pronto para rolar");
  renderDadoOptions();
  clearReward();
  setDadoNote("Tela limpa. O saldo continua sincronizado.", "success");
}};
(async function(){{
  try {{
    await loadDadoUser();
    await loadDadoState({{ silent: false }});
    createLiveRefresh(async function(){{ await loadDadoUser(); await loadDadoState({{ silent: true }}); }}, 7000);
  }} catch(err) {{
    setDadoNote(err.message, "error");
  }}
}})();
"""
    return _page_template("Dado", body, extra_js=js, include_tg=True)


def build_dado_page(*, uid: int, banner_url: str) -> str:
    body_parts: list[str] = []
    css_parts: list[str] = []
    js_parts: list[str] = []

    body_parts.append(
        """
<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
"""
    )
    body_parts.append(
        """
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="__DADO_BANNER__" alt="Dado"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Dice system 3D</div>
    <h1 class="hero-title">Sistema de dados com impacto real.</h1>
    <p class="hero-subtitle">O coracao da experiencia volta a ser o dado 3D: uma rolagem com peso, pouso forte no resultado e revelacao mais premium para cada personagem obtido.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Jogador</span><span class="metric-value" id="dadoPlayerHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Saldo</span><span class="metric-value" id="dadoBalanceHero">0</span></div>
      <div class="metric-card"><span class="metric-label">Proximo</span><span class="metric-value" id="dadoNextHero">--:--</span></div>
      <div class="metric-card"><span class="metric-label">Stage</span><span class="metric-value"><span class="pulse-dot"></span> 3D live</span></div>
    </div>
  </div>
</section>

<section class="dice-experience">
  <article class="panel dice-stage-card" id="dadoStageCard" data-state="idle">
    <div class="section-head">
      <div><div class="section-kicker">Rolagem</div><h2 class="section-title">Mesa de sorte</h2></div>
      <div class="section-meta" id="dadoMeta">Carregando estado...</div>
    </div>
    <div class="dice-stage-grid">
      <div class="dice-viewport">
        <div class="dice-stage-ring"></div>
        <div class="dice-stage-glow"></div>
        <div class="dice-stage-flash" id="dadoStageFlash"></div>
        <div id="sceneWrap" class="dice-scene"></div>
        <div class="dice-viewport-top">
          <span class="soft-pill soft-pill--cool" id="dadoHud">Pronto para rolar</span>
          <span class="soft-pill" id="dadoIdentityPill">Conta: ...</span>
        </div>
        <div class="dice-signal-card">
          <span class="dice-signal-kicker">Face</span>
          <strong id="dadoSignalValue">?</strong>
          <span id="dadoSignalLabel">Aguardando a proxima rolagem</span>
        </div>
      </div>
      <div class="dice-console">
        <div class="dice-console-copy">
          <div class="section-kicker">Controle</div>
          <h3 class="section-title">Rolar, pousar e revelar.</h3>
          <p class="hero-subtitle">Mantivemos a mesma logica do sistema, mas com uma apresentacao mais forte, mais clara e com melhor leitura em mobile e desktop.</p>
        </div>
        <div class="dice-console-stats">
          <div class="dice-mini-card">
            <span class="metric-label">Conta</span>
            <strong class="dice-mini-value" id="dadoAccountCard">...</strong>
          </div>
          <div class="dice-mini-card">
            <span class="metric-label">Dado atual</span>
            <strong class="dice-mini-value" id="dadoFaceCard">?</strong>
          </div>
          <div class="dice-mini-card">
            <span class="metric-label">Opcoes</span>
            <strong class="dice-mini-value" id="dadoOptionsCount">0</strong>
          </div>
        </div>
        <div class="hero-actions">
          <button type="button" class="action-btn action-btn--primary dado-action" id="rollDiceBtn">Rolar dado</button>
          <button type="button" class="action-btn action-btn--ghost dado-action" id="resetDiceBtn">Limpar tela</button>
        </div>
        <div class="pill-row">
          <span class="soft-pill soft-pill--cool" id="dadoEnergyPill">Saldo 0</span>
          <span class="soft-pill" id="dadoNextPill">Proximo --:--</span>
        </div>
      </div>
    </div>
  </article>

  <article class="panel panel--soft">
    <div class="section-head">
      <div><div class="section-kicker">Escolha</div><h2 class="section-title">Animes da rodada</h2></div>
      <div class="section-meta" id="dadoOptionsMeta">Role o dado para gerar as opcoes.</div>
    </div>
    <div class="dado-option-grid" id="dadoOptionsGrid"></div>
    <div id="dadoOptionsEmpty" class="empty-state" style="margin-top:14px;"><strong>Nenhuma rolagem ativa</strong>Quando a rolagem acontecer, as opcoes aparecem aqui para voce escolher.</div>
  </article>

  <article class="panel panel--soft">
    <div class="section-head">
      <div><div class="section-kicker">Revelacao</div><h2 class="section-title">Personagem obtido</h2></div>
      <div class="section-meta" id="dadoRewardMeta">Nenhum personagem revelado ainda.</div>
    </div>
    <div id="dadoRewardRoot" class="empty-state dado-reward-shell" style="margin-top:14px;"><strong>Sem premio ainda</strong>Escolha um anime da rodada para revelar o personagem.</div>
  </article>
</section>

<div id="dadoNote" class="floating-note">Sistema de dados sendo carregado...</div>
<div class="footer-note">Source Baltigo . Dice</div>
"""
    )
    css_parts.append(
        r"""
.dice-experience{
  display:grid;
  gap:16px;
  margin-top:16px;
}
.dice-stage-card{
  overflow:hidden;
  background:
    radial-gradient(720px 360px at 12% 0%, rgba(122,213,255,.15), transparent 52%),
    radial-gradient(520px 280px at 100% 100%, rgba(255,111,148,.14), transparent 54%),
    linear-gradient(180deg, rgba(10,18,37,.94), rgba(6,11,22,.98));
}
.dice-stage-card::before{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:
    linear-gradient(135deg, rgba(255,255,255,.04), transparent 34%),
    radial-gradient(circle at 50% 44%, rgba(122,213,255,.08), transparent 38%);
}
.dice-stage-card[data-state="rolling"]{
  border-color:rgba(122,213,255,.42);
  box-shadow:0 28px 70px rgba(0,0,0,.42), 0 0 0 1px rgba(122,213,255,.08) inset;
}
.dice-stage-card[data-state="landed"]{
  border-color:rgba(255,111,148,.32);
}
.dice-stage-grid{
  position:relative;
  z-index:1;
  display:grid;
  gap:16px;
  margin-top:16px;
}
.dice-viewport{
  position:relative;
  min-height:320px;
  border-radius:26px;
  border:1px solid rgba(255,255,255,.1);
  background:
    radial-gradient(circle at 50% 28%, rgba(255,255,255,.08), transparent 34%),
    linear-gradient(180deg, rgba(7,13,26,.6), rgba(3,8,18,.9));
  overflow:hidden;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05);
}
.dice-scene{
  position:absolute;
  inset:0;
}
.dice-stage-ring,
.dice-stage-glow,
.dice-stage-flash{
  position:absolute;
  left:50%;
  top:52%;
  transform:translate(-50%, -50%);
  border-radius:999px;
  pointer-events:none;
}
.dice-stage-ring{
  width:72%;
  aspect-ratio:1 / 1;
  border:1px solid rgba(122,213,255,.14);
  box-shadow:0 0 0 18px rgba(122,213,255,.02), 0 0 40px rgba(122,213,255,.08);
}
.dice-stage-glow{
  width:68%;
  aspect-ratio:1 / 1;
  background:radial-gradient(circle, rgba(122,213,255,.16) 0%, rgba(122,213,255,.08) 24%, rgba(122,213,255,0) 68%);
  filter:blur(12px);
  opacity:.92;
}
.dice-stage-flash{
  width:74%;
  aspect-ratio:1 / 1;
  background:radial-gradient(circle, rgba(255,255,255,.30) 0%, rgba(122,213,255,.16) 22%, rgba(255,111,148,.12) 46%, rgba(255,255,255,0) 72%);
  opacity:0;
}
.dice-stage-flash.is-live{
  animation:diceStageFlash .7s ease;
}
.dice-stage-card[data-state="rolling"] .dice-stage-ring{
  animation:diceRingOrbit 1.2s linear infinite;
}
.dice-stage-card[data-state="rolling"] .dice-stage-glow{
  animation:diceGlowPulse 1.2s ease-in-out infinite;
}
.dice-viewport-top{
  position:absolute;
  inset:14px 14px auto 14px;
  z-index:2;
  display:flex;
  flex-wrap:wrap;
  gap:10px;
}
.dice-signal-card{
  position:absolute;
  left:16px;
  right:16px;
  bottom:16px;
  z-index:2;
  display:grid;
  gap:4px;
  padding:16px 18px;
  border-radius:22px;
  border:1px solid rgba(255,255,255,.12);
  background:linear-gradient(180deg, rgba(8,14,28,.8), rgba(7,12,22,.96));
  backdrop-filter:blur(18px);
  box-shadow:var(--shadow-md);
}
.dice-signal-kicker{
  color:var(--muted);
  font-size:11px;
  font-weight:800;
  letter-spacing:.18em;
  text-transform:uppercase;
}
.dice-signal-card strong{
  font-family:"Space Grotesk", "Plus Jakarta Sans", sans-serif;
  font-size:44px;
  line-height:1;
  letter-spacing:-.06em;
}
.dice-signal-card span:last-child{
  color:var(--muted-strong);
  font-size:13px;
}
.dice-console{
  display:grid;
  gap:14px;
}
.dice-console-copy{
  display:grid;
  gap:8px;
}
.dice-console-copy .section-title{
  margin:0;
  font-size:28px;
}
.dice-console-copy .hero-subtitle{
  max-width:none;
}
.dice-console-stats{
  display:grid;
  grid-template-columns:repeat(3, minmax(0, 1fr));
  gap:10px;
}
.dice-mini-card{
  padding:14px;
  border-radius:20px;
  border:1px solid rgba(255,255,255,.1);
  background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.025));
}
.dice-mini-value{
  display:block;
  margin-top:8px;
  font-family:"Space Grotesk", "Plus Jakarta Sans", sans-serif;
  font-size:22px;
  line-height:1.05;
  letter-spacing:-.04em;
}
.dado-action{
  flex:1 1 180px;
}
.action-btn--ghost{
  border-color:rgba(255,255,255,.12);
  background:rgba(255,255,255,.04);
}
"""
    )
    css_parts.append(
        r"""
.dado-option-grid{
  display:grid;
  gap:12px;
  margin-top:14px;
}
.dado-anime-option{
  width:100%;
  padding:0;
  overflow:hidden;
  text-align:left;
  border-radius:24px;
  border:1px solid rgba(255,255,255,.1);
  background:linear-gradient(180deg, rgba(13,21,42,.94), rgba(8,13,25,.98));
  box-shadow:var(--shadow-md);
  transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.dado-anime-option:active{
  transform:scale(.985);
}
.dado-anime-option[disabled]{
  opacity:.68;
}
.dado-anime-option-cover{
  position:relative;
  aspect-ratio:16 / 9;
  overflow:hidden;
  background:linear-gradient(180deg, rgba(122,213,255,.14), rgba(255,111,148,.16));
}
.dado-anime-option-cover img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}
.dado-anime-option-cover::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(7,11,22,.08), rgba(7,11,22,.84));
}
.dado-anime-option-index{
  position:absolute;
  left:14px;
  top:14px;
  z-index:1;
}
.dado-anime-option-body{
  display:grid;
  gap:12px;
  padding:16px;
}
.dado-anime-option-copy{
  display:grid;
  gap:8px;
}
.dado-anime-option-title{
  margin:0;
  font-size:20px;
  line-height:1.06;
  letter-spacing:-.03em;
}
.dado-anime-option-sub{
  color:var(--muted-strong);
  font-size:13px;
  line-height:1.5;
}
.dado-anime-option .action-btn{
  width:100%;
}
.dado-reward-shell{
  min-height:0;
}
.dado-reward-card{
  display:grid;
  gap:16px;
  padding:16px;
  border-radius:24px;
  border:1px solid rgba(255,255,255,.1);
  background:
    radial-gradient(520px 220px at 100% 0%, rgba(255,111,148,.16), transparent 52%),
    linear-gradient(180deg, rgba(14,23,45,.96), rgba(8,13,25,.98));
  box-shadow:var(--shadow-md);
  animation:dadoRewardReveal .48s cubic-bezier(.2,.8,.2,1);
}
.dado-reward-media{
  position:relative;
  border-radius:22px;
  overflow:hidden;
  min-height:220px;
  background:linear-gradient(180deg, rgba(122,213,255,.14), rgba(255,111,148,.14));
}
.dado-reward-media img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}
.dado-reward-media::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(7,11,22,.04), rgba(7,11,22,.82));
}
.dado-reward-copy{
  display:grid;
  gap:10px;
  align-content:start;
}
.dado-reward-title{
  margin:0;
  font-size:clamp(26px, 7vw, 38px);
  line-height:.98;
  letter-spacing:-.05em;
}
.dado-reward-stars{
  color:rgba(255,236,168,.92);
  font-size:15px;
  letter-spacing:.16em;
}
.dado-reward-copy .pill-row{
  gap:8px;
}
@keyframes diceRingOrbit{
  from{ transform:translate(-50%, -50%) rotate(0deg); }
  to{ transform:translate(-50%, -50%) rotate(360deg); }
}
@keyframes diceGlowPulse{
  0%,100%{ opacity:.58; transform:translate(-50%, -50%) scale(.96); }
  50%{ opacity:1; transform:translate(-50%, -50%) scale(1.04); }
}
@keyframes diceStageFlash{
  0%{ opacity:0; transform:translate(-50%, -50%) scale(.84); }
  22%{ opacity:1; }
  100%{ opacity:0; transform:translate(-50%, -50%) scale(1.18); }
}
@keyframes dadoRewardReveal{
  from{ opacity:0; transform:translateY(12px) scale(.985); }
  to{ opacity:1; transform:translateY(0) scale(1); }
}
@media (min-width:860px){
  .dice-stage-grid{
    grid-template-columns:minmax(0, 1.2fr) minmax(320px, .8fr);
    align-items:stretch;
  }
  .dice-console{
    align-content:space-between;
  }
  .dado-option-grid{
    grid-template-columns:repeat(2, minmax(0, 1fr));
  }
  .dado-reward-card{
    grid-template-columns:minmax(260px, .9fr) minmax(0, 1.1fr);
    align-items:center;
  }
}
@media (min-width:1080px){
  .dado-option-grid{
    grid-template-columns:repeat(3, minmax(0, 1fr));
  }
}
@media (max-width:520px){
  .dice-console-stats{
    grid-template-columns:1fr;
  }
  .dice-viewport{
    min-height:292px;
  }
  .dice-signal-card strong{
    font-size:38px;
  }
}
"""
    )
    js_parts.append(
        """
const DADO_UID = resolveWebappUid(__DADO_UID__);
const dadoNote = document.getElementById("dadoNote");
const dadoStageCard = document.getElementById("dadoStageCard");
const dadoStageFlash = document.getElementById("dadoStageFlash");
const dadoHud = document.getElementById("dadoHud");
const dadoSignalValue = document.getElementById("dadoSignalValue");
const dadoSignalLabel = document.getElementById("dadoSignalLabel");
const rollDiceBtn = document.getElementById("rollDiceBtn");
const resetDiceBtn = document.getElementById("resetDiceBtn");
const dadoOptionsGrid = document.getElementById("dadoOptionsGrid");
const dadoOptionsEmpty = document.getElementById("dadoOptionsEmpty");
const dadoRewardRoot = document.getElementById("dadoRewardRoot");
const dadoRewardMeta = document.getElementById("dadoRewardMeta");
const dadoState = {
  user: null,
  balance: 0,
  next: "--:--",
  rollId: 0,
  diceValue: 0,
  options: [],
  rolling: false,
  picking: false,
  sceneReady: false,
  refreshHandle: null
};
const tgDado = getTelegramWebApp();
if (tgDado) {
  try {
    tgDado.ready();
    tgDado.expand();
  } catch(err) {}
}

let renderer = null;
let scene = null;
let camera = null;
let diceMesh = null;
let frameHandle = 0;
let particles = [];
let stageFloor = null;

function setDadoNote(message, tone){
  dadoNote.textContent = message || "";
  dadoNote.dataset.tone = tone || "";
}

function dadoUserLabel(){
  const user = dadoState.user || {};
  return String(user.nickname || user.display_name || user.full_name || (DADO_UID > 0 ? ("UID " + DADO_UID) : "Jogador"));
}

function setStageMode(mode){
  dadoStageCard.dataset.state = mode || "idle";
}

function pulseStage(){
  dadoStageFlash.classList.remove("is-live");
  void dadoStageFlash.offsetWidth;
  dadoStageFlash.classList.add("is-live");
}

function setStageSignal(value, label){
  dadoSignalValue.textContent = value == null || value === "" ? "?" : String(value);
  dadoSignalLabel.textContent = label || "Aguardando a proxima rolagem";
  document.getElementById("dadoFaceCard").textContent = value == null || value === "" ? "?" : String(value);
}

function syncDadoHero(){
  const label = dadoUserLabel();
  document.getElementById("dadoPlayerHero").textContent = label;
  document.getElementById("dadoBalanceHero").textContent = String(dadoState.balance || 0);
  document.getElementById("dadoNextHero").textContent = String(dadoState.next || "--:--");
  document.getElementById("dadoIdentityPill").textContent = label;
  document.getElementById("dadoAccountCard").textContent = label;
  document.getElementById("dadoEnergyPill").textContent = "Saldo " + String(dadoState.balance || 0);
  document.getElementById("dadoNextPill").textContent = "Proximo " + String(dadoState.next || "--:--");
  document.getElementById("dadoOptionsCount").textContent = String((dadoState.options || []).length || 0);
  document.getElementById("dadoMeta").textContent = "Atualizado " + humanClock() + " . Saldo " + String(dadoState.balance || 0) + " . Proximo " + String(dadoState.next || "--:--");
}

function clearReward(){
  dadoRewardRoot.className = "empty-state dado-reward-shell";
  dadoRewardRoot.innerHTML = "<strong>Sem premio ainda</strong>Escolha um anime da rodada para revelar o personagem.";
  dadoRewardMeta.textContent = "Nenhum personagem revelado ainda.";
}

function renderReward(character){
  const safeCharacter = character || {};
  const stars = "\\u2605".repeat(Math.max(1, Number(safeCharacter.stars || 1)));
  const img = safeCharacter.image
    ? '<img src="' + esc(safeCharacter.image) + '" alt="' + esc(safeCharacter.name || "Personagem") + '" loading="lazy" onerror="setImageFallback(this,\\'WIN\\')">'
    : "";
  dadoRewardRoot.className = "dado-reward-shell";
  dadoRewardRoot.innerHTML = ""
    + '<article class="dado-reward-card">'
    +   '<div class="dado-reward-media">' + img + '<div class="media-badge media-badge--accent">' + esc((safeCharacter.tier || "COMMON").toUpperCase()) + '</div></div>'
    +   '<div class="dado-reward-copy">'
    +     '<div class="section-kicker">Drop confirmado</div>'
    +     '<h3 class="dado-reward-title">' + esc(safeCharacter.name || "Personagem") + '</h3>'
    +     '<div class="dado-reward-stars">' + esc(stars) + '</div>'
    +     '<div class="pill-row">'
    +       '<span class="soft-pill soft-pill--cool">' + esc(safeCharacter.anime_title || "Anime") + '</span>'
    +       '<span class="soft-pill">ID ' + esc(safeCharacter.id || 0) + '</span>'
    +       '<span class="soft-pill soft-pill--accent">' + esc((safeCharacter.tier || "COMMON").toUpperCase()) + '</span>'
    +     '</div>'
    +     '<p class="hero-subtitle">Resultado revelado com sincronia imediata e pronto para refletir no restante do ecossistema.</p>'
    +   '</div>'
    + '</article>';
  dadoRewardMeta.textContent = "Premio revelado com sucesso.";
  pulseStage();
}

function renderDadoOptions(){
  if (!Array.isArray(dadoState.options) || !dadoState.options.length){
    dadoOptionsGrid.innerHTML = "";
    dadoOptionsEmpty.style.display = "";
    document.getElementById("dadoOptionsMeta").textContent = "Role o dado para gerar as opcoes.";
    document.getElementById("dadoOptionsCount").textContent = "0";
    return;
  }

  dadoOptionsEmpty.style.display = "none";
  document.getElementById("dadoOptionsMeta").textContent = "Escolha um anime para revelar o personagem.";
  document.getElementById("dadoOptionsCount").textContent = String(dadoState.options.length);
  dadoOptionsGrid.innerHTML = dadoState.options.map(function(opt, index){
    const cover = opt.cover
      ? '<img src="' + esc(opt.cover) + '" alt="' + esc(opt.title || "Anime") + '" loading="lazy" onerror="setImageFallback(this,\\'ANIME\\')">'
      : "";
    return ""
      + '<button type="button" class="dado-anime-option" data-pick-anime="' + esc(opt.id || 0) + '">'
      +   '<div class="dado-anime-option-cover">'
      +     cover
      +     '<span class="soft-pill soft-pill--cool dado-anime-option-index">Opcao ' + esc(index + 1) + '</span>'
      +   '</div>'
      +   '<div class="dado-anime-option-body">'
      +     '<div class="dado-anime-option-copy">'
      +       '<h3 class="dado-anime-option-title">' + esc(opt.title || "Anime") + '</h3>'
      +       '<div class="dado-anime-option-sub">Toque para travar a escolha e revelar um personagem dessa obra.</div>'
      +     '</div>'
      +     '<span class="action-btn action-btn--primary">Escolher este anime</span>'
      +   '</div>'
      + '</button>';
  }).join("");

  dadoOptionsGrid.querySelectorAll("[data-pick-anime]").forEach(function(button){
    button.onclick = async function(){
      const animeId = Number(button.getAttribute("data-pick-anime") || 0);
      if (!animeId || !dadoState.rollId || dadoState.picking) return;
      dadoState.picking = true;
      dadoOptionsGrid.querySelectorAll("[data-pick-anime]").forEach(function(node){ node.disabled = true; });
      setDadoNote("Revelando personagem...", "");
      dadoHud.textContent = "Escolha confirmada";
      setStageMode("landed");

      try {
        const response = await authJson("/api/dado/pick", { uid: DADO_UID, method: "POST", json: { roll_id: dadoState.rollId, anime_id: animeId } });
        if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.error) || "Falha ao revelar personagem.");
        dadoState.balance = Number(response.data.balance || dadoState.balance || 0);
        dadoState.rollId = 0;
        dadoState.options = [];
        syncDadoHero();
        renderDadoOptions();
        renderReward(response.data.character || {});
        dadoHud.textContent = "Personagem revelado";
        setDadoNote("Personagem obtido com sucesso.", "success");
      } catch(err) {
        dadoOptionsGrid.querySelectorAll("[data-pick-anime]").forEach(function(node){ node.disabled = false; });
        setDadoNote(err.message, "error");
      } finally {
        dadoState.picking = false;
      }
    };
  });
}
"""
    )
    js_parts.append(
        """
function createRoundedRect(ctx, x, y, width, height, radius){
  const safe = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + safe, y);
  ctx.lineTo(x + width - safe, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + safe);
  ctx.lineTo(x + width, y + height - safe);
  ctx.quadraticCurveTo(x + width, y + height, x + width - safe, y + height);
  ctx.lineTo(x + safe, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - safe);
  ctx.lineTo(x, y + safe);
  ctx.quadraticCurveTo(x, y, x + safe, y);
  ctx.closePath();
}

function createFaceTexture(value, accent){
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");

  const gradient = ctx.createLinearGradient(0, 0, 512, 512);
  gradient.addColorStop(0, "#182445");
  gradient.addColorStop(1, "#070c18");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 512, 512);

  ctx.fillStyle = "rgba(255,255,255,.03)";
  for (let y = 0; y < 512; y += 16){
    ctx.fillRect(0, y, 512, 1);
  }

  ctx.strokeStyle = "rgba(255,255,255,.14)";
  ctx.lineWidth = 12;
  ctx.strokeRect(18, 18, 476, 476);

  ctx.strokeStyle = accent || "#7ad5ff";
  ctx.lineWidth = 10;
  createRoundedRect(ctx, 44, 44, 424, 424, 42);
  ctx.stroke();

  ctx.shadowColor = accent || "#7ad5ff";
  ctx.shadowBlur = 32;
  ctx.fillStyle = "#ffffff";
  ctx.font = "700 240px 'Segoe UI', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(value), 256, 278);

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(255,255,255,.52)";
  ctx.font = "700 34px 'Segoe UI', sans-serif";
  ctx.fillText("DICE", 256, 94);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function ensureScene(){
  if (dadoState.sceneReady) return true;
  if (typeof window.THREE === "undefined"){
    setStageSignal("?", "3D indisponivel neste momento");
    return false;
  }

  const sceneWrap = document.getElementById("sceneWrap");
  if (!sceneWrap) return false;

  const width = sceneWrap.clientWidth || 320;
  const height = sceneWrap.clientHeight || 320;

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  sceneWrap.innerHTML = "";
  sceneWrap.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
  camera.position.set(0, 0.8, 6.8);

  const ambient = new THREE.AmbientLight(0xffffff, 1.5);
  scene.add(ambient);

  const point = new THREE.PointLight(0xffffff, 2.4, 32);
  point.position.set(2.8, 3.6, 5.4);
  scene.add(point);

  const rim = new THREE.PointLight(0xff6f94, 1.2, 20);
  rim.position.set(-3.2, -0.6, 2.8);
  scene.add(rim);

  const floorGeo = new THREE.CircleGeometry(3.1, 72);
  const floorMat = new THREE.MeshBasicMaterial({
    color: 0x12233a,
    transparent: true,
    opacity: 0.34
  });
  stageFloor = new THREE.Mesh(floorGeo, floorMat);
  stageFloor.rotation.x = -Math.PI / 2;
  stageFloor.position.y = -1.58;
  scene.add(stageFloor);

  const faceColors = ["#7ad5ff", "#ff7ea6", "#8ef0ff", "#ff9f7d", "#9b8bff", "#ffe07d"];
  const materials = [
    new THREE.MeshStandardMaterial({ map: createFaceTexture(2, faceColors[1]), roughness: 0.36, metalness: 0.42, emissive: 0x09111f }),
    new THREE.MeshStandardMaterial({ map: createFaceTexture(5, faceColors[4]), roughness: 0.36, metalness: 0.42, emissive: 0x09111f }),
    new THREE.MeshStandardMaterial({ map: createFaceTexture(3, faceColors[2]), roughness: 0.36, metalness: 0.42, emissive: 0x09111f }),
    new THREE.MeshStandardMaterial({ map: createFaceTexture(4, faceColors[3]), roughness: 0.36, metalness: 0.42, emissive: 0x09111f }),
    new THREE.MeshStandardMaterial({ map: createFaceTexture(1, faceColors[0]), roughness: 0.36, metalness: 0.42, emissive: 0x09111f }),
    new THREE.MeshStandardMaterial({ map: createFaceTexture(6, faceColors[5]), roughness: 0.36, metalness: 0.42, emissive: 0x09111f })
  ];

  const geometry = new THREE.BoxGeometry(2.08, 2.08, 2.08, 1, 1, 1);
  diceMesh = new THREE.Mesh(geometry, materials);
  scene.add(diceMesh);

  const edgeGeo = new THREE.EdgesGeometry(geometry);
  const edgeMat = new THREE.LineBasicMaterial({ color: 0x9de8ff, transparent: true, opacity: 0.46 });
  const edges = new THREE.LineSegments(edgeGeo, edgeMat);
  diceMesh.add(edges);

  particles = [];
  for (let i = 0; i < 42; i += 1){
    const pGeo = new THREE.SphereGeometry(0.03, 8, 8);
    const pMat = new THREE.MeshBasicMaterial({ color: i % 2 ? 0x7ad5ff : 0xff6f94 });
    const p = new THREE.Mesh(pGeo, pMat);
    p.position.set((Math.random() - 0.5) * 4.6, (Math.random() - 0.5) * 3.4, (Math.random() - 0.5) * 3.2);
    p.userData = {
      vx: (Math.random() - 0.5) * 0.018,
      vy: (Math.random() - 0.5) * 0.018,
      vz: (Math.random() - 0.5) * 0.018
    };
    scene.add(p);
    particles.push(p);
  }

  cancelAnimationFrame(frameHandle);
  const tick = function(){
    if (!renderer || !scene || !camera || !diceMesh) return;
    if (!dadoState.rolling){
      diceMesh.rotation.x += 0.0022;
      diceMesh.rotation.y += 0.003;
      if (stageFloor) stageFloor.rotation.z += 0.0014;
    }
    particles.forEach(function(p){
      p.position.x += p.userData.vx;
      p.position.y += p.userData.vy;
      p.position.z += p.userData.vz;
      if (Math.abs(p.position.x) > 3.2) p.userData.vx *= -1;
      if (Math.abs(p.position.y) > 2.1) p.userData.vy *= -1;
      if (Math.abs(p.position.z) > 2.2) p.userData.vz *= -1;
    });
    renderer.render(scene, camera);
    frameHandle = requestAnimationFrame(tick);
  };
  tick();
  dadoState.sceneReady = true;
  return true;
}

function resizeScene(){
  const sceneWrap = document.getElementById("sceneWrap");
  if (!renderer || !camera || !sceneWrap) return;
  const width = sceneWrap.clientWidth || 320;
  const height = sceneWrap.clientHeight || 320;
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

async function animateDiceResult(value, options){
  const opts = options || {};
  if (!ensureScene()){
    setStageMode("landed");
    setStageSignal(value || "?", "Resultado: " + String(value || "?"));
    dadoHud.textContent = "Resultado: " + String(value || "?");
    return;
  }

  const targets = {
    1: { x: 0, y: 0 },
    2: { x: 0, y: -Math.PI / 2 },
    3: { x: Math.PI / 2, y: 0 },
    4: { x: -Math.PI / 2, y: 0 },
    5: { x: 0, y: Math.PI / 2 },
    6: { x: 0, y: Math.PI }
  };
  const target = targets[value] || targets[1];
  const restore = !!opts.restore;
  const duration = restore ? 1100 : 1850;
  const baseX = diceMesh.rotation.x;
  const baseY = diceMesh.rotation.y;
  const baseZ = diceMesh.rotation.z;
  const endX = target.x + Math.PI * (restore ? 4.5 : 8.5);
  const endY = target.y + Math.PI * (restore ? 5.0 : 9.0);
  const endZ = baseZ + Math.PI * (restore ? 1.4 : 2.4);
  const start = performance.now();

  dadoState.rolling = true;
  rollDiceBtn.disabled = true;
  setStageMode("rolling");
  dadoHud.textContent = restore ? "Recuperando rolagem" : "Rolando...";
  setStageSignal("...", restore ? "Retomando resultado" : "Agitando o dado 3D");
  pulseStage();

  await new Promise(function(resolve){
    function step(now){
      const progress = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 4);
      const wobble = Math.sin(progress * Math.PI * 9) * (1 - progress) * 0.22;

      diceMesh.rotation.x = baseX + (endX - baseX) * ease + wobble * 0.4;
      diceMesh.rotation.y = baseY + (endY - baseY) * ease + wobble;
      diceMesh.rotation.z = baseZ + (endZ - baseZ) * ease;
      camera.position.x = Math.sin(progress * Math.PI * 2) * 0.26;
      camera.position.y = 0.8 + Math.sin(progress * Math.PI * 5) * 0.09;
      camera.lookAt(0, 0, 0);

      if (progress < 1){
        requestAnimationFrame(step);
      } else {
        resolve();
      }
    }
    requestAnimationFrame(step);
  });

  diceMesh.rotation.x = target.x;
  diceMesh.rotation.y = target.y;
  diceMesh.rotation.z = 0;
  camera.position.set(0, 0.8, 6.8);
  camera.lookAt(0, 0, 0);

  dadoState.rolling = false;
  rollDiceBtn.disabled = false;
  setStageMode("landed");
  setStageSignal(value || "?", restore ? "Rolagem recuperada" : "Resultado confirmado");
  dadoHud.textContent = "Resultado: " + String(value || "?");
  pulseStage();
}
"""
    )
    js_parts.append(
        """
async function loadDadoUser(){
  const response = await authJson("/api/webapp/context", { uid: DADO_UID });
  if (!response.ok || !response.data.ok) throw new Error("Falha ao identificar o jogador.");
  dadoState.user = response.data.profile || null;
  syncDadoHero();
}

async function loadDadoState(options){
  const opts = options || {};
  if ((dadoState.rolling || dadoState.picking) && opts.silent) return;

  const response = await authJson("/api/dado/state", { uid: DADO_UID });
  if (!response.ok || !response.data.ok) throw new Error("Falha ao carregar o estado dos dados.");

  dadoState.balance = Number(response.data.balance || 0);
  dadoState.next = String(response.data.next_recharge_hhmm || "--:--");

  if (response.data.active_roll && response.data.active_roll.roll_id){
    const nextRollId = Number(response.data.active_roll.roll_id || 0);
    const nextDiceValue = Number(response.data.active_roll.dice_value || 0);
    const nextOptions = Array.isArray(response.data.active_roll.options) ? response.data.active_roll.options : [];
    const changedRoll = nextRollId !== dadoState.rollId || nextDiceValue !== dadoState.diceValue;

    dadoState.rollId = nextRollId;
    dadoState.diceValue = nextDiceValue;
    dadoState.options = nextOptions;
    syncDadoHero();

    if (dadoState.diceValue > 0){
      if (changedRoll){
        await animateDiceResult(dadoState.diceValue, { restore: !!opts.silent });
      } else {
        setStageMode("landed");
        setStageSignal(dadoState.diceValue, "Resultado confirmado");
        dadoHud.textContent = "Resultado: " + String(dadoState.diceValue);
      }
    }
  } else {
    dadoState.rollId = 0;
    dadoState.diceValue = 0;
    dadoState.options = [];
    syncDadoHero();
    setStageMode("idle");
    setStageSignal("?", "Aguardando a proxima rolagem");
    dadoHud.textContent = "Pronto para rolar";
  }

  renderDadoOptions();
  if (!opts.silent) setDadoNote("Estado do sistema de dados atualizado.", "success");
}

async function rollDice(){
  if (dadoState.rolling || dadoState.picking) return;
  dadoState.rolling = true;
  rollDiceBtn.disabled = true;
  clearReward();
  dadoState.options = [];
  renderDadoOptions();

  try {
    setDadoNote("Rolando dado...", "");
    const response = await authJson("/api/dado/roll", { uid: DADO_UID, method: "POST", json: {} });
    if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.error) || "Falha ao rolar.");
    dadoState.rollId = Number(response.data.roll_id || 0);
    dadoState.diceValue = Number(response.data.dice_value || 0);
    dadoState.options = Array.isArray(response.data.options) ? response.data.options : [];
    dadoState.balance = Number(response.data.balance || dadoState.balance || 0);
    syncDadoHero();
    await animateDiceResult(dadoState.diceValue || "?");
    renderDadoOptions();
    setDadoNote("Escolha um anime para revelar o personagem.", "success");
  } catch(err) {
    setStageMode("idle");
    setStageSignal("?", "Rolagem interrompida");
    dadoHud.textContent = "Falha na rolagem";
    setDadoNote(err.message, "error");
  } finally {
    dadoState.rolling = false;
    rollDiceBtn.disabled = false;
  }
}

rollDiceBtn.onclick = rollDice;
resetDiceBtn.onclick = function(){
  dadoState.rollId = 0;
  dadoState.diceValue = 0;
  dadoState.options = [];
  setStageMode("idle");
  setStageSignal("?", "Aguardando a proxima rolagem");
  dadoHud.textContent = "Pronto para rolar";
  renderDadoOptions();
  clearReward();
  setDadoNote("Tela limpa. O saldo continua sincronizado.", "success");
};

window.addEventListener("resize", resizeScene);

(async function(){
  try {
    ensureScene();
    setStageSignal("?", "Aguardando a proxima rolagem");
    await loadDadoUser();
    await loadDadoState({ silent: false });
    dadoState.refreshHandle = createLiveRefresh(async function(){
      await loadDadoUser();
      await loadDadoState({ silent: true });
    }, 7000);
  } catch(err) {
    setDadoNote(err.message, "error");
  }
})();
"""
    )

    body = "".join(body_parts).replace("__DADO_BANNER__", _h(banner_url))
    extra_css = "".join(css_parts)
    js = "".join(js_parts).replace("__DADO_UID__", str(int(uid)))
    return _page_template("Dado", body, extra_css=extra_css, extra_js=js, include_tg=True)


def build_baltigoflix_page(*, uid: int, banner_url: str) -> str:
    body = f"""
<section class="hero-card">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="BaltigoFlix"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">BaltigoFlix</div>
    <h1 class="hero-title">Planos premium para assistir sem bagunca.</h1>
    <p class="hero-subtitle">Uma vitrine mais elegante para apresentar os planos, reforcar confianca e levar o usuario do Mini App ate o checkout com menos ruido e mais cara de produto profissional.</p>
    <div class="hero-metrics">
      <div class="metric-card"><span class="metric-label">Jogador</span><span class="metric-value" id="flixPlayerHero">...</span></div>
      <div class="metric-card"><span class="metric-label">Planos</span><span class="metric-value">4 opcoes</span></div>
      <div class="metric-card"><span class="metric-label">Checkout</span><span class="metric-value">Cakto</span></div>
      <div class="metric-card"><span class="metric-label">Status</span><span class="metric-value"><span class="pulse-dot"></span> Disponivel</span></div>
    </div>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Assinatura</div><h2 class="section-title">Escolha seu plano</h2></div>
    <div class="section-meta" id="flixMeta">Carregando contexto do usuario...</div>
  </div>
  <div class="buy-grid" style="margin-top:14px;">
    <article class="buy-tile"><h3 class="buy-title">Plano Mensal</h3><p class="buy-copy">Entrada rapida para testar toda a experiencia sem compromisso longo.</p><div class="buy-price">R$ 25,90</div><button class="action-btn action-btn--primary" style="width:100%; margin-top:14px;" data-flix-plan="mensal">Assinar mensal</button></article>
    <article class="buy-tile"><h3 class="buy-title">Plano Trimestral</h3><p class="buy-copy">Mais tempo de uso com melhor custo para quem ja quer continuar.</p><div class="buy-price">R$ 59,90</div><button class="action-btn action-btn--cool" style="width:100%; margin-top:14px;" data-flix-plan="trimestral">Assinar trimestral</button></article>
    <article class="buy-tile"><h3 class="buy-title">Plano Semestral</h3><p class="buy-copy">Equilibrio entre economia e permanencia para uso recorrente.</p><div class="buy-price">R$ 89,90</div><button class="action-btn action-btn--cool" style="width:100%; margin-top:14px;" data-flix-plan="semestral">Assinar semestral</button></article>
    <article class="buy-tile"><h3 class="buy-title">Plano Anual</h3><p class="buy-copy">Melhor custo para quem quer resolver tudo de uma vez e aproveitar o maximo.</p><div class="buy-price">R$ 129,90</div><button class="action-btn action-btn--primary" style="width:100%; margin-top:14px;" data-flix-plan="anual">Assinar anual</button></article>
  </div>
</section>

<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Motivos</div><h2 class="section-title">Uma apresentacao mais confiavel</h2></div>
    <div class="section-meta">Sem exagero visual, com foco em decisao rapida e clareza no mobile.</div>
  </div>
  <div class="chip-row scroll-x" style="margin-top:14px;">
    <div class="chip">Checkout com contexto do usuario</div>
    <div class="chip chip--accent">Fluxo limpo</div>
    <div class="chip">Visual premium</div>
    <div class="chip">Touch friendly</div>
    <div class="chip">Telegram ready</div>
  </div>
</section>

<div id="flixNote" class="floating-note">BaltigoFlix sendo carregado...</div>
<div class="footer-note">Source Baltigo . BaltigoFlix</div>
"""
    js = f"""
const FLIX_UID = resolveWebappUid({int(uid)});
const flixNote = document.getElementById("flixNote");
const flixState = {{ user: null }};
const tgFlix = getTelegramWebApp();
if (tgFlix) {{ try {{ tgFlix.ready(); tgFlix.expand(); }} catch(err) {{}} }}
function setFlixNote(message, tone){{ flixNote.textContent = message || ""; flixNote.dataset.tone = tone || ""; }}
function flixUserLabel(){{
  const user = flixState.user || {{}};
  return String(user.nickname || user.display_name || user.full_name || (FLIX_UID > 0 ? ("UID " + FLIX_UID) : "Jogador"));
}}
async function loadFlixUser(){{
  const response = await authJson("/api/webapp/context", {{ uid: FLIX_UID }});
  if (!response.ok || !response.data.ok) throw new Error("Falha ao identificar o usuario do plano.");
  flixState.user = response.data.profile || null;
  document.getElementById("flixPlayerHero").textContent = flixUserLabel();
  document.getElementById("flixMeta").textContent = "Checkout vinculado a " + flixUserLabel();
}}
async function createFlixIntent(planCode, button){{
  button.disabled = true;
  try {{
    setFlixNote("Preparando checkout...", "");
    const user = flixState.user || {{}};
    const payload = {{
      telegram_user_id: Number(user.user_id || FLIX_UID || 0),
      telegram_username: String(user.username || ""),
      telegram_full_name: String(user.full_name || user.display_name || flixUserLabel()),
      plan_code: String(planCode || "")
    }};
    const response = await authJson("/api/baltigoflix/create-intent", {{ uid: FLIX_UID, method: "POST", json: payload }});
    if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.error) || "Nao foi possivel criar o checkout.");
    setFlixNote("Checkout criado com sucesso. Abrindo pagamento...", "success");
    openExternalLink(String(response.data.checkout_url || ""));
  }} catch(err) {{
    button.disabled = false;
    setFlixNote(err.message, "error");
  }}
}}
document.querySelectorAll("[data-flix-plan]").forEach(function(button){{
  button.onclick = function(){{
    createFlixIntent(String(button.getAttribute("data-flix-plan") || ""), button);
  }};
}});
(async function(){{
  try {{
    await loadFlixUser();
    setFlixNote("Escolha um plano para continuar.", "success");
  }} catch(err) {{
    setFlixNote(err.message, "error");
  }}
}})();
"""
    return _page_template("BaltigoFlix", body, extra_js=js, include_tg=True)


def build_cards_contrib_page(*, uid: int, banner_url: str) -> str:
    uid_q = _uid_query(uid)
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Cards contrib"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Community cards</div>
    <h1 class="hero-title">Central de contribuicoes</h1>
    <p class="hero-subtitle">Um fluxo mais organizado para os membros sugerirem novas fotos, indicar novas obras e acompanhar as regras sem ficar perdido em telas quebradas.</p>
  </div>
</section>

<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Acoes</div><h2 class="section-title">Escolha como quer ajudar</h2></div>
    <div class="section-meta">As sugestoes ficam salvas e prontas para avaliacao.</div>
  </div>
  <div class="grid-tiles" style="margin-top:14px;">
    <a class="hub-tile" href="/cards/contrib/image{uid_q}">
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill soft-pill--cool">Imagem</div>
        <h3 class="hub-title">Sugerir nova foto</h3>
        <p class="hub-copy">Pesquise um personagem e envie uma URL melhor para a arte do card.</p>
      </div>
    </a>
    <a class="hub-tile" href="/cards/contrib/work{uid_q}">
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill soft-pill--accent">Obra</div>
        <h3 class="hub-title">Pedir nova obra</h3>
        <p class="hub-copy">Busque um anime ou manga e registre uma solicitacao focada em cards.</p>
      </div>
    </a>
    <a class="hub-tile" href="/cards/contrib/rules{uid_q}">
      <div class="hub-tile-overlay"></div>
      <div class="hub-tile-content">
        <div class="soft-pill">Regras</div>
        <h3 class="hub-title">Ler regras</h3>
        <p class="hub-copy">Veja o padrao esperado antes de enviar a sua contribuicao.</p>
      </div>
    </a>
  </div>
</section>

<div class="footer-note">Source Baltigo . Cards contrib</div>
"""
    return _page_template("Cards contrib", body, include_tg=True)


def build_cards_contrib_rules_page(*, banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Regras"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Rules</div>
    <h1 class="hero-title">Padrao das contribuicoes</h1>
    <p class="hero-subtitle">Regras objetivas para manter a qualidade visual do sistema de cards sem perder consistencia.</p>
  </div>
</section>
<section class="panel panel--soft">
  <div class="setting-group">
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Formato 2:3</h3><p class="setting-sub">A imagem precisa respeitar o padrao vertical usado nos cards.</p></div></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Fidelidade ao personagem</h3><p class="setting-sub">Evite fanarts que descaracterizam muito ou confundem o personagem principal.</p></div></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Sem poluicao</h3><p class="setting-sub">Nao envie imagem com texto, watermark, moldura estranha ou varios personagens na frente do protagonista.</p></div></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Qualidade visual</h3><p class="setting-sub">Prefira imagem limpa, centralizada e em boa resolucao para o card ficar bonito no Mini App e no bot.</p></div></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Aprovacao</h3><p class="setting-sub">Sugestoes aprovadas podem substituir a imagem atual em todo o sistema e gerar a recompensa configurada.</p></div></div>
  </div>
</section>
<div class="footer-note">Source Baltigo . Rules</div>
"""
    return _page_template("Regras cards", body, include_tg=True)


def build_cards_contrib_image_page(*, uid: int, banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Nova foto"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Photo suggestion</div>
    <h1 class="hero-title">Sugerir nova foto</h1>
    <p class="hero-subtitle">Pesquise o personagem, selecione o card certo e envie uma nova URL para analise da equipe.</p>
  </div>
</section>
<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Busca</div><h2 class="section-title">Encontre o personagem</h2></div>
    <div class="section-meta" id="contribImageMeta">Digite pelo menos 2 letras.</div>
  </div>
  <label class="searchbar" style="margin-top:14px;"><span class="input-icon">Busca</span><input id="contribImageSearchInput" type="text" placeholder="Buscar personagem para sugerir foto..."></label>
  <div class="media-grid" id="contribImageResults" style="margin-top:14px;"></div>
  <div id="contribImageEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nenhum resultado</strong>Continue digitando para encontrar o personagem correto.</div>
</section>
<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Envio</div><h2 class="section-title">Dados da sugestao</h2></div>
    <div class="section-meta">A imagem nova so entra depois da aprovacao.</div>
  </div>
  <div class="setting-group" style="margin-top:14px;">
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Selecionado</h3><p class="setting-sub" id="contribImageSelectedLabel">Nenhum personagem selecionado ainda.</p></div></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Nova imagem</h3><p class="setting-sub">Use uma URL publica e direta.</p></div><label class="field" style="width:100%;"><input id="contribImageUrlInput" placeholder="https://..."></label></div>
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Observacao</h3><p class="setting-sub">Opcional. Explique rapidamente o motivo da troca.</p></div><label class="field" style="width:100%; min-height:120px; align-items:flex-start; padding:14px;"><textarea id="contribImageNoteInput" style="width:100%; min-height:90px; resize:vertical; border:0; outline:none; background:transparent; color:inherit;" placeholder="Ex: imagem mais limpa, melhor enquadramento, arte oficial."></textarea></label></div>
    <button class="action-btn action-btn--primary" id="sendContribImageBtn" style="width:100%;">Enviar sugestao de foto</button>
  </div>
</section>
<div id="contribImageNote" class="floating-note">Area de contribuicao sendo carregada...</div>
<div class="footer-note">Source Baltigo . Suggest photo</div>
"""
    js = f"""
const CONTRIB_IMAGE_UID = resolveWebappUid({int(uid)});
const contribImageState = {{ selected: null, items: [] }};
const contribImageNote = document.getElementById("contribImageNote");
function setContribImageNote(message, tone){{ contribImageNote.textContent = message || ""; contribImageNote.dataset.tone = tone || ""; }}
function renderContribImageResults(){{
  const root = document.getElementById("contribImageResults");
  const empty = document.getElementById("contribImageEmpty");
  document.getElementById("contribImageMeta").textContent = contribImageState.items.length ? ("Resultados " + String(contribImageState.items.length)) : "Digite pelo menos 2 letras.";
  if (!contribImageState.items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = contribImageState.items.map(function(item){{
    const img = item.image ? '<img src="' + esc(item.image) + '" alt="' + esc(item.name) + '" loading="lazy" onerror="setImageFallback(this,\\'CARD\\')">' : '';
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge">Card</div><div class="media-count">ID ' + esc(item.id || 0) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.name || "Personagem") + '</h3><div class="pill-row"><span class="soft-pill soft-pill--cool">' + esc(item.anime || "") + '</span></div><button class="action-btn action-btn--cool" style="width:100%; margin-top:14px;" data-select-char="' + esc(item.id || 0) + '">Selecionar</button></div>'
      + '</article>';
  }}).join("");
  root.querySelectorAll("[data-select-char]").forEach(function(button){{
    button.onclick = function(){{
      const cid = Number(button.getAttribute("data-select-char") || 0);
      contribImageState.selected = contribImageState.items.find(function(item){{ return Number(item.id || 0) === cid; }}) || null;
      document.getElementById("contribImageSelectedLabel").textContent = contribImageState.selected ? (contribImageState.selected.name + " . " + contribImageState.selected.anime + " . ID " + contribImageState.selected.id) : "Nenhum personagem selecionado ainda.";
      setContribImageNote("Personagem selecionado. Agora envie a nova URL.", "success");
    }};
  }});
}}
async function searchContribImages(query){{
  const q = String(query || "").trim();
  if (q.length < 2){{
    contribImageState.items = [];
    renderContribImageResults();
    return;
  }}
  setSkeleton("contribImageResults", 4);
  const res = await fetch("/api/cards/search?q=" + encodeURIComponent(q) + "&limit=24&_ts=" + Date.now());
  const data = await res.json();
  contribImageState.items = Array.isArray(data.items) ? data.items : [];
  renderContribImageResults();
}}
document.getElementById("contribImageSearchInput").addEventListener("input", debounce(async function(event){{
  try {{
    await searchContribImages(event.target.value || "");
  }} catch(err) {{
    contribImageState.items = [];
    renderContribImageResults();
    setContribImageNote("Falha ao buscar personagens.", "error");
  }}
}}, 260));
document.getElementById("sendContribImageBtn").onclick = async function(){{
  try {{
    if (!contribImageState.selected) throw new Error("Selecione um personagem antes de enviar.");
    const url = String(document.getElementById("contribImageUrlInput").value || "").trim();
    if (!/^https?:\\/\\//i.test(url)) throw new Error("Envie uma URL publica valida.");
    const note = String(document.getElementById("contribImageNoteInput").value || "").trim();
    setContribImageNote("Enviando sugestao...", "");
    const response = await authJson("/api/cards/contrib/image", {{ uid: CONTRIB_IMAGE_UID, method: "POST", json: {{ character_id: contribImageState.selected.id, suggested_image_url: url, note: note }} }});
    if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.message) || "Nao foi possivel enviar.");
    document.getElementById("contribImageUrlInput").value = "";
    document.getElementById("contribImageNoteInput").value = "";
    setContribImageNote("Sugestao enviada com sucesso para avaliacao.", "success");
  }} catch(err) {{
    setContribImageNote(err.message, "error");
  }}
}};
"""
    return _page_template("Sugerir foto", body, extra_js=js, include_tg=True)


def build_cards_contrib_work_page(*, uid: int, banner_url: str) -> str:
    body = f"""
<section class="hero-card hero-card--compact">
  <div class="hero-media"><img src="{_h(banner_url)}" alt="Nova obra"></div>
  <div class="hero-overlay"></div>
  <div class="hero-content">
    <div class="eyebrow-chip">Work request</div>
    <h1 class="hero-title">Pedir nova obra para cards</h1>
    <p class="hero-subtitle">Busque um titulo na base, selecione o item certo e registre o pedido com o mesmo padrao visual do restante do produto.</p>
  </div>
</section>
<section class="panel">
  <div class="section-head">
    <div><div class="section-kicker">Busca</div><h2 class="section-title">Escolha o tipo de obra</h2></div>
    <div class="section-meta" id="contribWorkMeta">Pesquise anime ou manga.</div>
  </div>
  <div class="segmented" style="margin-top:14px;">
    <button type="button" class="segmented-btn active" id="contribWorkAnimeBtn">Anime</button>
    <button type="button" class="segmented-btn" id="contribWorkMangaBtn">Manga</button>
  </div>
  <label class="searchbar" style="margin-top:14px;"><span class="input-icon">Busca</span><input id="contribWorkSearchInput" type="text" placeholder="Buscar obra para cards..."></label>
  <div class="media-grid" id="contribWorkResults" style="margin-top:14px;"></div>
  <div id="contribWorkEmpty" class="empty-state" style="display:none; margin-top:14px;"><strong>Nenhum resultado</strong>Pesquise um titulo para registrar o pedido.</div>
</section>
<section class="panel panel--soft">
  <div class="section-head">
    <div><div class="section-kicker">Envio</div><h2 class="section-title">Obra selecionada</h2></div>
    <div class="section-meta">A equipe vai analisar se a obra entra no sistema de cards.</div>
  </div>
  <div class="setting-group" style="margin-top:14px;">
    <div class="setting-row"><div class="setting-copy"><h3 class="setting-title">Selecionado</h3><p class="setting-sub" id="contribWorkSelectedLabel">Nenhuma obra selecionada ainda.</p></div></div>
    <button class="action-btn action-btn--primary" id="sendContribWorkBtn" style="width:100%;">Enviar pedido de obra</button>
  </div>
</section>
<div id="contribWorkNote" class="floating-note">Area de pedidos de obra sendo carregada...</div>
<div class="footer-note">Source Baltigo . Suggest work</div>
"""
    js = f"""
const CONTRIB_WORK_UID = resolveWebappUid({int(uid)});
const contribWorkState = {{ mediaType: "anime", selected: null, items: [] }};
const contribWorkNote = document.getElementById("contribWorkNote");
function setContribWorkNote(message, tone){{ contribWorkNote.textContent = message || ""; contribWorkNote.dataset.tone = tone || ""; }}
function applyContribWorkType(){{
  document.getElementById("contribWorkAnimeBtn").classList.toggle("active", contribWorkState.mediaType === "anime");
  document.getElementById("contribWorkMangaBtn").classList.toggle("active", contribWorkState.mediaType === "manga");
  document.getElementById("contribWorkSearchInput").placeholder = contribWorkState.mediaType === "anime" ? "Buscar anime para cards..." : "Buscar manga para cards...";
}}
function renderContribWorkResults(){{
  const root = document.getElementById("contribWorkResults");
  const empty = document.getElementById("contribWorkEmpty");
  document.getElementById("contribWorkMeta").textContent = contribWorkState.items.length ? ("Resultados " + String(contribWorkState.items.length)) : "Pesquise anime ou manga.";
  if (!contribWorkState.items.length){{
    root.innerHTML = "";
    empty.style.display = "";
    return;
  }}
  empty.style.display = "none";
  root.innerHTML = contribWorkState.items.map(function(item){{
    const disabled = item.already_exists || item.already_requested;
    const img = item.cover ? '<img src="' + esc(item.cover) + '" alt="' + esc(item.title) + '" loading="lazy" onerror="setImageFallback(this,\\'MEDIA\\')">' : '';
    const statePill = item.already_exists ? '<span class="soft-pill">Ja existe</span>' : (item.already_requested ? '<span class="soft-pill soft-pill--accent">Ja pedido</span>' : '<span class="soft-pill soft-pill--cool">Disponivel</span>');
    return ''
      + '<article class="media-card">'
      + '<div class="media-cover">' + img + '<div class="media-badge">' + esc(contribWorkState.mediaType) + '</div></div>'
      + '<div class="media-body"><h3 class="card-title">' + esc(item.title || "Obra") + '</h3><div class="pill-row">' + statePill + (item.year ? '<span class="soft-pill">' + esc(item.year) + '</span>' : '') + '</div><button class="action-btn action-btn--cool" style="width:100%; margin-top:14px;" data-select-work="' + esc(item.id || 0) + '"' + (disabled ? ' disabled' : '') + '>Selecionar obra</button></div>'
      + '</article>';
  }}).join("");
  root.querySelectorAll("[data-select-work]").forEach(function(button){{
    button.onclick = function(){{
      const id = Number(button.getAttribute("data-select-work") || 0);
      contribWorkState.selected = contribWorkState.items.find(function(item){{ return Number(item.id || 0) === id; }}) || null;
      document.getElementById("contribWorkSelectedLabel").textContent = contribWorkState.selected ? (contribWorkState.selected.title + " . " + contribWorkState.mediaType + " . ID " + contribWorkState.selected.id) : "Nenhuma obra selecionada ainda.";
      setContribWorkNote("Obra selecionada para o pedido.", "success");
    }};
  }});
}}
async function searchContribWork(query){{
  const q = String(query || "").trim();
  if (q.length < 2){{
    contribWorkState.items = [];
    renderContribWorkResults();
    return;
  }}
  setSkeleton("contribWorkResults", 4);
  const res = await fetch("/api/cards/contrib/work/search?q=" + encodeURIComponent(q) + "&media_type=" + encodeURIComponent(contribWorkState.mediaType));
  const data = await res.json();
  contribWorkState.items = Array.isArray(data.items) ? data.items : [];
  renderContribWorkResults();
}}
document.getElementById("contribWorkAnimeBtn").onclick = function(){{ contribWorkState.mediaType = "anime"; contribWorkState.items = []; contribWorkState.selected = null; applyContribWorkType(); renderContribWorkResults(); }};
document.getElementById("contribWorkMangaBtn").onclick = function(){{ contribWorkState.mediaType = "manga"; contribWorkState.items = []; contribWorkState.selected = null; applyContribWorkType(); renderContribWorkResults(); }};
document.getElementById("contribWorkSearchInput").addEventListener("input", debounce(async function(event){{
  try {{
    await searchContribWork(event.target.value || "");
  }} catch(err) {{
    contribWorkState.items = [];
    renderContribWorkResults();
    setContribWorkNote("Falha ao buscar obra.", "error");
  }}
}}, 260));
document.getElementById("sendContribWorkBtn").onclick = async function(){{
  try {{
    if (!contribWorkState.selected) throw new Error("Selecione uma obra antes de enviar.");
    setContribWorkNote("Enviando pedido de obra...", "");
    const response = await authJson("/api/cards/contrib/work", {{ uid: CONTRIB_WORK_UID, method: "POST", json: {{ media_type: contribWorkState.mediaType, anilist_id: contribWorkState.selected.id, title: contribWorkState.selected.title, cover_url: contribWorkState.selected.cover || "" }} }});
    if (!response.ok || !response.data.ok) throw new Error((response.data && response.data.message) || "Nao foi possivel enviar.");
    setContribWorkNote("Pedido de obra enviado com sucesso.", "success");
  }} catch(err) {{
    setContribWorkNote(err.message, "error");
  }}
}};
applyContribWorkType();
"""
    return _page_template("Pedir obra", body, extra_js=js, include_tg=True)
