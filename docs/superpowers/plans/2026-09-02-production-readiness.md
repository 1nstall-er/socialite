# Socialite Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir Socialite en un servicio desplegable horizontalmente con configuración validada, Socket.IO coordinado por Redis, autenticación estricta por sesión, avatares en S3 y una imagen Docker operada por Gunicorn y Gevent.

**Architecture:** Flask conserva SQL como fuente de verdad y la sesión HTTP firmada como identidad. Redis funciona únicamente como broker de eventos Socket.IO. Los avatares nuevos se procesan en memoria, se almacenan en S3 y se sirven mediante una base HTTPS configurable; los nombres locales existentes siguen siendo legibles durante la transición. Cada contenedor ejecuta un único worker WebSocket y escala por réplicas con afinidad de sesión.

**Tech Stack:** Python 3.12, Flask 3.0.3, Flask-SocketIO 5.6.1, SQLAlchemy/Alembic, Redis 8.1.0, boto3 1.43.87, Gunicorn 26.2.0, Gevent 26.8.0, gevent-websocket 0.10.1, Pillow 11.3.0, `unittest`, Ruff y mypy.

**Spec:** `docs/superpowers/specs/2026-09-02-production-readiness-design.md`

## Global Constraints

- Trabajar únicamente en el worktree `.worktrees/production-ready` y en la rama `codex/production-ready`.
- Aplicar RED-GREEN-REFACTOR en cada comportamiento: escribir una prueba, observar el fallo esperado, implementar lo mínimo y volver a ejecutar.
- No iniciar conexiones reales a Redis, S3 ni SMTP durante las pruebas unitarias.
- No registrar secretos, URLs con credenciales, contenidos de imágenes ni tokens CSRF.
- No ejecutar migraciones automáticamente desde `Dockerfile`, `wsgi.py` o el comando web.
- Mantener compatibilidad de lectura con avatares locales legados, pero eliminar toda escritura local nueva.
- Después de cada tarea, ejecutar sus pruebas focalizadas y `ruff check` sobre los archivos tocados antes de crear el commit indicado.

---

## Task 1: Centralizar y validar la configuración de producción

**Files:**

- Create: `config.py`
- Create: `tests/test_production_config.py`
- Modify: `app.py:216-275`

- [x] **Step 1: Escribir las pruebas de configuración que deben fallar**

Crear `tests/test_production_config.py` con una base de configuración completa y casos explícitos para desarrollo, producción válida y cada grupo obligatorio:

```python
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from config import DEFAULT_SECRET_KEY, build_config, validate_production_config


class ProductionConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.production = {
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
        validate_production_config(config)

    def test_complete_production_configuration_is_accepted(self) -> None:
        validate_production_config(self.production)

    def test_production_rejects_missing_or_insecure_dependencies(self) -> None:
        invalid_cases = {
            "secret": {"SECRET_KEY": DEFAULT_SECRET_KEY},
            "database": {"SQLALCHEMY_DATABASE_URI": "sqlite:///socialite.db"},
            "smtp": {"MAIL_BACKEND": "console"},
            "redis": {"REDIS_URL": ""},
            "s3": {"AWS_S3_BUCKET": ""},
            "public_url": {"S3_PUBLIC_BASE_URL": "http://media.example.com"},
        }
        for name, override in invalid_cases.items():
            with self.subTest(name=name):
                config = {**self.production, **override}
                with self.assertRaisesRegex(RuntimeError, name):
                    validate_production_config(config)
```

- [x] **Step 2: Ejecutar la prueba y confirmar RED**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_production_config -v
```

Expected: `ModuleNotFoundError: No module named 'config'`.

- [x] **Step 3: Implementar el constructor y validador tipados**

Crear `config.py` con estas interfaces y reglas completas:

```python
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

DEFAULT_SECRET_KEY = "clave-local-socialite"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value == "1"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return default if raw is None else int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} debe ser un número entero") from error


