# Socialite: Conecta por un plan

Fecha: 2026-09-04.
Estado: dirección conceptual aprobada; especificación escrita pendiente de revisión del usuario.
Base inspeccionada: `d69534d`.

## 1. Resultado esperado

Transformar la experiencia autenticada de Socialite en un lugar limpio, cercano
y entretenido para encontrar compañía universitaria. La entrada será «¿Qué te
provoca hacer hoy?», seguida de personas compatibles y una propuesta concreta.
El usuario conservará el control: explorar no enviará invitaciones; ninguna
sugerencia enviará un mensaje automáticamente.

La dirección aprobada equilibra estudio y vida social. Se eligieron planes
compartidos sobre dos alternativas: un swipe centrado en fotos, que daría menos
protagonismo al contexto universitario, y un mapa de afinidades, que añadiría
complejidad de navegación en pantallas pequeñas.

Esta es una hipótesis de experiencia para probar, no una promesa de que todos
los estudiantes la preferirán. No se añadirán métricas inventadas de actividad,
testimonios ficticios ni contadores de personas «en línea» sin soporte real.

## 2. Alcance de esta entrega

- Nuevo inicio personal en `/panel`; `/` conserva la portada para visitantes
  y lleva al panel cuando existe una sesión autenticada.
- Rediseño de `/companeros` como Descubrir, con selección de plan y propuestas
  individuales, manteniendo una vista de lista y los filtros existentes.
- Plantilla real para `/personas/<id>`; actualmente falta, igual que `panel.html`.
- Invitaciones con contexto y match confirmado por aceptación mutua.
- Una identidad visual compartida por perfil, grupos, conexiones, mensajes,
  conversación, notificaciones y seguridad.
- Adaptaciones pequeñas de persistencia y respuestas para soportar estas
  interacciones sin abandonar Application Factory, Blueprints ni Jinja2.

No incluye reservas de espacios UPC, calendario, geolocalización, presencia en
tiempo real, agenda automática, recomendaciones generadas con un LLM, nuevos
proveedores de nube ni una migración a React. El registro y la verificación
conservan su flujo y heredan únicamente los ajustes visuales compartidos.

## 3. Dirección visual

Identidad: editorial universitaria, luminosa y expresiva, sin saturar la pantalla.

- Fondo blanco cálido; superficies blancas y texto carbón. Verde profundo como
  color principal, conservando reconocimiento de Socialite, y lima para acentos.
- Tipografía del sistema con jerarquía clara: títulos amplios, cuerpo legible,
  etiquetas cortas. Sin fuentes remotas ni dependencias visuales pesadas.
- Fotos reales del perfil con recorte cuidado. Iniciales cuando no haya foto;
  nunca caras ficticias presentadas como estudiantes registrados.
- Un objetivo principal por pantalla. Los desgloses y filtros extensos serán
  desplegables, no el primer elemento de cada propuesta.
- Iconos SVG locales consistentes. Animaciones breves, aproximadamente
  180–240 ms, y celebración de match no bloqueante.
- Estado de foco visible, controles táctiles de al menos 44 px y opciones de
  movimiento reducido. La información no dependerá únicamente del color.

En escritorio habrá una navegación lateral compacta y una cabecera con contexto
y notificaciones. En móvil, navegación inferior: Inicio, Descubrir, Grupos,
Mensajes y Perfil. «Mis equipos» enlazará a conexiones desde Descubrir y el
panel; seguridad seguirá accesible desde Perfil y cada perfil público.

## 4. Nuevo inicio personal

`panel.html` aprovechará el contrato existente de `pages.panel`:

1. Saludo con el nombre del usuario y la pregunta «¿Qué te provoca hacer hoy?».
2. Tres accesos: «Preparar un parcial», «Avanzar un proyecto», «Conocer gente».
3. Hasta tres personas sugeridas por el ranking real, con una razón de afinidad
   y un acceso a Descubrir. No afirmar que aceptaron el plan ni están disponibles
   ahora.
4. Invitaciones pendientes y acceso a equipos ya formados.
5. Grupos propios y recomendaciones existentes, sin crear eventos ficticios.
6. Una sugerencia breve para completar información cuando falten señales.

El primer acceso conducirá a una acción útil sin obligar a rellenar otra vez
todo el perfil. Los perfiles incompletos podrán explorar; se explicará cuándo
faltan datos para ofrecer razones más específicas.

## 5. Descubrimiento por planes

### Selección y datos

El parámetro opcional `plan` tendrá tres valores: `estudio`, `proyecto`, `social`.
El valor por defecto será `estudio`. El modo se conservará en la URL para que
recargar, volver atrás y compartir un enlace no pierdan el contexto.
Los valores inválidos en GET volverán a los valores por defecto; un `plan`
inválido enviado por POST se rechazará con 400 sin guardar una invitación.
La vista por defecto será `descubrir`, con alternativa explícita `lista`.

