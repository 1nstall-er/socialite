# Contratos de contexto para Jinja2

Este documento separa la logica del backend de las plantillas. Las rutas
existentes siguen funcionando con el frontend actual. Las rutas cuyas
plantillas aun no existen responden temporalmente con JSON; al agregar la
plantilla indicada, Flask le entregara exactamente el mismo contrato.

## Convenciones

- Los objetos de los contratos son diccionarios serializables, no modelos de
  SQLAlchemy. En Jinja2 se pueden leer con notacion de punto.
- Ningun perfil publico contiene `correo_institucional` hasta que la conexion
  entre ambas personas este en estado `aceptada`.
- Las colecciones paginadas usan `pagina`, `por_pagina`, `total`, `paginas`,
  `tiene_anterior` y `tiene_siguiente`.
- Los POST requieren un campo oculto `csrf_token` con `{{ csrf_token() }}`.

## `GET /panel` → `panel.html`

Variables de primer nivel:

- `usuario`: perfil completo del usuario conectado.
- `metricas`: `perfil_completo`, `grupos_activos` y
  `solicitudes_pendientes`.
- `sugerencias`: hasta tres contratos de matching.
- `mis_grupos`: hasta tres grupos a los que pertenece.
- `grupos_recomendados`: grupos con su afinidad calculada.
- `solicitudes`: solicitudes recibidas pendientes.

## `GET /companeros` → `companeros.html`

Mantiene `sugerencias` con modelos para compatibilidad con el template actual y
agrega `contrato`, listo para el nuevo frontend:

- `contrato.resultados[]`
  - `usuario`: `id`, `nombre`, `iniciales`, `carrera`, `ciclo`, `intereses`,
    `cursos`, `horarios`, `perfil_completo`, `perfil_upc` y
    `participaciones_upc`.
  - `porcentaje`: afinidad final entre 0 y 100.
  - `confianza`: porcentaje de senales disponibles para calcularla.
  - `razones[]`: `tipo`, `titulo`, `detalle`.
  - `componentes.cursos|horarios|intereses`: `valor`, `puntos`, `peso`.
  - Cuando ambos perfiles tienen datos suficientes se agregan, sin romper las
    claves anteriores: `campus`, `contexto_academico`, `estilo_objetivo`,
    `vida_universitaria` y `metas_curso`.
  - `contexto_upc`: evidencia estructurada de las coincidencias UPC usadas.
  - `horas`, `minutos`, `cursos`, `intereses`.
- `contrato.paginacion`.
- `contrato.filtros`: `q`, `curso`, `afinidad`.

Query params admitidos: `q`, `curso`, `afinidad`, `pagina`, `por_pagina`.
El mismo contrato esta disponible como JSON en `GET /api/v1/companeros`.

## `GET /perfil` → `perfil.html`

Además de las variables actuales, entrega:

- `perfil.perfil_upc`: campus, facultad, carrera normalizada, modalidad, objetivo, estilo de
  estudio, disponibilidad para Viernes Cultural, movilidad entre campus y
  espacio preferido.
- `perfil.participaciones_upc[]`: tipo, nombre, rol, campus, periodo, créditos
  confirmados y estado.
- `perfil.creditos_extraacademicos`: `confirmados`, `requeridos` y
  `pendientes`.
- `perfil.metas_curso[]`: curso, rol de estudio, prioridad, intento y si busca
  equipo.
- `catalogo_upc`: opciones de enums y los espacios oficiales disponibles.

El mismo contrato privado está disponible en `GET /api/v1/perfil`. El catálogo
público puede obtenerse por separado en `GET /api/v1/catalogo-upc`.

Formularios POST listos para integrar:

- `/perfil/upc`: `campus`, `facultad`, `carrera_upc_id`, `modalidad`, `objetivo`,
  `estilo_estudio`, `viernes_cultural_disponible`, `acepta_intercampus` y
  `espacio_preferido_id`.
- `/perfil/participaciones`: `tipo`, `nombre`, `rol`, `campus`, `periodo`,
  `creditos_confirmados` y `activa`.
- `/perfil/participaciones/<id>/eliminar`.
- `/perfil/cursos/<curso_id>/meta`: `rol`, `prioridad`, `intento` y
  `busca_equipo`.

Todos los POST deben incluir `csrf_token`.

## `GET /personas/<id>` → `persona.html`

- `persona`: perfil publico y, si corresponde, correo institucional.
- `afinidad`: contrato de matching completo.
- `conexion`: `null` o `id`, `estado`, `direccion`, `persona`, timestamps.

Mientras `persona.html` no exista, esta ruta responde JSON para facilitar la
integracion.

## `GET /grupos` → `grupos.html`

Mantiene `grupos` con modelos para compatibilidad y agrega:

- `contrato.resultados[]`: datos del grupo, curso, creador, miembros,
  capacidad y afinidad opcional.
- `contrato.paginacion`.
- `contrato.filtros`: `q`, `tipo`, `curso`, `dia`, `disponibles`.
- `afinidades`: mapa por id para el template actual.

Query params admitidos: `q`, `tipo`, `curso`, `dia`, `disponibles=1`, `pagina`
y `por_pagina`. El JSON equivalente vive en `GET /api/v1/grupos`.

## `GET /grupos/nuevo` → `grupo_nuevo.html`

- `tipos`: `estudio`, `social`.
- `dias`: dias permitidos.
- `cursos`: cursos del usuario conectado.
- `limites`: `min_miembros=2`, `max_miembros=12`.

El formulario envia POST a `/grupos` con `tipo`, `curso_id`, `lugar`, `dia`,
`hora_inicio`, `hora_fin`, `max_miembros` y `csrf_token`.

## `GET /grupos/<id>` → `grupo_detalle.html`

Entrega el contrato de grupo directamente y agrega:

- `afinidad`: `score`, `porcentaje`, `mismo_curso`, `horas`, `minutos`.
- `usuario_es_miembro`.
- `usuario_es_creador`.

## `GET /conexiones` → `conexiones.html`

- `recibidas`: solicitudes pendientes recibidas.
- `enviadas`: solicitudes pendientes enviadas.
- `aceptadas`: conexiones aceptadas; estas si contienen el email de la otra
  persona.

Acciones POST disponibles:

- `/companeros/<usuario_id>/conectar`
- `/conexiones/<conexion_id>/aceptar`
- `/conexiones/<conexion_id>/rechazar`
- `/conexiones/<conexion_id>/cancelar`

## Codigos y seguridad

- `400`: datos invalidos o token CSRF vencido.
- `403`: el usuario no tiene permiso para la accion.
- `404`: recurso inexistente.
- `429`: bloqueo temporal tras cinco intentos de login fallidos.
- Las respuestas autenticadas llevan `Cache-Control: private, no-store`.
