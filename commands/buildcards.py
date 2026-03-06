# =========================================================
# BUILD CARDS ASSETS (ANILIST)
# =========================================================

import json
import asyncio
import aiohttp

CARDS_FILE = "data/cards_assets.json"
CHAR_FILE = "data/personagens_anilist.txt"

ANILIST_API = "https://graphql.anilist.co"

CARDS_SLEEP = 2.5


def read_cards_source():

    animes = {}

    with open(CHAR_FILE, encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            parts = line.split("|")

            char_id = int(parts[0])
            char_name = parts[1]
            anime_name = parts[2]
            anime_id = int(parts[3])

            if anime_id not in animes:

                animes[anime_id] = {
                    "anime_id": anime_id,
                    "anime": anime_name,
                    "characters": []
                }

            animes[anime_id]["characters"].append({
                "id": char_id,
                "name": char_name
            })

    return list(animes.values())


async def fetch_anime_data(session, anime_id):

    query = """
    query ($id:Int){
      Media(id:$id,type:ANIME){
        id
        bannerImage
        coverImage{extraLarge}
        characters(page:1,perPage:50){
          edges{
            node{
              id
              name{full}
              image{large}
            }
          }
        }
      }
    }
    """

    async with session.post(
        ANILIST_API,
        json={"query": query, "variables": {"id": anime_id}}
    ) as r:

        if r.status == 429:
            raise Exception("RATE LIMIT")

        data = await r.json()

    media = data["data"]["Media"]

    chars = {}

    for edge in media["characters"]["edges"]:

        node = edge["node"]

        chars[node["id"]] = {
            "name": node["name"]["full"],
            "image": node["image"]["large"]
        }

    return {
        "banner": media["bannerImage"],
        "cover": media["coverImage"]["extraLarge"],
        "chars": chars
    }


async def build_cards_assets():

    source = read_cards_source()

    result = []

    async with aiohttp.ClientSession() as session:

        for i, anime in enumerate(source):

            anime_id = anime["anime_id"]

            print(f"[{i+1}/{len(source)}] {anime['anime']}")

            try:

                data = await fetch_anime_data(session, anime_id)

            except Exception:

                print("rate limit... aguardando")

                await asyncio.sleep(15)

                data = await fetch_anime_data(session, anime_id)

            characters = []

            for c in anime["characters"]:

                img = data["chars"].get(c["id"], {}).get("image", "")

                characters.append({
                    "id": c["id"],
                    "name": c["name"],
                    "image": img
                })

            result.append({

                "anime_id": anime_id,
                "anime": anime["anime"],
                "banner": data["banner"],
                "cover": data["cover"],
                "characters": characters

            })

            await asyncio.sleep(CARDS_SLEEP)

    with open(CARDS_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("cards_assets.json gerado")


# =========================================================
# COMANDO
# =========================================================

async def buildcards_command(update, context):

    if update.effective_user.id not in ADMIN_IDS:
        return

    await update.message.reply_text("⚙️ Gerando assets dos cards...")

    await build_cards_assets()

    await update.message.reply_text("✅ cards_assets.json criado com sucesso!")
