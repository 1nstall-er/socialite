import os
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
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

    def test_wsgi_exports_flask_application_in_fresh_process(self) -> None:
        environment = {
            **os.environ,
            "APP_ENV": "development",
            "SOCKETIO_ASYNC_MODE": "threading",
            "SYNC_UPC_CATALOG": "0",
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from wsgi import application; print(application.name)",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "app")

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
