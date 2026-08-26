from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from utils.public_url import require_public_base_url
from utils.webapp_auth import create_webapp_launch_token


def build_webapp_url(
    path: str,
    *,
    user_id: int,
    username: str = "",
    full_name: str = "",
) -> str:
    """Build a production-compatible Telegram WebApp URL.

    Historical Source Baltigo pages received ``uid`` in the URL. Keep that
    compatibility hint for legacy JavaScript, but add a signed ``launch`` token
    which is the actual authority used by V2 authentication.
    """
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN não encontrado para gerar sessão da MiniApp.")

    raw_path = str(path or "/").strip() or "/"
    parts = urlsplit(raw_path)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in {"uid", "launch"}
    ]

    token = create_webapp_launch_token(
        int(user_id),
        bot_token,
        username=str(username or ""),
        full_name=str(full_name or ""),
    )
    query.extend(
        [
            ("uid", str(int(user_id))),
            ("launch", token),
        ]
    )

    relative = urlunsplit(
        ("", "", parts.path or "/", urlencode(query), parts.fragment)
    )
    return f"{require_public_base_url()}{relative}"