Los planes contextualizan la presentación y la invitación; en esta primera
entrega no cambian los pesos, la fórmula ni el orden del ranking existente.
Los filtros de curso, búsqueda y afinidad mínima sí conservarán su efecto actual.
La pantalla explicará «Personas ordenadas por afinidad con tu perfil».

- Estudio: destacar primero cursos y horarios compartidos.
- Proyecto: destacar cursos, área académica y metas de equipo cuando existan.
- Social: destacar intereses y campus compartidos cuando existan.

Si no existen coincidencias específicas, mostrar una propuesta genérica
honesta, como «Organizar un repaso» o «Conversar y conocerse». No inventar un
curso, una amistad de segundo grado, un lugar reservado ni una hora de encuentro.
Los horarios del perfil son coincidencias declaradas, no disponibilidad en vivo.

### Presentación

Cada propuesta mostrará foto, nombre, carrera/campus si están disponibles, una
biografía breve y hasta tres razones relevantes. El porcentaje será «Afinidad
calculada» y el detalle explicará contribuciones y cobertura de datos.
El valor heurístico existente de probabilidad se conservará en contratos y
detalle técnico, con su advertencia; no encabezará la experiencia ni se
presentará como probabilidad empírica de aceptación.

Acciones:

- «Hagamos equipo» para estudio/proyecto y «Me gustaría conocerte» para social:
  abrir una confirmación breve con el plan que recibirá la otra persona.
- «Conocer más»: perfil público completo, con acceso a volver al descubrimiento.
- «Ver otra persona»: pasar a la siguiente propuesta, sin rechazar, bloquear ni
  notificar al estudiante mostrado.
- «Anterior»: recuperar la propuesta previa antes de realizar una acción.
- «Ver lista»: alternativa visible con navegación y filtros tradicionales.

El gesto horizontal será únicamente una mejora opcional para avanzar. Nunca
enviará una invitación. Las acciones completas funcionarán con botones y teclado.
No habrá navegación infinita ni rachas obligatorias: cada lote será acotado por
la paginación existente, con «Ver más» y un estado de fin claro.

Las personas con invitación enviada no ofrecerán otra acción de envío. Una
invitación recibida mostrará «Ver su propuesta»; las conexiones aceptadas,
«Abrir chat». Los bloqueados seguirán excluidos por las consultas actuales.

## 6. Invitación, aceptación y celebración

Se conserva el ciclo de `Conexion`, con contexto adicional del plan:

```text
Explorar -> Confirmar invitación -> Pendiente
                                   | aceptar destinatario -> Aceptada -> Chat
                                   | ahora no             -> Rechazada
                                   | cancelar remitente   -> Cancelada/eliminada
```

Solo la aceptación explícita del destinatario convierte la invitación en
equipo. Si existe una invitación en sentido contrario, se muestra esa propuesta
para responderla; pulsar enviar no la acepta de forma silenciosa.

Después de un commit exitoso de aceptación se muestra «¡Hacen equipo!» con ambos
nombres y el plan. La celebración se puede cerrar, no bloquea el chat y respeta
movimiento reducido. Recargar una conexión antigua no dispara una celebración.

Las invitaciones se presentan con frases como «Ana propone organizar un repaso».
Aceptar expresa interés en coordinar, no confirma una cita, reserva u horario.
Las conexiones antiguas sin plan seguirán funcionando como conexiones generales.

El chat podrá ofrecer una frase inicial basada en el contexto real, por ejemplo
una pregunta sobre el curso compartido. Pulsarla solo llena el borrador: el
usuario debe enviar el mensaje. No sustituirá un borrador ya escrito sin una
acción explícita.

## 7. Pantallas complementarias

- Perfil: cabecera con identidad, foto y presentación; secciones académicas y
  sociales claramente agrupadas. Se conservan todos los campos y validaciones.
- Perfil público: identidad, coincidencias, biografía y acciones según el estado
  de conexión. Correo visible únicamente en las condiciones actuales.
- Conexiones: «Invitaciones», «Mis equipos» y «Enviadas», con contexto del plan.
- Mensajes: bandeja legible y conversación orientada al contenido; conservar
  historial, estados de lectura, envío HTTP y Socket.IO.
- Grupos: jerarquía clara para actividad, curso, lugar, horario y cupos reales.
- Notificaciones y seguridad: coherencia visual sin ocultar bloquear, reportar,
  solicitudes pendientes ni controles de cuenta.

## 8. Arquitectura y persistencia

