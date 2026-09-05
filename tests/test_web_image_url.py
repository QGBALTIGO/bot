from __future__ import annotations

from urllib.parse import quote

from utils.web_image_url import web_image_url


def test_web_image_url_keeps_empty_data_and_existing_proxy_values() -> None:
    assert web_image_url("") == ""
    assert web_image_url(None) == ""
    assert web_image_url("data:image/png;base64,abc") == "data:image/png;base64,abc"
    assert web_image_url("/api/image-proxy?url=abc") == "/api/image-proxy?url=abc"


def test_web_image_url_keeps_direct_anilist_hosts() -> None:
    anilist = "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/test.jpg"
    anili = "https://img.anili.st/media/test.jpg"

    assert web_image_url(anilist) == anilist
    assert web_image_url(anili) == anili


def test_web_image_url_uses_portrait_crop_for_wallhaven() -> None:
    target = "https://w.wallhaven.cc/full/ab/wallhaven-abcd.jpg"
    assert web_image_url(target) == (
        "/api/image-proxy?crop=portrait&url=" + quote(target, safe="")
    )


def test_web_image_url_proxies_other_public_http_urls() -> None:
    target = "https://images.example.com/a b.jpg"
    assert web_image_url(target) == "/api/image-proxy?url=" + quote(target, safe="")


def test_web_image_url_leaves_non_http_values_unchanged() -> None:
    assert web_image_url("relative/image.jpg") == "relative/image.jpg"


def test_web_image_url_rebuilds_stale_absolute_proxy_as_current_relative_proxy() -> None:
    source = "https://cdn.donmai.us/original/approved.jpg"
    stale = (
        "https://old-bot.up.railway.app/api/image-proxy?crop=portrait&url="
        + quote(source, safe="")
    )
    assert web_image_url(stale) == (
        "/api/image-proxy?crop=portrait&url=" + quote(source, safe="")
    )
