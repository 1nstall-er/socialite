"""Entrypoint WSGI de producción con monkey patch antes de importar Flask."""

from gevent import monkey

monkey.patch_all()

from app import create_app  # noqa: E402

application = create_app()
