import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from utils.public_url import get_public_base_url
from utils.webapp_auth import validate_webapp_launch_token
from utils.webapp_url import build_webapp_url


BOT_TOKEN = "123456:TEST_TOKEN_FOR_UNIT_TESTS"


class WebAppUrlTests(unittest.TestCase):
    def test_explicit_base_url_wins_over_railway_fallback(self):
        with patch.dict(
            os.environ,
            {
                "BASE_URL": "https://stable.example.com",
                "RAILWAY_PUBLIC_DOMAIN": "new-production.up.railway.app",
            },
            clear=False,
        ):
            self.assertEqual(get_public_base_url(), "https://stable.example.com")

    def test_signed_url_preserves_query_and_fragment(self):
        with patch.dict(
            os.environ,
            {"BOT_TOKEN": BOT_TOKEN, "BASE_URL": "https://stable.example.com"},
            clear=False,
        ):
            url = build_webapp_url(
                "/hub?section=games#social",
                user_id=987654321,
                username="tester",
                full_name="Source Tester",
            )

        parts = urlsplit(url)
        query = parse_qs(parts.query)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "stable.example.com")
        self.assertEqual(parts.path, "/hub")
        self.assertEqual(parts.fragment, "social")
        self.assertEqual(query["section"], ["games"])
        self.assertEqual(query["uid"], ["987654321"])
        self.assertIn("launch", query)

        identity = validate_webapp_launch_token(
            query["launch"][0],
            BOT_TOKEN,
            max_age_seconds=60,
        )
        self.assertEqual(identity.user_id, 987654321)
        self.assertEqual(identity.username, "tester")


if __name__ == "__main__":
    unittest.main()
