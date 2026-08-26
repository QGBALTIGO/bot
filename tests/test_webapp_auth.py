import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode

from utils.webapp_auth import (
    WebAppAuthError,
    create_webapp_launch_token,
    validate_telegram_init_data,
    validate_webapp_launch_token,
)


BOT_TOKEN = "123456:TEST_TOKEN_FOR_UNIT_TESTS"
NOW = 1_800_000_000


def build_init_data(*, user_id=123456789, auth_date=NOW, username="tester"):
    values = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Source",
                "last_name": "Tester",
                "username": username,
                "language_code": "pt-br",
            },
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    values["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)


class TelegramWebAppAuthTests(unittest.TestCase):
    def test_accepts_valid_signed_init_data(self):
        identity = validate_telegram_init_data(
            build_init_data(),
            BOT_TOKEN,
            now=NOW,
        )
        self.assertEqual(identity.user_id, 123456789)
        self.assertEqual(identity.username, "tester")
        self.assertEqual(identity.full_name, "Source Tester")

    def test_rejects_tampered_user_id(self):
        init_data = build_init_data().replace("123456789", "987654321")
        with self.assertRaises(WebAppAuthError):
            validate_telegram_init_data(init_data, BOT_TOKEN, now=NOW)

    def test_rejects_wrong_token(self):
        with self.assertRaises(WebAppAuthError):
            validate_telegram_init_data(
                build_init_data(),
                "999999:WRONG_TOKEN",
                now=NOW,
            )

    def test_rejects_expired_init_data(self):
        with self.assertRaises(WebAppAuthError):
            validate_telegram_init_data(
                build_init_data(auth_date=NOW - 7200),
                BOT_TOKEN,
                max_age_seconds=3600,
                now=NOW,
            )

    def test_rejects_missing_init_data(self):
        with self.assertRaises(WebAppAuthError):
            validate_telegram_init_data("", BOT_TOKEN, now=NOW)


class SignedLaunchTokenTests(unittest.TestCase):
    def test_accepts_valid_launch_token(self):
        token = create_webapp_launch_token(
            123456789,
            BOT_TOKEN,
            username="tester",
            full_name="Source Tester",
            now=NOW,
        )
        identity = validate_webapp_launch_token(token, BOT_TOKEN, now=NOW)
        self.assertEqual(identity.user_id, 123456789)
        self.assertEqual(identity.username, "tester")
        self.assertEqual(identity.full_name, "Source Tester")

    def test_rejects_tampered_launch_token(self):
        token = create_webapp_launch_token(123456789, BOT_TOKEN, now=NOW)
        payload, signature = token.split(".", 1)
        tampered = f"{payload[:-1]}A.{signature}"
        with self.assertRaises(WebAppAuthError):
            validate_webapp_launch_token(tampered, BOT_TOKEN, now=NOW)

    def test_rejects_launch_token_signed_by_another_bot(self):
        token = create_webapp_launch_token(123456789, BOT_TOKEN, now=NOW)
        with self.assertRaises(WebAppAuthError):
            validate_webapp_launch_token(token, "999999:WRONG_TOKEN", now=NOW)

    def test_rejects_expired_launch_token(self):
        token = create_webapp_launch_token(123456789, BOT_TOKEN, now=NOW - 7200)
        with self.assertRaises(WebAppAuthError):
            validate_webapp_launch_token(
                token,
                BOT_TOKEN,
                max_age_seconds=3600,
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
