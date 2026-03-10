import os
import asyncio
import time
from typing import Optional, Tuple

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import database as db
from cards_service import get_character_by_id
from utils.gatekeeper import gatekeeper


ANTIFLOOD = 2.0
_profile_locks: dict[int, asyncio.Lock] = {}
_last_profile: dict[int, float] = {}


# =========================================================
# ADMINS
# =========================================================

def _load_admins() -> set[int]:
    raw = os.getenv("ADMINS", "").strip()
    if not raw:
        return set()

    out = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except Exception:
            pass
    return out


ADMINS_SET = _load_admins()


def is_admin(user_id: int) -> bool:
    return int(user_id) in ADMINS_SET


# =========================================================
# LOCK / ANTIFLOOD
# =========================================================

def _get_profile_lock(user_id: int) -> asyncio.Lock:
    lock = _profile_locks.get(int(user_id))
    if lock is None:
        lock = asyncio.Lock()
        _profile_locks[int(user_id)] = lock
    return lock


def _anti_spam(user_id: int) -> bool:
    now = time.time()
    last = _last_profile.get(int(user_id), 0.0)

    if now - last < ANTIFLOOD:
        return False

    _last_profile[int(user_id)] = now
    return True


# =========================================================
# CHAT / LANG HELPERS
# =========================================================

def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.type) in ("group", "supergroup")


def _country_flag(code: str) -> str:
    code = str(code or "").strip().upper()
    mapping = {
        "BR": "🇧🇷",
        "US": "🇺🇸",
        "ES": "🇪🇸",
        "JP": "🇯🇵",
    }
    return mapping.get(code, "🏳️")


def _lang_pack(lang: str) -> dict:
    lang = str(lang or "pt").strip().lower()

    packs = {
        "pt": {
            "profile_title": "PERFIL DO USUÁRIO",
            "role_admin": "Admin",
            "role_user": "User",
            "collection": "Coleção",
            "coins": "Coins",
            "level": "Nível",
            "favorite": "Favorito",
            "none_favorite": "— Nenhum favorito",
            "private_profile": "Perfil privado!",
            "not_found_title": "Usuário não encontrado",
            "not_found_help": "Use:\n<code>/perfil</code>\nou\n<code>/perfil Nickname</code>",
        },
        "en": {
            "profile_title": "USER PROFILE",
            "role_admin": "Admin",
            "role_user": "User",
            "collection": "Collection",
            "coins": "Coins",
            "level": "Level",
            "favorite": "Favorite",
            "none_favorite": "— No favorite",
            "private_profile": "Private profile!",
            "not_found_title": "User not found",
            "not_found_help": "Use:\n<code>/perfil</code>\nor\n<code>/perfil Nickname</code>",
        },
        "es": {
            "profile_title": "PERFIL DEL USUARIO",
            "role_admin": "Admin",
            "role_user": "User",
            "collection": "Colección",
            "coins": "Coins",
            "level": "Nivel",
            "favorite": "Favorito",
            "none_favorite": "— Sin favorito",
            "private_profile": "¡Perfil privado!",
            "not_found_title": "Usuario no encontrado",
            "not_found_help": "Usa:\n<code>/perfil</code>\no\n<code>/perfil Nickname</code>",
        },
    }

    return packs.get(lang, packs["pt"])


# =========================================================
# DATA HELPERS
# =========================================================

def _safe_display_name(user_id: int, user_row: dict, settings_row: dict) -> str:
    nickname = str((settings_row or {}).get("nickname") or "").strip()
    if nickname:
        return nickname

    full_name = str((user_row or {}).get("full_name") or "").strip()
    if full_name:
        return full_name

    username = str((user_row or {}).get("username") or "").strip()
    if username:
        return f"@{username}"

    return f"User {user_id}"


def _get_level(user_id: int) -> int:
    try:
        row = db.get_progress_row(int(user_id)) or {}
        return int(row.get("level") or 1)
    except Exception:
        return 1


def _get_collection_total(user_id: int) -> int:
    try:
        cards = db.get_user_card_collection(int(user_id)) or []
        return len(cards)
    except Exception:
        return 0


def _get_favorite_from_settings(settings_row: dict):
    try:
        fav_id = (settings_row or {}).get("favorite_character_id")
        if not fav_id:
            return None

        ch = get_character_by_id(int(fav_id))
        if not ch:
            return None

        return {
            "id": int(fav_id),
            "name": str(ch.get("name") or "").strip(),
            "anime": str(ch.get("anime") or "").strip(),
            "image": str(ch.get("image") or "").strip(),
        }
    except Exception:
        return None


def _ensure_viewer_user(update: Update) -> Optional[int]:
    user = update.effective_user
    if not user:
        return None

    user_id = int(user.id)
    db.create_or_get_user(user_id)

    try:
        db.touch_user_identity(
            user_id,
            user.username or "",
            user.full_name or "",
        )
    except Exception:
        pass

    try:
        db.ensure_profile_settings_row(user_id)
    except Exception:
        pass

    return user_id


def _get_user_by_nickname(nickname: str) -> Tuple[Optional[dict], Optional[dict]]:
    nickname = str(nickname or "").strip()
    if not nickname:
        return None, None

    try:
        settings_row = db.get_profile_settings_by_nickname(nickname)
    except Exception:
        settings_row = None

    if not settings_row:
        return None, None

    user_id = int(settings_row["user_id"])
    user_row = db.get_user_status(user_id)
    if not user_row:
        return None, None

    return (
        {
            "user_id": user_id,
            **dict(user_row),
        },
        dict(settings_row),
    )


