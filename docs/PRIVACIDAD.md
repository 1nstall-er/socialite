# Privacidad y proteccion de datos personales

Version de politica vigente: **2026-09-01** (constante `VERSION_POLITICA_ACTUAL` en `privacidad.py`).

Marco aplicable: **Ley N.° 29733**, Ley de Proteccion de Datos Personales del Peru, y su reglamento (D.S. 003-2013-JUS). Socialite trata datos de estudiantes universitarios, por lo que el area legal de la institucion exige poder auditar este documento.

> Nota de alcance: este documento describe el diseno tecnico de cumplimiento. **No sustituye la revision de un abogado**, y la inscripcion del banco de datos ante la Autoridad Nacional de Proteccion de Datos Personales es un tramite administrativo que debe hacer el titular del proyecto.

---

## 1. Que datos tratamos

| Dato | Categoria | Origen | Por que lo necesitamos |
|---|---|---|---|
| Nombre | Identificacion | El usuario | Mostrar quien es en grupos y matches |
| Correo institucional | Identificacion | El usuario | Verificar que pertenece a la UPC |
| Foto de perfil | Identificacion (sensible) | El usuario | Reconocimiento mutuo en el campus |
| Biografia | Perfil | El usuario | Contexto para el match |
| Carrera y ciclo | Academico | El usuario | Senal de afinidad |
| Cursos y horarios | Academico | El usuario | Nucleo del matching |
| Intereses | Perfil | El usuario | Senal de afinidad |
| Campus y facultad | Academico | El usuario | Grafo UPC y matching contextual |
| Mensajes privados | Comunicaciones (sensible) | El usuario | Funcion de chat |
| Conexiones y bloqueos | Grafo social (sensible) | Derivado | Red de contactos y seguridad |
| Reportes de convivencia | Conducta (sensible) | El usuario | Moderacion y seguridad |
| Codigo de verificacion | Autenticacion | Generado | Confirmar titularidad del correo |
| Hash de contrasena | Autenticacion | Derivado | Autenticacion (nunca reversible) |

**Minimizacion pendiente:** hoy la foto es obligatoria en el registro. Una foto de estudiante es dato sensible; se recomienda volverla **opcional** para reducir la superficie de riesgo sin perder valor de producto.

---

## 2. Base de licitud y consentimiento

El tratamiento se sustenta en el **consentimiento libre, previo, expreso e informado** del titular (art. 5 de la Ley 29733).

- El consentimiento se registra **versionado**: se guarda que version de politica acepto el usuario y en que momento.
- Si la politica cambia, se sube `VERSION_POLITICA_ACTUAL` y el usuario debe **volver a aceptar**; `requiere_consentimiento()` lo detecta.
- El consentimiento nunca se asume por el solo uso de la aplicacion.

---

## 3. Derechos del titular (ARCO)

| Derecho | Como se atiende | Estado |
|---|---|---|
| **Acceso** | `exportar_datos_usuario()` genera un JSON descargable con todo lo que el titular aporto y lo derivado de el | Implementado (modulo) |
| **Rectificacion** | El usuario edita su perfil desde la aplicacion | Ya existia |
| **Cancelacion (supresion)** | `plan_eliminacion()` borra dependencias y anonimiza la PII de forma irreversible | Implementado (modulo) |
| **Oposicion** | El usuario puede eliminar su cuenta y dejar de ser tratado | Implementado (modulo) |

### Como se exporta

El paquete usa el formato `socialite-export-v1`. Incluye perfil, cursos, horarios, intereses, grupos, conexiones y **solo los mensajes enviados por el titular**: el mensaje de la otra persona es dato de esa otra persona y no se entrega. El hash de contrasena **nunca** se exporta.

### Como se elimina

1. El titular solicita la eliminacion.
2. Se marca la solicitud con su fecha; empieza un **periodo de gracia de 30 dias** que permite revertir un borrado accidental.
3. Vencido el plazo (`purga_vencida()`), se ejecuta `plan_eliminacion()`: se borran mensajes, conexiones, bloqueos, notificaciones, horarios y participaciones; luego se **anonimiza** el registro de usuario.
4. La anonimizacion deja el correo como `eliminado+<id>@invalido.local`, vacia nombre, biografia, foto e intereses, y limpia el hash de contrasena. **No permite reidentificar a la persona.**
5. La operacion devuelve una **bitacora** de lo eliminado, que sirve como evidencia de que la solicitud se atendio.

Se anonimiza en lugar de borrar la fila cuando existen registros que deben sobrevivir por integridad referencial (por ejemplo un reporte de convivencia en revision).

---

## 4. Plazos de retencion

| Dato | Plazo | Constante |
|---|---|---|
| Cuenta tras solicitud de eliminacion | 30 dias de gracia, luego purga | `DIAS_GRACIA_ELIMINACION` |
| Reportes de convivencia | 365 dias | `DIAS_RETENCION_REPORTES` |
| Codigos de verificacion | Caducan por diseno (ver `verification.py`) | — |
| Avatares en S3 | Se eliminan junto con la cuenta | — |

Los plazos viven como constantes en `privacidad.py` para que sean auditables en un solo lugar y no queden escondidos en la logica.

---

## 5. Registro de accesos (audit log)

`RegistroAcceso` deja constancia de **quien consulto los datos de quien y cuando**. Responde la pregunta que toda universidad hace en una auditoria: como demuestran que nadie consulta datos de estudiantes sin motivo.

Campos: `actor_id`, `titular_id`, `recurso`, `momento`.

---

## 6. Seguridad aplicada

Ya implementado en el proyecto:

- Correo institucional verificado con codigo de un solo uso, caducidad e intentos limitados.
- Contrasenas con hash (nunca en claro).
- Avatares procesados en memoria, sin metadatos, **cifrados en S3**; no se escriben a disco local.
- CSRF, cabeceras de seguridad (incluida CSP), cookies `HttpOnly` / `SameSite`, expiracion de sesion.
- Rate limiting en login y reenvio de correo.
- Bloqueo bidireccional y reportes con motivos controlados y estado de revision.
- `config.py` valida el entorno de produccion con fallo temprano.

---

## 7. Pendientes de cumplimiento

Honestidad sobre lo que **todavia falta** antes de una auditoria institucional:

1. **Persistir** el consentimiento, la solicitud de eliminacion y el audit log (este modulo define la logica; falta el modelo y su migracion Alembic).
2. **Exponer los endpoints** de exportar y eliminar cuenta en la interfaz.
3. **Tarea programada** que ejecute la purga vencida y expire reportes.
4. **Texto legal** de la politica de privacidad y del DPA, revisado por abogado.
5. **Inscripcion del banco de datos** ante la Autoridad Nacional.
6. **Cifrado en reposo** de la base de datos (hoy solo esta cifrado S3).
7. **Forzar `COOKIE_SECURE`** y TLS obligatorio en produccion.
8. **WCAG 2.1 AA + VPAT** para compras institucionales.
