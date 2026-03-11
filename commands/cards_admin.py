import os
import re
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
from utils.runtime_guard import lock_manager, rate_limiter

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

ADMIN_RATE_LIMIT = int(os.getenv("ADMIN_RATE_LIMIT", "12"))
ADMIN_RATE_WINDOW_SECONDS = float(os.getenv("ADMIN_RATE_WINDOW_SECONDS", "10"))


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False

    if user.id in CARD_ADMIN_IDS:
        return True

    username = (user.username or "").strip().lower().lstrip("@")
    if username and username in CARD_ADMIN_USERNAMES:
        return True

    return False


def _extract_payload(update: Update, command_name: str) -> str:
    text = (update.effective_message.text or "").strip() if update.effective_message else ""
    if not text:
        return ""

    pattern = rf"^/{re.escape(command_name)}(?:@[\w_]+)?\s*"
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()


async def _reply(update: Update, text: str) -> None:
    msg = update.effective_message
    if msg:
        await msg.reply_text(text)


async def _deny(update: Update):
    await _reply(update, "❌ Você não tem permissão para usar esse comando.")


def _split_pipe(text: str):
    return [x.strip() for x in text.split("|")]


async def _allow_admin_command(update: Update, command_name: str) -> bool:
    user = update.effective_user
    if not user:
        return False

    if not _is_admin(update):
        await _deny(update)
        return False

    allowed = await rate_limiter.allow(
        key=f"admincmd:{user.id}",
        limit=ADMIN_RATE_LIMIT,
        window_seconds=ADMIN_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        await _reply(update, "⌛ Aguarde um instante antes de enviar mais comandos administrativos.")
        return False

    return True


async def card_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_reload"):
        return

    try:
        lock = await lock_manager.acquire("cards-admin:reload")
        try:
            reload_cards_cache()
        finally:
            lock.release()
        await _reply(update, "✅ Cache de cards recarregado.")
    except Exception as e:
        await _reply(update, f"❌ Erro no reload: {e}")


async def card_delchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_delchar"):
        return

    try:
        if not context.args or not context.args[0].isdigit():
            return await _reply(update, "Uso: /card_delchar 24311")

        cid = int(context.args[0])
        lock = await lock_manager.acquire(f"cards-admin:char:{cid}")
        try:
            override_delete_character(cid)
        finally:
            lock.release()
        await _reply(update, f"✅ Personagem {cid} apagado dos cards.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao apagar personagem: {e}")


async def card_addchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_addchar"):
        return

    try:
        raw = _extract_payload(update, "card_addchar")
        parts = _split_pipe(raw)

        if len(parts) != 5:
            return await _reply(
                update,
                "Uso:\n/card_addchar 999001 | Nome | 21366 | 3-gatsu no Lion | https://img.jpg",
            )

        if not parts[0].isdigit() or not parts[2].isdigit():
            return await _reply(update, "❌ character_id e anime_id precisam ser números.")

        cid = int(parts[0])
        name = parts[1]
        anime_id = int(parts[2])
        anime_name = parts[3]
        image = parts[4]

        lock = await lock_manager.acquire(f"cards-admin:char:{cid}")
        try:
            override_add_character(cid, name, anime_id, anime_name, image)
        finally:
            lock.release()
        await _reply(update, f"✅ Personagem {name} ({cid}) adicionado.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao adicionar personagem: {e}")


async def card_setcharimg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_setcharimg"):
        return

    try:
        if len(context.args) < 2 or not context.args[0].isdigit():
            return await _reply(update, "Uso: /card_setcharimg 24311 https://img.jpg")

        cid = int(context.args[0])
        url = context.args[1].strip()

        lock = await lock_manager.acquire(f"cards-admin:char:{cid}")
        try:
            override_set_character_image(cid, url)
        finally:
            lock.release()
        await _reply(update, f"✅ Imagem do personagem {cid} atualizada.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao trocar imagem: {e}")


async def card_setcharname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_setcharname"):
        return

    try:
        if len(context.args) < 2 or not context.args[0].isdigit():
            return await _reply(update, "Uso: /card_setcharname 24311 Novo Nome")

        cid = int(context.args[0])
        name = " ".join(context.args[1:]).strip()

        lock = await lock_manager.acquire(f"cards-admin:char:{cid}")
        try:
            override_set_character_name(cid, name)
        finally:
            lock.release()
        await _reply(update, f"✅ Nome do personagem {cid} atualizado para {name}.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao trocar nome: {e}")


async def card_delanime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_delanime"):
        return

    try:
        if not context.args or not context.args[0].isdigit():
            return await _reply(update, "Uso: /card_delanime 21366")

        aid = int(context.args[0])
        lock = await lock_manager.acquire(f"cards-admin:anime:{aid}")
        try:
            override_delete_anime(aid)
        finally:
            lock.release()
        await _reply(update, f"✅ Obra {aid} apagada dos cards.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao apagar obra: {e}")


async def card_addanime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_addanime"):
        return

    try:
        raw = _extract_payload(update, "card_addanime")
        parts = _split_pipe(raw)

        if len(parts) != 4:
            return await _reply(
                update,
                "Uso:\n/card_addanime 999999 | Minha Obra | https://banner.jpg | https://cover.jpg",
            )

        if not parts[0].isdigit():
            return await _reply(update, "❌ anime_id precisa ser número.")

        aid = int(parts[0])
        anime_name = parts[1]
        banner = parts[2]
        cover = parts[3]

        lock = await lock_manager.acquire(f"cards-admin:anime:{aid}")
        try:
            override_add_anime(aid, anime_name, banner, cover)
        finally:
            lock.release()
        await _reply(update, f"✅ Obra {anime_name} ({aid}) adicionada.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao adicionar obra: {e}")


async def card_setanimebanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_setanimebanner"):
        return

    try:
        if len(context.args) < 2 or not context.args[0].isdigit():
            return await _reply(update, "Uso: /card_setanimebanner 21366 https://banner.jpg")

        aid = int(context.args[0])
        url = context.args[1].strip()

        lock = await lock_manager.acquire(f"cards-admin:anime:{aid}")
        try:
            override_set_anime_banner(aid, url)
        finally:
            lock.release()
        await _reply(update, f"✅ Banner da obra {aid} atualizado.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao trocar banner: {e}")


async def card_setanimecover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_setanimecover"):
        return

    try:
        if len(context.args) < 2 or not context.args[0].isdigit():
            return await _reply(update, "Uso: /card_setanimecover 21366 https://cover.jpg")

        aid = int(context.args[0])
        url = context.args[1].strip()

        lock = await lock_manager.acquire(f"cards-admin:anime:{aid}")
        try:
            override_set_anime_cover(aid, url)
        finally:
            lock.release()
        await _reply(update, f"✅ Cover da obra {aid} atualizada.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao trocar cover: {e}")


async def card_addsubcat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_addsubcat"):
        return

    try:
        if not context.args:
            return await _reply(update, "Uso: /card_addsubcat princesas")

        name = " ".join(context.args).strip()
        lock = await lock_manager.acquire(f"cards-admin:subcat:{name.lower()}")
        try:
            override_add_subcategory(name)
        finally:
            lock.release()
        await _reply(update, f"✅ Subcategoria {name} criada.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao criar subcategoria: {e}")


async def card_delsubcat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_delsubcat"):
        return

    try:
        if not context.args:
            return await _reply(update, "Uso: /card_delsubcat princesas")

        name = " ".join(context.args).strip()
        lock = await lock_manager.acquire(f"cards-admin:subcat:{name.lower()}")
        try:
            override_delete_subcategory(name)
        finally:
            lock.release()
        await _reply(update, f"✅ Subcategoria {name} apagada.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao apagar subcategoria: {e}")


async def card_subadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_subadd"):
        return

    try:
        if len(context.args) < 2 or not context.args[-1].isdigit():
            return await _reply(update, "Uso: /card_subadd princesas 24311")

        cid = int(context.args[-1])
        name = " ".join(context.args[:-1]).strip()

        lock = await lock_manager.acquire(f"cards-admin:subcat:{name.lower()}")
        try:
            override_subcategory_add_character(name, cid)
        finally:
            lock.release()
        await _reply(update, f"✅ Personagem {cid} adicionado em {name}.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao adicionar na subcategoria: {e}")


async def card_subremove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "card_subremove"):
        return

    try:
        if len(context.args) < 2 or not context.args[-1].isdigit():
            return await _reply(update, "Uso: /card_subremove princesas 24311")

        cid = int(context.args[-1])
        name = " ".join(context.args[:-1]).strip()

        lock = await lock_manager.acquire(f"cards-admin:subcat:{name.lower()}")
        try:
            override_subcategory_remove_character(name, cid)
        finally:
            lock.release()
        await _reply(update, f"✅ Personagem {cid} removido de {name}.")
    except Exception as e:
        await _reply(update, f"❌ Erro ao remover da subcategoria: {e}")

