import asyncio
from html import escape
import os
import random
import time
from typing import Any, Dict, List, Optional

from telegram import Message, Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data
from database import (
    delete_active_group_spawn,
    get_active_group_spawn,
    get_all_global_character_images,
    upsert_active_group_spawn,
)


ACTIVE_SPAWNS: Dict[int, Dict[str, Any]] = {}
MESSAGE_COUNTER: Dict[int, int] = {}
RECENT_CHARACTER_IDS: Dict[int, List[int]] = {}
LAST_SPAWN_RESULTS: Dict[int, Dict[str, Any]] = {}

SPAWN_EVERY = max(1, int(os.getenv("CAPTURE_SPAWN_EVERY", "75")))
ESCAPE_TIME = max(30, int(os.getenv("CAPTURE_ESCAPE_TIME", "300")))
XP_REWARD = max(1, int(os.getenv("CAPTURE_XP_REWARD", "10")))
PURCHASE_COST = max(1, int(os.getenv("CAPTURE_PURCHASE_COST", "5")))
PURCHASE_WINDOW_SECONDS = max(30, int(os.getenv("CAPTURE_PURCHASE_WINDOW", "180")))
CURATED_WEIGHT = max(2, int(os.getenv("CAPTURE_CURATED_WEIGHT", "4")))
RECENT_HISTORY_SIZE = max(4, int(os.getenv("CAPTURE_RECENT_HISTORY", "12")))
RESULT_TTL_SECONDS = max(900, PURCHASE_WINDOW_SECONDS + 600, ESCAPE_TIME + 600)


def _format_window(seconds: int) -> str:
    total = max(int(seconds), 0)
    minutes, sec = divmod(total, 60)

    if minutes <= 0:
        return f"{sec}s"
    if sec == 0:
        return f"{minutes} min"
    return f"{minutes} min {sec}s"


def _character_block(character: Dict[str, Any]) -> str:
    name = escape(str(character.get("name") or "Visitante desconhecido"))
    anime = escape(str(character.get("anime") or "Origem desconhecida"))
    return (
        "<blockquote>"
        f"👤 <b>{name}</b>\n"
        f"🎬 <b>{anime}</b>"
        "</blockquote>"
    )


def get_chat_spawn_result(chat_id: int) -> Optional[Dict[str, Any]]:
    row = LAST_SPAWN_RESULTS.get(int(chat_id))
    if not row:
        return None

    ended_at = float(row.get("ended_at") or 0.0)
    if ended_at and (time.time() - ended_at) > RESULT_TTL_SECONDS:
        LAST_SPAWN_RESULTS.pop(int(chat_id), None)
        return None

    return row


def record_chat_spawn_result(
    chat_id: int,
    status: str,
    character: Dict[str, Any],
    *,
    winner_user_id: int = 0,
    winner_name: str = "",
) -> Dict[str, Any]:
    row = {
        "status": str(status or "").strip().lower(),
        "character_id": int(character.get("id") or 0),
        "character_name": str(character.get("name") or "Sem nome"),
        "anime_name": str(character.get("anime") or "Obra desconhecida"),
        "winner_user_id": int(winner_user_id or 0),
        "winner_name": str(winner_name or "").strip(),
        "ended_at": time.time(),
    }
    LAST_SPAWN_RESULTS[int(chat_id)] = row
    return row


async def _edit_spawn_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    caption: str,
    reply_markup=None,
) -> bool:
    if not message_id:
        return False

    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        return False


def get_current_spawn(chat_id: int) -> Optional[Dict[str, Any]]:
    chat_id = int(chat_id)
    state = ACTIVE_SPAWNS.get(chat_id)
    if state:
        expires_at = float(state.get("expires_at") or 0.0)
        if not expires_at or expires_at > time.time():
            return state
        ACTIVE_SPAWNS.pop(chat_id, None)

    row = get_active_group_spawn(chat_id)
    if not row:
        return None

    state = {
        "character": {
            "id": int(row.get("character_id") or 0),
            "name": str(row.get("character_name") or "Sem nome"),
            "anime": str(row.get("anime_name") or "Obra desconhecida"),
            "image": str(row.get("image_url") or "").strip(),
            "curated": False,
        },
        "time": float(row.get("created_at_ts") or time.time()),
        "manual": bool(row.get("is_manual")),
        "expires_at": float(row.get("expires_at_ts") or 0.0),
        "message_id": int(row.get("message_id") or 0),
    }
    ACTIVE_SPAWNS[chat_id] = state
    return state


def _load_spawn_characters() -> List[Dict[str, Any]]:
    data = build_cards_final_data()

    if isinstance(data, dict):
        chars_by_id = data.get("characters_by_id", {}) or {}
        items = list(chars_by_id.values())
    else:
        items = []

    curated_ids = set(get_all_global_character_images().keys())
    out: List[Dict[str, Any]] = []

    for ch in items:
        if not isinstance(ch, dict):
            continue

        try:
            cid = int(ch.get("id"))
        except Exception:
            continue

        name = str(ch.get("name") or "").strip()
        anime = str(ch.get("anime") or "Obra desconhecida").strip()
        image = str(ch.get("image") or "").strip()

        if not name or not image:
            continue

        out.append(
            {
                "id": cid,
                "name": name,
                "anime": anime,
                "image": image,
                "curated": cid in curated_ids,
            }
        )

    return out


