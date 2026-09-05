from __future__ import annotations

import os


def _safe_catalog_bootstrap() -> None:
    if str(os.getenv("SOURCE_CATALOG_SAFE_ROLLOUT") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    try:
        from utils.catalog_safe_rollout import prepare_runtime_safe_catalog

        prepare_runtime_safe_catalog()
    except Exception as exc:
        # Fail-open para disponibilidade e fail-closed para a mudança de catálogo:
        # o processo continua com CARDS_OVERRIDES_PATH original, sem aplicar o rollout.
        print(
            f"CATALOG_SAFE_ROLLOUT bootstrap_failed error={type(exc).__name__}",
            flush=True,
        )


_safe_catalog_bootstrap()
