# Contrato Socket.IO de Socialite

El cliente usa Socket.IO sobre el mismo origen que Flask. La sesión HTTP es la
fuente de identidad: no se acepta un `usuario_id` enviado por el navegador.
Además, el handshake debe incluir el token CSRF renderizado en
`meta[name="csrf-token"]`:

```javascript
const socket = io({ auth: { csrf_token: token } });
```

El servidor rechaza el handshake si falta la sesión, la cuenta requiere
verificación o el token no coincide. Cada evento vuelve a consultar la sesión y
las reglas de autorización; pertenecer previamente a una sala no concede acceso
permanente.

## Eventos del cliente

### `join_room`

Payload: `{ "contacto_id": 42 }`. Solo une al chat si existe una conexión
aceptada y no hay bloqueo. Acknowledgement exitoso:
`{ "ok": true, "contacto_id": 42 }`.

### `leave_room`

Payload: `{ "contacto_id": 42 }`. Retira únicamente el socket actual de la
sala canónica de ambos usuarios.

### `send_message`

Payload: `{ "contacto_id": 42, "texto": "..." }`. El texto admite de 1 a
2000 caracteres. El servidor valida nuevamente conexión y bloqueo, persiste el
mensaje y su notificación en una sola transacción, y después emite los eventos.

Acknowledgement exitoso:

```json
{ "ok": true, "mensaje": { "id": 1, "emisor_id": 7, "receptor_id": 42 } }
```

### `mark_read`

Payload: `{ "contacto_id": 42 }`. Marca en una transacción los mensajes y sus
notificaciones asociadas como leídos.

## Eventos del servidor

- `socket_ready`: confirma el usuario y entrega `notificaciones_no_leidas`.
- `message_received`: mensaje persistido para quienes están dentro del chat.
- `notification_received`: alerta persistida emitida a todas las pestañas
  conectadas del destinatario; incluye `total_no_leidas`.
- `messages_read`: informa al emisor que el contacto leyó la conversación.
- `notifications_synced`: sincroniza el contador después de marcar como leído.
- `socket_error`: error estable con `codigo`, `mensaje` y, para rate limiting,
  `reintentar_en`.

Los errores también regresan en el acknowledgement con la forma:

```json
{
  "ok": false,
  "error": { "codigo": "conexion_requerida", "mensaje": "..." }
}
```

## Escalabilidad

Las salas personales usan `usuario:<id>` y los chats `chat:<id-menor>:<id-mayor>`.
El proceso actual usa `threading`, suficiente para desarrollo. En un despliegue
con varios workers se debe configurar Redis como `message_queue` de Socket.IO y
reemplazar `LimitadorVentanaDeslizante` por un contador compartido.
