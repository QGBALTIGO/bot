import os
import unittest
from unittest.mock import patch

from utils.public_character_image import (
    character_portrait_url,
    is_own_image_proxy_url,
    is_wallhaven_asset,
    public_origin,
)


class PublicCharacterImageTests(unittest.TestCase):
    def test_wallhaven_asset_detection(self):
        self.assertTrue(is_wallhaven_asset("https://w.wallhaven.cc/full/aa/wallhaven-test.jpg"))
        self.assertFalse(is_wallhaven_asset("https://wallhaven.cc/w/abc123"))
        self.assertFalse(is_wallhaven_asset("https://s4.anilist.co/example.jpg"))

    def test_custom_base_url_wins(self):
        with patch.dict(
            os.environ,
            {
                "BASE_URL": "https://bot.example.com/",
                "RAILWAY_PUBLIC_DOMAIN": "service-production.up.railway.app",
            },
            clear=False,
        ):
            self.assertEqual(public_origin(), "https://bot.example.com")

    def test_current_railway_domain_replaces_railway_generated_base(self):
        with patch.dict(
            os.environ,
            {
                "BASE_URL": "https://old-production.up.railway.app",
                "RAILWAY_PUBLIC_DOMAIN": "current-production.up.railway.app",
            },
            clear=False,
        ):
            self.assertEqual(public_origin(), "https://current-production.up.railway.app")

    def test_wallhaven_becomes_exact_portrait_proxy_url(self):
        source = "https://w.wallhaven.cc/full/2e/wallhaven-2ep9mg.jpg"
        with patch.dict(
            os.environ,
            {"BASE_URL": "https://bot.example.com", "RAILWAY_PUBLIC_DOMAIN": ""},
            clear=False,
        ):
            value = character_portrait_url(source)
            self.assertTrue(value.startswith("https://bot.example.com/api/image-proxy?crop=portrait&url="))
            self.assertTrue(is_own_image_proxy_url(value))

    def test_non_wallhaven_is_untouched(self):
        source = "https://s4.anilist.co/file/anilistcdn/character/large/test.png"
        with patch.dict(os.environ, {"BASE_URL": "https://bot.example.com"}, clear=False):
            self.assertEqual(character_portrait_url(source), source)


if __name__ == "__main__":
    unittest.main()
