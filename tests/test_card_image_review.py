from utils.card_image_review_rules import score_danbooru_post, score_zerochan_post, zerochan_queries


def _post(tags, width=1600, height=2400):
    return {"tags": tags, "width": width, "height": height}


def test_candidate_requires_safe_high_quality_solo_fanart():
    assert score_zerochan_post(_post(["Fanart", "Solo", "Looking At Camera"])) is not None
    assert score_zerochan_post(_post(["Fanart", "Solo", "Bikini"])) is None
    assert score_zerochan_post(_post(["Official Art", "Solo"])) is None
    assert score_zerochan_post(_post(["Fanart", "Solo"], width=400, height=600)) is None
    assert score_zerochan_post(_post(["Fanart", "Solo", "Shirtless Male"])) is None
    assert score_zerochan_post(_post(["Fanart", "Solo", "Tongue"])) is None
    assert score_zerochan_post(_post(["Fanart", "Solo"], width=1600, height=1200)) is None


def test_preferred_artist_and_action_score_higher():
    plain = score_zerochan_post(_post(["Fanart", "Solo"]))
    styled = score_zerochan_post(_post(["Fanart", "Solo", "Behindxa", "Glow", "Fight Stance"]))
    assert styled is not None and plain is not None and styled > plain


def test_zerochan_query_uses_family_name_first():
    assert zerochan_queries("Kakashi Hatake")[0] == "Hatake Kakashi"
    assert "Uchiha Sasuke" in zerochan_queries("Sasuke Uchiha")
    assert zerochan_queries("Anko Mitarashi")[0] == "Mitarashi Anko"


def test_danbooru_candidate_requires_general_rating_and_portrait():
    post = {
        "rating": "g",
        "tag_string_general": "solo looking_at_viewer",
        "tag_string_character": "uzumaki_naruto",
        "tag_string_meta": "",
        "image_width": 1200,
        "image_height": 1800,
        "score": 100,
        "fav_count": 25,
    }
    assert score_danbooru_post(post) is not None
    assert score_danbooru_post({**post, "rating": "s"}) is None
    assert score_danbooru_post({**post, "tag_string_general": "solo bikini"}) is None
