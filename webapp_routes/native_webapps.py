"""Native React entry points. Only explicit HTML routes are replaced; APIs stay intact."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from urllib.parse import parse_qsl, urlencode
from utils.webapp_identity import resolve_webapp_user

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "aninexus_runtime"
NICKNAME_PRICE = 3


class _TermsSections(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[dict[str, str]] = []
        self.current_key = ""

    def handle_starttag(self, tag, attrs):
        if tag != "div":
            return
        cls = dict(attrs).get("class", "")
        if cls == "sectionTitle":
            self.sections.append({"title": "", "text": ""})
            self.current_key = "title"
        elif cls == "sectionText":
            self.current_key = "text"

    def handle_endtag(self, tag):
        if tag == "div":
            self.current_key = ""

    def handle_data(self, data):
        if self.current_key and self.sections:
            self.sections[-1][self.current_key] += data


def native_config(lang: str = Query(default="pt", max_length=8)):
    from webapp import BALTIGOFLIX_PLANS, REQUIRED_CHANNEL_URL
    from webapp_services.terms import TERMS_LONG, TERMS_VERSION, TEXTS, pick_lang

    language = pick_lang(lang)
    parser = _TermsSections()
    parser.feed(TERMS_LONG[language])
    return {
        "ok": True,
        "plans": list(BALTIGOFLIX_PLANS.values()),
        "nickname_price": NICKNAME_PRICE,
        "sell_price": 1,
        "channel_url": REQUIRED_CHANNEL_URL,
        "terms_version": TERMS_VERSION,
        "language": language,
        "terms": [
            {k: " ".join(v.split()) for k, v in section.items()}
            for section in parser.sections
        ],
        "texts": {
            k: re.sub(r"^[^A-Za-zÀ-ÿ]+", "", v) for k, v in TEXTS[language].items()
        },
    }


def change_nickname_atomic(user_id: int, nickname: str) -> dict:
    """Charge only if the nickname was changed successfully, in the same transaction."""
    from psycopg import IntegrityError
    from psycopg.rows import dict_row
    from database_core import pool
    from webapp_routes.profile_settings import valid_menu_nickname

    nickname = nickname.strip()
    if not valid_menu_nickname(nickname):
        raise HTTPException(400, "Use 4-17 caracteres, começando com letra maiúscula.")
    try:
        with pool.connection() as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        "SELECT coins FROM users WHERE user_id=%s FOR UPDATE",
                        (user_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise HTTPException(404, "Conta não encontrada.")
                    coins = int(row.get("coins") or 0)
                    if coins < NICKNAME_PRICE:
                        raise HTTPException(409, "Coins insuficientes.")
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(lower(%s), 7341))",
                        (nickname,),
                    )
                    cursor.execute(
                        "SELECT user_id FROM user_profile_settings WHERE lower(nickname)=lower(%s)",
                        (nickname,),
                    )
                    if cursor.fetchone():
                        raise HTTPException(409, "Esse nickname já está em uso.")
                    cursor.execute(
                        "INSERT INTO user_profile_settings (user_id,nickname) VALUES (%s,%s) ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname,updated_at=NOW()",
                        (user_id, nickname),
                    )
                    cursor.execute(
                        "UPDATE users SET coins=coins-%s,updated_at=NOW() WHERE user_id=%s",
                        (NICKNAME_PRICE, user_id),
                    )
                    cursor.execute(
                        "INSERT INTO shop_transactions (user_id,type,amount,balance_after,metadata) VALUES (%s,%s,%s,%s,%s::jsonb)",
                        (
                            user_id,
                            "buy_nickname",
                            -NICKNAME_PRICE,
                            coins - NICKNAME_PRICE,
                            json.dumps({"nickname": nickname}),
                        ),
                    )
        return {"ok": True, "nickname": nickname, "coins": coins - NICKNAME_PRICE}
    except IntegrityError as exc:
        raise HTTPException(409, "Esse nickname já está em uso.") from exc


def native_nickname(
    payload: dict = Body(...), x_telegram_init_data: str = Header(default="")
):
    context = resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data, body_uid=payload.get("uid")
    )
    return change_nickname_atomic(
        int(context["user_id"]), str(payload.get("nickname") or "")
    )


def install_native_webapps(app: FastAPI) -> None:
    index = RUNTIME / "index.html"
    manifest = RUNTIME / "native-routes.json"
    if not index.is_file() or not manifest.is_file():
        raise RuntimeError(
            "Build nativo ausente. Execute o build da MiniApp antes de publicar."
        )
    routes = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(routes, dict) or "/menu" not in routes:
        raise RuntimeError("Manifesto de rotas nativas inválido.")
    for path in routes:
        if not path.startswith("/") or path.startswith(("/api", "/assets", "//")):
            raise RuntimeError("O manifesto deve conter apenas rotas HTML explícitas.")

    version_file = RUNTIME / 'ui-version.json'
    version = (json.loads(version_file.read_text()).get('version') if version_file.is_file()
               else hashlib.sha256(index.read_bytes()).hexdigest()[:16])
    headers = {'Cache-Control': 'no-store, max-age=0', 'X-Source-UI': 'native',
               'X-Source-UI-Version': version, 'Link': '</menu>; rel="canonical"'}

    def native_entry(request: Request):
        path = request.url.path.rstrip('/') or '/'
        if path != '/menu':
            entry = routes[path]
            pairs = list(parse_qsl(request.url.query, keep_blank_values=True))
            keys = {key for key, _ in pairs}
            defaults = dict(entry.get('params') or {})
            if not keys.intersection({'tab', 'route', 'startapp', 'tgWebAppStartParam'}):
                defaults['tab'] = entry['tab']
            pairs = [(k, v) for k, v in defaults.items() if k not in keys] + pairs
            # No fragment in Location: browser preserves Telegram's signed fragment.
            return RedirectResponse('/menu' + ('?' + urlencode(pairs) if pairs else ''),
                                    status_code=307, headers=headers)
        return FileResponse(index, media_type='text/html', headers=headers)

    def native_version():
        return JSONResponse({'version': version, 'entrypoint': '/menu'}, headers=headers)

    # Replace flat legacy handlers; prioritize native entries over nested included routers.
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) in routes
            and "GET" in (getattr(route, "methods", None) or set())
        )
    ]
    previous_routes = list(app.router.routes)
    for path in routes:
        app.add_api_route(path, native_entry, methods=["GET", "HEAD"], include_in_schema=False)
    existing = {getattr(route, "path", "") for route in app.routes}
    if "/api/native/version" not in existing:
        app.add_api_route("/api/native/version", native_version, methods=["GET"], include_in_schema=False)
    if "/api/native/config" not in existing:
        app.add_api_route("/api/native/config", native_config, methods=["GET"])
    if "/api/native/nickname" not in existing:
        app.add_api_route("/api/native/nickname", native_nickname, methods=["POST"])
    # Newer FastAPI versions retain included routers as nested route wrappers.
    # Exact native GET entries must run before those wrappers, or old HTML can win.
    native_entries = [route for route in app.router.routes if route not in previous_routes]
    app.router.routes[:] = native_entries + previous_routes
    app.openapi_schema = None