def build_config(instance_path: str | Path) -> dict[str, object]:
    instance = Path(instance_path)
    local_database = (instance / "socialite.db").resolve().as_posix()
    return {
        "APP_ENV": os.getenv("APP_ENV", "development").lower(),
        "SECRET_KEY": os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY),
        "SQLALCHEMY_DATABASE_URI": os.getenv(
            "DATABASE_URL", f"sqlite:///{local_database}"
        ),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "CSRF_ENABLED": True,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _env_bool("COOKIE_SECURE", False),
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=12),
        "MAX_CONTENT_LENGTH": 6 * 1024 * 1024,
        "AVATAR_UPLOAD_FOLDER": os.getenv(
            "AVATAR_UPLOAD_FOLDER", str(instance / "avatares")
        ),
        "AUTO_CREATE_SCHEMA": _env_bool("AUTO_CREATE_SCHEMA", False),
        "SYNC_UPC_CATALOG": _env_bool("SYNC_UPC_CATALOG", True),
        "EMAIL_VERIFICATION_REQUIRED": _env_bool(
            "EMAIL_VERIFICATION_REQUIRED", True
        ),
        "MAIL_BACKEND": os.getenv("MAIL_BACKEND", "console"),
        "MAIL_SERVER": os.getenv("MAIL_SERVER", "localhost"),
        "MAIL_PORT": _env_int("MAIL_PORT", 587),
        "MAIL_USE_TLS": _env_bool("MAIL_USE_TLS", True),
        "MAIL_USE_SSL": _env_bool("MAIL_USE_SSL", False),
        "MAIL_USERNAME": os.getenv("MAIL_USERNAME"),
        "MAIL_PASSWORD": os.getenv("MAIL_PASSWORD"),
        "MAIL_DEFAULT_SENDER": os.getenv(
            "MAIL_DEFAULT_SENDER", "Socialite <no-reply@socialite.local>"
        ),
        "MAIL_TIMEOUT": _env_int("MAIL_TIMEOUT", 10),
        "LOGIN_MAX_FALLOS": _env_int("LOGIN_MAX_FALLOS", 3),
        "LOGIN_VENTANA_SEGUNDOS": _env_int("LOGIN_VENTANA_SEGUNDOS", 60),
        "REENVIO_VENTANA_SEGUNDOS": _env_int("REENVIO_VENTANA_SEGUNDOS", 60),
        "SOCKETIO_ASYNC_MODE": os.getenv("SOCKETIO_ASYNC_MODE", "threading"),
        "SOCKET_MESSAGE_MAX": _env_int("SOCKET_MESSAGE_MAX", 20),
        "SOCKET_MESSAGE_WINDOW_SECONDS": _env_int(
            "SOCKET_MESSAGE_WINDOW_SECONDS", 60
        ),
        "REDIS_URL": os.getenv("REDIS_URL"),
        "SOCKETIO_CHANNEL": os.getenv("SOCKETIO_CHANNEL", "socialite"),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "AWS_SESSION_TOKEN": os.getenv("AWS_SESSION_TOKEN"),
        "AWS_REGION": os.getenv("AWS_REGION"),
        "AWS_S3_BUCKET": os.getenv("AWS_S3_BUCKET"),
        "S3_PUBLIC_BASE_URL": os.getenv("S3_PUBLIC_BASE_URL"),
        "S3_AVATAR_PREFIX": os.getenv("S3_AVATAR_PREFIX", "avatars"),
    }


def validate_production_config(config: Mapping[str, object]) -> None:
    if config.get("APP_ENV") != "production":
        return
    errors: list[str] = []
    secret = str(config.get("SECRET_KEY") or "")
    database = str(config.get("SQLALCHEMY_DATABASE_URI") or "")
    mail_fields = ("MAIL_SERVER", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER")
    redis_url = str(config.get("REDIS_URL") or "")
    public_url = str(config.get("S3_PUBLIC_BASE_URL") or "")

    if not secret or secret == DEFAULT_SECRET_KEY:
        errors.append("secret")
    if not database or database.startswith("sqlite:"):
        errors.append("database")
    if str(config.get("MAIL_BACKEND") or "").lower() != "smtp" or not all(
        config.get(field) for field in mail_fields
    ):
        errors.append("smtp")
    parsed_redis = urlsplit(redis_url)
    if parsed_redis.scheme not in {"redis", "rediss"} or not parsed_redis.netloc:
        errors.append("redis")
    if not str(config.get("SOCKETIO_CHANNEL") or "").strip():
        errors.append("socket_channel")
    if not all(
        config.get(field)
        for field in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "AWS_S3_BUCKET",
        )
    ):
        errors.append("s3")
    parsed_public = urlsplit(public_url)
    if (
        parsed_public.scheme != "https"
        or not parsed_public.netloc
        or parsed_public.username
        or parsed_public.password
        or parsed_public.query
        or parsed_public.fragment
    ):
        errors.append("public_url")
    prefix = str(config.get("S3_AVATAR_PREFIX") or "")
    if len(prefix) > 128 or not re.fullmatch(
        r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix
    ):
        errors.append("avatar_prefix")
    if errors:
        raise RuntimeError(
            "Configuración de producción inválida: " + ", ".join(errors)
        )
```

La implementación final de `validate_production_config()` debe construir una lista de nombres (`secret`, `database`, `smtp`, `redis`, `socket_channel`, `s3`, `public_url`, `avatar_prefix`) y lanzar `RuntimeError("Configuración de producción inválida: " + ", ".join(errors))`. Solo se inspeccionan esquemas y presencia; nunca se incluyen valores sensibles en el mensaje.

- [x] **Step 4: Integrar la configuración en el factory**

En `app.py`, importar `build_config` y `validate_production_config`, reemplazar el bloque actual de `app.config.from_mapping` por:

```python
app.config.from_mapping(build_config(app.instance_path))
if test_config:
    app.config.update(test_config)
