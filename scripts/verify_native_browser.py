"""Offline browser regression harness. Uses synthetic accounts, never a live bot.

Usage: python scripts/verify_native_browser.py --serve
       python scripts/verify_native_browser.py --test --output /tmp/native-proof
Requires Playwright and Chromium; does not change production configuration.
"""

from __future__ import annotations
import argparse
import json
import mimetypes
import os
import shutil
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "aninexus_frontend/dist"
PORT = 8765
STATE = {
    "posts": [],
    "gets": [],
    "me_delay": 0,
    "favorite": {"id": 1, "name": "Personagem 01", "anime": "Obra de teste 01", "image": "/fixture-art/0.svg"},
    "coins": 100,
    "nickname": "Tester",
    "private_profile": False,
    "notifications_enabled": True,
    "country_code": "BR",
    "language": "pt",
}
USER = {
    "id": 77,
    "first_name": "Usuário de teste",
    "last_name": "",
    "username": "source_tester",
    "avatar": "/fixture-art/0.svg",
    "is_sudo": True,
    "can_upload": True,
    "balance": 100,
    "zenith": 12,
    "stats": {
        "points": 100,
        "zenith": 12,
        "level": 8,
        "xp_current": 25,
        "xp_needed": 100,
        "total_characters": 12,
        "unique_characters": 12,
        "total_available_characters": 60,
        "collection_percent": 20,
        "rank": 2,
        "percentile": 10,
        "pass_type": "free",
    },
    "titles": {"current": "Colecionador"},
    "characters": [],
    "pets": [],
    "eggs": [],
    "current_pet": None,
}
WORKS = [
    {
        "anime_id": i + 1,
        "anime": f"Obra de teste {i + 1:02}",
        "cover_image": f"/fixture-art/{i % 18}.svg",
        "banner_image": f"/fixture-art/{i % 18}.svg",
        "count": 6,
        "owned_count": 2,
        "total_count": 6,
        "completion_pct": 33,
        "missing_count": 4,
    }
    for i in range(55)
]
CHARACTERS = [
    {
        "id": i + 1,
        "character_id": i + 1,
        "name": f"Personagem {i + 1:02}",
        "anime": "Obra de teste 01",
        "anime_id": 1,
        "image": f"/fixture-art/{i % 18}.svg",
        "quantity": 2,
        "character_name": f"Personagem {i + 1:02}",
        "anime_title": "Obra de teste 01",
        "rarity": "COMUM",
        "subcategory": "Heróis",
    }
    for i in range(55)
]
CATALOG = [
    {
        "message_id": i + 1,
        "titulo": f"Obra de teste {i + 1:02}",
        "cover_url": f"/fixture-art/{i % 18}.svg",
        "link_post": f"https://t.me/SourceBaltigo/{i + 1}",
        "format": "TV",
        "score": 8,
        "year": 2026,
        "letter": "O",
    }
    for i in range(55)
]
PLANS = [
    {"code": "mensal", "name": "Plano Mensal", "amount_cents": 2590},
    {"code": "trimestral", "name": "Plano Trimestral", "amount_cents": 5990},
    {"code": "semestral", "name": "Plano Semestral", "amount_cents": 8990},
    {"code": "anual", "name": "Plano Anual", "amount_cents": 12990},
]
TEXTS = {
    "title": "Termos de Uso e Privacidade",
    "subtitle": "Revisão de teste",
    "intro": "Leia os termos antes de continuar.",
    "check1": "Aceito a Política de Privacidade",
    "check2": "Aceito os Termos de Uso",
    "accept": "Aceitar e continuar",
    "decline": "Não aceito",
    "done": "Aceito com sucesso. Volte ao Telegram.",
    "no": "Termos não aceitos.",
    "join_title": "Canal obrigatório",
    "join_text": "Entre no canal para continuar.",
    "join_button": "Entrar no canal",
    "verify_button": "Verificar inscrição",
    "verify_ok": "Inscrição confirmada.",
    "verify_confirmed": "Confirmado",
}
BOOT = """
window.__bootCount=Number(sessionStorage.getItem('fixture_boots')||0)+1;
sessionStorage.setItem('fixture_boots',String(window.__bootCount));
sessionStorage.setItem('auth_token','fixture-token');sessionStorage.setItem('aninexus_intro_seen','1');
if(new URLSearchParams(location.search).has('cold_start')){sessionStorage.removeItem('auth_token');sessionStorage.removeItem('aninexus_intro_seen');}
window.__backHandlers=new Set();window.__external=[];
window.Telegram={WebApp:{initData:'fixture-signed-data',initDataUnsafe:{user:{id:77}},colorScheme:'dark',themeParams:{bg_color:'#09090b'},ready(){},expand(){},close(){window.__closed=true},setHeaderColor(){},setBackgroundColor(){},enableVerticalSwipes(){},disableVerticalSwipes(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(fn){window.__backHandlers.add(fn)},offClick(fn){window.__backHandlers.delete(fn)}},HapticFeedback:{selectionChanged(){},impactOccurred(){},notificationOccurred(){}},openLink(url){window.__external.push(url)},openTelegramLink(url){window.__external.push(url)}}};
"""


