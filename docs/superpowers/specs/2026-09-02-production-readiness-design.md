# Socialite Production Readiness Design

**Fecha:** 2026-09-02

**Estado:** Documento revisado y aprobado por el usuario.

## Objetivo

Preparar Socialite para un despliegue horizontal seguro: coordinar Socket.IO
entre réplicas con Redis, bloquear conexiones anónimas en el handshake y en
cada evento, reemplazar las escrituras locales de avatares por AWS S3 y
entregar una imagen Docker ejecutable con Gunicorn y Gevent.

## Decisiones principales

- AWS S3 es el almacenamiento de imágenes. `S3_PUBLIC_BASE_URL` permite servir
  desde CloudFront sin hacer público el bucket.
- Redis es el broker de Socket.IO. Los mensajes y notificaciones continúan en
  SQL; Redis no es la fuente de verdad del chat.
- La autenticación sigue usando la sesión HTTP firmada de Flask. No se añade
  JWT porque el producto no dispone de un flujo JWT y operar dos identidades
  aumentaría la superficie de ataque.
- Gevent reemplaza a Eventlet porque Eventlet ya no recibe mantenimiento
  activo. Cada contenedor ejecuta un solo worker WebSocket; el escalamiento se
  realiza con varias réplicas detrás de un balanceador con afinidad de sesión.
- Desarrollo y pruebas pueden funcionar sin servicios externos. En
  `APP_ENV=production`, Redis, base de datos, secretos, correo y S3 son
  obligatorios y el proceso falla antes de aceptar tráfico si falta alguno.

## Configuración

Un nuevo `config.py` construirá y validará la configuración. `create_app()`
seguirá aceptando `test_config` para pruebas, pero las variables de producción
se comprobarán después de combinar la configuración final.

Variables obligatorias en producción:

- `APP_ENV=production`
- `SECRET_KEY`: secreto propio, no el valor local predeterminado.
- `DATABASE_URL`: base persistente; SQLite no se acepta en producción.
- `MAIL_BACKEND=smtp` y las variables SMTP ya existentes.
- `REDIS_URL`: URL TLS o privada utilizada por Socket.IO.
- `SOCKETIO_CHANNEL`: canal dedicado; valor recomendado `socialite`.
- `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`.
- `AWS_REGION`.
- `AWS_S3_BUCKET`.
- `S3_PUBLIC_BASE_URL`: origen HTTPS de CloudFront o del bucket servido.
- `S3_AVATAR_PREFIX`: prefijo aislado; valor predeterminado `avatars`.

Variables de proceso:

- `PORT`: puerto HTTP, predeterminado `8000`.
- `GUNICORN_TIMEOUT`: predeterminado `60` segundos.
- `GUNICORN_LOG_LEVEL`: predeterminado `info`.
- `AWS_SESSION_TOKEN`: opcional para credenciales temporales.

Los valores sensibles nunca se escribirán en logs, Dockerfile ni archivos
versionados. `.env.example` contendrá únicamente marcadores seguros.

## Socket.IO y Redis

`inicializar_socketio(app)` pasará `REDIS_URL` como `message_queue` y
`SOCKETIO_CHANNEL` como `channel`. Sin Redis, desarrollo y pruebas utilizarán
el administrador local actual. Producción rechazará el arranque sin Redis.

La política CORS seguirá siendo same-origin. El proxy de producción deberá
reenviar `Upgrade` y `Connection` y mantener afinidad de sesión. Una réplica
Gunicorn tendrá exactamente un `GeventWebSocketWorker`; varias réplicas se
coordinan mediante Redis.

Redis transporta eventos y administración de salas, no historiales. La caída
temporal de Redis puede degradar el canal en tiempo real, pero no corrompe los
mensajes ya confirmados en SQL.

## Autenticación estricta de sockets

`auth.py` expondrá una función tipada que resuelve una identidad de socket desde
la sesión HTTP. Comprobará:

1. `session["usuario_id"]` es un entero válido.
2. El usuario todavía existe.
3. El correo está verificado cuando la política lo exige.
4. El token CSRF del payload `auth` coincide mediante comparación constante.

El handler `connect` invocará esta función y devolverá `False` ante cualquier
fallo, antes de unir al cliente a una sala. No se aceptará un identificador de
usuario suministrado por el navegador.

Un decorador `socket_authenticated` protegerá los eventos `join_room`,
`leave_room`, `send_message` y `mark_read`. El decorador resolverá nuevamente
la identidad antes de ejecutar la función y desconectará sockets cuya sesión
ya no sea válida. Las reglas de conexión aceptada y bloqueo continuarán
evaluándose en cada operación.

## Almacenamiento S3

