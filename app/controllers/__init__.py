"""Registro explícito de adaptadores HTTP."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .auth import bp as auth_bp
    from .companions import bp as companions_bp
    from .connections import bp as connections_bp
    from .groups import bp as groups_bp
    from .messaging import bp as messaging_bp
    from .notifications import bp as notifications_bp
    from .pages import bp as pages_bp
    from .profile import bp as profile_bp
    from .safety import bp as safety_bp

    for blueprint in (
        auth_bp,
        pages_bp,
        profile_bp,
        companions_bp,
        groups_bp,
        messaging_bp,
        notifications_bp,
        connections_bp,
        safety_bp,
    ):
        app.register_blueprint(blueprint)
