import os
import runpy
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class DeploymentTestCase(unittest.TestCase):
    def test_gunicorn_config_is_single_websocket_worker(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PORT": "9010",
                "GUNICORN_TIMEOUT": "75",
                "GUNICORN_LOG_LEVEL": "warning",
            },
            clear=False,
        ):
            config = runpy.run_path(str(ROOT / "gunicorn.conf.py"))

        self.assertEqual(config["bind"], "0.0.0.0:9010")
        self.assertEqual(config["workers"], 1)
        self.assertEqual(
            config["worker_class"],
            "geventwebsocket.gunicorn.workers.GeventWebSocketWorker",
        )
        self.assertEqual(config["timeout"], 75)
        self.assertEqual(config["loglevel"], "warning")
        self.assertEqual(config["accesslog"], "-")
        self.assertEqual(config["errorlog"], "-")

    def test_gunicorn_rejects_invalid_numeric_environment(self) -> None:
        with (
            patch.dict(os.environ, {"PORT": "not-a-port"}, clear=False),
            self.assertRaisesRegex(RuntimeError, "PORT"),
        ):
            runpy.run_path(str(ROOT / "gunicorn.conf.py"))

    def test_run_exports_flask_application_in_fresh_process(self) -> None:
        environment = {
            **os.environ,
            "APP_ENV": "development",
            "SOCKETIO_ASYNC_MODE": "threading",
            "SYNC_UPC_CATALOG": "0",
            "AUTO_CREATE_SCHEMA": "0",
            "DATABASE_URL": "sqlite:///:memory:",
            "REDIS_URL": "",
            "CORS_ALLOWED_ORIGINS": "",
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from run import app; print(app.name)",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "app")

    def test_migrations_and_seed_use_new_package_without_changing_schema(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "migration-test.db"
            environment = {
                **os.environ,
                "APP_ENV": "development",
                "SOCKETIO_ASYNC_MODE": "threading",
                "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                "AUTO_CREATE_SCHEMA": "0",
                "SYNC_UPC_CATALOG": "0",
                "REDIS_URL": "",
                "CORS_ALLOWED_ORIGINS": "",
            }
            for action in ("upgrade", "check"):
                result = subprocess.run(
                    [sys.executable, "-m", "flask", "--app", "app:create_app", "db", action],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            environment["SYNC_UPC_CATALOG"] = "1"
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, "seed.py"],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with closing(sqlite3.connect(database_path)) as connection:
                users = connection.execute(
                    "SELECT correo_institucional, password_hash, correo_verificado_en FROM usuarios"
                ).fetchall()
                self.assertEqual(len(users), 10)
                self.assertEqual(
                    {user[0] for user in users},
                    {f"test{number}@upc.edu.pe" for number in range(1, 11)},
                )
                self.assertTrue(all(user[1] != "123456" and user[2] for user in users))

    @unittest.skipIf(os.name == "nt", "Gunicorn solo se ejecuta en sistemas Unix")
    def test_websocket_worker_imports_with_runtime_dependencies(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from geventwebsocket.gunicorn.workers import "
                    "GeventWebSocketWorker; print(GeventWebSocketWorker.__name__)"
                ),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "GeventWebSocketWorker")


if __name__ == "__main__":
    unittest.main()
