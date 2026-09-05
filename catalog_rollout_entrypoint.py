from __future__ import annotations

import asyncio
import json
import os

from utils.catalog_safe_rollout import prepare_runtime_safe_catalog

# Materializa apenas as adições seguras antes de qualquer módulo de cards ser importado.
# Se o manifesto estiver inválido/incompleto, o bot continua com o catálogo antigo.
prepare_runtime_safe_catalog()

from webapp_entrypoint import app  # noqa: E402,F401


if str(os.getenv("CATALOG_USAGE_AUDIT_ON_START") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
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
