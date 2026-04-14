import asyncio
import os
import random
import time
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from telegram import Bot, Message, Update
from telegram.ext import Application, ContextTypes

from cards_service import build_cards_final_data
from database import (
    attach_capture_spawn_message,
    create_capture_spawn,
    delete_capture_spawn,
    get_active_capture_spawn,
    get_all_global_character_images,
    get_capture_spawn,
    get_recent_capture_character_ids,
    list_active_capture_spawns,
    mark_capture_spawn_escaped,
    register_capture_group_activity,
    reset_capture_group_message_count,
    set_capture_group_message_count,
)
from utils.runtime_guard import lock_manager


SPAWN_EVERY = max(1, int(os.getenv("CAPTURE_SPAWN_EVERY", "75")))
ESCAPE_TIME = max(30, int(os.getenv("CAPTURE_ESCAPE_TIME", "300")))
XP_REWARD = max(1, int(os.getenv("CAPTURE_XP_REWARD", "10")))
PURCHASE_COST = max(1, int(os.getenv("CAPTURE_PURCHASE_COST", "5")))
PURCHASE_WINDOW_SECONDS = max(30, int(os.getenv("CAPTURE_PURCHASE_WINDOW", "180")))
CURATED_WEIGHT = max(2, int(os.getenv("CAPTURE_CURATED_WEIGHT", "4")))
RECENT_HISTORY_SIZE = max(4, int(os.getenv("CAPTURE_RECENT_HISTORY", "12")))
SPAWN_POOL_TTL_SECONDS = max(15, int(os.getenv("CAPTURE_POOL_TTL", "60")))


_SPAWN_POOL_CACHE: Dict[str, Any] = {"loaded_at": 0.0, "items": []}
_SCHEDULED_ESCAPE_TASKS: set[int] = set()


def format_capture_window(seconds: int) -> str:
    total = max(int(seconds), 0)
    minutes, sec = divmod(total, 60)

    if minutes <= 0:
        return f"{sec}s"
    if sec == 0:
        return f"{minutes} min"
    return f"{minutes} min {sec}s"


def build_character_block(data: Dict[str, Any]) -> str:
    name = escape(
        str(
            data.get("character_name")
            or data.get("name")
            or "Visitante desconhecido"
        )
    )
    anime = escape(
        str(
            data.get("anime_name")
            or data.get("anime")
            or "Origem desconhecida"
        )
    )
    return (
        "<blockquote>"
        f"👤 <b>{name}</b>\n"
        f"🎬 <b>{anime}</b>"
        "</blockquote>"
    )


def build_escape_caption(spawn: Dict[str, Any]) -> str:
    return (
        "💨 <b>O VISITANTE ESCAPOU</b>\n\n"
        f"{build_character_block(spawn)}\n\n"
        "<i>Ninguem acertou a tempo. Continuem conversando para chamar o proximo visitante.</i>"
    )


def _spawn_intro(is_manual: bool, is_curated: bool) -> str:
    if is_manual:
        options = [
            "Um portal acabou de se abrir so para testar o sistema.",
            "Esse portal foi aberto para testar o evento completo do chat.",
        ]
    elif is_curated:
        options = [
            "O chat chamou um visitante especial com arte destacada.",
            "Um visitante raro atravessou o portal com visual de destaque.",
            "A conversa do grupo atraiu um drop especial.",
        ]
    else:
        options = [
            "Um portal acabou de se abrir e alguem acabou de atravessar.",
            "O movimento do chat chamou mais um visitante para o grupo.",
            "A conversa esquentou o bastante para atrair um novo visitante.",
        ]

    return random.choice(options)


def build_spawn_caption(spawn: Dict[str, Any]) -> str:
    is_manual = bool(spawn.get("is_manual"))
    is_curated = bool(spawn.get("is_curated"))

    title = "🧪 <b>SPAWN DE TESTE</b>" if is_manual else "✨ <b>UM VISITANTE APARECEU</b>"
    intro = _spawn_intro(is_manual, is_curated)

    rules = (
        "<blockquote>"
        f"🎯 O primeiro que acertar com <code>/capturar nome</code> ganha <b>{XP_REWARD} XP</b>\n"
        f"🪙 Quem capturar desbloqueia a compra exclusiva da carta por <b>{PURCHASE_COST} coins</b>\n"
        f"⏳ O visitante foge em <b>{format_capture_window(ESCAPE_TIME)}</b>"
        "</blockquote>"
    )
    footer = (
        "<i>Vale nome completo, primeiro nome ou sobrenome. "
        "Capricha no chute e corre antes que ele suma.</i>"
    )

    return f"{title}\n\n<i>{escape(intro)}</i>\n\n{rules}\n\n{footer}"


