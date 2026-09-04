from __future__ import annotations

import asyncio
import html
import os
from typing import Any

from utils.system_health import application_version, database_snapshot, worker_snapshot


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


HEALTH_ALERTS_ENABLED = _env_bool("SOURCE_HEALTH_ALERTS_ENABLED", True)
HEALTH_INTERVAL_SECONDS = _env_int(
    "SOURCE_HEALTH_INTERVAL_SECONDS",
    120,
    60,
    3600,
)
HEALTH_FAILURE_THRESHOLD = _env_int(
    "SOURCE_HEALTH_FAILURE_THRESHOLD",
    2,
    1,
    10,
)


def alert_target() -> int | str | None:
    raw = (
        str(os.getenv("SOURCE_ALERT_CHAT_ID", "") or "").strip()
        or str(os.getenv("BOT_OWNER_ID", "") or "").strip()
    )
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return raw if raw.startswith("@") else None
    return value if value != 0 else None


def evaluate_components(
    *,
    database: dict[str, Any],
    telegram_ok: bool,
    workers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {
        "telegram": {
            "ok": bool(telegram_ok),
            "status": "healthy" if telegram_ok else "unhealthy",
        },
        "database": {
            "ok": bool(database.get("ok")),
            "status": str(database.get("status") or "unknown"),
        },
    }
    for name, state in workers.items():
        components[f"worker:{name}"] = {
            "ok": bool(state.get("ok")),
            "status": str(state.get("status") or "unknown"),
        }

    failed = tuple(
        sorted(name for name, state in components.items() if not state.get("ok"))
    )
    return {
        "ok": not failed,
        "components": components,
        "failed": failed,
    }


def _status_message(snapshot: dict[str, Any], *, recovered: bool = False) -> str:
    if recovered:
        return (
            "🟢 <b>SOURCE RECUPERADO</b>\n\n"
            "Todos os componentes monitorados voltaram ao estado saudável.\n\n"
            f"🏷 <b>Versão:</b> <code>{html.escape(application_version())}</code>"
        )

    lines = ["🚨 <b>SOURCE ALERT</b>", "", "Componentes com falha:"]
    components = snapshot.get("components") or {}
    for name in snapshot.get("failed") or ():
        state = components.get(name) or {}
        lines.append(
            f"🔴 <code>{html.escape(str(name))}</code> — "
            f"{html.escape(str(state.get('status') or 'unknown'))}"
        )
    lines.extend(
        [
            "",
            f"🏷 <b>Versão:</b> <code>{html.escape(application_version())}</code>",
            "O monitor continuará verificando automaticamente.",
        ]
    )
    return "\n".join(lines)


async def _collect_snapshot(app) -> dict[str, Any]:
    database_task = asyncio.to_thread(database_snapshot)
    try:
        me = await app.bot.get_me()
        telegram_ok = bool(me and me.id)
    except Exception:
        telegram_ok = False

    database = await database_task
    workers = worker_snapshot(app)
    return evaluate_components(
        database=database,
        telegram_ok=telegram_ok,
        workers=workers,
    )


async def _send_alert(app, target: int | str, text: str) -> None:
    try:
        await app.bot.send_message(
            chat_id=target,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        print(
            f"[source-health] alert-send-failed type={type(exc).__name__}",
            flush=True,
        )


async def source_health_monitor(app) -> None:
    target = alert_target()
    if not HEALTH_ALERTS_ENABLED:
        print("[source-health] monitor desativado", flush=True)
        return
    if target is None:
        print("[source-health] sem destino de alerta; monitor não iniciado", flush=True)
        return

    print(
        f"[source-health] monitor iniciado interval={HEALTH_INTERVAL_SECONDS}s",
        flush=True,
    )

    consecutive_failures = 0
    notified_failed: tuple[str, ...] = ()

    while True:
        try:
            snapshot = await _collect_snapshot(app)
            failed = tuple(snapshot.get("failed") or ())

            if failed:
                consecutive_failures += 1
                if (
                    consecutive_failures >= HEALTH_FAILURE_THRESHOLD
                    and failed != notified_failed
                ):
                    await _send_alert(app, target, _status_message(snapshot))
                    notified_failed = failed
            else:
                consecutive_failures = 0
                if notified_failed:
                    await _send_alert(
                        app,
                        target,
                        _status_message(snapshot, recovered=True),
                    )
                    notified_failed = ()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[source-health] monitor-error type={type(exc).__name__}",
                flush=True,
            )

        await asyncio.sleep(HEALTH_INTERVAL_SECONDS)
