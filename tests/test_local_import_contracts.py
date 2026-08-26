from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "tests"}


def _module_file(module: str) -> Path | None:
    if not module or module.startswith("."):
        return None
    parts = module.split(".")
    direct = ROOT.joinpath(*parts).with_suffix(".py")
    if direct.exists():
        return direct
    package = ROOT.joinpath(*parts, "__init__.py")
    if package.exists():
        return package
    return None


def _exported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
    return names


class LocalImportContractTests(unittest.TestCase):
    def test_named_imports_from_local_modules_exist(self):
        failures: list[str] = []
        for path in ROOT.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level != 0 or not node.module:
                    continue
                target = _module_file(node.module)
                if target is None:
                    continue
                exported = _exported_names(target)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if alias.name not in exported:
                        failures.append(
                            f"{path.relative_to(ROOT)} imports {alias.name!r} from "
                            f"{target.relative_to(ROOT)}, but that name is not defined"
                        )
        self.assertEqual([], failures, "\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