def get_spawn_pool() -> List[Dict[str, Any]]:
    return _load_spawn_characters()


def _remember_recent_character(chat_id: int, character_id: int) -> None:
    history = RECENT_CHARACTER_IDS.get(chat_id, [])
    history = [cid for cid in history if cid != character_id]
    history.append(character_id)

    if len(history) > RECENT_HISTORY_SIZE:
        history = history[-RECENT_HISTORY_SIZE:]

    RECENT_CHARACTER_IDS[chat_id] = history


def _pick_spawn_character(chat_id: int, characters: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not characters:
        return None

    recent_ids = set(RECENT_CHARACTER_IDS.get(chat_id, []))
    fresh_pool = [item for item in characters if int(item.get("id") or 0) not in recent_ids]
    pool = fresh_pool or list(characters)

    weights = [CURATED_WEIGHT if item.get("curated") else 1 for item in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def _spawn_caption(character: Dict[str, Any], manual: bool = False) -> str:
    if manual:
        title = "🧪 <b>SPAWN DE TESTE</b>"
        intro = "<i>Um portal acabou de se abrir só para testar o sistema.</i>"
    else:
        title = "✨ <b>UM VISITANTE APARECEU</b>"
        if character.get("curated"):
            intro = "<i>O chat chamou um visitante especial. Esse drop veio com arte destacada.</i>"
        else:
            intro = "<i>O chat chamou mais um visitante. Quem reconhecer primeiro fecha a captura.</i>"

    rules = (
        "<blockquote>"
        f"🎯 O primeiro que capturar com <code>/capturar nome</code> ganha <b>{XP_REWARD} XP</b>\n"
        f"🪙 Quem capturar também libera a compra exclusiva da carta por <b>{PURCHASE_COST} coins</b>\n"
        f"⏳ Mas corre: ele desaparece em <b>{_format_window(ESCAPE_TIME)}</b>"
        "</blockquote>"
    )
    footer = "<i>Vale nome completo, primeiro nome ou sobrenome. Capricha no chute e corre antes que ele suma.</i>"

    return (
        f"{title}\n\n"
        f"{intro}\n\n"
        f"{rules}\n\n"
        f"{footer}"
    )


async def start_spawn(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    manual: bool = False,
) -> Optional[Dict[str, Any]]:
    if not message or not message.chat:
        return None

    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        return None

    chat_id = chat.id
    if get_current_spawn(chat_id):
        return None

    characters = get_spawn_pool()
    if not characters:
        return None

    character = _pick_spawn_character(chat_id, characters)
    if not character:
        return None

        state = {
            "character": character,
            "time": time.time(),
            "manual": bool(manual),
            "expires_at": time.time() + ESCAPE_TIME,
        }

    try:
        sent = await message.reply_photo(
            photo=character["image"],
            caption=_spawn_caption(character, manual=manual),
            parse_mode="HTML",
        )
    except Exception:
        return None

    state["message_id"] = getattr(sent, "message_id", 0)
    ACTIVE_SPAWNS[chat_id] = state
    MESSAGE_COUNTER[chat_id] = 0
    _remember_recent_character(chat_id, int(character["id"]))
    upsert_active_group_spawn(
        chat_id=chat_id,
        character_id=int(character["id"]),
        character_name=str(character.get("name") or "Sem nome"),
        anime_name=str(character.get("anime") or "Obra desconhecida"),
        image_url=str(character.get("image") or "").strip(),
        message_id=int(state["message_id"]),
        is_manual=bool(manual),
        created_at_ts=float(state["time"]),
        expires_at_ts=float(state["expires_at"]),
    )

    asyncio.create_task(_escape_character(chat_id, context))
    return state


async def capture_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    user = update.effective_user
    if user and getattr(user, "is_bot", False):
        return

    chat_id = chat.id
    if get_current_spawn(chat_id):
        return

    MESSAGE_COUNTER[chat_id] = MESSAGE_COUNTER.get(chat_id, 0) + 1

    if MESSAGE_COUNTER[chat_id] < SPAWN_EVERY:
        return

    spawned = await start_spawn(update.message, context, manual=False)
    if not spawned:
        MESSAGE_COUNTER[chat_id] = SPAWN_EVERY - 1


async def _escape_character(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = get_current_spawn(chat_id)
    if not state:
        return

    delay = max(float(state.get("expires_at") or 0.0) - time.time(), 0.0)
    await asyncio.sleep(delay)
    await finish_spawn_as_escaped(chat_id, context)


async def finish_spawn_as_escaped(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> Optional[Dict[str, Any]]:
    state = ACTIVE_SPAWNS.pop(chat_id, None)
    if not state:
        state = get_current_spawn(chat_id)
        ACTIVE_SPAWNS.pop(chat_id, None)
    if not state:
        return None

    delete_active_group_spawn(chat_id)

    character = state.get("character") or {}
    record_chat_spawn_result(chat_id, "escaped", character)

    caption = (
        "💨 <b>O VISITANTE ESCAPOU</b>\n\n"
        f"{_character_block(character)}\n\n"
        "<i>Ninguém acertou a tempo. Continuem conversando para chamar o próximo visitante.</i>"
    )

    edited = await _edit_spawn_message(
        context,
        int(chat_id),
        int(state.get("message_id") or 0),
        caption,
        reply_markup=None,
    )

    if not edited:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
        )

    return state