Se mantienen Flask, Jinja2 y JavaScript progresivo. No se cambiará el framework
ni se volverá a concentrar lógica de negocio en controladores o plantillas.

- `app/services/discovery.py`: funciones tipadas y sin acceso a Flask/SQL para
  construir propuestas y frases iniciales a partir de contratos ya calculados.
- `app/services/connections.py`: operaciones compartidas de proponer, aceptar,
  rechazar y cancelar, con validación de actor, bloqueo y transición de estado.
- `app/controllers/pages.py`, `companions.py`, `connections.py`, `messaging.py`:
  adaptaciones HTTP y composición de contextos; sin fórmulas nuevas de matching.
- `app/controllers/presenters.py`: añadir contexto del plan de manera compatible.
- `app/core/sockets.py`: publicación de cambios confirmados, usando las salas de
  usuario autenticadas y Redis existentes.
- `templates/components/`: navegación, identidad, propuesta, vacío y diálogo.
- `static/`: separar tokens/base, estructura autenticada, descubrimiento y
  comportamiento de interfaz. Mantener aislado el JavaScript del chat.

### Cambio de esquema mínimo

Añadir a `Conexion` dos columnas anulables:

- `plan_tipo`: texto de hasta 16 caracteres, restringido a estudio/proyecto/social.
- `plan_tema`: texto de hasta 120 caracteres generado y validado en el servidor,
  como una síntesis de la propuesta. No es un campo libre para enviar mensajes
  antes de que exista conexión.

Ambas columnas estarán presentes juntas o ambas ausentes. Las filas existentes
permanecerán sin plan. El servidor recalculará el tema desde el modo y las
coincidencias vigentes al confirmar: nunca confiará en texto o afinidades enviados
por el navegador. Una invitación pendiente o aceptada no se sobrescribe por un
nuevo clic; la creación y las transiciones devolverán el estado persistido.
Si el tema recalculado difiere del mostrado en la confirmación porque cambiaron
los perfiles, devolver 409 con la propuesta actualizada y pedir confirmación de
nuevo. La comparación del tema de la vista previa no autoriza aceptar texto
arbitrario del cliente.

Extender `TipoNotificacion` con invitación recibida y conexión aceptada. Usar
`actor_id`, `usuario_id` y `destino_url` ya existentes; no crear una tabla paralela
de notificaciones ni mensajes falsos para representar invitaciones.

Aplicar una migración aditiva después de la última revisión existente, probada
desde una base nueva y una copia de la base actual. No ejecutar migraciones al
arrancar Flask. Crear backup antes de aplicarlas a los datos locales; no modificar
revisiones históricas, borrar perfiles ni mover avatares.

## 9. Contratos HTTP y eventos

Conservar las 49 rutas y sus métodos. La experiencia de descubrimiento usará
`/companeros`; no necesita un conjunto paralelo de rutas.

- GET de compañeros: parámetros actuales más `plan` y `vista` (`descubrir` o
  `lista`). Se añaden campos de propuesta y estado de conexión cuando se solicite
  el contexto de descubrimiento; no se eliminan campos de las APIs existentes.
- POST de conectar: `csrf_token`, `plan` opcional y tema de vista previa cuando
  corresponda, usado solo para detectar cambios antes de confirmar. Sin `plan`, conservar el
  comportamiento de conexión general para formularios o integraciones previas.
- POST de aceptar/rechazar/cancelar: seguir validando al actor y el estado en el
  servidor. Repetir el mismo envío no debe duplicar invitaciones ni alertas.
- Solicitudes mejoradas con `Accept: application/json`: recibir el estado
  confirmado, conexión y navegación siguiente. Formularios normales: conservar
  redirect y mensajes. CSRF seguirá viajando como campo de formulario.
- `/panel` y `/personas/<id>` devolverán HTML por defecto. Para consumidores que
  soliciten explícitamente JSON, conservar el contrato serializado; las pruebas
  que esperaban `template_pendiente` deberán verificar la plantilla real.
- `/conexiones` también admitirá `Accept: application/json` para reconciliar
  invitaciones y equipos después de un evento o una reconexión.

Invitación y notificación se persistirán en una transacción. Emitir eventos solo
después del commit, nunca desde `discovery.py`. `notification_received` continuará
actualizando el contador; un evento adicional `connection_updated` indicará a
las pestañas implicadas que deben reconciliar el estado autorizado por HTTP.

Los eventos son una mejora de latencia, no la fuente de verdad. Si falla el
socket, el envío HTTP y la bandeja persistida siguen funcionando; no mostrar un
error de guardado por una emisión fallida posterior al commit. Al reconectar o
volver a la pestaña se consulta el estado actual. Las celebraciones solo se
activan para transiciones nuevas observadas, con deduplicación por conexión y
fecha de actualización en la sesión del navegador, sin guardar datos personales.

