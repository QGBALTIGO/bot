from __future__ import annotations

import ast
from pathlib import Path

DATABASE = Path("database.py")
WORKFLOW = Path(".github/workflows/apply-database-profile-extraction.yml")
SELF = Path(__file__)

PROFILE_FUNCTIONS = {
    "create_profile_settings_table",
    "ensure_profile_settings_row",
    "get_profile_settings",
    "get_profile_settings_by_nickname",
    "nickname_exists",
    "set_profile_nickname",
    "set_profile_favorite",
    "set_profile_country",
    "set_profile_language",
    "set_profile_private",
    "set_profile_notifications",
}

CORE_IMPORT = "from database_core import DATABASE_URL, pool, run as _run\n"
PROFILE_IMPORT = """from database_profile import (
    create_profile_settings_table,
    ensure_profile_settings_row,
    get_profile_settings,
    get_profile_settings_by_nickname,
    nickname_exists,
    set_profile_country,
    set_profile_favorite,
    set_profile_language,
    set_profile_nickname,
    set_profile_notifications,
    set_profile_private,
)
"""

PROFILE_HEADER = """# =========================================================
# MENU / PROFILE SETTINGS
# =========================================================

"""


def main() -> None:
    text = DATABASE.read_text(encoding="utf-8")

    if text.count(CORE_IMPORT) != 1:
        raise SystemExit("database_core import not found exactly once")
    if "from database_profile import (" in text:
        raise SystemExit("database_profile import already present")
    text = text.replace(CORE_IMPORT, CORE_IMPORT + PROFILE_IMPORT, 1)

    tree = ast.parse(text, filename=str(DATABASE))
    nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in PROFILE_FUNCTIONS
    }
    missing = sorted(PROFILE_FUNCTIONS - set(nodes))
    if missing:
        raise SystemExit(f"profile functions not found: {missing}")

    lines = text.splitlines(keepends=True)
    ranges = sorted(
        (
            node.lineno - 1,
            int(node.end_lineno or node.lineno),
            name,
        )
        for name, node in nodes.items()
    )

    for start, end, _name in reversed(ranges):
        while end < len(lines) and not lines[end].strip():
            end += 1
        del lines[start:end]

    text = "".join(lines)
    text = text.replace(PROFILE_HEADER, "", 1)

    for name in PROFILE_FUNCTIONS:
        if f"def {name}(" in text:
            raise SystemExit(f"legacy profile function still present: {name}")
        if name not in PROFILE_IMPORT:
            raise SystemExit(f"profile function missing from re-export import: {name}")

    if "def delete_user_account(" not in text:
        raise SystemExit("cross-domain account deletion was removed unexpectedly")

    DATABASE.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
