# Arquitectura modular de Socialite

La reorganización conserva las URLs, métodos HTTP, contratos de Jinja2/JSON,
eventos Socket.IO y esquema SQL. No introduce una API diferente ni modifica el
algoritmo de matching. Es una arquitectura Flask por capas; no impone un dominio
completamente independiente del ORM a los casos de uso que ya usan SQLAlchemy.

## Estructura

```text
app/
  __init__.py             # create_app(config): composición y registro
  extensions.py           # db, migrate, socketio, cors sin app ligada al importar
  controllers/
    __init__.py           # registro explícito de Blueprints
    auth.py               # registro, ingreso y verificación HTTP
    pages.py              # inicio y panel
    profile.py            # perfil, catálogo, cursos, horarios y avatares
    companions.py         # compañeros, Top 10 y perfil público
    groups.py             # grupos y membresías
    messaging.py          # bandeja y conversación HTTP
    notifications.py      # notificaciones y lectura
    connections.py        # solicitudes de conexión
    safety.py             # bloqueos y reportes
    common.py             # validación HTTP y helpers de respuesta
    contexts.py           # composición de contextos Jinja2/JSON
    presenters.py         # serialización de los contratos
  services/
    matching.py           # algoritmo puro, sin Flask ni SQLAlchemy
    messaging.py          # autorización y transacción compartida por HTTP/socket
    mailer.py             # entrega de correos
    media.py              # normalización y persistencia de avatares
  core/
    auth.py               # identidad y decorador login_required
    config.py             # entorno y validación de producción
    hooks.py              # usuario actual, CSRF, headers y manejo de 413
    sockets.py            # eventos autenticados y broker Redis
    rate_limit.py         # limitadores
    verification.py       # retos de verificación
    privacy_policy.py     # reglas puras de privacidad
  models/
    entities.py           # modelos sociales y catálogo UPC
    privacy.py            # evidencia de privacidad
    queries.py            # consultas y planes de carga
run.py                    # entrada local / Gunicorn run:app
seed.py                   # utilidad CLI; no inicia el servidor
templates/ static/ instance/ migrations/ tests/
```

## Reglas de dependencias

- Las rutas importan servicios y consultas; no crean extensiones ni importan `run`.
- Los servicios no importan controladores. HTTP y sockets usan el mismo caso de
  uso de mensajes; el motor de matching recibe datos, no el objeto Flask.
- Los modelos importan `db` desde `app.extensions`. Solo la fábrica llama
  `init_app`, registra Blueprints y hooks y decide cuándo sincronizar el catálogo.
- El estado por aplicación (configuración y rate limiters) se consulta mediante
  `current_app`; no se captura una app concreta dentro de las rutas.
- `app.models.entities` y `app.models.privacy` se cargan antes de registrar
  migraciones o crear tablas de prueba. La metadata incluye todos los modelos.

Imports canónicos:

```python
from app import create_app
from app.extensions import db, socketio
from app.models.entities import Usuario
from app.services.matching import calcular_afinidad
```

## Migración aplicada, paso a paso

1. Crear una rama y respaldar SQLite usando su API de backup.
2. Capturar las 49 rutas/métodos en `tests/fixtures/routes_before_modular.json`.
3. Mover modelos, consultas, servicios y seguridad a sus paquetes y actualizar
   imports de la aplicación, pruebas y `seed.py`.
4. Extraer las 48 vistas en nueve Blueprints, conservando sus decoradores de
   autorización y separando hooks, contextos y validadores compartidos.
5. Actualizar los `url_for` de Python y Jinja2: por ejemplo, `auth.ingresar`,
   `profile.perfil`, `companions.companeros`, `messaging.conversacion`.
   Los enlaces públicos (`/ingresar`, `/perfil`, etc.) no cambian.
6. Centralizar extensiones y construir la fábrica; configurar explícitamente
   las carpetas raíz de templates, static, instance y migraciones.
7. Reemplazar `app.py` y `wsgi.py` por `run.py`; actualizar Dockerfile y Procfile.
8. Verificar regresiones, almacenamiento local, migraciones en una base temporal
   y arranque antes de integrar la rama.

No hay wrappers de compatibilidad para imports antiguos: scripts externos deben
usar los imports canónicos. No ejecutes de nuevo comandos para mover archivos;
la distribución ya está aplicada en el repositorio.

## Datos y configuración conservados

- SQLite sigue en `instance/socialite.db`; los avatares siguen en
  `instance/avatares/` por defecto (`AVATAR_UPLOAD_FOLDER` en config).
- Las fotos locales se almacenan como nombres seguros en `foto_archivo`, no
  como rutas absolutas. `foto_url` conserva `/media/avatares/<nombre>`.
- No se añade ninguna revisión Alembic por mover código. Las migraciones siguen
  siendo un release command separado, no se ejecutan al iniciar el servidor.
- `CORS_ALLOWED_ORIGINS` es la única variable nueva: vacía por defecto,
  lista explícita separada por comas si se necesita otro origen para `/api/*`.
  No cambia las cookies, CSRF ni los orígenes admitidos por Socket.IO.

## Comandos desde la raíz (PowerShell)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m flask --app app:create_app db current
.\.venv\Scripts\python.exe run.py
```

Las bases nuevas se preparan con `python -m flask --app app:create_app db upgrade`.
Para producción usa `gunicorn --config gunicorn.conf.py run:app`, un worker
WebSocket por réplica y Redis como coordinación entre réplicas.