import re
from typing import List, Tuple

from cards_service import (
    override_set_character_image,
    reload_cards_cache,
)

# =========================================================
# /setfoto
# - unitário: /setfoto ID LINK
# - lote via reply: responder msg com várias linhas "ID - LINK"
# =========================================================

_SETFOTO_MAX_BATCH = 50
_SETFOTO_LINE_RE = re.compile(
    r"^\s*(\d+)\s*(?:[-|]|)\s*(https?://\S+)\s*$",
    flags=re.IGNORECASE,
)

def _is_direct_image_url(url: str) -> bool:
    url = str(url or "").strip().lower()
    if not url.startswith(("http://", "https://")):
        return False

    base = url.split("?", 1)[0].split("#", 1)[0]
    return base.endswith((".jpg", ".jpeg", ".png", ".webp"))

def _parse_setfoto_lines(text: str) -> Tuple[List[Tuple[int, str]], List[str]]:
    items: List[Tuple[int, str]] = []
    errs: List[str] = []
    seen = set()

    for idx, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            continue

        m = _SETFOTO_LINE_RE.match(line)
        if not m:
            errs.append(f"Linha {idx}: formato inválido")
            continue

        try:
            cid = int(m.group(1))
        except Exception:
            errs.append(f"Linha {idx}: ID inválido")
            continue

        url = m.group(2).strip()

        if not _is_direct_image_url(url):
            errs.append(f"Linha {idx}: link inválido")
            continue

        if cid in seen:
            errs.append(f"Linha {idx}: ID duplicado ({cid})")
            continue

        seen.add(cid)
        items.append((cid, url))

    return items, errs


