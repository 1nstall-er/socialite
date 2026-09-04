# Socialite

Socialite es una app web para que estudiantes universitarios encuentren
companeros y creen grupos dentro del campus. El MVP esta enfocado en la UPC.

## Funciones disponibles

- Registro restringido al correo institucional `@upc.edu.pe`, con código de
  verificación de un solo uso, caducidad, límite de intentos y reenvío protegido.
- Foto obligatoria procesada completamente en memoria: valida el contenido,
  corrige la orientación, elimina metadatos, genera un avatar cuadrado y lo
  almacena cifrado en AWS S3, con almacenamiento local de prueba si no hay nube.
- Ingreso con contrasena almacenada de forma segura.
- Perfil academico con foto, presentación, carrera, ciclo, cursos, intereses y
  horas disponibles.
- Grupos sociales o de estudio con curso, horario, lugar y capacidad.
- Opcion para unirse o salir de un grupo.
- Matching transparente por cursos, horarios e intereses en comun.
- Matching contextual por campus, facultad, vida universitaria y metas por
  curso cuando ambos estudiantes completan esos datos.
- Grafo UPC implícito por campus y facultad, con conexiones de primer y segundo
  grado calculadas mediante BFS sin materializar relaciones cuadráticas.
- Top 10 exacto con max-heap en `O(n + k log n)`, sin ordenar todo el universo
  de candidatos.
- Catalogo verificado de bibliotecas, cubiculos y espacios UPC.
- Selectores interactivos para 59 carreras, ciclos validos por carrera y 50
  intereses predefinidos agrupados por categoria.
- Porcentaje por señal y probabilidad heuristica de emparejamiento ajustada por
  la cobertura real del perfil.
- Seguimiento de los cuatro creditos extraacademicos requeridos.
- Interfaz adaptable a computadoras y celulares.
- Búsqueda y filtros de compañeros, solicitudes de conexión accionables y una
  pantalla para administrar contactos.
- Bloqueo bidireccional efectivo sobre matching y conexiones, reportes privados
  con motivos controlados y estado de revisión.
- Chat privado uno a uno entre conexiones aceptadas, historial por cursor,
  mensajes no leídos e índices de conversación.
- Chat bidireccional con Flask-SocketIO, salas autorizadas, reconexión y
  fallback HTTP cuando el canal en tiempo real no está disponible.
- Notificaciones in-app persistentes con contador y alertas instantáneas en
  todas las pestañas conectadas del destinatario.
- Broker Redis para propagar salas, mensajes y notificaciones Socket.IO entre
  varias réplicas sin convertir Redis en la fuente de verdad del chat.
- Rate limiting thread-safe: tres fallos de login por IP y un reenvío de correo
  por minuto, además del cooldown persistido en base de datos.
- Migraciones versionadas con Alembic/Flask-Migrate para evolucionar la base sin
  borrar datos.

## Stack

- Flask 3
- Flask-SQLAlchemy
- Flask-SocketIO
- Redis para coordinación en tiempo real
- AWS S3/CloudFront para avatares
- Gunicorn con Gevent en producción
- Pillow para procesar imágenes sin confiar en la extensión del archivo
- SQLite en desarrollo
- HTML y CSS sin dependencias de frontend
- Python 3.11 o superior

## Arquitectura de backend

- `app/__init__.py`: Application Factory (`create_app`), sin rutas ni app global.
- `app/extensions.py`: instancias compartidas de SQLAlchemy, Migrate, SocketIO y CORS.
- `app/controllers/`: nueve Blueprints HTTP, validación de solicitudes y contratos
  Jinja2/JSON. `presenters.py` serializa; `contexts.py` compone las vistas.
- `app/services/`: matching puro, casos de uso de mensajería, correo e imágenes.
- `app/core/`: configuración, autenticación, verificación, hooks HTTP, sockets,
  rate limiting y política de privacidad.
- `app/models/`: entidades sociales, entidades de privacidad y consultas SQL
  reutilizables sin N+1.
- `run.py`: único punto de entrada del servidor local y de Gunicorn.
- `gunicorn.conf.py`: proceso WebSocket de producción.
- `migrations/`: historial de esquema existente, sin cambios por esta reorganización.

La distribución de responsabilidades, los imports y los pasos de migración están
documentados en `docs/ARCHITECTURE.md`.

Los contratos que debe consumir el frontend estan documentados en
`docs/JINJA_CONTEXT.md` y `docs/REALTIME.md`.

La configuración operativa, migraciones y rollout están documentados en
`docs/DEPLOYMENT.md`.

Los hechos institucionales, fuentes y decisiones de modelado se documentan en
`docs/UPC_DOMAIN.md`.

## Ejecutar en local

```powershell
git clone https://github.com/1nstall-er/socialite.git
cd socialite
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m flask --app app:create_app db upgrade
python run.py
```

La aplicacion queda disponible en `http://127.0.0.1:5000`.

En desarrollo, `MAIL_BACKEND=console` imprime el código de verificación en la
terminal donde corre Flask. Sin configuración de S3, las fotos de prueba se guardan
en `instance/avatares/` y se sirven mediante `/media/avatares/<nombre>`. No hace falta
contratar almacenamiento para registrar o editar perfiles en local. En producción
la validación de configuración sigue exigiendo S3.

Desde PowerShell, sin activar el entorno, también puedes arrancar con
`.\.venv\Scripts\python.exe run.py`. Para crear las cuentas de prueba, ejecuta
`.\.venv\Scripts\python.exe seed.py` exclusivamente en desarrollo.

Si ya tenías una base creada antes de incorporar Alembic, márcala una sola vez
con la revisión base y aplica el resto:

```powershell
python -m flask --app app:create_app db stamp 54cf41b8962b
python -m flask --app app:create_app db upgrade
```

Las cuentas existentes quedan marcadas como verificadas durante esa migración;
las nuevas deben confirmar el código recibido.

Para producción, parte de `.env.example`, usa el gestor de secretos del
proveedor y ejecuta el release command antes del proceso web. El despliegue
completo está en `docs/DEPLOYMENT.md`.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Para validar el tipado estricto del motor puro:

```powershell
pip install -r requirements-dev.txt
python -m mypy app/services/matching.py app/core/verification.py app/core/auth.py app/core/rate_limit.py app/services/media.py app/core/config.py app/core/sockets.py --ignore-missing-imports --follow-imports=skip
```

Para ejecutar el análisis estático del proyecto:

```powershell
python -m ruff check .
```

El ranking de compañeros conserva un orden exacto, pero mantiene en memoria
solo el prefijo necesario para la página solicitada. En las primeras páginas
reduce el ordenamiento de `O(n log n)` a `O(n log k)`, donde `k` es el último
resultado visible. El endpoint Top‑10 usa un max-heap: construye la cola en
`O(n)` y extrae únicamente los diez máximos en `O(k log n)`.

## Alcance pendiente

El despliegue debe aportar credenciales reales de SMTP, Redis, S3 y PostgreSQL.
Los rate limiters siguen siendo locales a cada réplica; una siguiente iteración
puede mover sus contadores a Redis sin cambiar las reglas de negocio actuales.