validate_production_config(app.config)
```

Eliminar las dos validaciones parciales que consultan `os.getenv("APP_ENV")`. Mantener `Path` porque la ruta de lectura de avatares legados todavía lo usa.

- [x] **Step 5: Ejecutar GREEN y regresión focalizada**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_production_config tests.test_app -v
& ..\..\.venv\Scripts\ruff.exe check config.py app.py tests/test_production_config.py
```

Expected: todas las pruebas pasan y Ruff termina con `All checks passed!`.

- [x] **Step 6: Commit**

```powershell
git add config.py app.py tests/test_production_config.py
git commit -m "refactor: validate production configuration"
```

---

## Task 2: Coordinar Socket.IO por Redis y autenticar cada evento

**Files:**

- Modify: `auth.py`
- Modify: `sockets.py`
- Modify: `tests/test_sockets.py`

- [x] **Step 1: Escribir pruebas RED para Redis e identidad revocada**

Agregar a `tests/test_sockets.py` imports de `Flask`, `patch` e `inicializar_socketio`, y estos comportamientos:

```python
def test_socketio_uses_configured_redis_queue_and_channel(self) -> None:
    probe = Flask("socket-config-test")
    probe.config.update(
        SOCKETIO_ASYNC_MODE="threading",
        REDIS_URL="redis://redis:6379/0",
        SOCKETIO_CHANNEL="socialite-test",
        SOCKET_MESSAGE_MAX=3,
        SOCKET_MESSAGE_WINDOW_SECONDS=60,
    )
    with patch.object(socketio, "init_app") as init_app:
        inicializar_socketio(probe)
    init_app.assert_called_once_with(
        probe,
        async_mode="threading",
        manage_session=True,
        cors_allowed_origins=None,
        max_http_buffer_size=16_384,
        message_queue="redis://redis:6379/0",
        channel="socialite-test",
    )

def test_protected_events_disconnect_when_session_identity_no_longer_exists(self) -> None:
    client = socketio.test_client(
        self.app,
        flask_test_client=self.ana_http,
        auth={"csrf_token": "csrf-ana"},
    )
    with self.app.app_context():
        db.session.delete(db.session.get(Usuario, self.ana_id))
        db.session.commit()
    response = client.emit(
        "join_room", {"contacto_id": self.bruno_id}, callback=True
    )
    self.assertEqual(response["error"]["codigo"], "no_autenticado")
    self.assertFalse(client.is_connected())

def test_socket_rejects_boolean_session_identity(self) -> None:
    boolean_http = self._cliente_http(True, "csrf-boolean")
    client = socketio.test_client(
        self.app,
        flask_test_client=boolean_http,
        auth={"csrf_token": "csrf-boolean"},
    )
    self.assertFalse(client.is_connected())
```

Añadir un test con `subTest` que conecte un cliente fresco, invalide la identidad y pruebe también `leave_room`, `send_message` y `mark_read`; cada handler debe producir `no_autenticado` y desconectar.

- [x] **Step 2: Ejecutar y confirmar RED**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_sockets -v
```

Expected: falla la aserción de argumentos porque `message_queue` y `channel` todavía no se pasan; también falla la identidad booleana porque Python considera `True` una instancia de `int` y el código actual puede resolverla como usuario 1.

- [x] **Step 3: Crear la resolución de identidad en `auth.py`**

Agregar, sin aceptar nunca un ID desde el payload del cliente:

```python
from hmac import compare_digest
from typing import Any

from flask import current_app, session

from models import Usuario, db


def resolver_identidad_socket(
    auth: Any = None, *, exigir_csrf: bool = False
) -> Usuario | None:
    usuario_id = session.get("usuario_id")
    if isinstance(usuario_id, bool) or not isinstance(usuario_id, int):
        return None
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        return None
    if current_app.config["EMAIL_VERIFICATION_REQUIRED"] and not usuario.correo_verificado:
        return None
    if exigir_csrf and current_app.config["CSRF_ENABLED"]:
        esperado = session.get("_csrf_token")
        recibido = auth.get("csrf_token") if isinstance(auth, dict) else None
        if not (
            isinstance(esperado, str)
            and isinstance(recibido, str)
            and compare_digest(esperado, recibido)
        ):
            return None
    return usuario
```

- [x] **Step 4: Aplicar un decorador único a todos los eventos protegidos**

En `sockets.py`, eliminar `_usuario_autenticado()` y `_csrf_valido()`. Implementar con `ParamSpec` y `Concatenate`:

```python
from functools import wraps
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar

from auth import resolver_identidad_socket

P = ParamSpec("P")
R = TypeVar("R")


def socket_authenticated(
    handler: Callable[Concatenate[Usuario, P], R],
) -> Callable[P, R | dict[str, Any]]:
    @wraps(handler)
    def protected(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]:
        usuario = resolver_identidad_socket()
        if usuario is None:
            return _sesion_invalida()
        return handler(usuario, *args, **kwargs)

    return protected