def _get_spawn_pool(force_reload: bool = False) -> List[Dict[str, Any]]:
    now = time.time()
    cached_items = _SPAWN_POOL_CACHE.get("items") or []
    loaded_at = float(_SPAWN_POOL_CACHE.get("loaded_at") or 0.0)

    if cached_items and not force_reload and (now - loaded_at) < SPAWN_POOL_TTL_SECONDS:
        return list(cached_items)

    data = build_cards_final_data(force_reload=force_reload)
    items = []
    if isinstance(data, dict):
        items = list((data.get("characters_by_id") or {}).values())

    curated_ids = set(get_all_global_character_images().keys())
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        try:
            character_id = int(item.get("id") or 0)
        except Exception:
            continue

        if character_id <= 0:
            continue

        name = str(item.get("name") or "").strip()
        anime = str(item.get("anime") or "Obra desconhecida").strip()
        image = str(item.get("image") or "").strip()

        if not name or not image:
            continue

        out.append(
            {
                "id": character_id,
                "name": name,
                "anime": anime,
                "image": image,
                "is_curated": character_id in curated_ids,
            }
        )

    _SPAWN_POOL_CACHE["items"] = list(out)
    _SPAWN_POOL_CACHE["loaded_at"] = now
    return out


def _pick_spawn_character(chat_id: int, characters: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not characters:
        return None

    recent_ids = set(get_recent_capture_character_ids(chat_id, RECENT_HISTORY_SIZE))
    fresh_pool = [item for item in characters if int(item.get("id") or 0) not in recent_ids]
    pool = fresh_pool or list(characters)

    weights = []
    for item in pool:
        weight = CURATED_WEIGHT if item.get("is_curated") else 1
        weights.append(max(1, int(weight)))

    return random.choices(pool, weights=weights, k=1)[0]


async def _send_spawn_post(message: Message, image_url: str, caption: str) -> Tuple[Optional[Message], bool]:
    try:
        sent = await message.reply_photo(
            photo=image_url,
            caption=caption,
            parse_mode="HTML",
        )
        return sent, True
    except Exception:
        try:
            sent = await message.reply_html(caption)
            return sent, False
        except Exception:
            return None, False


async def edit_spawn_post(bot: Bot, spawn: Dict[str, Any], caption: str, reply_markup=None) -> bool:
    message_id = int(spawn.get("spawn_message_id") or 0)

    if message_id:
        try:
            if spawn.get("spawn_has_photo"):
                await bot.edit_message_caption(
                    chat_id=int(spawn["chat_id"]),
                    message_id=message_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                await bot.edit_message_text(
                    chat_id=int(spawn["chat_id"]),
                    message_id=message_id,
                    text=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            return True
        except Exception:
            pass

    try:
        image_url = str(spawn.get("image_url") or "").strip()
        kwargs = {
            "chat_id": int(spawn["chat_id"]),
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }
        if image_url and spawn.get("spawn_has_photo"):
            photo_kwargs = {
                "chat_id": int(spawn["chat_id"]),
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            if message_id:
                try:
                    await bot.send_photo(reply_to_message_id=message_id, **photo_kwargs)
                    return True
                except Exception:
                    pass

            try:
                await bot.send_photo(**photo_kwargs)
                return True
            except Exception:
                pass

        if message_id:
            try:
                await bot.send_message(reply_to_message_id=message_id, **kwargs)
                return True
            except Exception:
                pass

        await bot.send_message(**kwargs)
        return True
    except Exception:
        return False


async def _publish_escape(bot: Bot, spawn: Dict[str, Any]) -> None:
    await edit_spawn_post(bot, spawn, build_escape_caption(spawn), reply_markup=None)


def get_active_spawn(chat_id: int) -> Optional[Dict[str, Any]]:
    return get_active_capture_spawn(chat_id)


async def _expire_active_spawn_if_needed_locked(chat_id: int, bot: Bot) -> Optional[Dict[str, Any]]:
    spawn = get_active_capture_spawn(chat_id)
    if not spawn:
        return None

    if float(spawn.get("expires_at_ts") or 0.0) > time.time():
        return None

    escaped = mark_capture_spawn_escaped(int(spawn["id"]))
    if not escaped:
        return None

    await _publish_escape(bot, escaped)
    return escaped


async def expire_active_spawn_if_needed(chat_id: int, bot: Bot) -> Optional[Dict[str, Any]]:
    lock = await lock_manager.acquire(f"capture:chat:{int(chat_id)}")
    try:
        return await _expire_active_spawn_if_needed_locked(int(chat_id), bot)
    finally:
        lock.release()


async def _start_spawn_locked(
    message: Message,
    bot: Bot,
    *,
    manual: bool = False,
) -> Optional[Dict[str, Any]]:
    if not message or not message.chat:
        return None

    chat_id = int(message.chat.id)
    await _expire_active_spawn_if_needed_locked(chat_id, bot)

    if get_active_capture_spawn(chat_id):
        return None

    characters = _get_spawn_pool()
    if not characters:
        return None

    character = _pick_spawn_character(chat_id, characters)
    if not character:
        return None

    expires_at_ts = time.time() + ESCAPE_TIME
    spawn = create_capture_spawn(
        chat_id=chat_id,
        character_id=int(character["id"]),
        character_name=str(character.get("name") or "Sem nome"),
        anime_name=str(character.get("anime") or "Obra desconhecida"),
        image_url=str(character.get("image") or "").strip(),
        is_curated=bool(character.get("is_curated")),
        is_manual=bool(manual),
        expires_at_ts=expires_at_ts,
    )
    if not spawn:
        return None

    sent, has_photo = await _send_spawn_post(message, spawn["image_url"], build_spawn_caption(spawn))
    if not sent:
        delete_capture_spawn(int(spawn["id"]))
        set_capture_group_message_count(chat_id, SPAWN_EVERY - 1 if not manual else 0)
        return None

    stored = attach_capture_spawn_message(
        int(spawn["id"]),
        int(getattr(sent, "message_id", 0)),
        has_photo=bool(has_photo),
    )
    if stored:
        spawn = stored
    else:
        spawn["spawn_message_id"] = int(getattr(sent, "message_id", 0))
        spawn["spawn_has_photo"] = bool(has_photo)

    reset_capture_group_message_count(chat_id, last_spawn_id=int(spawn["id"]))
    return spawn


async def start_spawn(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    manual: bool = False,
) -> Optional[Dict[str, Any]]:
    if not message or not message.chat:
        return None

    if message.chat.type not in ("group", "supergroup"):
        return None

    chat_id = int(message.chat.id)
    lock = await lock_manager.acquire(f"capture:chat:{chat_id}")
    try:
        spawn = await _start_spawn_locked(message, context.bot, manual=manual)
    finally:
        lock.release()

    if spawn:
        _schedule_escape_task(int(spawn["id"]), context.application)
    return spawn


async def capture_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    user = update.effective_user
    if user and getattr(user, "is_bot", False):
        return

    chat_id = int(chat.id)
    should_spawn = False

    lock = await lock_manager.acquire(f"capture:chat:{chat_id}")
    try:
        escaped = await _expire_active_spawn_if_needed_locked(chat_id, context.bot)
        if escaped:
            pass

        if get_active_capture_spawn(chat_id):
            return

        activity = register_capture_group_activity(chat_id, SPAWN_EVERY)
        should_spawn = bool(activity.get("should_spawn"))
    finally:
        lock.release()

    if should_spawn:
        await start_spawn(update.message, context, manual=False)


async def _escape_worker(spawn_id: int, application: Application) -> None:
    try:
        while True:
            spawn = get_active_capture_spawn_by_id(spawn_id)
            if not spawn:
                return

            delay = max(float(spawn.get("expires_at_ts") or 0.0) - time.time(), 0.0)
            if delay > 0:
                await asyncio.sleep(delay)

            lock = await lock_manager.acquire(f"capture:chat:{int(spawn['chat_id'])}")
            try:
                fresh = get_active_capture_spawn_by_id(spawn_id)
                if not fresh:
                    return

                if float(fresh.get("expires_at_ts") or 0.0) > time.time():
                    continue

                escaped = mark_capture_spawn_escaped(int(spawn_id))
                if not escaped:
                    return
            finally:
                lock.release()

            await _publish_escape(application.bot, escaped)
            return
    finally:
        _SCHEDULED_ESCAPE_TASKS.discard(int(spawn_id))


def _schedule_escape_task(spawn_id: int, application: Application) -> None:
    spawn_id = int(spawn_id)
    if spawn_id <= 0 or spawn_id in _SCHEDULED_ESCAPE_TASKS:
        return

    _SCHEDULED_ESCAPE_TASKS.add(spawn_id)
    asyncio.create_task(_escape_worker(spawn_id, application))


async def restore_capture_runtime(application: Application) -> None:
    for spawn in list_active_capture_spawns():
        _schedule_escape_task(int(spawn["id"]), application)


def get_active_capture_spawn_by_id(spawn_id: int) -> Optional[Dict[str, Any]]:
    spawn = get_capture_spawn(int(spawn_id))
    if not spawn:
        return None
    if str(spawn.get("status") or "").strip().lower() != "active":
        return None
    return spawn
