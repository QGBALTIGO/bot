from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
NETWORK_FUNCTIONS = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.request",
    "httpx.get",
    "httpx.post",
    "httpx.put",
    "httpx.patch",
    "httpx.delete",
    "httpx.request",
}
RISKY_FILENAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
}
RISKY_SUFFIXES = {
    ".session",
    ".session-journal",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
BOT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])\d{6,12}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_])")
_PRIVATE_KEY_PREFIX = "-" * 5 + "BEGIN "
_PRIVATE_KEY_SUFFIX = "-" * 5
PRIVATE_KEY_MARKERS = tuple(
    _PRIVATE_KEY_PREFIX + kind + _PRIVATE_KEY_SUFFIX
    for kind in ("PRIVATE KEY", "RSA PRIVATE KEY", "OPENSSH PRIVATE KEY")
)
JSON_LIKE_TEXT_FILES = {
    "personagens_anilist.txt",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    line: int
    message: str


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def iter_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if path.is_file() and not is_excluded(path):
            yield path


def dotted_module(path: Path) -> str:
    rel = path.relative_to(ROOT)
    if rel.suffix == ".py":
        rel = rel.with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def resolve_import_module(current_module: str, level: int, module: str | None) -> str:
    if level <= 0:
        return module or ""
    current_parts = current_module.split(".")
    if current_parts:
        current_parts.pop()
    keep = max(0, len(current_parts) - level + 1)
    prefix = current_parts[:keep]
    if module:
        prefix.extend(module.split("."))
    return ".".join(prefix)


def build_module_index(py_files: list[Path], trees: dict[Path, ast.AST]) -> tuple[dict[str, Path], dict[str, set[str]]]:
    modules: dict[str, Path] = {}
    symbols: dict[str, set[str]] = {}
    for path in py_files:
        module = dotted_module(path)
        modules[module] = path
        tree = trees.get(path)
        exported: set[str] = set()
        if isinstance(tree, ast.Module):
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    exported.add(node.name)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            exported.add(target.id)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        exported.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name != "*":
                            exported.add(alias.asname or alias.name)
        symbols[module] = exported
    return modules, symbols


def inspect_repository() -> list[Finding]:
    findings: list[Finding] = []
    all_files = list(iter_files())
    py_files = sorted(path for path in all_files if path.suffix == ".py")
    trees: dict[Path, ast.AST] = {}
    texts: dict[Path, str] = {}

    for path in py_files:
        rel = relative(path)
        try:
            text = path.read_text(encoding="utf-8")
            texts[path] = text
            trees[path] = ast.parse(text, filename=rel)
        except UnicodeDecodeError as exc:
            findings.append(Finding("error", "ENCODING", rel, 0, f"arquivo Python não é UTF-8: {exc}"))
        except SyntaxError as exc:
            findings.append(Finding("error", "PARSE", rel, int(exc.lineno or 0), str(exc)))
        except OSError as exc:
            findings.append(Finding("error", "READ", rel, 0, str(exc)))

    modules, symbols = build_module_index(py_files, trees)
    local_roots = {name.split(".")[0] for name in modules}
    global_routes: dict[tuple[str, str], list[tuple[str, int, str]]] = defaultdict(list)

    for path, tree in trees.items():
        if not isinstance(tree, ast.Module):
            continue
        rel = relative(path)
        current_module = dotted_module(path)

        definitions: dict[str, list[int]] = defaultdict(list)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions[node.name].append(node.lineno)
        for name, lines in definitions.items():
            if len(lines) > 1:
                findings.append(Finding("error", "DUPDEF", rel, lines[-1], f"{name} definido várias vezes nas linhas {lines}"))

        module_routes: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
        command_handlers: dict[str, list[tuple[str, int]]] = defaultdict(list)
        callback_patterns: dict[str, list[tuple[str, int]]] = defaultdict(list)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                        continue
                    method = decorator.func.attr.lower()
                    if method not in HTTP_METHODS or not decorator.args:
                        continue
                    route_path = literal_string(decorator.args[0])
                    if route_path is None:
                        continue
                    key = (method.upper(), route_path)
                    module_routes[key].append((node.name, node.lineno))
                    global_routes[key].append((rel, node.lineno, node.name))

            if isinstance(node, ast.Call):
                name = call_name(node.func)

                if name.endswith("CommandHandler") and node.args:
                    command = literal_string(node.args[0])
                    handler = call_name(node.args[1]) if len(node.args) > 1 else ""
                    if command:
                        command_handlers[command].append((handler, node.lineno))

                if name.endswith("CallbackQueryHandler"):
                    pattern = None
                    for keyword in node.keywords:
                        if keyword.arg == "pattern":
                            pattern = literal_string(keyword.value)
                            break
                    handler = call_name(node.args[0]) if node.args else ""
                    if pattern:
                        callback_patterns[pattern].append((handler, node.lineno))

                if name in NETWORK_FUNCTIONS and not any(keyword.arg == "timeout" for keyword in node.keywords):
                    findings.append(Finding("warning", "HTTP_TIMEOUT", rel, node.lineno, f"{name} sem timeout explícito"))

                if name in {"eval", "exec"}:
                    findings.append(Finding("error", "DYNAMIC_EXEC", rel, node.lineno, f"uso de {name}()"))

                if name in {"pickle.loads", "pickle.load", "marshal.loads", "marshal.load"}:
                    findings.append(Finding("error", "UNSAFE_DESERIALIZE", rel, node.lineno, f"uso de {name}"))

                if name.startswith("subprocess.") and any(
                    keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                    for keyword in node.keywords
                ):
                    findings.append(Finding("error", "SHELL_TRUE", rel, node.lineno, f"{name} com shell=True"))

                if any(
                    keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                    for keyword in node.keywords
                ) and (name.startswith("requests.") or name.startswith("httpx.")):
                    findings.append(Finding("error", "TLS_VERIFY_FALSE", rel, node.lineno, f"{name} com verify=False"))

                if isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "executemany"}:
                    if node.args and isinstance(node.args[0], ast.JoinedStr):
                        findings.append(Finding("error", "SQL_FSTRING", rel, node.lineno, "SQL montado com f-string"))

        for key, values in module_routes.items():
            if len(values) > 1:
                findings.append(Finding("error", "DUPROUTE", rel, values[-1][1], f"rota {key[0]} {key[1]} registrada várias vezes: {values}"))

        for command, values in command_handlers.items():
            unique_handlers = {handler for handler, _ in values}
            if len(values) > 1 and len(unique_handlers) > 1:
                findings.append(Finding("warning", "DUPCOMMAND", rel, values[-1][1], f"/{command} registrado para handlers diferentes: {values}"))

        for pattern, values in callback_patterns.items():
            unique_handlers = {handler for handler, _ in values}
            if len(values) > 1 and len(unique_handlers) > 1:
                findings.append(Finding("warning", "DUPCALLBACK", rel, values[-1][1], f"pattern {pattern!r} registrado para handlers diferentes: {values}"))

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and call_name(child.func) == "time.sleep":
                        findings.append(Finding("error", "ASYNC_BLOCK", rel, child.lineno, f"time.sleep dentro de async {node.name}"))

            if isinstance(node, ast.ImportFrom):
                target = resolve_import_module(current_module, int(node.level or 0), node.module)
                if not target or target.split(".")[0] not in local_roots:
                    continue
                if target not in modules:
                    findings.append(Finding("error", "LOCAL_IMPORT_MODULE", rel, node.lineno, f"módulo local inexistente: {target}"))
                    continue
                available = symbols.get(target, set())
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    nested_module = f"{target}.{alias.name}"
                    if alias.name not in available and nested_module not in modules:
                        findings.append(Finding("error", "LOCAL_IMPORT_SYMBOL", rel, node.lineno, f"{alias.name} não existe em {target}"))

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    if target.split(".")[0] in local_roots and target not in modules:
                        findings.append(Finding("error", "LOCAL_IMPORT_MODULE", rel, node.lineno, f"módulo local inexistente: {target}"))

        for node in tree.body:
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            name = call_name(node.value.func)
            if name == "create_tables" or name.startswith("create_") and name.endswith("_tables"):
                findings.append(Finding("warning", "IMPORT_SIDE_EFFECT", rel, node.lineno, f"{name} executado durante import"))

        text = texts.get(path, "")
        if len(text.splitlines()) > 2500:
            findings.append(Finding("warning", "LARGE_MODULE", rel, 1, f"módulo possui {len(text.splitlines())} linhas"))

    for key, values in global_routes.items():
        unique_files = {item[0] for item in values}
        if len(unique_files) > 1:
            findings.append(Finding("warning", "CROSS_FILE_ROUTE", values[-1][0], values[-1][1], f"rota {key[0]} {key[1]} aparece em: {values}"))

    for path in all_files:
        rel = relative(path)
        lower_name = path.name.lower()
        lower_suffix = path.suffix.lower()
        if lower_name in RISKY_FILENAMES or lower_suffix in RISKY_SUFFIXES:
            findings.append(Finding("error", "TRACKED_SECRET_FILE", rel, 0, "arquivo sensível não deve estar versionado"))

        if path.suffix.lower() in {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".toml", ".ini", ".cfg"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if BOT_TOKEN_RE.search(text):
                findings.append(Finding("error", "HARDCODED_BOT_TOKEN", rel, 0, "possível token de bot Telegram no repositório"))
            if any(marker in text for marker in PRIVATE_KEY_MARKERS):
                findings.append(Finding("error", "PRIVATE_KEY", rel, 0, "chave privada encontrada no repositório"))

        if path.suffix.lower() == ".json" or path.name in JSON_LIKE_TEXT_FILES:
            if path.stat().st_size > 32 * 1024 * 1024:
                findings.append(Finding("warning", "JSON_TOO_LARGE", rel, 0, "JSON maior que 32 MiB não foi validado"))
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
                findings.append(Finding("error", "INVALID_JSON", rel, getattr(exc, "lineno", 0) or 0, str(exc)))

    readme = ROOT / "README.md"
    if not readme.exists() or len(readme.read_text(encoding="utf-8", errors="replace").strip()) < 200:
        findings.append(Finding("warning", "README_INCOMPLETE", "README.md", 1, "README ausente ou insuficiente para operar o projeto"))

    return sorted(findings, key=lambda item: (item.severity != "error", item.path, item.line, item.code))


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria estática do Source Baltigo Bot")
    parser.add_argument("--report", default="artifacts/system-audit.json", help="caminho do relatório JSON")
    parser.add_argument("--fail-on-warning", action="store_true", help="trata warnings como falha")
    args = parser.parse_args()

    findings = inspect_repository()
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]

    for item in findings:
        print(f"{item.severity.upper():7} {item.code:22} {item.path}:{item.line} {item.message}")

    report_path = ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "summary": {"errors": len(errors), "warnings": len(warnings), "total": len(findings)},
                "findings": [asdict(item) for item in findings],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"AUDIT_ERRORS={len(errors)}")
    print(f"AUDIT_WARNINGS={len(warnings)}")
    print(f"AUDIT_REPORT={relative(report_path)}")
    return 1 if errors or (args.fail_on_warning and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
