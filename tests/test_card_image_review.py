from utils.card_image_review_rules import score_zerochan_post, zerochan_queries


def _post(tags, width=1600, height=2400):
    return {"tags": tags, "width": width, "height": height}


def test_candidate_requires_safe_high_quality_solo_fanart():
    assert score_zerochan_post(_post(["Fanart", "Solo", "Looking At Camera"])) is not None
    assert score_zerochan_post(_post(["Fanart", "Solo", "Bikini"])) is None
    assert score_zerochan_post(_post(["Official Art", "Solo"])) is None
    assert score_zerochan_post(_post(["Fanart", "Solo"], width=400, height=600)) is None
    assert score_zerochan_post(_post(["Fanart", "Solo", "Shirtless Male"])) is None
    assert score_zerochan_post(_post(["Fanart", "Solo", "Tongue"])) is None


def test_preferred_artist_and_action_score_higher():
    plain = score_zerochan_post(_post(["Fanart", "Solo"]))
    styled = score_zerochan_post(_post(["Fanart", "Solo", "Behindxa", "Glow", "Fight Stance"]))
    assert styled is not None and plain is not None and styled > plain


def test_zerochan_query_uses_family_name_first():
    assert zerochan_queries("Kakashi Hatake")[0] == "Hatake Kakashi"
    assert "Uchiha Sasuke" in zerochan_queries("Sasuke Uchiha")
