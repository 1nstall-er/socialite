import unittest
from io import BytesIO
from typing import Any
from unittest.mock import patch

from botocore.exceptions import ClientError
from flask import Flask
from PIL import Image
from werkzeug.datastructures import FileStorage

from media import MediaStorageError, delete_image, upload_image


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.deletes: list[dict[str, str]] = []
        self.upload_error: Exception | None = None
        self.delete_error: Exception | None = None

    def upload_fileobj(
        self,
        stream: BytesIO,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, str],
    ) -> None:
        if self.upload_error is not None:
            raise self.upload_error
        self.uploads.append(
            {
                "bytes": stream.read(),
                "bucket": bucket,
                "key": key,
                "args": ExtraArgs,
            }
        )

    def delete_object(self, **kwargs: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deletes.append(kwargs)


class MediaS3TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask("media-test")
        self.app.config.update(
            AWS_ACCESS_KEY_ID="access-key",
            AWS_SECRET_ACCESS_KEY="secret-key",
            AWS_SESSION_TOKEN="session-token",
            AWS_REGION="us-east-1",
            AWS_S3_BUCKET="socialite-media",
            S3_PUBLIC_BASE_URL="https://media.example.com/assets",
            S3_AVATAR_PREFIX="avatars",
        )
        self.s3 = FakeS3Client()
        self.boto_client = patch("media.boto3.client", return_value=self.s3)
        self.boto_client_mock = self.boto_client.start()
        self.addCleanup(self.boto_client.stop)

    @staticmethod
    def image_file(
        *,
        size: tuple[int, int] = (420, 300),
        image_format: str = "PNG",
    ) -> FileStorage:
        content = BytesIO()
        Image.new("RGB", size, (31, 107, 79)).save(content, image_format)
        content.seek(0)
        return FileStorage(stream=content, filename=f"profile.{image_format.lower()}")

    def test_upload_image_normalizes_and_uploads_jpeg_without_filesystem(self) -> None:
        with self.app.app_context(), patch(
            "builtins.open", side_effect=AssertionError("filesystem access")
        ):
            public_url = upload_image(self.image_file())

        upload = self.s3.uploads[0]
        self.assertRegex(
            public_url,
            r"^https://media\.example\.com/assets/avatars/[A-Za-z0-9_-]{32}\.jpg$",
        )
        self.assertEqual(upload["bucket"], "socialite-media")
        self.assertEqual(upload["key"], public_url.removeprefix("https://media.example.com/assets/"))
        self.assertEqual(
            upload["args"],
            {
                "ContentType": "image/jpeg",
                "CacheControl": "public, max-age=31536000, immutable",
                "ServerSideEncryption": "AES256",
            },
        )
        with Image.open(BytesIO(upload["bytes"])) as avatar:
            self.assertEqual(avatar.format, "JPEG")
            self.assertEqual(avatar.size, (640, 640))
        self.boto_client_mock.assert_called_once_with(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="access-key",
            aws_secret_access_key="secret-key",
            aws_session_token="session-token",
        )

    def test_upload_rejects_missing_empty_large_invalid_small_and_gif_files(self) -> None:
        invalid_cases = (
            (None, "Selecciona una foto"),
            (FileStorage(stream=BytesIO(), filename="empty.png"), "vacía"),
            (
                FileStorage(stream=BytesIO(b"x" * (5 * 1024 * 1024 + 1)), filename="big.png"),
                "máximo 5 MB",
            ),
            (FileStorage(stream=BytesIO(b"not-an-image"), filename="fake.jpg"), "imagen válida"),
            (self.image_file(size=(199, 300)), "al menos 200"),
            (self.image_file(image_format="GIF"), "JPG, PNG o WebP"),
        )
        with self.app.app_context():
            for uploaded_file, message in invalid_cases:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    upload_image(uploaded_file)
        self.assertEqual(self.s3.uploads, [])

    def test_delete_image_only_deletes_owned_avatar_urls(self) -> None:
        token = "a" * 32
        owned = f"https://media.example.com/assets/avatars/{token}.jpg"
        ignored = (
            None,
            "legacy-avatar.jpg",
            f"https://evil.example/assets/avatars/{token}.jpg",
            f"https://media.example.com/assets/other/{token}.jpg",
            "https://media.example.com/assets/avatars/../secret.jpg",
            f"https://media.example.com/assets/avatars%2F{token}.jpg",
            f"https://media.example.com/assets/avatars/{token}.jpg?version=1",
            "https://[",
        )

        with self.app.app_context():
            for public_url in ignored:
                delete_image(public_url)
            self.assertEqual(self.s3.deletes, [])
            delete_image(owned)

        self.assertEqual(
            self.s3.deletes,
            [{"Bucket": "socialite-media", "Key": f"avatars/{token}.jpg"}],
        )

    def test_storage_errors_are_translated_without_leaking_provider_details(self) -> None:
        provider_error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "provider-secret"}},
            "PutObject",
        )
        self.s3.upload_error = provider_error
        with self.app.app_context(), self.assertRaises(MediaStorageError) as raised:
            upload_image(self.image_file())
        self.assertNotIn("provider-secret", str(raised.exception))

        self.s3.upload_error = None
        self.s3.delete_error = provider_error
        owned = "https://media.example.com/assets/avatars/" + "b" * 32 + ".jpg"
        with self.app.app_context(), self.assertRaises(MediaStorageError) as raised:
            delete_image(owned)
        self.assertNotIn("provider-secret", str(raised.exception))

    def test_missing_or_insecure_s3_configuration_fails_before_client_creation(self) -> None:
        invalid_settings = (
            {"AWS_S3_BUCKET": ""},
            {"S3_PUBLIC_BASE_URL": "http://media.example.com"},
            {"S3_PUBLIC_BASE_URL": "https://["},
            {"S3_AVATAR_PREFIX": "avatars/../private"},
        )
        for override in invalid_settings:
            with self.subTest(override=override), self.app.app_context():
                original = {name: self.app.config.get(name) for name in override}
                self.app.config.update(override)
                try:
                    with self.assertRaises(MediaStorageError):
                        upload_image(self.image_file())
                finally:
                    self.app.config.update(original)
        self.boto_client_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
