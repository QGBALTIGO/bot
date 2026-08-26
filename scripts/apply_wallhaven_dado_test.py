from pathlib import Path

path = Path("webapp.py")
text = path.read_text(encoding="utf-8")
old = '''    char_id = int(char["id"])
    name = str(char["name"])
    image = str(char["image"] or char["anime_cover"] or DADO_BANNER_URL)
    anime_title = str(char["anime_title"] or "Anime")

    reward_caption = (
'''
new = '''    char_id = int(char["id"])
    name = str(char["name"])
    image = str(char["image"] or char["anime_cover"] or DADO_BANNER_URL)
    anime_title = str(char["anime_title"] or "Anime")

    try:
        from utils.character_image_resolver import resolve_character_portrait

        portrait = await resolve_character_portrait(
            character_id=char_id,
            character_name=name,
            anime_title=anime_title,
            fallback_url=image,
        )
        if portrait.url:
            image = portrait.url
        print(
            f"[dado-image] character={char_id} source={portrait.source} "
            f"size={portrait.width}x{portrait.height} cache={portrait.cache_hit}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[dado-image] resolver falhou character={char_id}: {type(exc).__name__}",
            flush=True,
        )

    reward_caption = (
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one Dado image marker, got {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