`media.py` conservará la defensa actual de Pillow: límite de 5 MB, detección
por contenido, protección contra bombas de descompresión, orientación EXIF,
recorte cuadrado y recodificación sin metadatos. Todo el procesamiento ocurrirá
en `BytesIO`; no se crearán carpetas ni archivos temporales locales.

La interfaz pública será:

```python
def upload_image(archivo: FileStorage | None) -> str: ...
def delete_image(public_url: str | None) -> None: ...
```

`upload_image()` generará una clave impredecible bajo
`<S3_AVATAR_PREFIX>/<token>.jpg`, enviará bytes JPEG con `ContentType`,
`CacheControl` y cifrado de servidor, y devolverá una URL HTTPS construida con
`S3_PUBLIC_BASE_URL`.

`delete_image()` solo extraerá claves de URLs que comiencen exactamente con la
base pública configurada y cuyo path pertenezca al prefijo de avatares. URLs
ajenas, rutas ambiguas o valores legados no generarán una eliminación S3.

El campo legado `usuarios.foto_archivo` se ampliará a 500 caracteres y pasará
a almacenar la URL retornada. Su propiedad `foto_url` devolverá directamente
URLs HTTPS. Para no romper los datos locales existentes, nombres `.jpg`
legados seguirán teniendo lectura temporal mediante la ruta autenticada actual;
ningún flujo nuevo escribirá o borrará archivos locales.

## Consistencia entre S3 y SQL

En registro o reemplazo de foto:

1. Se sube la imagen nueva a S3.
2. Se intenta confirmar la transacción SQL con la URL nueva.
3. Si SQL falla, se elimina la nueva imagen de S3 como compensación.
4. Si SQL confirma, se elimina de S3 la imagen remota anterior.

La eliminación anterior sucede después del commit para que una falla S3 no
deje el perfil sin referencia válida. Errores de compensación se registran sin
credenciales y no revierten una transacción SQL ya confirmada.

## Despliegue

Se crearán:

- `wsgi.py`, que expone `application = create_app()`.
- `Procfile`, con Gunicorn, un `GeventWebSocketWorker`, bind a `$PORT`, logs a
  stdout y timeouts configurables.
- `Dockerfile` multi-stage basado en `python:3.12-slim`. La etapa builder
  construye wheels; la etapa runtime instala únicamente artefactos y ejecuta
  con un usuario sin privilegios.
- `.dockerignore`, que excluye `.git`, `.env`, bases locales, avatares,
  worktrees, cachés, pruebas y entornos virtuales de la imagen final.

El contenedor no ejecutará migraciones automáticamente durante el arranque,
porque varias réplicas podrían competir. El despliegue deberá ejecutar
`python -m flask --app app:create_app db upgrade` como release command antes de
levantar las réplicas.

## Dependencias

`requirements.txt` fijará versiones compatibles de:

- `boto3`
- `redis`
- `gunicorn`
- `gevent`
- `gevent-websocket`

Flask-SocketIO y las dependencias existentes permanecerán fijadas. Eventlet no
se instalará.

## Estrategia de pruebas

El desarrollo seguirá RED-GREEN-REFACTOR:

- Configuración: producción falla con cada servicio obligatorio ausente y
  desarrollo conserva defaults seguros.
- Media: bytes válidos se suben sin filesystem; formato, cifrado, caché, bucket
  y clave son correctos; URLs ajenas no se eliminan.
- Integración de perfil: commit fallido compensa la nueva carga y reemplazo
  exitoso elimina la imagen anterior después del commit.
- Sockets: handshake anónimo, usuario eliminado, no verificado y CSRF inválido
  se rechazan; todos los eventos protegidos revalidan identidad.
- Redis: `message_queue` y `channel` se configuran en producción sin requerir
  un servidor Redis real durante unit tests.
- Despliegue: importación de `wsgi.py`, sintaxis del Procfile y construcción
  real de Docker cuando el daemon esté disponible.

La puerta final incluye suite completa, Ruff, mypy en módulos tipados,
`compileall`, comprobación Alembic, validación del Dockerfile, revisión del diff
y prueba HTTP/Socket.IO local.

## Migración y rollout

Alembic ampliará `usuarios.foto_archivo` de 160 a 500 caracteres sin eliminar
valores existentes. Antes de aplicarla se creará una copia local recuperable de
la base de desarrollo. En producción, la migración se ejecutará como release
command y se comprobará antes de iniciar tráfico nuevo.

El rollout recomendado es: provisionar S3/CloudFront y Redis, cargar secretos,
ejecutar migración, desplegar una réplica, verificar health y WebSocket, y luego
aumentar réplicas con sticky sessions.

## Fuera de alcance

- Introducir JWT o reemplazar el login actual.
- Migrar automáticamente avatares legados a S3 sin credenciales y aprobación
  operativa.
- Persistir mensajes o notificaciones en Redis.
- Añadir Kubernetes, Terraform, Nginx o un proveedor de hosting específico.
