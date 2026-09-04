"""Composición de la aplicación; las rutas viven en controllers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flask import Flask
from sqlalchemy import inspect

from app.core.config import build_config, cors_origin_patterns, validate_production_config
from app.extensions import cors, db, migrate


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        root_path=str(root),
        instance_path=str(root / "instance"),
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
        static_url_path="/static",
    )
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(build_config(app.instance_path))
    if test_config is not None:
        app.config.update(test_config)
    validate_production_config(app.config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from app.models import entities, privacy  # noqa: F401

    db.init_app(app)
    migrate.init_app(app, db, directory=str(root / "migrations"))

    origins = cors_origin_patterns(app.config["CORS_ALLOWED_ORIGINS"])
    if origins:
        cors.init_app(
            app,
            resources={r"/api/.*": {"origins": origins}},
            supports_credentials=True,
        )

    from app.controllers import register_blueprints
    from app.core.auth import crear_limitador_login
    from app.core.hooks import register_hooks
    from app.core.sockets import inicializar_socketio
    from app.core.verification import crear_limitador_reenvio

    app.extensions["login_rate_limiter"] = crear_limitador_login(
        app.config["LOGIN_MAX_FALLOS"], app.config["LOGIN_VENTANA_SEGUNDOS"]
    )
    app.extensions["verification_resend_rate_limiter"] = crear_limitador_reenvio(
        app.config["REENVIO_VENTANA_SEGUNDOS"]
    )
    inicializar_socketio(app)
    register_hooks(app)
    register_blueprints(app)

    with app.app_context():
        if app.config["TESTING"] or app.config["AUTO_CREATE_SCHEMA"]:
            db.create_all()
        tables = set(inspect(db.engine).get_table_names())
        if app.config["SYNC_UPC_CATALOG"] and {"espacios_upc", "carreras_upc"}.issubset(tables):
            entities.sincronizar_catalogo_upc()
    return app
