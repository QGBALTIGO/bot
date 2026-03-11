import os
import random
import asyncio
import time
from typing import Any, Dict, List

from telegram import Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data


ACTIVE_SPAWNS: Dict[int, Dict[str, Any]] = {}
MESSAGE_COUNTER: Dict[int, int] = {}

SPAWN_EVERY = int(os.getenv("CAPTURE_SPAWN_EVERY", "100"))
ESCAPE_TIME = int(os.getenv("CAPTURE_ESCAPE_TIME", "300"))

ENABLED_CHATS = set(
    int(x.strip())
    for x in os.getenv("CAPTURE_ENABLED_CHATS", "").split(",")
    if x.strip()
)


def _load_spawn_characters() -> List[Dict[str, Any]]:
    data = build_cards_final_data()

    if isinstance(data, dict):
        chars_by_id = data.get("characters_by_id", {}) or {}
        items = list(chars_by_id.values())
    else:
        items = []

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

        if not name:
            continue

        if not image:
            continue

        out.append(
            {
                "id": cid,
                "name": name,
                "anime": anime,
                "image": image,
            }
        )

    return out


def get_spawn_pool() -> List[Dict[str, Any]]:
    # Sem cache persistente aqui.
    # Sempre busca do cards_service para refletir mudanças admin.
    return _load_spawn_characters()


async def capture_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    chat_id = chat.id

    if chat_id not in ENABLED_CHATS:
        return

    characters = get_spawn_pool()
    if not characters:
        return

    MESSAGE_COUNTER[chat_id] = MESSAGE_COUNTER.get(chat_id, 0) + 1

    if chat_id in ACTIVE_SPAWNS:
        return

    if MESSAGE_COUNTER[chat_id] < SPAWN_EVERY:
        return

    MESSAGE_COUNTER[chat_id] = 0

    character = random.choice(characters)

    ACTIVE_SPAWNS[chat_id] = {
        "character": character,
        "time": time.time(),
    }

    caption = (
        "✨ <b>UM PERSONAGEM APARECEU!</b>\n\n"
        "🕵️ <i>Quem é esse personagem?</i>\n\n"
        "⏳ Ele fugirá em <b>5 minutos</b>\n\n"
        "💬 Use:\n"
        "<code>/capturar nome</code>"
    )

    await update.message.reply_photo(
        photo=character["image"],
        caption=caption,
        parse_mode="HTML",
    )

    asyncio.create_task(_escape_character(chat_id, context))


async def _escape_character(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(ESCAPE_TIME)

    if chat_id not in ACTIVE_SPAWNS:
        return

    char = ACTIVE_SPAWNS.pop(chat_id)["character"]

    text = (
        "💨 <b>O personagem fugiu...</b>\n\n"
        f"👤 <b>{char['name']}</b>\n"
        f"📺 {char['anime']}"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
    )
