from __future__ import annotations

import re
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-image-proxy-extraction.yml")
SELF = Path(__file__)


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")

    route_pattern = re.compile(
        r'\n@app\.get\("/api/image-proxy"\)\n'
        r'async def api_image_proxy\([\s\S]*?'
        r'\n\n\ndef pick_lang\(',
    )
    text, route_count = route_pattern.subn("\n\ndef pick_lang(", text, count=1)
    if route_count != 1:
        raise SystemExit(f"expected exactly one image proxy route, found {route_count}")

    constant_pattern = re.compile(
        r'\nIMAGE_PROXY_USER_AGENT = \(\n'
        r'(?:    .*\n)+'
        r'\)\n',
    )
    text, constant_count = constant_pattern.subn("\n", text, count=1)
    if constant_count != 1:
        raise SystemExit(
            f"expected exactly one IMAGE_PROXY_USER_AGENT constant, found {constant_count}"
        )

    if '@app.get("/api/image-proxy")' in text:
        raise SystemExit("legacy image proxy route still present after extraction")

    WEBAPP.write_text(text, encoding="utf-8")

    # Este aplicador existe apenas para evitar regravar manualmente o monólito inteiro.
    # Ele se remove no mesmo commit que produz a refatoração final.
    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
