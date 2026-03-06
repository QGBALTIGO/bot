from fastapi import Query
from fastapi.responses import HTMLResponse, JSONResponse

from cards_service import (
    build_cards_final_data,
    find_anime,
    list_subcategories,
    reload_cards_cache,
    search_characters,
)

CARDS_TOP_BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg"


def register_cards_routes(app):
    @app.get("/api/cards/reload")
    def api_cards_reload():
        reload_cards_cache()
        data = build_cards_final_data(force_reload=True)
        return JSONResponse({
            "ok": True,
            "total_animes": len(data["animes_list"]),
            "total_characters": len(data["characters_by_id"]),
        })

    @app.get("/api/cards/animes")
    def api_cards_animes(
        q: str = Query(default="", max_length=120),
        limit: int = Query(default=500, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
    ):
        data = build_cards_final_data()
        items = data["animes_list"]

        qn = q.strip().lower()
        if qn:
            items = [x for x in items if qn in x["anime"].lower()]

        total = len(items)
        items = items[offset: offset + limit]

        return JSONResponse({
            "ok": True,
            "total": total,
            "items": items,
        })

    @app.get("/api/cards/characters")
    def api_cards_characters(
        anime_id: int = Query(...),
        q: str = Query(default="", max_length=120),
        limit: int = Query(default=500, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
    ):
        data = build_cards_final_data()
        anime = data["animes_by_id"].get(anime_id)

        if not anime:
            return JSONResponse({
                "ok": False,
                "anime": None,
                "total": 0,
                "items": [],
            })

        chars = list(data["characters_by_anime"].get(anime_id, []))

        qn = q.strip().lower()
        if qn:
            chars = [x for x in chars if qn in x["name"].lower()]

        total = len(chars)
        chars = chars[offset: offset + limit]

        return JSONResponse({
            "ok": True,
            "anime": anime,
            "total": total,
            "items": chars,
        })

    @app.get("/api/cards/search")
    def api_cards_search(
        q: str = Query(..., min_length=1, max_length=120),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        items = search_characters(q, limit=limit)
        return JSONResponse({
            "ok": True,
            "total": len(items),
            "items": items,
        })

    @app.get("/api/cards/find-anime")
    def api_cards_find_anime(q: str = Query(..., min_length=1, max_length=120)):
        anime = find_anime(q)
        return JSONResponse({
            "ok": bool(anime),
            "anime": anime,
        })

    @app.get("/api/cards/subcategories")
    def api_cards_subcategories():
        return JSONResponse({
            "ok": True,
            "items": list_subcategories(),
        })

    @app.get("/api/cards/subcategory")
    def api_cards_subcategory(
        name: str = Query(..., min_length=1, max_length=120),
        q: str = Query(default="", max_length=120),
        limit: int = Query(default=500, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
    ):
        data = build_cards_final_data()
        chars = list(data["subcategories"].get(name, []))

        qn = q.strip().lower()
        if qn:
            chars = [x for x in chars if qn in x["name"].lower()]

        total = len(chars)
        chars = chars[offset: offset + limit]

        return JSONResponse({
            "ok": True,
            "subcategory": name,
            "total": total,
            "items": chars,
        })

    @app.get("/cards", response_class=HTMLResponse)
    def cards_page():
        return HTMLResponse(f"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Cards</title>
<style>
:root{{
  --bg:#08111d;
  --bg2:#0d1726;
  --card:rgba(255,255,255,.06);
  --stroke:rgba(255,255,255,.10);
  --text:#f5f7fb;
  --muted:rgba(255,255,255,.68);
}}
*{{box-sizing:border-box}}
body{{
  margin:0;
  font-family:Arial,Helvetica,sans-serif;
  background:linear-gradient(180deg,var(--bg),var(--bg2));
  color:var(--text);
}}
.wrap{{max-width:1100px;margin:0 auto;padding:18px}}
.banner{{
  width:100%;height:180px;object-fit:cover;border-radius:20px;
  border:1px solid var(--stroke);display:block;
}}
.top{{margin-top:16px;display:grid;gap:12px}}
.input{{
  width:100%;padding:14px 16px;border-radius:14px;border:1px solid var(--stroke);
  background:rgba(255,255,255,.05);color:#fff;font-size:15px;outline:none;
}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-top:18px}}
.card{{
  background:var(--card);border:1px solid var(--stroke);border-radius:18px;overflow:hidden;
  cursor:pointer;transition:.18s transform ease,.18s border-color ease;
}}
.card:hover{{transform:translateY(-2px);border-color:rgba(255,255,255,.22)}}
.cover{{width:100%;height:130px;object-fit:cover;background:#111}}
.info{{padding:12px}}
.title{{font-weight:700;font-size:15px;line-height:1.3}}
.meta{{margin-top:6px;color:var(--muted);font-size:13px}}
.section-title{{margin-top:26px;font-size:18px;font-weight:800}}
.subs{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}}
.sub{{
  padding:10px 14px;border-radius:999px;background:rgba(255,255,255,.06);
  border:1px solid var(--stroke);cursor:pointer;font-size:13px
}}
.small{{font-size:13px;color:var(--muted)}}
</style>
</head>
<body>
  <div class="wrap">
    <img class="banner" src="{CARDS_TOP_BANNER_URL}" alt="Cards">
    <div class="top">
      <input id="animeSearch" class="input" placeholder="Buscar obra... ex: one piece">
      <input id="charSearch" class="input" placeholder="Buscar personagem... ex: zoro">
      <div class="small">Você pode buscar por obra ou personagem.</div>
    </div>

    <div class="section-title">Subcategorias</div>
    <div id="subs" class="subs"></div>

    <div class="section-title">Obras</div>
    <div id="grid" class="grid"></div>
  </div>

<script>
const animeSearch = document.getElementById("animeSearch");
const charSearch = document.getElementById("charSearch");
const grid = document.getElementById("grid");
const subs = document.getElementById("subs");

function esc(s){{
  return String(s || "").replace(/[&<>"]/g, m => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[m]));
}}

async function loadAnimes(q=""){{
  const res = await fetch("/api/cards/animes?q=" + encodeURIComponent(q) + "&limit=5000");
  const data = await res.json();
  grid.innerHTML = "";

  for (const a of (data.items || [])) {{
    const cover = a.cover_image || a.banner_image || "{CARDS_TOP_BANNER_URL}";
    const el = document.createElement("div");
    el.className = "card";
    el.onclick = () => {{
      window.location.href = "/cards/anime?anime_id=" + encodeURIComponent(a.anime_id);
    }};
    el.innerHTML = `
      <img class="cover" src="${{esc(cover)}}" alt="">
      <div class="info">
        <div class="title">${{esc(a.anime)}}</div>
        <div class="meta">${{a.characters_count || 0}} personagens</div>
      </div>
    `;
    grid.appendChild(el);
  }}
}}

async function loadSubs(){{
  const res = await fetch("/api/cards/subcategories");
  const data = await res.json();
  subs.innerHTML = "";
  for (const s of (data.items || [])) {{
    const el = document.createElement("div");
    el.className = "sub";
    el.textContent = `${{s.name}} (${{s.count}})`;
    el.onclick = () => {{
      window.location.href = "/cards/subcategory?name=" + encodeURIComponent(s.name);
    }};
    subs.appendChild(el);
  }}
}}

animeSearch.addEventListener("input", () => loadAnimes(animeSearch.value));

charSearch.addEventListener("keydown", async (e) => {{
  if (e.key !== "Enter") return;
  const q = charSearch.value.trim();
  if (!q) return;
  window.location.href = "/cards/search?q=" + encodeURIComponent(q);
}});

loadAnimes();
loadSubs();
</script>
</body>
</html>
""")

    @app.get("/cards/anime", response_class=HTMLResponse)
    def cards_anime_page(anime_id: int = Query(...)):
        return HTMLResponse(f"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Cards Anime</title>
<style>
:root{{
  --bg:#08111d;
  --bg2:#0d1726;
  --card:rgba(255,255,255,.06);
  --stroke:rgba(255,255,255,.10);
  --text:#f5f7fb;
  --muted:rgba(255,255,255,.68);
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:linear-gradient(180deg,var(--bg),var(--bg2));color:var(--text)}}
.wrap{{max-width:1100px;margin:0 auto;padding:18px}}
.banner{{width:100%;height:220px;object-fit:cover;border-radius:20px;border:1px solid var(--stroke);display:block}}
.back{{display:inline-block;margin-bottom:12px;color:#fff;text-decoration:none;font-weight:700}}
.title{{font-size:28px;font-weight:800;margin:14px 0 4px}}
.meta{{color:var(--muted);margin-bottom:16px}}
.input{{width:100%;padding:14px 16px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.05);color:#fff;font-size:15px;outline:none}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-top:18px}}
.card{{background:var(--card);border:1px solid var(--stroke);border-radius:18px;overflow:hidden}}
.char-img{{width:100%;height:240px;object-fit:cover;background:#111}}
.info{{padding:12px}}
.name{{font-weight:700;font-size:14px;line-height:1.3}}
.anime{{margin-top:6px;font-size:12px;color:var(--muted)}}
</style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="/cards">← Voltar</a>
    <div id="head"></div>
    <input id="q" class="input" placeholder="Buscar personagem nesta obra...">
    <div id="grid" class="grid"></div>
  </div>

<script>
const animeId = {anime_id};
const head = document.getElementById("head");
const grid = document.getElementById("grid");
const q = document.getElementById("q");

function esc(s){{
  return String(s || "").replace(/[&<>"]/g, m => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[m]));
}}

async function load(){{
  const res = await fetch("/api/cards/characters?anime_id=" + animeId + "&q=" + encodeURIComponent(q.value) + "&limit=5000");
  const data = await res.json();

  if (!data.ok || !data.anime) {{
    head.innerHTML = "<div class='title'>Obra não encontrada</div>";
    grid.innerHTML = "";
    return;
  }}

  const banner = data.anime.banner_image || data.anime.cover_image || "{CARDS_TOP_BANNER_URL}";
  head.innerHTML = `
    <img class="banner" src="${{esc(banner)}}" alt="">
    <div class="title">${{esc(data.anime.anime)}}</div>
    <div class="meta">${{data.total}} personagens</div>
  `;

  grid.innerHTML = "";
  for (const c of (data.items || [])) {{
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <img class="char-img" src="${{esc(c.image || '{CARDS_TOP_BANNER_URL}')}}" alt="">
      <div class="info">
        <div class="name">${{esc(c.name)}}</div>
        <div class="anime">${{esc(c.anime)}}</div>
      </div>
    `;
    grid.appendChild(el);
  }}
}}

q.addEventListener("input", load);
load();
</script>
</body>
</html>
""")

    @app.get("/cards/subcategory", response_class=HTMLResponse)
    def cards_subcategory_page(name: str = Query(...)):
        return HTMLResponse(f"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Subcategoria</title>
<style>
:root{{
  --bg:#08111d;
  --bg2:#0d1726;
  --card:rgba(255,255,255,.06);
  --stroke:rgba(255,255,255,.10);
  --text:#f5f7fb;
  --muted:rgba(255,255,255,.68);
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:linear-gradient(180deg,var(--bg),var(--bg2));color:var(--text)}}
.wrap{{max-width:1100px;margin:0 auto;padding:18px}}
.back{{display:inline-block;margin-bottom:12px;color:#fff;text-decoration:none;font-weight:700}}
.title{{font-size:28px;font-weight:800;margin:6px 0 4px}}
.meta{{color:var(--muted);margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-top:18px}}
.card{{background:var(--card);border:1px solid var(--stroke);border-radius:18px;overflow:hidden}}
.char-img{{width:100%;height:240px;object-fit:cover;background:#111}}
.info{{padding:12px}}
.name{{font-weight:700;font-size:14px;line-height:1.3}}
.anime{{margin-top:6px;font-size:12px;color:var(--muted)}}
</style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="/cards">← Voltar</a>
    <div class="title">Subcategoria: {name}</div>
    <div id="meta" class="meta"></div>
    <div id="grid" class="grid"></div>
  </div>

<script>
const grid = document.getElementById("grid");
const meta = document.getElementById("meta");

function esc(s){{
  return String(s || "").replace(/[&<>"]/g, m => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[m]));
}}

async function load(){{
  const res = await fetch("/api/cards/subcategory?name=" + encodeURIComponent({name!r}) + "&limit=5000");
  const data = await res.json();
  meta.textContent = (data.total || 0) + " personagens";
  grid.innerHTML = "";

  for (const c of (data.items || [])) {{
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <img class="char-img" src="${{esc(c.image || '{CARDS_TOP_BANNER_URL}')}}" alt="">
      <div class="info">
        <div class="name">${{esc(c.name)}}</div>
        <div class="anime">${{esc(c.anime)}}</div>
      </div>
    `;
    grid.appendChild(el);
  }}
}}

load();
</script>
</body>
</html>
""")

    @app.get("/cards/search", response_class=HTMLResponse)
    def cards_search_page(q: str = Query(...)):
        return HTMLResponse(f"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Busca</title>
<style>
:root{{
  --bg:#08111d;
  --bg2:#0d1726;
  --card:rgba(255,255,255,.06);
  --stroke:rgba(255,255,255,.10);
  --text:#f5f7fb;
  --muted:rgba(255,255,255,.68);
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:linear-gradient(180deg,var(--bg),var(--bg2));color:var(--text)}}
.wrap{{max-width:1100px;margin:0 auto;padding:18px}}
.back{{display:inline-block;margin-bottom:12px;color:#fff;text-decoration:none;font-weight:700}}
.title{{font-size:28px;font-weight:800;margin:6px 0 4px}}
.meta{{color:var(--muted);margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-top:18px}}
.card{{background:var(--card);border:1px solid var(--stroke);border-radius:18px;overflow:hidden}}
.char-img{{width:100%;height:240px;object-fit:cover;background:#111}}
.info{{padding:12px}}
.name{{font-weight:700;font-size:14px;line-height:1.3}}
.anime{{margin-top:6px;font-size:12px;color:var(--muted)}}
</style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="/cards">← Voltar</a>
    <div class="title">Busca: {q}</div>
    <div id="meta" class="meta"></div>
    <div id="grid" class="grid"></div>
  </div>

<script>
const grid = document.getElementById("grid");
const meta = document.getElementById("meta");

function esc(s){{
  return String(s || "").replace(/[&<>"]/g, m => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[m]));
}}

async function load(){{
  const res = await fetch("/api/cards/search?q=" + encodeURIComponent({q!r}) + "&limit=500");
  const data = await res.json();
  meta.textContent = (data.total || 0) + " resultados";
  grid.innerHTML = "";

  for (const c of (data.items || [])) {{
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <img class="char-img" src="${{esc(c.image || '{CARDS_TOP_BANNER_URL}')}}" alt="">
      <div class="info">
        <div class="name">${{esc(c.name)}}</div>
        <div class="anime">${{esc(c.anime)}}</div>
      </div>
    `;
    grid.appendChild(el);
  }}
}}

load();
</script>
</body>
</html>
""")
