# Despliegue de Socialite

Esta guía describe el despliegue horizontal del backend Flask. SQL conserva
usuarios, mensajes y notificaciones; Redis coordina eventos Socket.IO y AWS S3
almacena los avatares nuevos.

## 1. Servicios necesarios

Provisiona antes de desplegar:

- PostgreSQL accesible mediante TLS o una red privada.
- Redis accesible mediante `redis://` en red privada o `rediss://` con TLS.
- Un bucket S3 y, de preferencia, una distribución CloudFront que lo sirva.
- Un proveedor SMTP para verificar los correos UPC.
- Un balanceador que soporte WebSocket y afinidad de sesión.

No uses SQLite en producción. No uses Redis como fuente de verdad de mensajes.

## 2. Permisos de S3

La identidad usada por la aplicación necesita únicamente subir y borrar dentro
del prefijo configurado. Sustituye bucket y prefijo en esta política mínima:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::replace-media-bucket/avatars/*"
    }
  ]
}
```

El backend no establece ACL públicas. `S3_PUBLIC_BASE_URL` debe ser el origen
HTTPS que entrega los objetos, normalmente CloudFront.

## 3. Variables de entorno

Copia `.env.example` solo como referencia y carga los valores mediante el
gestor de secretos del proveedor. Nunca incluyas `.env` dentro de la imagen.

Producción exige:

- `APP_ENV=production`, `SECRET_KEY` y `DATABASE_URL` no SQLite.
- `MAIL_BACKEND=smtp` y credenciales `MAIL_*` completas.
- `REDIS_URL` y un `SOCKETIO_CHANNEL` exclusivo de Socialite.
- Credenciales `AWS_*`, región, bucket, base pública HTTPS y prefijo S3.

`AWS_SESSION_TOKEN` solo se define cuando se usan credenciales temporales.
Configura `SOCKETIO_ASYNC_MODE=gevent` y `COOKIE_SECURE=1`.

## 4. Construcción

```bash
docker build --tag socialite:production-ready .
```

La etapa builder genera wheels. La imagen final instala esos artefactos, copia
el código y ejecuta como el usuario sin privilegios `socialite`.

## 5. Migraciones y backup

Antes de cada migración, crea un backup verificable de la base. Ejecuta Alembic
como un release command único antes de iniciar o escalar el proceso web:

```bash
python -m flask --app app:create_app db upgrade
```

No encadenes ese comando al arranque de Gunicorn: varias réplicas podrían
intentar modificar el esquema simultáneamente.

## 6. Proceso web y escalamiento

El comando de producción es:

```bash
gunicorn --config gunicorn.conf.py wsgi:application
```

Cada contenedor ejecuta exactamente un
`GeventWebSocketWorker`. Aumenta capacidad agregando réplicas, no workers dentro
del mismo contenedor. Redis propaga eventos y salas entre réplicas.

El balanceador debe:

- Mantener afinidad de sesión para todas las peticiones Socket.IO.
- Reenviar `Upgrade` y `Connection` sin degradar WebSocket.
- Terminar TLS y preservar HTTPS hacia el usuario.
- Usar un timeout superior a los intervalos de ping del socket.

## 7. Orden de rollout

1. Provisiona PostgreSQL, Redis, S3/CloudFront y SMTP.
2. Carga secretos y comprueba que `APP_ENV=production` falla ante cualquier
   dependencia ausente.
3. Crea el backup y ejecuta el release command de Alembic.
4. Despliega una réplica y comprueba la página pública.
5. Inicia sesión con una cuenta verificada y abre el socket con su token CSRF.
6. Envía un mensaje entre dos conexiones y confirma mensaje, notificación y
   contador sin recargar.
7. Sube un avatar y confirma que la URL pública responde por HTTPS.
8. Escala a dos réplicas y repite el mensaje cruzando conexiones persistentes.

## 8. Rollback

Revierte primero la imagen de aplicación y conserva Redis, S3 y SQL. La
migración de `foto_archivo` de 160 a 500 caracteres es compatible hacia
adelante con los nombres locales. Antes de ejecutar su downgrade, comprueba que
no existan URLs mayores de 160 caracteres: reducir la columna podría truncar
datos según el motor SQL.

Los avatares locales existentes continúan disponibles en la ruta autenticada
`/media/avatares/<nombre>`. Los flujos nuevos nunca escriben ni eliminan
archivos locales.
