import json
import logging
import os
from http.cookies import SimpleCookie
from typing import Iterable
from urllib.parse import parse_qs

from fastapi.responses import HTMLResponse as BaseHTMLResponse

import webapp as legacy_webapp
from utils.route_hygiene import dedupe_http_routes_keep_last
from utils.webapp_auth import (
    TelegramWebAppIdentity,
    WebAppAuthError,
    validate_telegram_init_data,
    validate_webapp_launch_token,
)
from v2_webapp_registry import PROTECTED_V2_PATHS, register_v2_routes

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado para autenticação da MiniApp.")

try:
    WEBAPP_AUTH_MAX_AGE_SECONDS = int(os.getenv("WEBAPP_AUTH_MAX_AGE_SECONDS", "3600"))
    WEBAPP_LAUNCH_MAX_AGE_SECONDS = int(os.getenv("WEBAPP_LAUNCH_MAX_AGE_SECONDS", "21600"))
except ValueError as exc:
    raise RuntimeError("Tempos de autenticação da MiniApp precisam ser inteiros.") from exc

if WEBAPP_AUTH_MAX_AGE_SECONDS <= 0 or WEBAPP_LAUNCH_MAX_AGE_SECONDS <= 0:
    raise RuntimeError("Tempos de autenticação da MiniApp precisam ser maiores que zero.")

WEBAPP_ADMIN_TOKEN = os.getenv("WEBAPP_ADMIN_TOKEN", "").strip()
SESSION_COOKIE = "baltigo_webapp_session"

PROTECTED_TELEGRAM_PATHS = {
    "/api/channel/check",
    "/api/terms/accept",
    "/api/terms/decline",
    "/api/pedido",
    "/api/pedido/limit",
    "/api/pedido/search",
    "/api/pedido/send",
    "/api/pedido/report",
} | PROTECTED_V2_PATHS

IDENTITY_BODY_PATHS = {
    "/api/channel/check",
    "/api/terms/accept",
    "/api/terms/decline",
    "/api/pedido",
    "/api/pedido/send",
    "/api/pedido/report",
}

ADMIN_PROTECTED_PATHS = {"/api/cards/reload"}

INIT_DATA_INJECTION = """
<script id="source-baltigo-initdata-guard">
(() => {
  const params = new URLSearchParams(window.location.search);
  const launchFromUrl = params.get('launch') || '';
  if (launchFromUrl) {
    try { sessionStorage.setItem('baltigo_launch', launchFromUrl); } catch (_) {}
  }
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    try {
      const rawUrl = typeof input === 'string' ? input : input.url;
      const url = new URL(rawUrl, window.location.href);
      if (url.origin === window.location.origin) {
        const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
        const initData = tg && tg.initData ? tg.initData : '';
        let launch = launchFromUrl;
        if (!launch) { try { launch = sessionStorage.getItem('baltigo_launch') || ''; } catch (_) {} }
        const headers = new Headers(init.headers || {});
        if (initData) headers.set('X-Telegram-Init-Data', initData);
        if (launch) headers.set('X-Baltigo-Launch', launch);
        init = { ...init, headers };
      }
    } catch (_) {}
    return nativeFetch(input, init);
  };
})();
</script>
""".strip()


class SecureHTMLResponse(BaseHTMLResponse):
    """Inject Telegram/session credentials into historical same-origin fetches."""

    def render(self, content) -> bytes:
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                return content
        else:
            text = str(content)

        if "</head>" in text and "source-baltigo-initdata-guard" not in text:
            text = text.replace("</head>", f"{INIT_DATA_INJECTION}\n</head>", 1)
        return text.encode(self.charset)


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _headers_dict(raw_headers: Iterable[tuple[bytes, bytes]]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in raw_headers
    }


def _query_params(scope) -> dict[str, list[str]]:
    raw = (scope.get("query_string") or b"").decode("utf-8", errors="replace")
    return parse_qs(raw, keep_blank_values=True)


