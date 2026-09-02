# Socialite

Socialite es una app web para que estudiantes universitarios encuentren
companeros y creen grupos dentro del campus. El MVP esta enfocado en la UPC.

## Funciones disponibles

- Registro restringido al correo institucional `@upc.edu.pe`.
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
- Catalogo verificado de bibliotecas, cubiculos y espacios UPC.
- Selectores interactivos para 59 carreras, ciclos validos por carrera y 50
  intereses predefinidos agrupados por categoria.
- Porcentaje por señal y probabilidad heuristica de emparejamiento ajustada por
  la cobertura real del perfil.
- Seguimiento de los cuatro creditos extraacademicos requeridos.
- Interfaz adaptable a computadoras y celulares.
- Búsqueda y filtros de compañeros, solicitudes de conexión accionables y una
  pantalla para administrar contactos.

## Stack

- Flask 3
- Flask-SQLAlchemy
- Pillow para procesar imágenes sin confiar en la extensión del archivo
- SQLite en desarrollo
- HTML y CSS sin dependencias de frontend

## Arquitectura de backend

- `app.py`: rutas, validacion, autorizacion y contratos de respuesta.
- `matching.py`: algoritmo puro de afinidad y solapamiento de horarios.
- `queries.py`: consultas con carga anticipada para evitar N+1.
- `presenters.py`: contratos serializables para Jinja2 y JSON.
- `models.py`: entidades y relaciones persistentes.
- `media.py`: validación, normalización y almacenamiento privado de avatares.

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
python app.py
```

La aplicacion queda disponible en `http://127.0.0.1:5000`.

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
python -m mypy --strict matching.py
```

## Alcance pendiente

El MVP todavia no envia un codigo real de verificacion al correo, no incluye
chat en tiempo real y no tiene una app nativa. La coordinacion ocurre dentro
del campus y el contacto posterior se mantiene fuera de la app.