def fixture(path, query, method, body):
    if method == "GET":
        STATE["gets"].append(path)
        if path == "/api/native/version":
            version_file = DIST / "ui-version.json"
            return json.loads(version_file.read_text()) if version_file.is_file() else {}
    if method == "POST":
        STATE["posts"].append({"path": path, "body": body})
        if path.endswith("/secure_init"):
            return {"token": "fixture-token"}
        if path == "/api/menu/favorite":
            cid = body.get("character_id")
            c = next((c for c in CHARACTERS if c["id"] == cid), None)
            STATE["favorite"] = {k: c[k] for k in ("id", "name", "anime", "image")} if c else None
            return {"ok": True, "favorite": STATE["favorite"]}
        if path == "/api/menu/delete-account":
            return {"ok": True}
        if path == "/api/native/nickname":
            STATE["nickname"] = body["nickname"]
            STATE["coins"] -= 3
        if path == "/api/shop/sell/confirm":
            STATE["coins"] += 1
        for key in ["country", "language", "privacy", "notifications"]:
            if path == f"/api/menu/{key}":
                field = {
                    "country": "country_code",
                    "language": "language",
                    "privacy": "private_profile",
                    "notifications": "notifications_enabled",
                }[key]
                STATE[field] = body.get("value", body.get(field))
        if path == "/api/baltigoflix/create-intent":
            return {
                "ok": True,
                "plan_name": "Plano Mensal",
                "amount_cents": 2590,
                "checkout_url": "https://pay.cakto.com.br/test-only",
                "intent_token": "fixture-intent",
            }
        if path.endswith("/dado/roll"):
            return {
                "ok": True,
                "roll_id": 1,
                "dice_value": 2,
                "balance": 11,
                "options": [
                    {
                        "id": 1,
                        "title": "Obra de teste 01",
                        "cover": "/fixture-art/0.svg",
                    },
                    {
                        "id": 2,
                        "title": "Obra de teste 02",
                        "cover": "/fixture-art/1.svg",
                    },
                ],
            }
        if path.endswith("/dado/pick"):
            return {
                "ok": True,
                "balance": 11,
                "character": {
                    "id": 1,
                    "name": "Personagem 01",
                    "anime_title": "Obra de teste 01",
                    "tier": "COMUM",
                    "image": "/fixture-art/0.svg",
                },
            }
        return {"ok": True, "message": "Operação de teste concluída."}
    if path == "/api/native/config":
        return {
            "ok": True,
            "plans": PLANS,
            "nickname_price": 3,
            "sell_price": 1,
            "channel_url": "https://t.me/SourceBaltigo",
            "terms_version": "test",
            "language": "pt",
            "texts": TEXTS,
            "terms": [
                {
                    "title": "SUA PRIVACIDADE",
                    "text": "Texto sintético para validar a leitura nativa de termos.",
                },
                {
                    "title": "USO JUSTO",
                    "text": "Não use automação ou exploração de falhas.",
                },
            ],
        }
    if path.endswith("/me"):
        time.sleep(STATE["me_delay"])
        return {
            **USER,
            "favorite": STATE["favorite"],
            "nickname": STATE["nickname"],
            "balance": STATE["coins"],
            "stats": {**USER["stats"], "points": STATE["coins"]},
        }
    if path.endswith("/bot/info"):
        return {"name": "Source Baltigo"}
    if path.endswith("/healthz"):
        return {"ok": True}
    if path.endswith("/source-shop"):
        return {
            "coins": STATE["coins"],
            "dado_balance": 12,
            "dado_max": 24,
            "dado_price": 2,
            "level": 8,
            "countdown_label": "08:00:00",
            "offers": [
                {
                    "slot_code": "normal_1",
                    "group": "normal",
                    "card_id": 1,
                    "name": "Personagem 01",
                    "title": "Obra de teste 01",
                    "card_no": "001",
                    "rarity": "COMUM",
                    "bp": "A",
                    "image": "/fixture-art/0.svg",
                    "price": 3,
                    "level_required": 1,
                    "bought": False,
                }
            ],
        }
    if path.endswith("/dado/state"):
        return {
            "balance": 12,
            "max_balance": 24,
            "next_recharge_hhmm": "16:00",
            "active_roll": None,
        }
    if path.endswith("/social/marriage"):
        return None
    if path.endswith("/battle/stats"):
        return {"total_battles": 10, "wins": 6, "losses": 4, "win_rate": 60}
    if path.endswith("/rarities"):
        return ["COMUM", "RARO"]
    if path.endswith("/harem"):
        return {
            "items": [
                {
                    "id": str(c["id"]),
                    "name": c["name"],
                    "anime": c["anime"],
                    "rarity": "COMUM",
                    "img_url": c["image"],
                    "zenith_price": 3,
                    "owned": True,
                    "count": 2,
                }
                for c in CHARACTERS[:12]
            ],
            "total": 12,
            "has_more": False,
        }
    if path == "/api/menu/profile":
        return {
            "ok": True,
            "profile": {
                "user_id": 77,
                "display_name": "Usuário de teste",
                "coins": STATE["coins"],
                "level": 8,
                "nickname": STATE["nickname"],
                "country_code": STATE["country_code"],
                "language": STATE["language"],
                "private_profile": STATE["private_profile"],
                "notifications_enabled": STATE["notifications_enabled"],
                "favorite": STATE["favorite"],
            },
            "countries": [
                {"code": "BR", "name": "Brasil"},
                {"code": "JP", "name": "Japão"},
            ],
            "languages": [
                {"code": "pt", "name": "Português"},
                {"code": "en", "name": "English"},
            ],
        }
    if path == "/api/collection/state":
        return {
            "ok": True,
            "stats": {"unique_cards": 12, "total_copies": 24, "completed_animes": 1},
            "profile": {},
        }
    if path == "/api/cards/subcategories":
        return {"ok": True, "items": [{"name": "Heróis", "count": 55}]}
    if path == "/api/memory/best":
        return {
            "ok": True,
            "by_level": {"easy": {"time_ms": 60000, "moves": 12}},
            "summary": {},
        }
    if path == "/api/pedido/limit":
        return {"ok": True, "used": 0, "remaining": 3, "limit": 3}
    q = query.get("q", [""])[0].lower()
    if path in ["/api/pedido/search", "/api/cards/contrib/work/search"]:
        return {
            "ok": True,
            "items": [
                {
                    "id": 99,
                    "title": "Nova obra de teste",
                    "cover": "/fixture-art/1.svg",
                    "year": 2026,
                    "format": "TV",
                    "already_exists": False,
                    "already_requested": False,
                }
            ],
        }
    if path in ["/api/catalogo", "/api/mangas/catalogo"]:
        items = [x for x in CATALOG if q in x["titulo"].lower()]
        if query.get("letter", ["ALL"])[0] not in ["ALL", "O"]:
            items = []
    elif path in ["/api/cards/animes", "/api/collection/animes"]:
        items = [x for x in WORKS if q in x["anime"].lower()]
    elif path in [
        "/api/cards/characters",
        "/api/cards/search",
        "/api/cards/subcategory",
        "/api/shop/sell/all",
        "/api/collection/cards",
        "/api/collection/anime",
        "/api/menu/collection-characters",
    ]:
        items = [
            x for x in CHARACTERS if q in x["name"].lower() or q in x["anime"].lower()
        ]
    else:
        return {"ok": True, "items": []}
    offset = int(query.get("offset", [0])[0])
    limit = int(query.get("limit", [100])[0])
    return {
        "ok": True,
        "items": items[offset : offset + limit],
        "total": len(items),
        "anime": WORKS[0],
        "owned_count": 2,
        "total_count": 6,
        "missing_count": 4,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, kind="application/json", status=200):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}"
        )
        if parsed.path.startswith("/api/"):
            STATE["last_headers"] = dict(self.headers)
            self.send(fixture(parsed.path, parse_qs(parsed.query), "POST", body))
        else:
            self.send({}, status=404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/__test__/state":
            self.send(STATE)
            return
        if path.startswith("/api/"):
            self.send(fixture(path, parse_qs(parsed.query), "GET", {}))
            return
        if path.startswith("/fixture-art/"):
            n = re.findall(r"\d+", path)[0]
            hue = (int(n) * 31) % 360
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"><rect width="300" height="450" fill="hsl({hue},30%,20%)"/><circle cx="150" cy="155" r="60" fill="hsl({hue},30%,40%)"/><path d="M30 400 Q35 230 150 235 Q270 230 270 400Z" fill="hsl({hue},25%,32%)"/><text x="150" y="430" text-anchor="middle" fill="#ccc" font-family="sans-serif" font-size="15">ARTE DE TESTE {n}</text></svg>'
            self.send(svg.encode(), "image/svg+xml")
            return
        filename = (DIST / path.lstrip("/")).resolve()
        if (
            path.startswith(("/assets/", "/favicon", "/icons"))
            and filename.is_relative_to(DIST.resolve())
            and filename.is_file()
        ):
            self.send(
                filename.read_bytes(),
                mimetypes.guess_type(str(filename))[0] or "application/octet-stream",
            )
            return
        html = (DIST / "index.html").read_text()
        html = re.sub(r'<script[^>]+src="https://telegram.org[^>]*></script>', "", html)
        html = re.sub(r"<link[^>]+(?:googleapis|gstatic)[^>]*>", "", html)
        html = html.replace("frame-ancestors 'none'; ", "")
        self.send(
            html.replace("<head>", "<head><script>" + BOOT + "</script>").encode(),
            "text/html",
        )


def run_tests(output: Path):
    from playwright.sync_api import sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    report = {"routes": [], "checks": [], "page_errors": [], "console_errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.getenv("CHROMIUM_PATH")
            or shutil.which("chromium")
            or shutil.which("google-chrome"),
            args=["--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 360, "height": 800}, reduced_motion="reduce"
        )
        page = context.new_page()
        page.set_default_timeout(12000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.on(
            "console",
            lambda msg: (
                report["console_errors"].append(msg.text)
                if msg.type == "error"
                else None
            ),
        )
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        try:
            routes = json.loads(
                (ROOT / "aninexus_frontend/src/native/routes.json").read_text()
            )
            paths = list(routes)
            paths += [
                "/menu?section=sell#shop",
                "/menu?section=nickname#shop",
                "/menu#settings",
                "/cards/anime?anime_id=1",
                "/cards/subcategory?name=Heróis",
                "/cards/search?q=Personagem",
                "/cccolecao?anime_id=1",
                "/menu?view=image&character_id=1&q=Personagem%2001#contribute",
            ]
            for width in [320, 360, 390, 768, 1280]:
                page.set_viewport_size({"width": width, "height": 800})
                for path in paths:
                    page.goto(f"http://127.0.0.1:{PORT}{path}")
                    page.wait_for_selector("[data-source-shell]")
                    page.wait_for_selector("main h1")
                    page.wait_for_timeout(120)
                    title = page.locator("main h1").first.inner_text()
                    assert title and "Erro" not in title, (path, title)
                    assert page.locator("iframe").count() == 0, path
                    assert page.locator("header.sticky").count() == 1, path
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth > innerWidth + 1"
                    )
                    assert not overflow, ("overflow", path, width)
                    header_overlap = page.evaluate('() => { const h=document.querySelector(\'header.sticky\'); const b=h.querySelector(\'button[aria-label="Ir para o painel"]\'); const x=h.lastElementChild.getBoundingClientRect().left; return Array.from(b.querySelectorAll(\'span\')).some(e => {const r=e.getBoundingClientRect(); return r.width>0 && r.right>x+1;}); }')
                    assert not header_overlap, ("header overlap", path, width)
                    report["routes"].append(
                        {"path": path, "width": width, "title": title}
                    )
                page.goto(f"http://127.0.0.1:{PORT}/cards")
                page.wait_for_selector("main h1")
                page.wait_for_timeout(200)
                page.screenshot(path=str(output / f"cards-{width}.png"))
            page.set_viewport_size({"width": 360, "height": 800})
            for path, name in [
                ("/dado", "dado"),
                ("/shop", "shop"),
                ("/pedido", "requests"),
                ("/menu#settings", "settings"),
                ("/memoria", "memory"),
            ]:
                page.goto(f"http://127.0.0.1:{PORT}{path}")
                page.wait_for_selector("main h1")
                page.wait_for_timeout(150)
                page.screenshot(path=str(output / f"{name}-360.png"))
            # SPA list/detail/modal/contribution round trip, without document navigation.
            page.goto(f"http://127.0.0.1:{PORT}/cards")
            page.get_by_role("button", name="Obra de teste 01", exact=True).wait_for()
            boots = page.evaluate("window.__bootCount")
            page.get_by_role("button", name="Obra de teste 01", exact=True).click()
            page.get_by_role("button", name="Personagem 01", exact=True).wait_for()
            page.get_by_role("button", name="Personagem 01", exact=True).click()
            page.get_by_role("dialog").wait_for()
            page.get_by_role("button", name="Sugerir nova imagem").click()
            page.get_by_role("heading", name="Contribuições", exact=True).wait_for()
            assert page.evaluate("window.__bootCount") == boots
            page.go_back()
            page.get_by_role("button", name="Personagem 01", exact=True).wait_for()
            page.go_back()
            page.get_by_role("button", name="Obra de teste 01", exact=True).wait_for()
            report["checks"].append(
                "native detail, dialog, contribution and browser Back without reload"
            )
            # Real shared drawer.
            page.get_by_role("button", name="Abrir menu").click()
            page.get_by_role("dialog", name="Navegação").wait_for()
            page.get_by_role("button", name="Mangás", exact=True).click()
            page.get_by_role("heading", name="Mangás", exact=True).wait_for()
            assert page.evaluate("window.__bootCount") == boots
            page.get_by_role("button", name="Carregar mais").click()
            page.get_by_role("button", name="Obra de teste 55", exact=True).wait_for()
            page.get_by_role("textbox", name="Buscar no catálogo").fill("55")
            page.wait_for_timeout(600)
            assert (
                page.get_by_role("button", name="Obra de teste 55", exact=True).count()
                == 1
            )
            report["checks"].append(
                "shared drawer, catalog pagination and debounced search"
            )
            # First visit must follow real network readiness, not a decorative timer.
            STATE["me_delay"] = 0.15
            before_init = len([x for x in STATE["posts"] if x["path"].endswith("secure_init")])
            started = time.monotonic()
            page.goto(f"http://127.0.0.1:{PORT}/menu?cold_start=1")
            page.wait_for_selector("[data-source-shell]")
            boot_ms = round((time.monotonic() - started) * 1000)
            assert boot_ms < 2000, ("artificial boot delay", boot_ms)
            assert len([x for x in STATE["posts"] if x["path"].endswith("secure_init")]) == before_init + 1
            STATE["me_delay"] = 0
            report["fixture_boot_ms"] = boot_ms
            report["checks"].append("cold startup uses one auth initialization and real readiness")
            # Favorite is selected within settings and shared immediately with the profile.
            page.goto(f"http://127.0.0.1:{PORT}/menu#settings")
            page.get_by_role("button", name="Alterar favorito", exact=True).click()
            page.get_by_role("dialog", name="Escolher personagem favorito").wait_for()
            page.get_by_role("textbox", name="Buscar personagem favorito").fill("02")
            favorite_button = page.get_by_role("button", name="Favoritar Personagem 02", exact=True)
            favorite_button.wait_for()
            # Even a slow /me must not hold a preference button hostage.
            before_me = STATE["gets"].count("/api/v1_7b82/me")
            STATE["me_delay"] = 3
            started = time.monotonic()
            favorite_button.click()
            page.get_by_role("dialog").wait_for(state="hidden", timeout=1500)
            save_ms = round((time.monotonic() - started) * 1000)
            assert STATE["favorite"]["id"] == 2
            assert STATE["gets"].count("/api/v1_7b82/me") == before_me
            STATE["me_delay"] = 0
            report["fixture_favorite_save_ms"] = save_ms
            page.get_by_role("button", name="Ir para o painel").click()
            page.locator("[data-profile-favorite]").get_by_text("Personagem 02", exact=True).wait_for()
            page.reload()
            page.locator("[data-profile-favorite]").get_by_text("Personagem 02", exact=True).wait_for()
            page.locator("[data-profile-favorite]").get_by_role("button", name="Alterar personagem favorito", exact=True).click()
            page.locator("[data-favorite-settings]").get_by_text("Personagem 02", exact=True).wait_for()
            for width in [320, 360, 390, 768, 1280]:
                page.set_viewport_size({"width": width, "height": 720})
                page.get_by_role("button", name="Alterar favorito", exact=True).click()
                page.get_by_role("dialog", name="Escolher personagem favorito").wait_for()
                bounds = page.get_by_role("dialog").bounding_box()
                assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
                assert bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= 721
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
                page.screenshot(path=str(output / f"favorite-picker-{width}.png"))
                page.keyboard.press("Escape")
                page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Remover favorito", exact=True).click()
            page.get_by_role("button", name="Escolher favorito", exact=True).wait_for()
            assert STATE["favorite"] is None
            page.get_by_role("button", name="Ir para o painel").click()
            page.locator("[data-profile-favorite]").wait_for(state="hidden")
            page.set_viewport_size({"width": 360, "height": 800})
            report["checks"].append("favorite picker search, save, profile sync, reload persistence, removal and responsive dialog")
            # Favorite selection from the album must update the same profile without a /me reload.
            page.goto(f"http://127.0.0.1:{PORT}/cccolecao")
            page.get_by_role("button", name="Personagem 01", exact=True).click()
            page.get_by_role("button", name="Definir como favorito").click()
            page.get_by_text("Favorito atualizado.", exact=True).wait_for()
            page.keyboard.press("Escape")
            page.get_by_role("button", name="Ir para o painel").click()
            page.locator("[data-profile-favorite]").get_by_text("Personagem 01", exact=True).wait_for()
            report["checks"].append("album favorite updates profile using the same account field")
            # Sale requires confirmation; cancellation does not mutate.
            page.goto(f"http://127.0.0.1:{PORT}/menu?section=sell#shop")
            before = len(STATE["posts"])
            page.get_by_role("button", name="Personagem 01", exact=True).click()
            page.get_by_role("button", name="Cancelar", exact=True).click()
            assert len(STATE["posts"]) == before
            page.get_by_role("button", name="Personagem 01", exact=True).click()
            page.get_by_role("button", name="Vender uma cópia", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert (
                len(
                    [
                        x
                        for x in STATE["posts"][before:]
                        if x["path"] == "/api/shop/sell/confirm"
                    ]
                )
                == 1
            )
            assert {k.lower(): v for k, v in STATE["last_headers"].items()}.get(
                "x-telegram-init-data"
            ) == "fixture-signed-data"
            report["checks"].append(
                "sale cancellation, explicit confirmation, single mutation and signed header"
            )
            # Paid nickname validates syntax and asks before charging.
            page.goto(f"http://127.0.0.1:{PORT}/menu?section=nickname#shop")
            page.get_by_role("textbox", name="Novo nickname").fill("invalid")
            assert page.get_by_role(
                "button", name=re.compile("Alterar por")
            ).is_disabled()
            page.get_by_role("textbox", name="Novo nickname").fill("NovoNome")
            page.get_by_role("button", name=re.compile("Alterar por")).click()
            page.get_by_role("button", name="Confirmar e alterar").click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert STATE["nickname"] == "NovoNome"
            report["checks"].append("nickname validation and confirmation")
            # Request / image contribution.
            page.goto(f"http://127.0.0.1:{PORT}/pedido")
            page.get_by_role("textbox", name="Buscar obra para solicitar").fill("nova")
            page.get_by_role("button", name="Nova obra de teste", exact=True).click()
            page.get_by_role("button", name="Confirmar solicitação").click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert any(
                x["path"] == "/api/pedido/send" and x["body"]["anilist_id"] == 99
                for x in STATE["posts"]
            )
            page.goto(
                f"http://127.0.0.1:{PORT}/menu?view=image&character_id=1&q=Personagem%2001#contribute"
            )
            page.get_by_placeholder("https://...").fill(
                "https://example.com/test-art.jpg"
            )
            page.get_by_role("button", name="Enviar imagem", exact=True).click()
            page.wait_for_timeout(300)
            assert any(
                x["path"] == "/api/cards/contrib/image"
                and x["body"]["character_id"] == 1
                for x in STATE["posts"]
            )
            report["checks"].append(
                "request and image contribution use original JSON APIs"
            )
            # Checkout creation is separate from opening payment (never actual payment).
            page.goto(f"http://127.0.0.1:{PORT}/baltigoflix")
            page.get_by_role("button", name="Escolher plano").first.click()
            page.get_by_role("button", name="Criar pedido", exact=True).click()
            page.get_by_role("button", name="Continuar para pagamento").wait_for()
            assert page.evaluate("window.__external.length") == 0
            page.get_by_role("button", name="Continuar para pagamento").click()
            assert (
                page.evaluate("window.__external[0]")
                == "https://pay.cakto.com.br/test-only"
            )
            report["checks"].append(
                "checkout intent and user-gesture external payment handoff"
            )
            # Terms require both checkboxes and channel verification.
            page.goto(f"http://127.0.0.1:{PORT}/terms?uid=77&lang=pt")
            accept = page.get_by_role("button", name="Aceitar e continuar", exact=True)
            assert accept.is_disabled()
            page.get_by_label("Aceito a Política de Privacidade").check()
            page.get_by_label("Aceito os Termos de Uso").check()
            assert accept.is_disabled()
            page.get_by_role("button", name="Verificar inscrição", exact=True).click()
            page.get_by_role("button", name="Confirmado", exact=True).wait_for()
            accept.click()
            page.get_by_role("status").wait_for()
            assert any(x["path"] == "/api/terms/accept" for x in STATE["posts"])
            report["checks"].append("terms consent and verified channel gating")
            # Actual memory board: learn only visible cards, then solve known pairs.
            page.goto(f"http://127.0.0.1:{PORT}/memoria?level=easy")
            page.get_by_role("button", name="Carta fechada 1", exact=True).wait_for()
            known = {}
            matched = set()
            moves = 0
            while len(matched) < 12 and moves < 70:
                closed = [i for i in range(1, 13) if i not in matched]
                pair = None
                for i in closed:
                    for j in closed:
                        if (
                            i != j
                            and i in known
                            and j in known
                            and known[i] == known[j]
                        ):
                            pair = (i, j)
                            break
                    if pair:
                        break
                first = (
                    pair[0]
                    if pair
                    else next((i for i in closed if i not in known), closed[0])
                )
                board = page.get_by_label("Tabuleiro de memória")
                buttons = board.get_by_role("button")
                buttons.nth(first - 1).click()
                name = buttons.nth(first - 1).get_attribute("aria-label")
                known[first] = name
                second = (
                    pair[1]
                    if pair
                    else next(
                        (i for i in closed if i != first and known.get(i) == name),
                        next(i for i in closed if i != first),
                    )
                )
                buttons.nth(second - 1).click()
                other = buttons.nth(second - 1).get_attribute("aria-label")
                known[second] = other
                moves += 1
                page.wait_for_timeout(900)
                if name == other:
                    matched.update([first, second])
            page.get_by_role("heading", name="Partida concluída").wait_for()
            page.get_by_text("Resultado salvo.", exact=True).wait_for()
            assert (
                len([x for x in STATE["posts"] if x["path"] == "/api/memory/finish"])
                == 1
            )
            report["checks"].append(
                "memory game completion and one authenticated score submission"
            )
            # Account deletion is typed confirmation and terminal (no user recreation).
            page.goto(f"http://127.0.0.1:{PORT}/menu#settings")
            page.get_by_role("button", name="Excluir minha conta").click()
            assert page.get_by_role(
                "button", name="Excluir definitivamente"
            ).is_disabled()
            page.get_by_role("textbox", name="Digite EXCLUIR").fill("EXCLUIR")
            page.get_by_role("button", name="Excluir definitivamente").click()
            page.get_by_role("heading", name="Conta excluída").wait_for()
            assert page.locator("header.sticky").count() == 0
            report["checks"].append(
                "typed account deletion and terminal signed-out state"
            )
            assert not report["page_errors"], report["page_errors"]
            assert not report["console_errors"], report["console_errors"]
        except Exception as error:
            report["failure"] = str(error)
            try:
                page.screenshot(path=str(output / "failure.png"))
            except Exception:
                pass
            (output / "browser-report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            raise
        finally:
            context.tracing.stop(path=str(output / "trace.zip"))
        browser.close()
    report["result"] = "passed"
    report["route_count"] = len(report["routes"])
    (output / "browser-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {
                "result": "passed",
                "route_checks": len(report["routes"]),
                "flow_checks": len(report["checks"]),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("/tmp/native-proof"))
    args = parser.parse_args()
    if args.serve:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    elif args.test:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            run_tests(args.output)
        finally:
            server.shutdown()
