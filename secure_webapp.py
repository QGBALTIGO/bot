import json
import logging
import os
from typing import Iterable
from urllib.parse import parse_qs

from fastapi.responses import HTMLResponse as BaseHTMLResponse

import webapp as legacy_webapp
from utils.webapp_auth import WebAppAuthError, validate_telegram_init_data

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado para autenticação da MiniApp.")

try:
    WEBAPP_AUTH_MAX_AGE_SECONDS = int(
        os.getenv("WEBAPP_AUTH_MAX_AGE_SECONDS", "3600")
    )
except ValueError as exc:
    raise RuntimeError("WEBAPP_AUTH_MAX_AGE_SECONDS precisa ser inteiro.") from exc

if WEBAPP_AUTH_MAX_AGE_SECONDS <= 0:
    raise RuntimeError("WEBAPP_AUTH_MAX_AGE_SECONDS precisa ser maior que zero.")

WEBAPP_ADMIN_TOKEN = os.getenv("WEBAPP_ADMIN_TOKEN", "").strip()

PROTECTED_TELEGRAM_PATHS = {
    "/api/channel/check",
    "/api/terms/accept",
    "/api/terms/decline",
    "/api/pedido",
    "/api/pedido/limit",
    "/api/pedido/search",
    "/api/pedido/send",
    "/api/pedido/report",
}

IDENTITY_BODY_PATHS = {
    "/api/channel/check",
    "/api/terms/accept",
    "/api/terms/decline",
    "/api/pedido",
    "/api/pedido/send",
    "/api/pedido/report",
}

ADMIN_PROTECTED_PATHS = {
    "/api/cards/reload",
}

INIT_DATA_INJECTION = """
<script id="source-baltigo-initdata-guard">
(() => {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    try {
      const rawUrl = typeof input === 'string' ? input : input.url;
      const url = new URL(rawUrl, window.location.href);
      if (url.origin === window.location.origin) {
        const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
        const initData = tg && tg.initData ? tg.initData : '';
        const headers = new Headers(init.headers || {});
        if (initData) headers.set('X-Telegram-Init-Data', initData);
        init = { ...init, headers };
      }
    } catch (_) {}
    return nativeFetch(input, init);
  };
})();
</script>
""".strip()


class SecureHTMLResponse(BaseHTMLResponse):
    """Inject signed Telegram initData into same-origin fetch requests."""

    def render(self, content) -> bytes:
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                return content
        else:
            text = str(content)

        if "</head>" in text and "source-baltigo-initdata-guard" not in text:
            text = text.replace(
                "</head>",
                f"{INIT_DATA_INJECTION}\n</head>",
                1,
            )

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


class TelegramWebAppAuthMiddleware:
    def __init__(
        self,
        app,
        *,
        bot_token: str,
        max_age_seconds: int,
        admin_token: str,
    ):
        self.app = app
        self.bot_token = bot_token
        self.max_age_seconds = max_age_seconds
        self.admin_token = admin_token

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path") or ""
        headers = _headers_dict(scope.get("headers") or [])

        if path in ADMIN_PROTECTED_PATHS:
            supplied = headers.get("x-admin-token", "")
            if not self.admin_token or supplied != self.admin_token:
                return await _send_json(
                    send,
                    404,
                    {"ok": False, "message": "Endpoint não encontrado."},
                )

        if path not in PROTECTED_TELEGRAM_PATHS:
            return await self.app(scope, receive, send)

        init_data = headers.get("x-telegram-init-data", "")
        try:
            identity = validate_telegram_init_data(
                init_data,
                self.bot_token,
                max_age_seconds=self.max_age_seconds,
            )
        except WebAppAuthError as exc:
            logger.warning("MiniApp auth recusada path=%s reason=%s", path, exc)
            return await _send_json(
                send,
                401,
                {
                    "ok": False,
                    "message": "Sessão do Telegram inválida ou expirada. Reabra o Mini App pelo bot.",
                },
            )

        # The request-limit endpoint identifies the user in its query string.
        if path == "/api/pedido/limit":
            raw_uid = (_query_params(scope).get("uid") or [""])[0]
            try:
                claimed_uid = int(raw_uid or 0)
            except ValueError:
                claimed_uid = 0

            if claimed_uid != identity.user_id:
                return await _send_json(
                    send,
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
                    send,
                    415,
                    {"ok": False, "message": "Content-Type inválido."},
                )

            try:
                payload = json.loads(final_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return await _send_json(
                    send,
                    400,
                    {"ok": False, "message": "JSON inválido."},
                )

            if not isinstance(payload, dict):
                return await _send_json(
                    send,
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
                    send,
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

        sent_body = False

        async def replay_receive():
            nonlocal sent_body
            if path not in IDENTITY_BODY_PATHS:
                return await receive()
            if not sent_body:
                sent_body = True
                return {
                    "type": "http.request",
                    "body": final_body,
                    "more_body": False,
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        pending_start = None
        replaced_error = False

        async def safe_send(message):
            nonlocal pending_start, replaced_error

            if message.get("type") == "http.response.start":
                if int(message.get("status") or 0) == 500:
                    pending_start = message
                    return
                return await send(message)

            if pending_start is not None:
                if not replaced_error:
                    replaced_error = True
                    pending_start = None
                    return await _send_json(
                        send,
                        500,
                        {"ok": False, "message": "Erro interno. Tente novamente."},
                    )
                return

            return await send(message)

        try:
            return await self.app(scope, replay_receive, safe_send)
        except Exception:
            logger.exception("Erro não tratado na MiniApp path=%s", path)
            return await _send_json(
                send,
                500,
                {"ok": False, "message": "Erro interno. Tente novamente."},
            )


# Transitional security layer: route functions in the legacy module resolve
# HTMLResponse from module globals at request time. This lets us secure existing
# pages now, before splitting the 5k+ line legacy WebApp into routers/templates.
legacy_webapp.HTMLResponse = SecureHTMLResponse

app = legacy_webapp.app
app.add_middleware(
    TelegramWebAppAuthMiddleware,
    bot_token=BOT_TOKEN,
    max_age_seconds=WEBAPP_AUTH_MAX_AGE_SECONDS,
    admin_token=WEBAPP_ADMIN_TOKEN,
)
