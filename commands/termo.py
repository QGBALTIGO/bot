import json
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import (
    create_termo_game,
    get_termo_active_game,
    update_termo_game_progress,
    finish_termo_game,
    record_termo_result,
    get_termo_stats,
    get_termo_global_ranking,
    add_user_coins,
    add_progress_xp,
)

SP_TZ = ZoneInfo("America/Sao_Paulo")

WORD_SIZE = 6
MAX_ATTEMPTS = 6

WORDS_FILE = "data/anime_words_365.json"

WORDS = []
VALID_WORDS = set()

ACTIVE_GAMES = {}


def sp_today():
    return datetime.now(SP_TZ).date()


# =========================================================
# WORDS
# =========================================================

def load_words():

    global WORDS, VALID_WORDS

    if WORDS:
        return WORDS

    with open(WORDS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    seen = set()

    for row in data:

        w = row["word"].lower().strip()

        if len(w) != WORD_SIZE:
            continue

        if w in seen:
            continue

        seen.add(w)

        WORDS.append({
            "word": w,
            "category": row.get("category","Anime"),
            "source": row.get("source","Anime")
        })

    VALID_WORDS = {x["word"] for x in WORDS}

    return WORDS


def daily_word():

    words = load_words()

    seed = sp_today().isoformat()

    rng = random.Random(seed)

    return rng.choice(words)


def random_word():

    return random.choice(load_words())


# =========================================================
# WORDLE ENGINE
# =========================================================

def evaluate(secret, guess):

    result = ["⬛"] * WORD_SIZE

    secret_letters = {}
    guess = guess.lower()

    for i in range(WORD_SIZE):

        if guess[i] == secret[i]:
            result[i] = "🟩"
        else:
            secret_letters[secret[i]] = secret_letters.get(secret[i],0)+1

    for i in range(WORD_SIZE):

        if result[i] == "🟩":
            continue

        letter = guess[i]

        if letter in secret_letters and secret_letters[letter] > 0:
            result[i] = "🟨"
            secret_letters[letter] -= 1

    return "".join(result)


def keyboard_state(secret, guesses):

    state = {}

    for guess in guesses:

        result = evaluate(secret, guess)

        for i,letter in enumerate(guess):

            r = result[i]

            prev = state.get(letter)

            if prev == "🟩":
                continue

            if r == "🟩":
                state[letter] = "🟩"
            elif r == "🟨":
                if prev != "🟩":
                    state[letter] = "🟨"
            else:
                if letter not in state:
                    state[letter] = "⬛"

    return state


def render_keyboard(state):

    rows = [
        "QWERTYUIOP",
        "ASDFGHJKL",
        "ZXCVBNM"
    ]

    out = []

    for row in rows:

        line = []

        for c in row.lower():

            emoji = state.get(c,"⬜")

            line.append(emoji)

        out.append("".join(line))

    return "\n".join(out)


def grid(game):

    lines = []

    for g in game["guesses"]:
        lines.append(evaluate(game["word"], g) + " " + g.upper())

    return "\n".join(lines)


# =========================================================
# GAME
# =========================================================

def start_game(user_id, mode):

    if mode == "daily":
        word = daily_word()
    else:
        word = random_word()

    game = {
        "user": user_id,
        "word": word["word"],
        "category": word["category"],
        "source": word["source"],
        "mode": mode,
        "guesses": [],
        "start": int(time.time())
    }

    ACTIVE_GAMES[user_id] = game

    if mode == "daily":

        create_termo_game(
            user_id=user_id,
            game_date=sp_today(),
            word=word["word"],
            category=word["category"],
            source=word["source"],
            start_time=game["start"],
            mode="daily",
        )

    return game


# =========================================================
# COMMANDS
# =========================================================

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    if user in ACTIVE_GAMES:

        await update.message.reply_text(
            "🎮 Você já tem um jogo ativo.\n"
            "Envie sua tentativa."
        )
        return

    db_game = get_termo_active_game(user)

    if db_game:

        ACTIVE_GAMES[user] = {
            "user": user,
            "word": db_game["word"],
            "category": db_game["category"],
            "source": db_game["source"],
            "mode": db_game["mode"],
            "guesses": db_game["guesses"] or [],
            "start": db_game["start_time"]
        }

        await update.message.reply_text(
            "🎮 Continue seu jogo do dia!"
        )
        return

    start_game(user, "daily")

    await update.message.reply_text(
        "🎮 <b>TERMO ANIME</b>\n\n"
        "Adivinhe a palavra de <b>6 letras</b>.\n\n"
        "🟩 letra correta\n"
        "🟨 letra existe\n"
        "⬛ letra não existe\n\n"
        "Envie sua tentativa.",
        parse_mode="HTML"
    )


async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    start_game(user, "train")

    await update.message.reply_text(
        "🎯 <b>MODO TREINO</b>\n\n"
        "Nova palavra escolhida.\n"
        "Boa sorte!",
        parse_mode="HTML"
    )


# =========================================================
# GUESS
# =========================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    guess = update.message.text.lower().strip()

    if len(guess) != WORD_SIZE:
        return

    user = update.effective_user.id

    if user not in ACTIVE_GAMES:
        return

    if guess not in VALID_WORDS:
        return

    game = ACTIVE_GAMES[user]

    game["guesses"].append(guess)

    board = grid(game)

    kb = render_keyboard(
        keyboard_state(game["word"], game["guesses"])
    )

    if guess == game["word"]:

        if game["mode"] == "daily":

            add_user_coins(user, 10)
            add_progress_xp(user, 15)

            record_termo_result(user, True, len(game["guesses"]))

        ACTIVE_GAMES.pop(user)

        await update.message.reply_text(
            f"{board}\n\n"
            f"🎉 <b>VOCÊ ACERTOU!</b>\n"
            f"Palavra: <b>{game['word'].upper()}</b>\n\n"
            f"{kb}",
            parse_mode="HTML"
        )
        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:

        if game["mode"] == "daily":
            record_termo_result(user, False, MAX_ATTEMPTS)

        ACTIVE_GAMES.pop(user)

        await update.message.reply_text(
            f"{board}\n\n"
            f"💀 <b>Fim de jogo</b>\n"
            f"Palavra: <b>{game['word'].upper()}</b>\n\n"
            f"{kb}",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"{board}\n\n{kb}"
    )


# =========================================================
# STATS
# =========================================================

async def termo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    stats = get_termo_stats(user)

    if not stats:
        await update.message.reply_text("Sem estatísticas ainda.")
        return

    msg = (
        "📊 <b>ESTATÍSTICAS</b>\n\n"
        f"Jogos: {stats['games']}\n"
        f"Vitórias: {stats['wins']}\n"
        f"Derrotas: {stats['losses']}\n"
        f"Streak: {stats['streak']}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")


# =========================================================
# RANKING
# =========================================================

async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    ranking = get_termo_global_ranking()

    lines = []

    medals = ["🥇","🥈","🥉"]

    for i,row in enumerate(ranking[:10]):

        medal = medals[i] if i < 3 else "▫️"

        lines.append(
            f"{medal} {i+1}. {row['username']} — {row['wins']} vitórias"
        )

    await update.message.reply_text(
        "🏆 <b>RANKING TERMO</b>\n\n" + "\n".join(lines),
        parse_mode="HTML"
    )
