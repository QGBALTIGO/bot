from utils.card_media_type import card_media_emoji, normalize_card_media_type


def test_anime_keeps_red_envelope_emoji():
    assert normalize_card_media_type("anime") == "anime"
    assert card_media_emoji({"media_type": "anime", "anime_id": 20}) == "🧧"


def test_movies_and_series_use_popcorn_emoji():
    assert card_media_emoji({"media_type": "movie"}) == "🍿"
    assert card_media_emoji({"media_type": "series"}) == "🍿"


def test_mcu_pilot_id_keeps_popcorn_during_metadata_migration():
    assert card_media_emoji({"anime_id": 900000001}) == "🍿"
