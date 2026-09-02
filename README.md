# Socialite

Socialite es una app web para que estudiantes universitarios encuentren
companeros y creen grupos dentro del campus. El MVP esta enfocado en la UPC.

## Funciones disponibles

- Registro restringido al correo institucional `@upc.edu.pe`.
- Ingreso con contrasena almacenada de forma segura.
- Perfil academico con carrera, ciclo, cursos, intereses y horas disponibles.
- Grupos sociales o de estudio con curso, horario, lugar y capacidad.
- Opcion para unirse o salir de un grupo.
- Matching transparente por cursos, horarios e intereses en comun.
- Interfaz adaptable a computadoras y celulares.

## Stack

- Flask 3
- Flask-SQLAlchemy
- SQLite en desarrollo
- HTML y CSS sin dependencias de frontend

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

Para produccion, configura las variables `SECRET_KEY` y `DATABASE_URL`.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Alcance pendiente

El MVP todavia no envia un codigo real de verificacion al correo, no incluye
chat en tiempo real y no tiene una app nativa. La coordinacion ocurre dentro
del campus y el contacto posterior se mantiene fuera de la app.