```

El `connect` debe invocar `resolver_identidad_socket(auth, exigir_csrf=True)` y devolver `False` antes de `join_room` si falla. Aplicar `@socket_authenticated` debajo de los decoradores `@socketio.on` de `entrar_sala`, `salir_sala`, `enviar_mensaje` y `marcar_leidos`; cada función recibe `usuario: Usuario` como primer argumento y deja de repetir la consulta manual.

- [x] **Step 5: Configurar Redis sin romper desarrollo**

Completar `inicializar_socketio()` así:

```python
socketio.init_app(
    app,
    async_mode=app.config["SOCKETIO_ASYNC_MODE"],
    manage_session=True,
    cors_allowed_origins=None,
    max_http_buffer_size=16_384,
    message_queue=app.config.get("REDIS_URL") or None,
    channel=app.config["SOCKETIO_CHANNEL"],
)
```

Redis permanece opcional fuera de producción y no debe contactarse durante `create_app()`.

- [x] **Step 6: Ejecutar GREEN y verificar tipado/estilo**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_sockets -v
& ..\..\.venv\Scripts\ruff.exe check auth.py sockets.py tests/test_sockets.py
& ..\..\.venv\Scripts\mypy.exe auth.py sockets.py --ignore-missing-imports --follow-imports=skip
```

Expected: pruebas verdes, Ruff sin errores y mypy sin errores en los módulos tipados.

- [x] **Step 7: Commit**

```powershell
git add auth.py sockets.py tests/test_sockets.py
git commit -m "feat: secure distributed socket gateway"
```

---

## Task 3: Reemplazar almacenamiento local por AWS S3 en memoria

**Files:**

- Rewrite: `media.py`
- Create: `tests/test_media_s3.py`
- Modify: `requirements.txt`

- [x] **Step 1: Añadir dependencias exactas**

Agregar a `requirements.txt`, en orden alfabético dentro de las dependencias de producción:

```text
boto3==1.43.87
redis==8.1.0
```

Instalarlas en el entorno compartido para poder ejecutar las pruebas:

```powershell
& ..\..\.venv\Scripts\python.exe -m pip install boto3==1.43.87 redis==8.1.0
```

- [x] **Step 2: Escribir pruebas RED contra un cliente S3 falso**

Crear `tests/test_media_s3.py`. El fake captura `upload_fileobj` y `delete_object` sin red:

```python
class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []
        self.deletes: list[dict[str, str]] = []

    def upload_fileobj(self, stream, bucket, key, ExtraArgs):
        self.uploads.append(
            {"bytes": stream.read(), "bucket": bucket, "key": key, "args": ExtraArgs}
        )

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)
```

Configurar una app Flask con `AWS_*`, `S3_PUBLIC_BASE_URL=https://media.example.com/assets` y `S3_AVATAR_PREFIX=avatars`. Parchear únicamente `media.boto3.client`. Cubrir:

```python
def test_upload_image_normalizes_and_uploads_jpeg_without_filesystem(self) -> None:
    public_url = upload_image(self.image_file())
    upload = self.s3.uploads[0]
    self.assertRegex(public_url, r"^https://media\.example\.com/assets/avatars/.+\.jpg$")
    self.assertEqual(upload["bucket"], "socialite-media")
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

def test_delete_image_only_deletes_owned_avatar_urls(self) -> None:
    owned = "https://media.example.com/assets/avatars/" + "a" * 32 + ".jpg"
    for ignored in (
        None,
        "legacy-avatar.jpg",
        "https://evil.example/avatars/" + "a" * 32 + ".jpg",
        "https://media.example.com/assets/other/" + "a" * 32 + ".jpg",
        "https://media.example.com/assets/avatars/../secret.jpg",
    ):
        delete_image(ignored)
    self.assertEqual(self.s3.deletes, [])
    delete_image(owned)
    self.assertEqual(
        self.s3.deletes,
        [{"Bucket": "socialite-media", "Key": "avatars/" + "a" * 32 + ".jpg"}],
    )
```

Conservar tests para archivo ausente, vacío, mayor de 5 MB, contenido falso, dimensión menor de 200 px y formatos no permitidos.

- [x] **Step 3: Ejecutar y confirmar RED**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_media_s3 -v
```

Expected: `ImportError` porque `upload_image` y `delete_image` todavía no existen.

- [x] **Step 4: Implementar `media.py` sin filesystem**

Mantener las constantes de validación y añadir:

```python
@dataclass(frozen=True, slots=True)
class S3Settings:
    access_key_id: str
    secret_access_key: str
    session_token: str | None
    region: str
    bucket: str
    public_base_url: str
    avatar_prefix: str

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "S3Settings":
        names = (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "AWS_S3_BUCKET",
            "S3_PUBLIC_BASE_URL",
            "S3_AVATAR_PREFIX",
        )
        values = {name: str(config.get(name) or "").strip() for name in names}
        if not all(values.values()):
            raise MediaStorageError("El almacenamiento de imágenes no está configurado.")
        public = urlsplit(values["S3_PUBLIC_BASE_URL"])
        prefix = values["S3_AVATAR_PREFIX"].strip("/")
        if (
            public.scheme != "https"
            or not public.netloc
            or public.username
            or public.password
            or public.query
            or public.fragment
            or len(prefix) > 128
            or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix)
        ):
            raise MediaStorageError("La configuración pública de imágenes no es válida.")
        return cls(
            access_key_id=values["AWS_ACCESS_KEY_ID"],
            secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
            session_token=str(config.get("AWS_SESSION_TOKEN") or "").strip() or None,
            region=values["AWS_REGION"],
            bucket=values["AWS_S3_BUCKET"],
            public_base_url=values["S3_PUBLIC_BASE_URL"].rstrip("/"),
            avatar_prefix=prefix,
        )