def _cookie_value(headers: dict[str, str], name: str) -> str:
    raw = headers.get("cookie", "")
    if not raw:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return ""
    morsel = jar.get(name)
    return str(morsel.value if morsel else "")


def _validate_launch(token: str) -> TelegramWebAppIdentity:
    return validate_webapp_launch_token(
        token,
        BOT_TOKEN,
        max_age_seconds=WEBAPP_LAUNCH_MAX_AGE_SECONDS,
    )


def _launch_cookie(token: str) -> bytes:
    return (
        f"{SESSION_COOKIE}={token}; Path=/; Max-Age={WEBAPP_LAUNCH_MAX_AGE_SECONDS}; "
        "HttpOnly; Secure; SameSite=Lax"
    ).encode("latin-1")


class TelegramWebAppAuthMiddleware:
    def __init__(self, app, *, bot_token: str, max_age_seconds: int, admin_token: str):
        self.app = app
        self.bot_token = bot_token
        self.max_age_seconds = max_age_seconds
        self.admin_token = admin_token

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path") or ""
        method = str(scope.get("method") or "GET")
        headers = _headers_dict(scope.get("headers") or [])
        query = _query_params(scope)

        launch_query = (query.get("launch") or [""])[0]
        launch_header = headers.get("x-baltigo-launch", "")
        launch_cookie = _cookie_value(headers, SESSION_COOKIE)
        launch_token = launch_query or launch_header or launch_cookie
        launch_identity = None
        if launch_token:
            try:
                launch_identity = _validate_launch(launch_token)
            except WebAppAuthError as exc:
                logger.warning("MiniApp launch recusado path=%s reason=%s", path, exc)

        if path != "/healthz":
            logger.info(
                "MiniApp HTTP method=%s path=%s init_data=%s launch=%s ua=%s",
                method,
                path,
                bool(headers.get("x-telegram-init-data")),
                bool(launch_identity),
                headers.get("user-agent", "")[:120],
            )

        async def send_with_session(message):
            if launch_query and launch_identity and message.get("type") == "http.response.start":
                copied = dict(message)
                copied_headers = list(message.get("headers") or [])
                copied_headers.append((b"set-cookie", _launch_cookie(launch_query)))
                copied["headers"] = copied_headers
                return await send(copied)
            return await send(message)

        if path in ADMIN_PROTECTED_PATHS:
            supplied = headers.get("x-admin-token", "")
            if not self.admin_token or supplied != self.admin_token:
                return await _send_json(
                    send_with_session,
                    404,
                    {"ok": False, "message": "Endpoint não encontrado."},
                )

        if path not in PROTECTED_TELEGRAM_PATHS:
            if launch_identity:
                scope.setdefault("state", {})["telegram_user_id"] = launch_identity.user_id
                scope["state"]["telegram_username"] = launch_identity.username
                scope["state"]["telegram_full_name"] = launch_identity.full_name
            return await self.app(scope, receive, send_with_session)

        init_identity = None
        init_error = None
        init_data = headers.get("x-telegram-init-data", "")
        if init_data:
            try:
                init_identity = validate_telegram_init_data(
                    init_data,
                    self.bot_token,
                    max_age_seconds=self.max_age_seconds,
                )
            except WebAppAuthError as exc:
                init_error = exc

        if init_identity and launch_identity and init_identity.user_id != launch_identity.user_id:
            logger.warning(
                "MiniApp auth divergente path=%s telegram=%s launch=%s",
                path,
                init_identity.user_id,
                launch_identity.user_id,
            )
            return await _send_json(
                send_with_session,
                403,
                {"ok": False, "message": "Identidade da sessão não confere."},
            )

        identity = init_identity or launch_identity
        auth_source = "telegram" if init_identity else ("launch" if launch_identity else "")
        if not identity:
            reason = str(init_error or "initData e sessão assinada ausentes")
            logger.warning("MiniApp auth recusada path=%s reason=%s", path, reason)
            return await _send_json(
                send_with_session,
                401,
                {
                    "ok": False,
                    "message": "Sessão inválida ou expirada. Reabra o Mini App pelo bot.",
                },
            )

        logger.debug("MiniApp auth ok path=%s source=%s user_id=%s", path, auth_source, identity.user_id)

        if path == "/api/pedido/limit":
            raw_uid = (query.get("uid") or [""])[0]
            try:
                claimed_uid = int(raw_uid or 0)
            except ValueError:
                claimed_uid = 0
            if claimed_uid != identity.user_id:
                return await _send_json(
                    send_with_session,
                    403,
                    {"ok": False, "message": "Identidade do Telegram não confere."},
                )

        final_body = b""
        if path in IDENTITY_BODY_PATHS:
            body = bytearray()
            more_body = True
            while more_body:
                event = await receive()
                if event.get("type") != "http.request":
                    continue
                body.extend(event.get("body") or b"")
                more_body = bool(event.get("more_body"))

            final_body = bytes(body)
            content_type = headers.get("content-type", "")
            if "application/json" not in content_type:
                return await _send_json(
                    send_with_session,
                    415,
                    {"ok": False, "message": "Content-Type inválido."},
                )

            try:
                payload = json.loads(final_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return await _send_json(
                    send_with_session,
                    400,
                    {"ok": False, "message": "JSON inválido."},
                )

            if not isinstance(payload, dict):
                return await _send_json(
                    send_with_session,
                    400,
                    {"ok": False, "message": "Payload inválido."},
                )

            claimed_id = payload.get("uid", payload.get("user_id"))
            try:
                claimed_id = int(claimed_id or 0)
            except (TypeError, ValueError):
                claimed_id = 0

            if claimed_id != identity.user_id:
                logger.warning(
                    "MiniApp identity mismatch path=%s signed=%s claimed=%s",
                    path,
                    identity.user_id,
                    claimed_id,
                )
                return await _send_json(
                    send_with_session,
                    403,
                    {"ok": False, "message": "Identidade do Telegram não confere."},
                )

            if "uid" in payload:
                payload["uid"] = identity.user_id
            if "user_id" in payload:
                payload["user_id"] = identity.user_id
            if "username" in payload:
                payload["username"] = identity.username
            if "full_name" in payload or "name" in payload:
                payload["full_name"] = identity.full_name
                if "name" in payload:
                    payload["name"] = identity.full_name

            final_body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

        scope.setdefault("state", {})["telegram_user_id"] = identity.user_id
        scope["state"]["telegram_username"] = identity.username
        scope["state"]["telegram_full_name"] = identity.full_name

        sent_body = False

        async def replay_receive():
            nonlocal sent_body
            if path not in IDENTITY_BODY_PATHS:
                return await receive()
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": final_body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        pending_start = None
        replaced_error = False

        async def safe_send(message):
            nonlocal pending_start, replaced_error
            if message.get("type") == "http.response.start":
                if int(message.get("status") or 0) == 500:
                    pending_start = message
                    return
                return await send_with_session(message)

            if pending_start is not None:
                if not replaced_error:
                    replaced_error = True
                    pending_start = None
                    return await _send_json(
                        send_with_session,
                        500,
                        {"ok": False, "message": "Erro interno. Tente novamente."},
                    )
                return
            return await send_with_session(message)

        try:
            return await self.app(scope, replay_receive, safe_send)
        except Exception:
            logger.exception("Erro não tratado na MiniApp path=%s", path)
            return await _send_json(
                send_with_session,
                500,
                {"ok": False, "message": "Erro interno. Tente novamente."},
            )


legacy_webapp.HTMLResponse = SecureHTMLResponse
app = legacy_webapp.app

# Clean historical duplicates, register V2, then clean again so the newest V2
# handler wins whenever it intentionally replaces a legacy method/path.
dedupe_http_routes_keep_last(app)
register_v2_routes(app)
dedupe_http_routes_keep_last(app)

app.add_middleware(
    TelegramWebAppAuthMiddleware,
    bot_token=BOT_TOKEN,
    max_age_seconds=WEBAPP_AUTH_MAX_AGE_SECONDS,
    admin_token=WEBAPP_ADMIN_TOKEN,
)