async def setfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _allow_admin_command(update, "setfoto"):
        return

    msg = update.effective_message
    if not msg:
        return

    try:
        # =====================================================
        # MODO 1: /setfoto ID LINK
        # =====================================================
        if len(context.args) >= 2 and str(context.args[0]).isdigit():
            cid = int(context.args[0])
            url = str(context.args[1]).strip()

            if not _is_direct_image_url(url):
                await _reply(
                    update,
                    "❌ Link inválido. Precisa terminar em .jpg, .jpeg, .png ou .webp",
                )
                return

            lock = await lock_manager.acquire(f"cards-admin:char:{cid}")
            try:
                override_set_character_image(cid, url)
                reload_cards_cache()
            finally:
                lock.release()

            await _reply(
                update,
                f"✅ Foto global do personagem {cid} atualizada.",
            )
            return

        # =====================================================
        # MODO 2: /setfoto respondendo uma mensagem com linhas
        # =====================================================
        reply = msg.reply_to_message
        if not context.args and reply:
            base_text = (reply.text or reply.caption or "").strip()

            if not base_text:
                await _reply(
                    update,
                    "❌ A mensagem respondida não tem texto para processar.",
                )
                return

            items, errs = _parse_setfoto_lines(base_text)

            if not items:
                detail = ""
                if errs:
                    detail = "\n" + "\n".join(f"• {e}" for e in errs[:15])

                await _reply(
                    update,
                    "❌ Não consegui ler nenhuma linha válida.\n\n"
                    "Use linhas assim:\n"
                    "12345 - https://site.com/img.jpg\n"
                    "12345 https://site.com/img.png"
                    + detail
                )
                return

            items = items[:_SETFOTO_MAX_BATCH]

            global_lock = await lock_manager.acquire("cards-admin:setfoto:batch")
            ok_count = 0
            fail_count = 0

            try:
                for cid, url in items:
                    try:
                        override_set_character_image(cid, url)
                        ok_count += 1
                    except Exception:
                        fail_count += 1

                reload_cards_cache()
            finally:
                global_lock.release()

            text = (
                "✅ Lote aplicado.\n\n"
                f"📌 Atualizados: {ok_count}\n"
                f"⚠️ Falhas: {fail_count}"
            )

            if errs:
                text += "\n\nLinhas ignoradas:\n" + "\n".join(f"• {e}" for e in errs[:15])

            await _reply(update, text)
            return

        # =====================================================
        # AJUDA
        # =====================================================
        await _reply(
            update,
            "🛠️ Admin — setar foto global\n\n"
            "1) Um personagem:\n"
            "/setfoto ID LINK\n"
            "Ex:\n"
            "/setfoto 12345 https://site.com/imagem.jpg\n\n"
            "2) Vários de uma vez:\n"
            "Responda uma mensagem com várias linhas:\n"
            "123 - https://site.com/a.jpg\n"
            "456 - https://site.com/b.png\n\n"
            "e envie apenas:\n"
            "/setfoto"
        )

    except Exception as e:
        await _reply(update, f"❌ Erro no /setfoto: {e}")