class MediaStorageError(RuntimeError):
    """Fallo remoto seguro para presentar sin filtrar credenciales."""


def upload_image(archivo: FileStorage | None) -> str:
    settings = S3Settings.from_config(current_app.config)
    stream = _normalize_avatar(archivo)
    key = f"{settings.avatar_prefix}/{secrets.token_urlsafe(24)}.jpg"
    client = _s3_client(settings)
    try:
        client.upload_fileobj(
            stream,
            settings.bucket,
            key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": "public, max-age=31536000, immutable",
                "ServerSideEncryption": "AES256",
            },
        )
    except (BotoCoreError, ClientError, S3UploadFailedError) as error:
        raise MediaStorageError(
            "No pudimos almacenar la foto. Intenta nuevamente."
        ) from error
    return f"{settings.public_base_url}/{quote(key, safe='/')}"


def delete_image(public_url: str | None) -> None:
    if not public_url:
        return
    settings = S3Settings.from_config(current_app.config)
    key = _owned_avatar_key(public_url, settings)
    if key is None:
        return
    try:
        _s3_client(settings).delete_object(Bucket=settings.bucket, Key=key)
    except (BotoCoreError, ClientError) as error:
        raise MediaStorageError(
            "No pudimos eliminar la foto remota."
        ) from error
```

Importar `boto3`, `current_app`, `dataclass`, `Mapping`, `quote`, `unquote`, `urlsplit`, `BotoCoreError`, `ClientError` y `S3UploadFailedError`. Extraer el procesamiento Pillow actual a `_normalize_avatar(archivo) -> BytesIO`; guardar JPEG en el buffer con `quality=88`, `optimize=True`, `progressive=True`, hacer `seek(0)` y no importar `os` ni `pathlib`. `_s3_client(settings)` debe pasar `region_name`, `aws_access_key_id`, `aws_secret_access_key` y, solo si existe, `aws_session_token` a `boto3.client("s3", **kwargs)`.

Para borrar, obtener la ruta relativa respecto a `S3_PUBLIC_BASE_URL`, aplicar `unquote`, rechazar segmentos ambiguos y exigir `fullmatch` de `<prefijo>/[A-Za-z0-9_-]{24,80}\.jpg` antes de llamar `delete_object`.

- [x] **Step 5: Ejecutar GREEN y verificar ausencia de escritura local**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_media_s3 -v
rg -n "from pathlib|^import os$|\.mkdir\(|\.unlink\(|os\.replace|builtins\.open" media.py
& ..\..\.venv\Scripts\ruff.exe check media.py tests/test_media_s3.py
& ..\..\.venv\Scripts\mypy.exe media.py --ignore-missing-imports --follow-imports=skip
```

Expected: pruebas verdes; `rg` no devuelve coincidencias; Ruff y mypy terminan correctamente.

- [x] **Step 6: Commit**

```powershell
git add media.py requirements.txt tests/test_media_s3.py
git commit -m "feat: store profile images in s3"
```

---

## Task 4: Integrar URLs remotas y compensación transaccional

**Files:**

- Modify: `models.py:565,663-698`
- Modify: `app.py:43,607-638,828-886`
- Modify: `tests/test_app.py`
- Create: `migrations/versions/9f8c2f0a64d1_widen_avatar_url.py`

- [x] **Step 1: Escribir pruebas RED del modelo y ciclo transaccional**

En `tests/test_app.py`, eliminar las aserciones de archivos nuevos en `TemporaryDirectory` y parchear el límite externo `app.upload_image`/`app.delete_image`. Agregar:

