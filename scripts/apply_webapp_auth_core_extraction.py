from __future__ import annotations

import re
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-auth-core-extraction.yml")
SELF = Path(__file__)

OLD_IMPORT = (
    "from utils.telegram_webapp_auth import TelegramWebAppAuthError, validate_telegram_init_data\n"
)
NEW_IMPORT = """from utils.webapp_identity import (
    build_fallback_webapp_user as _build_fallback_webapp_user,
    coerce_positive_uid as _coerce_positive_uid,
    get_tg_user as _get_tg_user,
    resolve_webapp_user as _resolve_webapp_user,
    verify_telegram_init_data,
)
"""


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")

    import_count = text.count(OLD_IMPORT)
    if import_count != 1:
        raise SystemExit(f"expected exactly one legacy Telegram auth import, found {import_count}")
    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)

    block_pattern = re.compile(
        r'\n# =========================================================\n'
        r'# TELEGRAM WEBAPP AUTH\n'
        r'# =========================================================\n'
        r'def verify_telegram_init_data\([\s\S]*?'
        r'raise HTTPException\(status_code=401, detail="telegram_init_data_required"\)\n'
        r'\n\n',
    )
    text, block_count = block_pattern.subn("\n", text, count=1)
    if block_count != 1:
        raise SystemExit(f"expected exactly one auth core block, found {block_count}")

    forbidden = (
        "def verify_telegram_init_data(",
        "def _get_tg_user(",
        "def _coerce_positive_uid(",
        "def _build_fallback_webapp_user(",
        "def _resolve_webapp_user(",
    )
    for marker in forbidden:
        if marker in text:
            raise SystemExit(f"legacy auth implementation still present: {marker}")

    WEBAPP.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
