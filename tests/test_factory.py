import json
import unittest
from pathlib import Path

from app import create_app
from app.models.entities import Usuario, db


class FactoryTestCase(unittest.TestCase):
    def make_app(self, **overrides):
        return create_app(
            {
                "TESTING": True,
                "APP_ENV": "development",
                "SECRET_KEY": "factory-test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SYNC_UPC_CATALOG": False,
                "SOCKETIO_ASYNC_MODE": "threading",
                "REDIS_URL": None,
                "CORS_ALLOWED_ORIGINS": [],
                **overrides,
            }
        )

    def test_public_routes_and_methods_are_preserved(self):
        app = self.make_app()
        fixture = Path(__file__).parent / "fixtures/routes_before_modular.json"
        expected = json.loads(fixture.read_text(encoding="utf-8"))
        actual = sorted(
            [
                [rule.rule, sorted(rule.methods - {"HEAD", "OPTIONS"})]
                for rule in app.url_map.iter_rules()
            ]
        )
        self.assertEqual(actual, expected)

    def test_factory_registers_blueprints_and_independent_databases(self):
        first = self.make_app()
        second = self.make_app()
        expected = {
            "auth",
            "pages",
            "profile",
            "companions",
            "groups",
            "messaging",
            "notifications",
            "connections",
            "safety",
        }
        self.assertEqual(set(first.blueprints), expected)
        self.assertEqual(set(second.blueprints), expected)
        with first.app_context():
            user = Usuario(nombre="Local", correo_institucional="local@upc.edu.pe")
            user.set_password("test-password")
            db.session.add(user)
            db.session.commit()
        with second.app_context():
            self.assertEqual(Usuario.query.count(), 0)
            self.assertTrue({"usuarios", "consentimientos"} <= set(db.metadata.tables))

    def test_cors_only_allows_explicit_api_origin(self):
        client = self.make_app(CORS_ALLOWED_ORIGINS=["https://frontend.example"]).test_client()
        headers = {"Origin": "https://frontend.example", "Access-Control-Request-Method": "GET"}
        response = client.options("/api/v1/catalogo-upc", headers=headers)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"), "https://frontend.example"
        )
        self.assertEqual(response.headers.get("Access-Control-Allow-Credentials"), "true")
        for route, origin in [
            ("/api/v1/catalogo-upc", "https://evil.example"),
            ("/ingresar", "https://frontend.example"),
        ]:
            response = client.options(route, headers={**headers, "Origin": origin})
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_cors_disabled_by_default_and_csrf_still_enforced(self):
        client = self.make_app().test_client()
        response = client.get("/api/v1/catalogo-upc", headers={"Origin": "https://other.example"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertEqual(client.post("/salir").status_code, 400)

    def test_wildcard_cors_is_rejected(self):
        for origins in (["*"], "*"):
            with self.subTest(origins=origins), self.assertRaises(ValueError):
                self.make_app(CORS_ALLOWED_ORIGINS=origins)

    def test_root_asset_and_migration_paths_do_not_move(self):
        app = self.make_app()
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(Path(app.instance_path), root / "instance")
        self.assertEqual(Path(app.static_folder), root / "static")
        self.assertEqual(Path(app.template_folder), root / "templates")
        self.assertEqual(Path(app.config["AVATAR_UPLOAD_FOLDER"]), root / "instance/avatares")
        self.assertEqual(Path(app.extensions["migrate"].directory), root / "migrations")


if __name__ == "__main__":
    unittest.main()
