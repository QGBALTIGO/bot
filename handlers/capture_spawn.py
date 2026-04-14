import asyncio
import os
import random
import time
from typing import Any, Dict, List, Optional

from telegram import Message, Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data
from database import get_all_global_character_images


ACTIVE_SPAWNS: Dict[int, Dict[str, Any]] = {}
MESSAGE_COUNTER: Dict[int, int] = {}
RECENT_CHARACTER_IDS: Dict[int, List[int]] = {}

SPAWN_EVERY = max(1, int(os.getenv("CAPTURE_SPAWN_EVERY", "75")))
ESCAPE_TIME = max(30, int(os.getenv("CAPTURE_ESCAPE_TIME", "300")))
XP_REWARD = max(1, int(os.getenv("CAPTURE_XP_REWARD", "10")))
PURCHASE_COST = max(1, int(os.getenv("CAPTURE_PURCHASE_COST", "5")))
PURCHASE_WINDOW_SECONDS = max(30, int(os.getenv("CAPTURE_PURCHASE_WINDOW", "180")))
CURATED_WEIGHT = max(2, int(os.getenv("CAPTURE_CURATED_WEIGHT", "4")))
RECENT_HISTORY_SIZE = max(4, int(os.getenv("CAPTURE_RECENT_HISTORY", "12")))

DROP_TITLES = [
    "✦ <b>DROP DE PERSONAGEM</b>",
    "✦ <b>CLAIM ABERTO</b>",
    "✦ <b>DROP SURPRESA</b>",
]

DROP_INTROS = [
    "Um personagem caiu no chat. Quem reclamar primeiro leva o claim.",
    "O chat ficou quente e um personagem apareceu para disputa.",
    "Uma nova carta viva apareceu por aqui. Corre para garantir o claim.",
]

DROP_CURATED_INTROS = [
    "Drop especial detectado. Esse personagem veio com arte destacada.",
    "Apareceu um destaque do setfoto. Esse drop merece corrida no claim.",
]


def _format_window(seconds: int) -> str:
    total = max(int(seconds), 0)
    minutes, sec = divmod(total, 60)

    if minutes <= 0:
        return f"{sec}s"
    if sec == 0:
        return f"{minutes} min"
    return f"{minutes} min {sec}s"


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
        title = "✦ <b>DROP DE TESTE</b>"
        intro = "Spawn manual ativado para testar o sistema de claim."
    else:
        title = random.choice(DROP_TITLES)
        if character.get("curated"):
            intro = random.choice(DROP_CURATED_INTROS)
        else:
            intro = random.choice(DROP_INTROS)

    claim_hint = "Vale nome completo, primeiro nome ou sobrenome."

    return (
        f"{title}\n\n"
        f"{intro}\n\n"
        f"⚡ Claim: <code>/capturar nome</code>\n"
        f"📝 {claim_hint}\n"
        f"⭐ Recompensa do claim: <b>{XP_REWARD} XP</b>\n"
        f"🛒 O vencedor desbloqueia a compra da carta por <b>{PURCHASE_COST} coins</b>\n"
        f"⏳ O drop some em <b>{_format_window(ESCAPE_TIME)}</b>"
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
    if chat_id in ACTIVE_SPAWNS:
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
    if chat_id in ACTIVE_SPAWNS:
        return

    MESSAGE_COUNTER[chat_id] = MESSAGE_COUNTER.get(chat_id, 0) + 1

    if MESSAGE_COUNTER[chat_id] < SPAWN_EVERY:
        return

    spawned = await start_spawn(update.message, context, manual=False)
    if not spawned:
        MESSAGE_COUNTER[chat_id] = SPAWN_EVERY - 1


async def _escape_character(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(ESCAPE_TIME)

    state = ACTIVE_SPAWNS.pop(chat_id, None)
    if not state:
        return

    char = state.get("character") or {}
    text = (
        "✦ <b>DROP PERDIDO</b>\n\n"
        f"👤 <b>{char.get('name', 'Sem nome')}</b>\n"
        f"🎬 <b>{char.get('anime', 'Obra desconhecida')}</b>\n\n"
        "Ninguem fechou o claim a tempo. Continuem conversando para puxar o proximo drop."
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
    )
