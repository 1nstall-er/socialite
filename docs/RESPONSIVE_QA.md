# Verificación responsive — 2026-09-07

- Edge headless: panel, compañeros, perfil, grupos, mensajes, conexiones y seguridad a 1440, 390 y 360 px: HTTP 200, sin desbordamiento horizontal.
- Inspección de capturas de panel desktop y descubrimiento móvil. Corregida interferencia del menú heredado que ocultaba los tipos de plan en móvil.
- Invitación y aceptación con cuentas aisladas: diálogo de conexión confirmado por servidor; abrir chat e insertar rompehielo no envía mensajes automáticamente.
- Los tres tipos de plan son visibles en móvil; tres perfiles accesibles con JavaScript deshabilitado.
- Sin errores JavaScript en el recorrido. Fotografías UPC locales con procedencia en `UPC_FRONTEND_SOURCES.md`.
- Unittest: 102 pruebas, 101 aprobadas y una omitida (Gunicorn en Windows). Ruff limpio. Mypy limpio para los siete módulos de CI.
- Base local respaldada antes de migrar a `c8e4b2197a30`; `flask db check` sin operaciones pendientes.

Límites: emulación de tamaños, no dispositivos físicos Safari/iOS. Los agentes de implementación no completaron una revisión independiente final por límite de uso; la integración, pruebas y revisión visual fueron completadas por el agente principal.
