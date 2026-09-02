# Socialite

Socialite es una app web para que estudiantes universitarios encuentren
companeros y creen grupos dentro del campus. El MVP esta enfocado en la UPC.

## Funciones disponibles

- Registro restringido al correo institucional `@upc.edu.pe`, con código de
  verificación de un solo uso, caducidad, límite de intentos y reenvío protegido.
- Foto obligatoria procesada por el servidor: valida el contenido, corrige la
  orientación, elimina metadatos y genera un avatar cuadrado optimizado.
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
- Rate limiting thread-safe: tres fallos de login por IP y un reenvío de correo
  por minuto, además del cooldown persistido en base de datos.
- Migraciones versionadas con Alembic/Flask-Migrate para evolucionar la base sin
  borrar datos.

## Stack

- Flask 3
- Flask-SQLAlchemy
- Pillow para procesar imágenes sin confiar en la extensión del archivo
- SQLite en desarrollo
- HTML y CSS sin dependencias de frontend
- Python 3.11 o superior

## Arquitectura de backend

- `app.py`: rutas, validacion, autorizacion y contratos de respuesta.
- `matching.py`: afinidad explicable, grafo UPC, BFS y max-heap Top‑K.
- `queries.py`: planes de carga reutilizables que evitan N+1 y productos
  cartesianos entre colecciones.
- `presenters.py`: contratos serializables para Jinja2 y JSON.
- `models.py`: entidades y relaciones persistentes.
- `media.py`: validación, normalización y almacenamiento privado de avatares.
- `verification.py`: reto criptográfico, expiración, intentos y reenvío.
- `rate_limit.py`: ventana deslizante acotada y sustituible por Redis.
- `mailer.py`: entrega transaccional por SMTP, consola local o memoria de prueba.
- `migrations/`: historial reproducible de cambios de esquema.

Los contratos que debe consumir el frontend estan documentados en
`docs/JINJA_CONTEXT.md`. Las rutas nuevas sin template responden JSON hasta que
se agregue la plantilla correspondiente, sin cambiar el contrato.

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
python app.py
```

La aplicacion queda disponible en `http://127.0.0.1:5000`.

En desarrollo, `MAIL_BACKEND=console` imprime el código de verificación en la
terminal donde corre Flask. Para enviar correos reales, copia `.env.example` a
`.env`, configura `MAIL_BACKEND=smtp` y completa las variables `MAIL_*` con tu
proveedor. En producción el backend SMTP y una `SECRET_KEY` propia son
obligatorios.

Si ya tenías una base creada antes de incorporar Alembic, márcala una sola vez
con la revisión base y aplica el resto:

```powershell
python -m flask --app app:create_app db stamp 54cf41b8962b
python -m flask --app app:create_app db upgrade
```

Las cuentas existentes quedan marcadas como verificadas durante esa migración;
las nuevas deben confirmar el código recibido.

Para produccion, configura las variables `SECRET_KEY`, `DATABASE_URL` y,
opcionalmente, `AVATAR_UPLOAD_FOLDER`. Por defecto las fotos viven en
`instance/avatares`, fuera de los archivos públicos de Flask.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Para validar el tipado estricto del motor puro:

```powershell
pip install -r requirements-dev.txt
python -m mypy --strict matching.py verification.py auth.py rate_limit.py media.py
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

El envío SMTP ya está listo, pero necesita las credenciales del proveedor de
correo del despliegue. El MVP todavía no incluye chat en tiempo real ni una app
nativa. La mensajería actual funciona con solicitudes HTTP y queda preparada
para incorporar WebSockets cuando se despliegue con infraestructura asíncrona.