```python
def test_usuario_accepts_https_avatar_and_preserves_legacy_url(self) -> None:
    with self.app.app_context():
        remote = Usuario(
            nombre="Remota",
            correo_institucional="remota@upc.edu.pe",
            password_hash="hash",
            foto_archivo="https://media.example.com/avatars/" + "a" * 32 + ".jpg",
        )
        self.assertEqual(remote.foto_url, remote.foto_archivo)
        legacy = Usuario(
            nombre="Legada",
            correo_institucional="legada@upc.edu.pe",
            password_hash="hash",
            foto_archivo="a" * 32 + ".jpg",
        )
        self.assertEqual(legacy.foto_url, "/media/avatares/" + legacy.foto_archivo)

def test_registration_deletes_new_upload_when_database_commit_fails(self) -> None:
    remote = "https://media.example.com/avatars/" + "b" * 32 + ".jpg"
    with (
        patch("app.upload_image", return_value=remote),
        patch("app.delete_image") as delete_image,
        patch.object(db.session, "commit", side_effect=SQLAlchemyError("db down")),
    ):
        response = self.registrar()
    self.assertIn("No pudimos crear tu cuenta", response.get_data(as_text=True))
    delete_image.assert_called_once_with(remote)

def test_profile_deletes_previous_remote_avatar_only_after_commit(self) -> None:
    previous = "https://media.example.com/avatars/" + "c" * 32 + ".jpg"
    replacement = "https://media.example.com/avatars/" + "d" * 32 + ".jpg"
    with patch("app.upload_image", return_value=previous):
        self.registrar()
    events: list[str] = []
    original_commit = db.session.commit

    def upload(_file):
        events.append("upload")
        return replacement

    def commit():
        events.append("commit")
        return original_commit()

    def delete(url):
        self.assertEqual(url, previous)
        events.append("delete-old")

    with (
        patch("app.upload_image", side_effect=upload),
        patch("app.delete_image", side_effect=delete),
        patch.object(db.session, "commit", side_effect=commit),
    ):
        response = self.client.post(
            "/perfil",
            data={
                "nombre": "Ana Actualizada",
                "carrera": "Ingenieria de Software",
                "ciclo": "6",
                "foto": self.foto_prueba(formato="JPEG"),
            },
            follow_redirects=True,
        )
    self.assertIn("Perfil actualizado", response.get_data(as_text=True))
    self.assertEqual(events, ["upload", "commit", "delete-old"])
```

Añadir el caso simétrico de actualización fallida: SQL conserva la URL anterior y `delete_image` recibe únicamente la URL nueva como compensación.

- [x] **Step 2: Ejecutar y confirmar RED**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_app.SocialiteTestCase.test_usuario_accepts_https_avatar_and_preserves_legacy_url tests.test_app.SocialiteTestCase.test_registration_deletes_new_upload_when_database_commit_fails tests.test_app.SocialiteTestCase.test_profile_deletes_previous_remote_avatar_only_after_commit -v
```

Expected: el validador rechaza la URL HTTPS y `app.upload_image` todavía no existe.

- [x] **Step 3: Ampliar el modelo sin romper datos legados**

Cambiar `foto_archivo` a `db.String(500)`. El validador debe aceptar exactamente una de dos formas:

```python
legacy = re.fullmatch(r"[A-Za-z0-9_-]{24,80}\.jpg", value)
parsed = urlsplit(value)
remote = (
    parsed.scheme == "https"
    and bool(parsed.netloc)
    and not parsed.username
    and not parsed.password
    and not parsed.query
    and not parsed.fragment
    and len(value) <= 500
)
if not legacy and not remote:
    raise ValueError("La referencia del avatar no es válida")
```

`foto_url` devuelve directamente el valor HTTPS y conserva `/media/avatares/<nombre>` para el formato legado.

- [x] **Step 4: Integrar S3 en registro y perfil**

Reemplazar imports por `MediaStorageError`, `delete_image`, `upload_image`. En ambos flujos:

```python
foto_nueva: str | None = None
try:
    foto_nueva = upload_image(foto)
    usuario.foto_archivo = foto_nueva
    db.session.commit()
except ValueError as error:
    db.session.rollback()
    _delete_image_safely(foto_nueva)
    flash(str(error), "error")
except IntegrityError:
    db.session.rollback()
    _delete_image_safely(foto_nueva)
    flash("Ese correo ya está registrado.", "error")
except SQLAlchemyError:
    db.session.rollback()
    _delete_image_safely(foto_nueva)
    current_app.logger.exception("Fallo al confirmar la foto y el perfil")
    flash("No pudimos guardar los cambios. Intenta nuevamente.", "error")
except MediaStorageError as error:
    db.session.rollback()
    flash(str(error), "error")
else:
    if foto_nueva:
        _delete_image_safely(foto_anterior)