## 10. Seguridad, errores y rendimiento

- Mantener sesión autenticada, verificación, CSRF, restricciones de correo,
  bloqueo bidireccional y permisos del chat. Comprobarlos también al aceptar una
  propuesta que pudo quedar obsoleta en pantalla.
- Tratar los nombres, biografías y respuestas como texto; no insertar HTML de
  usuarios. Mantener CSP y servir scripts desde archivos locales.
- Los errores de red mantienen la propuesta visible y permiten reintentar.
  Una respuesta tardía no sustituye el estado de una persona distinta.
- Controles de envío deshabilitados mientras la petición está en curso; el
  servidor revalida duplicados aunque el cliente envíe varias veces.
- Sin resultados: distinguir ausencia de compañeros de filtros demasiado
  restrictivos. Ofrecer limpiar filtros, revisar perfil o explorar grupos.
- Si falta una foto, una biografía o un curso, usar la alternativa prevista sin
  espacios rotos ni falsificar datos. Los fallos de imagen mostrarán iniciales.
- Reutilizar las cargas anticipadas, grafo y heap actuales. Preparar el contexto
  una vez por lote, sin una consulta por tarjeta ni reconstruir el grafo al
  avanzar en el navegador.
- Cargar progresivamente imágenes y siguientes lotes, respetar la paginación
  acotada y liberar listeners al salir. No añadir una librería de animaciones.
- Sin JavaScript, formularios, lista, perfil público y enlaces al chat seguirán
  siendo utilizables. Sin Socket.IO, la aceptación seguirá siendo válida en SQL.

## 11. Verificación y criterios de aceptación

La implementación deberá demostrar:

1. Inicio autenticado real, accesible desde el login normal; un `siguiente`
   válido conserva prioridad. Visitantes siguen viendo la portada pública.
2. Modos de plan conservados al recargar y filtros funcionando en ambas vistas.
3. Todas las razones y temas derivados de datos reales o texto genérico explícito.
4. Ranking y porcentajes iguales para los mismos datos y filtros, sea cual sea el plan.
5. Ver otra persona, volver y abrir detalles sin crear filas en SQL.
6. Proponer, responder, cancelar y abrir chat con dos cuentas distintas; el receptor
   ve el mismo plan confirmado por el remitente.
7. Doble clic y reintento sin invitaciones o notificaciones duplicadas.
8. Ningún match celebrado antes de aceptar ni mensajes enviados automáticamente.
9. Bloqueos, sesión vencida y CSRF inválido rechazados en las acciones mejoradas.
10. Eventos restringidos a destinatarios y emisores, con recuperación HTTP al
    desconectar y reconectar el socket; no emisión de éxito tras rollback.
11. Perfil público y panel con HTML y su representación JSON explícita.
12. Datos y fotos existentes conservados después de la migración.
13. Ninguna ruta anterior eliminada ni contratos API existentes recortados.
14. Pantallas autenticadas consistentes en móvil (360/390 px), tableta (768 px)
    y escritorio (1440 px), sin scroll horizontal accidental.
15. Flujo completo con teclado, foco restaurado al cerrar diálogos, lector de
    pantalla informado de cambios y movimiento reducido respetado.
16. Formulario/lista funcionales sin JavaScript, y chat HTTP sin WebSocket.

Pruebas: unitarias del constructor puro de propuestas; integración Flask/SQL de
invitaciones y negociación HTML/JSON; clientes de prueba Socket.IO; migraciones
en SQLite temporal; suite existente, Ruff y mypy para módulos tipados. La revisión
visual y de interacción se hará en navegador con dos cuentas de prueba, sin
enviar invitaciones a usuarios reales. Capturas antes/después en móvil y escritorio
permitirán comprobar el cambio, no solo inferirlo desde el HTML.

No se afirmará validación de producción real en PostgreSQL, Redis distribuido o
dispositivos que no se hayan probado; esas limitaciones se reportarán por separado.

## 12. Orden de entrega y control de cambios

Una vez aprobado este documento, preparar el plan de implementación en este orden:

1. Establecer componentes y navegación común; construir panel y perfil público.
2. Construir la experiencia de descubrimiento y sus alternativas accesibles.
3. Integrar planes persistidos, notificaciones y aceptación confirmada.
4. Aplicar la identidad al resto de pantallas sin perder controles ni contenido.
5. Verificar, revisar, migrar con backup, reiniciar y publicar los cambios en
   GitHub siguiendo la instrucción del usuario de actualizarlo al terminar.

Esta especificación no aplica todavía cambios a la app, a las imágenes ni a la
base de datos. La aprobación de la dirección conceptual no se presenta como una
interfaz ya implementada.
