import os
from telegram import Update
from telegram.ext import ContextTypes

_chars_cache = {}
_file_path = None


def find_file():
    global _file_path

    possible = [
        "data/personagens_anilist.txt",
        "./data/personagens_anilist.txt",
        "../data/personagens_anilist.txt",
        "/app/data/personagens_anilist.txt",
        "bot/data/personagens_anilist.txt",
    ]

    for p in possible:
        if os.path.exists(p):
            _file_path = p
            return p

    return None


def load_characters():
    global _chars_cache

    if _chars_cache:
        return _chars_cache

    path = find_file()

    if not path:
        print("❌ personagens_anilist.txt NÃO encontrado")
        return {}

    chars = {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:

            line = line.strip()

            if not line:
                continue

            parts = line.split("|")

            if len(parts) < 3:
                continue

            try:
                char_id = int(parts[0])
            except:
                continue

            name = parts[1].strip()
            anime = parts[2].strip()

            chars[char_id] = {
                "id": char_id,
                "name": name,
                "anime": anime
            }

    print(f"✅ {len(chars)} personagens carregados")

    _chars_cache = chars
    return chars


def search_character(query):

    chars = load_characters()

    if not chars:
        return None

    # busca por ID
    if query.isdigit():

        cid = int(query)

        if cid in chars:
            return chars[cid]

    # busca por nome
    query = query.lower()

    for char in chars.values():

        if query in char["name"].lower():
            return char

    return None


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.effective_message

    try:

        if not context.args:
            await msg.reply_text(
                "Use:\n"
                "/card nome\n"
                "/card ID"
            )
            return

        query = " ".join(context.args)

        char = search_character(query)

        if not char:

            path = find_file()

            if not path:
                await msg.reply_text(
                    "❌ Arquivo personagens_anilist.txt não encontrado."
                )
                return

            await msg.reply_text(
                "❌ Personagem não encontrado."
            )
            return

        name = char["name"]
        anime = char["anime"]
        char_id = char["id"]

        image = f"https://img.anili.st/character/{char_id}"

        text = (
            f"🎴 <b>{name}</b>\n"
            f"📺 {anime}\n"
            f"🆔 {char_id}"
        )

        await msg.reply_photo(
            photo=image,
            caption=text,
            parse_mode="HTML"
        )

    except Exception as e:
        await msg.reply_text(f"❌ Erro no /card: {e}")


async def card_stats_callback(update, context):
    query = update.callback_query
    await query.answer("Stats em breve.")
