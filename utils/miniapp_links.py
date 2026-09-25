"""One stable MiniApp URL for every launch button; identity comes from signed initData."""
from __future__ import annotations

import os
import re
from urllib.parse import urlencode, urlsplit, urlunsplit


def miniapp_entrypoint() -> str:
    """Explicit Source URL wins over old frontend settings. All apps use /menu."""
    value = next((os.getenv(key, '').strip() for key in (
        'SOURCE_MINIAPP_URL', 'BASE_URL', 'PUBLIC_BASE_URL', 'WEBAPP_URL', 'MINIAPP_URL'
    ) if os.getenv(key, '').strip()), '')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Configure SOURCE_MINIAPP_URL com a URL HTTPS pública do Source.')
    return urlunsplit((parsed.scheme, parsed.netloc, '/menu', '', ''))


def miniapp_url(tab: str = 'profile', **params: object) -> str:
    if not re.fullmatch(r'[a-z][a-z0-9_]*', tab):
        raise ValueError('Seção inválida da MiniApp.')
    # uid never selects an account. Every API still validates Telegram initData.
    query = urlencode({k: str(v) for k, v in params.items()
                       if v is not None and k not in {'uid', 'user_id', 'initData', 'token'}})
    return f"{miniapp_entrypoint()}{'?' + query if query else ''}#{tab}"
