from __future__ import annotations

import asyncio
import json
import os

from utils.catalog_safe_rollout import prepare_runtime_safe_catalog

# Materializa adições seguras e, quando explicitamente habilitado, o conjunto
# final de aposentadorias antes de qualquer módulo de cards ser importado.
prepare_runtime_safe_catalog()

from webapp_entrypoint import app  # noqa: E402,F401


def _flag(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


if _flag("CATALOG_USAGE_AUDIT_ON_START"):
    @app.on_event("startup")
    async def _catalog_usage_audit_once() -> None:
        try:
            from utils.catalog_usage_audit_runtime import run_and_log_readonly_usage_audit

            await asyncio.to_thread(run_and_log_readonly_usage_audit)
        except Exception as exc:
            print(
                "CATALOG_USAGE_AUDIT_ERROR "
                + json.dumps(
                    {"error": type(exc).__name__, "message": str(exc)[:500]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                flush=True,
            )


if _flag("CATALOG_RETIREMENT_APPLY_ON_START"):
    @app.on_event("startup")
    async def _catalog_retirement_apply_once() -> None:
        try:
            from utils.catalog_retirement_apply_runtime import run_and_log_apply

            await asyncio.to_thread(run_and_log_apply)
        except Exception as exc:
            print(
                "CATALOG_RETIREMENT_APPLY_ERROR "
                + json.dumps(
                    {"error": type(exc).__name__, "message": str(exc)[:1000]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                flush=True,
            )
            # Falha fechada: o deploy não se torna saudável se compensação e
            # remoção não terminarem atomicamente. Railway mantém a instância anterior.
            raise
