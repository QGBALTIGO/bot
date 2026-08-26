import os
import unittest
from unittest.mock import patch

from utils.public_url import get_public_base_url


class PublicUrlTests(unittest.TestCase):
    def test_custom_base_url_stays_authoritative(self):
        with patch.dict(
            os.environ,
            {
                "BASE_URL": "https://baltigo.example.com/",
                "RAILWAY_PUBLIC_DOMAIN": "new-service-production.up.railway.app",
            },
            clear=False,
        ):
            self.assertEqual(get_public_base_url(), "https://baltigo.example.com")

    def test_current_railway_domain_replaces_stale_railway_base_url(self):
        with patch.dict(
            os.environ,
            {
                "BASE_URL": "https://old-service-production.up.railway.app",
                "RAILWAY_PUBLIC_DOMAIN": "new-service-production.up.railway.app",
            },
            clear=False,
        ):
            self.assertEqual(
                get_public_base_url(),
                "https://new-service-production.up.railway.app",
            )

    def test_railway_domain_is_fallback_when_base_url_missing(self):
        with patch.dict(
            os.environ,
            {
                "BASE_URL": "",
                "RAILWAY_PUBLIC_DOMAIN": "service-production.up.railway.app",
            },
            clear=False,
        ):
            self.assertEqual(
                get_public_base_url(),
                "https://service-production.up.railway.app",
            )


if __name__ == "__main__":
    unittest.main()
