from __future__ import annotations

import re
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-channel-extraction.yml")
SELF = Path(__file__)


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")

    block_pattern = re.compile(
        r'\nfrom utils\.channel_verification_bridge import wait_for_verification, worker_health\n'
        r'\n\n@app\.get\("/api/channel/selftest"\)'
        r'[\s\S]*?'
        r'\n\n\n# =========================\n# CONFIG — CATÁLOGO',
    )
    text, count = block_pattern.subn(
        "\n\n# =========================\n# CONFIG — CATÁLOGO",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"expected exactly one channel route block, found {count}")

    for marker in (
        '@app.get("/api/channel/selftest")',
        '@app.post("/api/channel/check")',
    ):
        if marker in text:
            raise SystemExit(f"legacy route still present after extraction: {marker}")

    WEBAPP.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
