import os
import asyncio
import time

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from cards_service import get_character_by_id
from utils.gatekeeper import gatekeeper


ANTIFLOOD = 2.0
_profile_locks = {}
_last_profile = {}


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
# HELPERS
# =========================================================

def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


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


def _get_user_by_nickname(nickname: str):
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


def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer = update.effective_user
    if not viewer:
        return None, None

    # próprio perfil
    if not context.args:
        user_id = int(viewer.id)

        db.create_or_get_user(user_id)
        try:
            db.touch_user_identity(
                user_id,
                viewer.username or "",
                viewer.full_name or "",
            )
        except Exception:
            pass

        user_row = db.get_user_status(user_id) or {}
        settings_row = db.get_profile_settings(user_id) or {}

        return (
            {
                "user_id": user_id,
                **dict(user_row),
            },
            dict(settings_row),
        )

    # perfil por nickname
    raw_nick = str(context.args[0] or "").strip()
    return _get_user_by_nickname(raw_nick)


def _build_private_text(user_row: dict, settings_row: dict, favorite) -> str:
    user_id = int(user_row["user_id"])
    lang = str((settings_row or {}).get("language") or "pt").strip().lower()
    t = _lang_pack(lang)

    display_name = _safe_display_name(user_id, user_row, settings_row)
    role = t["role_admin"] if is_admin(user_id) else t["role_user"]
    flag = _country_flag(settings_row.get("country_code"))
    title = f"👤 | <i>{role}</i>"

    text = (
        f"{flag} <b>{t['profile_title']}</b>\n\n"
        f"{title}: <b>{display_name}</b>\n\n"
        f"🔐 | <b>{t['private_profile']}</b>\n\n"
        f"❤️ <b>{t['favorite']}:</b>\n"
    )

    if favorite:
        text += f"🧧 <b>{favorite['name']}</b>"
    else:
        text += t["none_favorite"]

    return text


def _build_public_text(user_row: dict, settings_row: dict, level: int, total_collection: int, favorite) -> str:
    user_id = int(user_row["user_id"])
    lang = str((settings_row or {}).get("language") or "pt").strip().lower()
    t = _lang_pack(lang)

    display_name = _safe_display_name(user_id, user_row, settings_row)
    coins = int(user_row.get("coins") or 0)
    role = t["role_admin"] if is_admin(user_id) else t["role_user"]
    flag = _country_flag(settings_row.get("country_code"))
    title = f"👤 | <i>{role}</i>"

    text = (
        f"{flag} <b>{t['profile_title']}</b>\n\n"
        f"{title}: <b>{display_name}</b>\n\n"
        f"📚 | <i>{t['collection']}:</i> <b>{total_collection}</b>\n"
        f"🪙 | <i>{t['coins']}:</i> <b>{coins}</b>\n"
        f"⭐️ | <i>{t['level']}:</i> <b>{level}</b>\n\n"
        f"❤️ <b>{t['favorite']}:</b>\n"
    )

    if favorite:
        text += f"🧧 <b>{favorite['name']}</b>"
    else:
        text += t["none_favorite"]

    return text


async def _send_profile_message(msg, text: str, favorite):
    if favorite and favorite.get("image"):
        try:
            await msg.reply_photo(
                photo=favorite["image"],
                caption=text,
                parse_mode="HTML",
            )
            return
        except Exception:
            pass

    await msg.reply_html(text)


# =========================================================
# /perfil
# =========================================================

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if not _anti_spam(int(user.id)):
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    lock = _get_profile_lock(int(user.id))

    async with lock:
        user_row, settings_row = _resolve_target(update, context)

        if not user_row:
            # idioma do próprio viewer, se existir
            viewer_settings = db.get_profile_settings(int(user.id)) or {}
            lang = str(viewer_settings.get("language") or "pt").strip().lower()
            t = _lang_pack(lang)

            await msg.reply_html(
                f"❌ <b>{t['not_found_title']}</b>\n\n"
                f"{t['not_found_help']}"
            )
            return

        viewer_id = int(user.id)
        target_id = int(user_row["user_id"])
        private_on = bool((settings_row or {}).get("private_profile"))
        favorite = _get_favorite_from_settings(settings_row)

        # REGRA:
        # - no PV do bot: sempre mostra normal
        # - em grupo: se perfil do alvo estiver privado e não for o próprio alvo, mostra reduzido
        if _is_group(update) and private_on and target_id != viewer_id:
            text = _build_private_text(
                user_row=user_row,
                settings_row=settings_row,
                favorite=favorite,
            )
            await _send_profile_message(msg, text, favorite)
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

        await _send_profile_message(msg, text, favorite)
