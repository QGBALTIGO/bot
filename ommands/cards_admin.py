import os
from telegram import Update
from telegram.ext import ContextTypes

from cards_service import (
    override_add_anime,
    override_add_character,
    override_add_subcategory,
    override_delete_anime,
    override_delete_character,
    override_delete_subcategory,
    override_set_anime_banner,
    override_set_anime_cover,
    override_set_character_image,
    override_set_character_name,
    override_subcategory_add_character,
    override_subcategory_remove_character,
    reload_cards_cache,
)

CARD_ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("CARD_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

CARD_ADMIN_USERNAMES = {
    x.strip().lower().lstrip("@")
    for x in os.getenv("CARD_ADMIN_USERNAMES", "").split(",")
    if x.strip()
}


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False

    if user.id in CARD_ADMIN_IDS:
        return True

    username = (user.username or "").strip().lower()
    if username and username in CARD_ADMIN_USERNAMES:
        return True

    return False


async def _deny(update: Update):
    await update.message.reply_text("❌ Você não tem permissão para usar esse comando.")


def _split_pipe(text: str):
    return [x.strip() for x in text.split("|")]


async def card_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    reload_cards_cache()
    await update.message.reply_text("✅ Cache de cards recarregado.")


async def card_delchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("Uso: /card_delchar 24311")

    cid = int(context.args[0])
    override_delete_character(cid)
    await update.message.reply_text(f"✅ Personagem {cid} apagado dos cards.")


async def card_addchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    raw = update.message.text.replace("/card_addchar", "", 1).strip()
    parts = _split_pipe(raw)

    if len(parts) != 5:
        return await update.message.reply_text(
            "Uso:\n/card_addchar 999001 | Nome | 21366 | 3-gatsu no Lion | https://img.jpg"
        )

    if not parts[0].isdigit() or not parts[2].isdigit():
        return await update.message.reply_text("❌ character_id e anime_id precisam ser números.")

    cid = int(parts[0])
    name = parts[1]
    anime_id = int(parts[2])
    anime_name = parts[3]
    image = parts[4]

    override_add_character(cid, name, anime_id, anime_name, image)
    await update.message.reply_text(f"✅ Personagem {name} ({cid}) adicionado.")


async def card_setcharimg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if len(context.args) < 2 or not context.args[0].isdigit():
        return await update.message.reply_text("Uso: /card_setcharimg 24311 https://img.jpg")

    cid = int(context.args[0])
    url = context.args[1].strip()

    override_set_character_image(cid, url)
    await update.message.reply_text(f"✅ Imagem do personagem {cid} atualizada.")


async def card_setcharname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if len(context.args) < 2 or not context.args[0].isdigit():
        return await update.message.reply_text("Uso: /card_setcharname 24311 Novo Nome")

    cid = int(context.args[0])
    name = " ".join(context.args[1:]).strip()

    override_set_character_name(cid, name)
    await update.message.reply_text(f"✅ Nome do personagem {cid} atualizado para {name}.")


async def card_delanime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("Uso: /card_delanime 21366")

    aid = int(context.args[0])
    override_delete_anime(aid)
    await update.message.reply_text(f"✅ Obra {aid} apagada dos cards.")


async def card_addanime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    raw = update.message.text.replace("/card_addanime", "", 1).strip()
    parts = _split_pipe(raw)

    if len(parts) != 4:
        return await update.message.reply_text(
            "Uso:\n/card_addanime 999999 | Minha Obra | https://banner.jpg | https://cover.jpg"
        )

    if not parts[0].isdigit():
        return await update.message.reply_text("❌ anime_id precisa ser número.")

    aid = int(parts[0])
    anime_name = parts[1]
    banner = parts[2]
    cover = parts[3]

    override_add_anime(aid, anime_name, banner, cover)
    await update.message.reply_text(f"✅ Obra {anime_name} ({aid}) adicionada.")


async def card_setanimebanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if len(context.args) < 2 or not context.args[0].isdigit():
        return await update.message.reply_text("Uso: /card_setanimebanner 21366 https://banner.jpg")

    aid = int(context.args[0])
    url = context.args[1].strip()

    override_set_anime_banner(aid, url)
    await update.message.reply_text(f"✅ Banner da obra {aid} atualizado.")


async def card_setanimecover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if len(context.args) < 2 or not context.args[0].isdigit():
        return await update.message.reply_text("Uso: /card_setanimecover 21366 https://cover.jpg")

    aid = int(context.args[0])
    url = context.args[1].strip()

    override_set_anime_cover(aid, url)
    await update.message.reply_text(f"✅ Cover da obra {aid} atualizada.")


async def card_addsubcat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if not context.args:
        return await update.message.reply_text("Uso: /card_addsubcat princesas")

    name = " ".join(context.args).strip()
    override_add_subcategory(name)
    await update.message.reply_text(f"✅ Subcategoria {name} criada.")


async def card_delsubcat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if not context.args:
        return await update.message.reply_text("Uso: /card_delsubcat princesas")

    name = " ".join(context.args).strip()
    override_delete_subcategory(name)
    await update.message.reply_text(f"✅ Subcategoria {name} apagada.")


async def card_subadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if len(context.args) < 2 or not context.args[-1].isdigit():
        return await update.message.reply_text("Uso: /card_subadd princesas 24311")

    cid = int(context.args[-1])
    name = " ".join(context.args[:-1]).strip()

    override_subcategory_add_character(name, cid)
    await update.message.reply_text(f"✅ Personagem {cid} adicionado em {name}.")


async def card_subremove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return await _deny(update)

    if len(context.args) < 2 or not context.args[-1].isdigit():
        return await update.message.reply_text("Uso: /card_subremove princesas 24311")

    cid = int(context.args[-1])
    name = " ".join(context.args[:-1]).strip()

    override_subcategory_remove_character(name, cid)
    await update.message.reply_text(f"✅ Personagem {cid} removido de {name}.")