```

Definir `_delete_image_safely(url)` una sola vez: llama `delete_image`, captura `MediaStorageError` y registra solo una descripción fija más `exc_info=True`. En registro no hay avatar anterior. En perfil no cambiar la referencia anterior hasta que la nueva carga haya terminado.

- [x] **Step 5: Crear y validar la migración Alembic**

Crear `migrations/versions/9f8c2f0a64d1_widen_avatar_url.py` con `down_revision = "25a14c8b7795"` y:

```python
def upgrade():
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.alter_column(
            "foto_archivo",
            existing_type=sa.String(length=160),
            type_=sa.String(length=500),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.alter_column(
            "foto_archivo",
            existing_type=sa.String(length=500),
            type_=sa.String(length=160),
            existing_nullable=True,
        )
```

Validarla sobre una base temporal separada:

```powershell
$migrationDb = Join-Path $env:TEMP "socialite-migration-$([guid]::NewGuid()).db"
$env:DATABASE_URL = "sqlite:///$($migrationDb -replace '\\','/')"
& ..\..\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
& ..\..\.venv\Scripts\python.exe -m flask --app app:create_app db downgrade 25a14c8b7795
& ..\..\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
Remove-Item -LiteralPath $migrationDb -Force
Remove-Item Env:\DATABASE_URL
```

Expected: las tres operaciones Alembic terminan sin error y solo se elimina la base temporal resuelta.

- [x] **Step 6: Ejecutar GREEN y regresión**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_app tests.test_media_s3 -v
& ..\..\.venv\Scripts\ruff.exe check app.py models.py tests/test_app.py migrations/versions/9f8c2f0a64d1_widen_avatar_url.py
& ..\..\.venv\Scripts\mypy.exe media.py config.py --ignore-missing-imports --follow-imports=skip
```

Expected: todas las pruebas pasan; no queda ninguna llamada a `guardar_avatar` o `eliminar_avatar`.

- [x] **Step 7: Commit**

```powershell
git add app.py models.py tests/test_app.py migrations/versions/9f8c2f0a64d1_widen_avatar_url.py
git commit -m "feat: integrate transactional s3 avatars"
```

---

## Task 5: Empaquetar el servicio con Gunicorn y Gevent

**Files:**

- Create: `wsgi.py`
- Create: `gunicorn.conf.py`
- Create: `Procfile`
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `.env.example`
- Create: `docs/DEPLOYMENT.md`
- Create: `tests/test_deployment.py`
- Modify: `requirements.txt`
- Modify: `README.md`

- [x] **Step 1: Añadir las dependencias de proceso fijadas**

Agregar a `requirements.txt`:

```text
gevent==26.8.0
gevent-websocket==0.10.1
gunicorn[gevent]==26.2.0
packaging==26.3
psycopg[binary]==3.3.5
```

Instalarlas para pruebas locales de importación:

```powershell
& ..\..\.venv\Scripts\python.exe -m pip install gevent==26.8.0 gevent-websocket==0.10.1 "gunicorn[gevent]==26.2.0" packaging==26.3 "psycopg[binary]==3.3.5"
```

- [x] **Step 2: Escribir pruebas RED del entrypoint y configuración de proceso**

Crear `tests/test_deployment.py` que cargue `gunicorn.conf.py` mediante `runpy.run_path`, y valide comportamiento en lugar de buscar texto:

```python
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
            {"PORT": "9010", "GUNICORN_TIMEOUT": "75", "GUNICORN_LOG_LEVEL": "warning"},
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

    def test_wsgi_exports_flask_application_in_fresh_process(self) -> None:
        environment = {
            **os.environ,
            "APP_ENV": "development",
            "SOCKETIO_ASYNC_MODE": "threading",
            "SYNC_UPC_CATALOG": "0",
        }
        result = subprocess.run(
            [sys.executable, "-c", "from wsgi import application; print(application.name)"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "app")
```

- [x] **Step 3: Ejecutar y confirmar RED**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_deployment -v
```

Expected: `FileNotFoundError` para `gunicorn.conf.py` y fallo al importar `wsgi`.

- [x] **Step 4: Crear entrypoint y configuración Gunicorn**

Crear `wsgi.py` con monkey patch antes de importar la aplicación:

```python
from gevent import monkey

monkey.patch_all()

from app import create_app  # noqa: E402

application = create_app()
```

Crear `gunicorn.conf.py`:

```python
import os

bind = f"0.0.0.0:{int(os.getenv('PORT', '8000'))}"
workers = 1
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
accesslog = "-"
errorlog = "-"
capture_output = True
```

Crear `Procfile`:

```text
web: gunicorn --config gunicorn.conf.py wsgi:application
release: python -m flask --app app:create_app db upgrade
```

El proceso `release` es independiente del web; nunca encadenarlo en el arranque del contenedor.

- [x] **Step 5: Crear Dockerfile multi-stage y `.dockerignore`**

`Dockerfile` debe usar `python:3.12-slim`, construir wheels en `builder`, instalarlos con `--no-index` en runtime, copiar el proyecto con dueño no root, crear el usuario `socialite`, exponer 8000 y ejecutar:

```dockerfile
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:application"]
```

`.dockerignore` debe excluir `.git`, `.worktrees`, `.env`, `.env.*` salvo `.env.example`, `.venv`, `venv`, `instance`, `*.db`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `tests`, `docs` y archivos de cobertura.

- [x] **Step 6: Documentar entorno y operación**

Crear `.env.example` con todos los nombres de la especificación y marcadores no secretos. Crear `docs/DEPLOYMENT.md` con:

1. Provisionamiento de PostgreSQL, Redis y S3/CloudFront.
2. Política IAM mínima: `s3:PutObject` y `s3:DeleteObject` restringidos a `<bucket>/<prefix>/*`.
3. Carga de variables sin versionar `.env`.
4. Backup y release command de Alembic.
5. Despliegue inicial de una réplica y escalamiento posterior con sticky sessions.
6. Proxy con `Upgrade` y `Connection` para WebSocket.
7. Smoke test HTTP, handshake autenticado, mensaje y notificación.
8. Rollback de aplicación y advertencia de truncamiento antes de downgrade si existen URLs de más de 160 caracteres.

Actualizar `README.md` con un enlace a `docs/DEPLOYMENT.md` y separar claramente ejecución local (`python app.py`) de producción (`gunicorn --config gunicorn.conf.py wsgi:application`).

- [x] **Step 7: Ejecutar GREEN y validar el paquete**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m unittest tests.test_deployment -v
& ..\..\.venv\Scripts\python.exe -m compileall -q app.py auth.py config.py media.py models.py sockets.py wsgi.py gunicorn.conf.py
& ..\..\.venv\Scripts\ruff.exe check .
& ..\..\.venv\Scripts\mypy.exe config.py media.py auth.py sockets.py --ignore-missing-imports --follow-imports=skip
```

Expected: todas las verificaciones terminan con código 0.

Si Docker Desktop está disponible, ejecutar:

```powershell
docker version
docker build --tag socialite:production-ready .
docker image inspect socialite:production-ready --format '{{.Config.User}} {{json .Config.Cmd}}'
```

Expected: imagen construida; el usuario no es `root` ni vacío y el comando apunta a Gunicorn. Si el daemon no está disponible, registrar exactamente ese bloqueo sin sustituirlo por una afirmación de éxito.

- [x] **Step 8: Commit**

```powershell
git add requirements.txt wsgi.py gunicorn.conf.py Procfile Dockerfile .dockerignore .env.example docs/DEPLOYMENT.md tests/test_deployment.py README.md
git commit -m "build: add production deployment stack"
```

---

## Task 6: Verificación integral, revisión e integración

**Files:**

- Verify: all tracked project files
- Modify only if verification exposes a defect

- [ ] **Step 1: Ejecutar la puerta completa desde cero**

Run:

```powershell
& ..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
& ..\..\.venv\Scripts\python.exe -m unittest discover -s tests -v
& ..\..\.venv\Scripts\ruff.exe check .
& ..\..\.venv\Scripts\mypy.exe config.py media.py auth.py sockets.py --ignore-missing-imports --follow-imports=skip
& ..\..\.venv\Scripts\python.exe -m compileall -q .
git diff --check
git status --short
```

Expected: suite completa verde, análisis estático en código 0, compilación en código 0, `git diff --check` sin salida y worktree limpio después de cualquier commit correctivo.

- [ ] **Step 2: Revisar manualmente seguridad y operaciones**

Inspeccionar el diff completo y confirmar:

- Ningún secreto o credencial real está versionado.
- Ningún ID de usuario enviado por Socket.IO se usa como identidad.
- Todos los handlers mutables tienen `@socket_authenticated`.
- S3 solo borra URLs propias bajo el prefijo permitido.
- No hay escrituras nuevas a `AVATAR_UPLOAD_FOLDER`.
- Gunicorn tiene exactamente un worker por contenedor.
- Redis no sustituye la persistencia SQL.
- Docker no ejecuta migraciones al arrancar.

Si el usuario eligió explícitamente ejecución con subagentes, invocar la revisión independiente indicada por `requesting-code-review` antes de integrar. En ejecución inline, realizar la misma matriz de revisión manual sin crear un subagente.

- [ ] **Step 3: Smoke test local HTTP y Socket.IO**

Arrancar con servicios externos deshabilitados en desarrollo:

```powershell
$env:SOCKETIO_ASYNC_MODE = "threading"
$env:SYNC_UPC_CATALOG = "0"
& ..\..\.venv\Scripts\python.exe app.py
```

En otra terminal, ejecutar `Invoke-WebRequest http://127.0.0.1:5000/` y confirmar estado 200. Ejecutar las pruebas `tests.test_sockets` una vez más para handshake y mensajería autenticada. Detener el proceso con `Ctrl+C` y limpiar solo esas dos variables de entorno.

- [ ] **Step 4: Preparar migración local recuperable después de integrar**

Antes de aplicar la migración a la base real, resolver y mostrar la ruta exacta de `instance/socialite.db`. Si existe, copiarla a `instance/backups/socialite-pre-avatar-url-<timestamp>.db` mediante `Copy-Item -LiteralPath`; verificar que origen y destino estén dentro del checkout. Luego ejecutar:

```powershell
& .\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
```

No borrar el backup. Informar su ruta absoluta en la entrega.

- [ ] **Step 5: Integrar, verificar el SHA remoto y subir a GitHub**

Desde el checkout principal, integrar `codex/production-ready` sin sobrescribir cambios ajenos, volver a ejecutar la suite completa, y después:

```powershell
git push origin main
$local = git rev-parse HEAD
$remote = git ls-remote origin refs/heads/main | ForEach-Object { ($_ -split "`t")[0] }
if ($local -ne $remote) { throw "El SHA remoto no coincide con el local" }
```

Expected: push exitoso y SHA local/remoto idénticos. No declarar que GitHub está actualizado antes de esta comparación.
