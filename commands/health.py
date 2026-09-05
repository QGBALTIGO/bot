from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from scripts.guard_catalog_retirements_by_usage import (
    DEFAULT_COPY_REVIEW_THRESHOLD,
    DEFAULT_OWNER_REVIEW_THRESHOLD,
    load_candidate_manifest,
    run_live_usage_guard,
)
from utils.runtime_guard import lock_manager, rate_limiter
from utils.system_health import (
    application_version,
    database_snapshot,
    uptime_seconds,
    worker_snapshot,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_MANIFEST_PATH = ROOT / "data" / "catalog_cleanup_retire_candidates.v1.json"


def _parse_admin_ids() -> set[int]:
    out: set[int] = set()
    for name in ("BOT_OWNER_ID", "ADMINS", "ADMIN_IDS", "CARD_ADMIN_IDS"):
        raw = str(os.getenv(name, "") or "")
        for part in raw.replace(";", ",").split(","):
            value = part.strip()
            if not value:
                continue
            try:
                user_id = int(value)
            except ValueError:
                continue
            if user_id > 0:
                out.add(user_id)
    return out


def _duration_label(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _status_icon(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def _catalog_manifest_policy(manifest: dict[str, Any]) -> tuple[int, int]:
    policy = manifest.get("policy") or {}
    owner_threshold = max(
        1,
        int(policy.get("owner_review_threshold") or DEFAULT_OWNER_REVIEW_THRESHOLD),
    )
    copy_threshold = max(
        1,
        int(policy.get("copy_review_threshold") or DEFAULT_COPY_REVIEW_THRESHOLD),
    )
    return owner_threshold, copy_threshold


def _catalog_public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"candidate_ids", "candidate_ids_zlib_base64"}
    }


def _catalog_impact_text(report: dict[str, Any]) -> str:
    before = report.get("before_guard") or {}
    after = report.get("after_guard") or {}
    moved = report.get("moved_to_review") or []

    def n(value: Any) -> str:
        return f"{int(value or 0):,}".replace(",", ".")

    lines = [
        "🔎 <b>CATALOG IMPACT — READ-ONLY</b>",
        "",
        f"🧾 Candidatos iniciais: <b>{n(report.get('candidate_count'))}</b>",
        f"🛡 Movidos para REVIEW: <b>{n(report.get('moved_to_review_count'))}</b>",
        f"🗑 RETIRE final: <b>{n(report.get('final_retire_count'))}</b>",
        "",
        "<b>Antes da trava</b>",
        f"• Usuários distintos: <b>{n(before.get('affected_users'))}</b>",
        f"• Cópias: <b>{n(before.get('copies'))}</b>",
        "",
        "<b>Depois da trava</b>",
        f"• Usuários distintos afetados: <b>{n(after.get('affected_users'))}</b>",
        f"• Cópias removidas: <b>{n(after.get('copies'))}</b>",
        f"• Coins necessários: <b>{n(report.get('coins_required_after_guard'))}</b>",
        "",
        (
            "Regra: REVIEW com "
            f"<b>≥{n(report.get('owner_review_threshold'))} donos</b> "
            f"OU <b>≥{n(report.get('copy_review_threshold'))} cópias</b>."
        ),
    ]

    if moved:
        lines.extend(["", "<b>Maior impacto salvo da remoção</b>"])
        for row in moved[:8]:
            name = html.escape(str(row.get("name") or row.get("character_id") or "?"))
            lines.append(
                f"• {name}: {n(row.get('owners'))} donos / {n(row.get('copies'))} cópias"
            )

    lines.extend(
        [
            "",
            "✅ Nenhum saldo, coleção, troca, spawn ou override foi alterado.",
            "📎 O JSON anexo contém a lista final e agregados por personagem, sem <code>user_id</code>.",
        ]
    )
    return "\n".join(lines)


async def _catalog_impact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    allowed = await rate_limiter.allow(
        key=f"catalogimpact:{int(user.id)}",
        limit=1,
        window_seconds=60.0,
    )
    if not allowed:
        await message.reply_text("⌛ A auditoria read-only pode ser executada novamente em instantes.")
        return

    status_message = await message.reply_text(
        "🔎 Consultando o impacto real no PostgreSQL em modo somente leitura..."
    )
    audit_lock = await lock_manager.acquire("catalog-impact:live-readonly")
    try:
        manifest = await asyncio.to_thread(load_candidate_manifest, CATALOG_MANIFEST_PATH)
        owner_threshold, copy_threshold = _catalog_manifest_policy(manifest)
        report = await asyncio.to_thread(
            run_live_usage_guard,
            manifest["candidate_ids"],
            owner_threshold=owner_threshold,
            copy_threshold=copy_threshold,
        )
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        report["manifest"] = _catalog_public_manifest(manifest)
        report["read_only"] = True
        report["contains_user_ids"] = False

        await status_message.edit_text(
            _catalog_impact_text(report),
            parse_mode="HTML",
        )

        document = io.BytesIO(
            json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        )
        document.name = "catalog_impact_readonly.json"
        await message.reply_document(
            document=document,
            filename=document.name,
            caption="Auditoria agregada do catálogo. READ-ONLY; não aplica aposentadorias.",
        )
    except Exception:
        logger.exception("Falha na auditoria read-only de impacto do catálogo")
        try:
            await status_message.edit_text(
                "❌ Não foi possível concluir a auditoria. Nenhuma alteração foi feita; o erro foi registrado."
            )
        except Exception:
            pass
    finally:
        audit_lock.release()


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    if int(user.id) not in _parse_admin_ids():
        await message.reply_text("Comando disponível apenas para a administração.")
        return

    mode = str(context.args[0] if context.args else "").strip().casefold()
    if mode in {"catalog", "catalogimpact", "catalogo"}:
        await _catalog_impact(update, context)
        return

    db_task = asyncio.to_thread(database_snapshot)

    telegram_started = time.perf_counter()
    try:
        bot_info = await context.bot.get_me()
        telegram_ok = bool(bot_info and bot_info.id)
        telegram_error = ""
    except Exception as exc:
        telegram_ok = False
        telegram_error = type(exc).__name__
    telegram_ms = round((time.perf_counter() - telegram_started) * 1000, 2)

    database = await db_task
    workers = worker_snapshot(context.application)

    worker_lines = []
    workers_ok = True
    for label, state in workers.items():
        ok = bool(state.get("ok"))
        workers_ok = workers_ok and ok
        worker_lines.append(
            f"{_status_icon(ok)} <code>{html.escape(label)}</code>: "
            f"{html.escape(str(state.get('status') or 'unknown'))}"
        )

    overall_ok = bool(database.get("ok")) and telegram_ok and workers_ok
    title_icon = "🟢" if overall_ok else "🟡"

    telegram_detail = f"{telegram_ms} ms"
    if telegram_error:
        telegram_detail += f" · {telegram_error}"

    text = (
        f"{title_icon} <b>SOURCE HEALTH</b>\n\n"
        f"{_status_icon(telegram_ok)} <b>Telegram:</b> <code>{html.escape(telegram_detail)}</code>\n"
        f"{_status_icon(bool(database.get('ok')))} <b>PostgreSQL:</b> "
        f"<code>{database.get('duration_ms', 0)} ms</code>\n\n"
        "<b>Workers</b>\n"
        + "\n".join(worker_lines)
        + "\n\n"
        f"⏱ <b>Uptime:</b> <code>{_duration_label(uptime_seconds())}</code>\n"
        f"🏷 <b>Versão:</b> <code>{html.escape(application_version())}</code>"
    )

    await message.reply_html(text)
