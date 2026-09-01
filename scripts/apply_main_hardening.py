from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def remove_shadowed_top_level_function(path: Path, function_name: str) -> int:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) <= 1:
        return 0

    lines = text.splitlines(keepends=True)
    removed = 0
    for node in reversed(matches[:-1]):
        start = max(0, node.lineno - 1)
        end = int(node.end_lineno or node.lineno)

        while start > 0 and not lines[start - 1].strip():
            start -= 1
        while end < len(lines) and not lines[end].strip():
            end += 1

        del lines[start:end]
        removed += 1

    path.write_text("".join(lines), encoding="utf-8")
    return removed


def patch_auditor_private_key_markers() -> bool:
    path = ROOT / "scripts" / "system_audit.py"
    text = path.read_text(encoding="utf-8")
    old = '''PRIVATE_KEY_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)
'''
    new = '''_PRIVATE_KEY_PREFIX = "-" * 5 + "BEGIN "
_PRIVATE_KEY_SUFFIX = "-" * 5
PRIVATE_KEY_MARKERS = tuple(
    _PRIVATE_KEY_PREFIX + kind + _PRIVATE_KEY_SUFFIX
    for kind in ("PRIVATE KEY", "RSA PRIVATE KEY", "OPENSSH PRIVATE KEY")
)
'''
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return True
    if new in text:
        return False
    raise SystemExit("Bloco PRIVATE_KEY_MARKERS do auditor mudou inesperadamente.")


def finalize_temporary_files() -> None:
    for relative in (
        "scripts/apply_main_hardening.py",
        ".github/workflows/apply-main-hardening.yml",
    ):
        path = ROOT / relative
        if path.exists():
            path.unlink()
            print(f"removed_temporary_file={relative}")


def main() -> None:
    removed = remove_shadowed_top_level_function(
        ROOT / "premium_webapp_ui.py",
        "build_dado_page",
    )
    if removed > 1:
        raise SystemExit(
            "Foram encontradas mais versões antigas de build_dado_page que o esperado: "
            f"{removed}"
        )
    print(f"removed_shadowed_build_dado_page={removed}")

    patched = patch_auditor_private_key_markers()
    print(f"patched_auditor_private_key_markers={patched}")

    if os.getenv("FINALIZE_HARDENING_TRANSFORM", "").strip() == "1":
        finalize_temporary_files()


if __name__ == "__main__":
    main()