def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Tuple[Optional[dict], Optional[dict]]:
    viewer_id = _ensure_viewer_user(update)
    if viewer_id is None:
        return None, None

    if not context.args:
        user_row = db.get_user_status(viewer_id) or {}
        settings_row = db.get_profile_settings(viewer_id) or {}
        return (
            {
                "user_id": viewer_id,
                **dict(user_row),
            },
            dict(settings_row),
        )

    raw_nick = " ".join(context.args).strip()
    return _get_user_by_nickname(raw_nick)


# =========================================================
# TEXT BUILDERS
# =========================================================

def _build_private_text(user_row: dict, settings_row: dict, favorite) -> str:
    user_id = int(user_row["user_id"])
    lang = str((settings_row or {}).get("language") or "pt").strip().lower()
    t = _lang_pack(lang)

    display_name = _safe_display_name(user_id, user_row, settings_row)
    role = t["role_admin"] if is_admin(user_id) else t["role_user"]
    flag = _country_flag(settings_row.get("country_code"))

    return (
        f"{flag} <b>{t['profile_title']}</b>\n\n"
        f"👤 | <i>{role}</i> <b>{display_name}</b>\n\n"
        f"🔐 | <b>{t['private_profile']}</b>\n\n"
        f"❤️ <b>{t['favorite']}:</b>\n"
        + (f"🧧 <b>{favorite['name']}</b>" if favorite else t["none_favorite"])
    )


def _build_public_text(user_row: dict, settings_row: dict, level: int, total_collection: int, favorite) -> str:
    user_id = int(user_row["user_id"])
    lang = str((settings_row or {}).get("language") or "pt").strip().lower()
    t = _lang_pack(lang)

    display_name = _safe_display_name(user_id, user_row, settings_row)
    coins = int(user_row.get("coins") or 0)
    role = t["role_admin"] if is_admin(user_id) else t["role_user"]
    flag = _country_flag(settings_row.get("country_code"))

    return (
        f"{flag} <b>{t['profile_title']}</b>\n\n"
        f"👤 | <i>{role}</i> <b>{display_name}</b>\n\n"
        f"📚 | <i>{t['collection']}:</i> <b>{total_collection}</b>\n"
        f"🪙 | <i>{t['coins']}:</i> <b>{coins}</b>\n"
        f"⭐️ | <i>{t['level']}:</i> <b>{level}</b>\n\n"
        f"❤️ <b>{t['favorite']}:</b>\n"
        + (f"🧧 <b>{favorite['name']}</b>" if favorite else t["none_favorite"])
    )


# =========================================================
# SEND HELPERS
# =========================================================

async def _send_text_fallback(update: Update, text: str):
    msg = update.effective_message
    chat = update.effective_chat

    if msg:
        try:
            await msg.reply_text(text, parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass

    if chat:
        await update.get_bot().send_message(
            chat_id=chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
        )


async def _send_profile_message(update: Update, text: str, favorite):
    msg = update.effective_message
    chat = update.effective_chat
    bot = update.get_bot()

    if favorite and favorite.get("image"):
        if msg:
            try:
                await msg.reply_photo(
                    photo=favorite["image"],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
                return
            except Exception:
                pass

        if chat:
            try:
                await bot.send_photo(
                    chat_id=chat.id,
                    photo=favorite["image"],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
                return
            except Exception:
                pass

    await _send_text_fallback(update, text)


# =========================================================
# /perfil
# =========================================================

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg and not update.effective_chat:
        return

    if user and not _anti_spam(int(user.id)):
        return

    # no PV usa gatekeeper
    if not _is_group(update):
        ok, bloqueio = await gatekeeper(update, context)
        if not ok:
            if bloqueio:
                await _send_text_fallback(update, bloqueio)
            return

    lock_user_id = int(user.id) if user else 0
    lock = _get_profile_lock(lock_user_id)

    async with lock:
        try:
            user_row, settings_row = _resolve_target(update, context)

            viewer_id = int(user.id) if user else 0
            viewer_settings = db.get_profile_settings(viewer_id) or {}
            viewer_lang = str(viewer_settings.get("language") or "pt").strip().lower()
            viewer_texts = _lang_pack(viewer_lang)

            if not user_row:
                await _send_text_fallback(
                    update,
                    f"❌ <b>{viewer_texts['not_found_title']}</b>\n\n{viewer_texts['not_found_help']}"
                )
                return

            target_id = int(user_row["user_id"])
            private_on = bool((settings_row or {}).get("private_profile"))
            favorite = _get_favorite_from_settings(settings_row)

            # em grupo: perfil privado sempre mostra reduzido
            if _is_group(update) and private_on:
                text = _build_private_text(
                    user_row=user_row,
                    settings_row=settings_row,
                    favorite=favorite,
                )
                await _send_profile_message(update, text, favorite)
                return

            level = _get_level(target_id)
            total_collection = _get_collection_total(target_id)

            text = _build_public_text(
                user_row=user_row,
                settings_row=settings_row,
                level=level,
                total_collection=total_collection,
                favorite=favorite,
            )

            await _send_profile_message(update, text, favorite)

        except Exception:
            # fallback final para não morrer silenciosamente em grupo
            try:
                viewer_id = int(user.id) if user else 0
                viewer_settings = db.get_profile_settings(viewer_id) or {}
                viewer_lang = str(viewer_settings.get("language") or "pt").strip().lower()
                viewer_texts = _lang_pack(viewer_lang)

                await _send_text_fallback(
                    update,
                    f"❌ <b>{viewer_texts['not_found_title']}</b>"
                )
            except Exception:
                pass
            raise
