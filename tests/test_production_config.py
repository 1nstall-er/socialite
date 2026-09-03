import os
import unittest
from pathlib import Path
from unittest.mock import patch

from config import DEFAULT_SECRET_KEY, build_config, validate_production_config


class ProductionConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.production: dict[str, object] = {
            "APP_ENV": "production",
            "SECRET_KEY": "secret-production-value",
            "SQLALCHEMY_DATABASE_URI": "postgresql://socialite:pw@db/socialite",
            "MAIL_BACKEND": "smtp",
            "MAIL_SERVER": "smtp.example.com",
            "MAIL_USERNAME": "mailer",
            "MAIL_PASSWORD": "mailer-password",
            "MAIL_DEFAULT_SENDER": "Socialite <noreply@example.com>",
            "REDIS_URL": "rediss://redis.example.com:6380/0",
            "SOCKETIO_CHANNEL": "socialite",
            "AWS_ACCESS_KEY_ID": "access-key",
            "AWS_SECRET_ACCESS_KEY": "secret-key",
            "AWS_REGION": "us-east-1",
            "AWS_S3_BUCKET": "socialite-media",
            "S3_PUBLIC_BASE_URL": "https://media.example.com",
            "S3_AVATAR_PREFIX": "avatars",
        }

    def test_development_uses_safe_local_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = build_config(Path("instance"))

        self.assertEqual(config["APP_ENV"], "development")
        self.assertEqual(config["SECRET_KEY"], DEFAULT_SECRET_KEY)
        self.assertIsNone(config["REDIS_URL"])
        self.assertEqual(config["SOCKETIO_CHANNEL"], "socialite")
        self.assertEqual(config["S3_AVATAR_PREFIX"], "avatars")
        validate_production_config(config)

    def test_complete_production_configuration_is_accepted(self) -> None:
        validate_production_config(self.production)

    def test_production_rejects_missing_or_insecure_dependencies(self) -> None:
        invalid_cases: dict[str, dict[str, object]] = {
            "secret": {"SECRET_KEY": DEFAULT_SECRET_KEY},
            "database": {"SQLALCHEMY_DATABASE_URI": "sqlite:///socialite.db"},
            "smtp": {"MAIL_PASSWORD": ""},
            "redis": {"REDIS_URL": ""},
            "socket_channel": {"SOCKETIO_CHANNEL": ""},
            "s3": {"AWS_S3_BUCKET": ""},
            "public_url": {"S3_PUBLIC_BASE_URL": "http://media.example.com"},
            "avatar_prefix": {"S3_AVATAR_PREFIX": "avatars/../private"},
        }
        for name, override in invalid_cases.items():
            with self.subTest(name=name):
                config = {**self.production, **override}
                with self.assertRaisesRegex(RuntimeError, name):
                    validate_production_config(config)

    def test_production_error_never_echoes_secret_values(self) -> None:
        secret_value = "do-not-leak-this-value"
        config = {
            **self.production,
            "AWS_SECRET_ACCESS_KEY": secret_value,
            "S3_PUBLIC_BASE_URL": "https://user:password@media.example.com",
        }
        with self.assertRaises(RuntimeError) as raised:
            validate_production_config(config)
        self.assertNotIn(secret_value, str(raised.exception))
        self.assertNotIn("password", str(raised.exception))

    def test_malformed_public_endpoint_is_reported_as_configuration_error(self) -> None:
        config = {**self.production, "S3_PUBLIC_BASE_URL": "https://["}
        with self.assertRaisesRegex(RuntimeError, "public_url"):
            validate_production_config(config)

    def test_invalid_integer_environment_value_fails_fast(self) -> None:
        with (
            patch.dict(os.environ, {"MAIL_PORT": "not-an-integer"}, clear=True),
            self.assertRaisesRegex(RuntimeError, "MAIL_PORT"),
        ):
            build_config(Path("instance"))


if __name__ == "__main__":
    unittest.main()
