# Dominio UPC verificado

Investigación contrastada el **2 de septiembre de 2026**. Este documento
separa hechos publicados por la UPC de decisiones de producto de Socialite.
Las mallas y reglas institucionales pueden cambiar; por eso cada espacio
persistido conserva `fuente_url` y `verificado_en`.

## Hechos institucionales usados

- La UPC publica cuatro campus actuales: Monterrico, Villa, San Isidro y San
  Miguel. Sus direcciones se contrastaron con la página de Aulas y
  Laboratorios.
- Los canales oficiales consultados llaman a estos ambientes **bibliotecas**,
  salas de lectura y **cubículos**; no se encontró una denominación oficial
  vigente “CRAI”, por lo que no se incorporó al catálogo.
- El cubículo de biblioteca es grupal, requiere por lo menos dos personas y
  permite hasta dos horas diarias por grupo. Los aforos publicados varían por
  campus, pabellón y piso entre cuatro y siete personas.
- La Biblioteca también publica Sala Creativa e International Lounge; este
  último existe únicamente en Monterrico. La Rotonda de Monterrico aparece en
  el mapa del campus y en noticias institucionales de 2026.
- Viernes Culturales funciona presencial y virtualmente los viernes de 1:00 a
  3:00 p. m. con actividades culturales, sociales, académicas y deportivas.
- La UPC exige cuatro créditos extraacadémicos para graduarse. Vida
  Universitaria publica como alternativas talleres, voluntariado, Grupos UPC,
  elencos, clubes, selecciones deportivas y Pasaporte de Actividades
  Culturales. La Semana Universitaria reúne facultades en deportes y retos.
- La página de Transparencia presenta 13 facultades de pregrado y sus carreras.
  Las modalidades publicadas son presencial, semipresencial y a distancia.
- Las carreras regulares consultadas publican una duración de 10 semestres.
  Medicina es una excepción verificada: dura 14 semestres académicos.
- Las mallas de Ingeniería Civil e Ingeniería de Software confirman cursos
  comunes como Matemática Básica y Cálculo I y publican una cadena formal de
  prerrequisitos.

## Decisión sobre “cursos filtro”

La UPC no publica una clasificación institucional denominada “curso filtro”.
Codificar una lista fija con ese nombre habría convertido testimonios o jerga
en un supuesto dato oficial. Socialite lo resuelve con `MetaCursoUPC`: cada
alumno declara el curso que desea reforzar, practicar, enseñar o desarrollar
como proyecto, además de prioridad e intento. El matching utiliza necesidades
reales declaradas y premia roles complementarios sin etiquetar ni estigmatizar
un curso.

## Entidades implementadas

- `PerfilUPC`: campus, facultad, modalidad, objetivo, estilo de estudio,
  disponibilidad para Viernes Cultural, movilidad entre campus y espacio
  preferido.
- `CarreraUPC`: catálogo normalizado de carreras vigentes enlazado a su
  facultad y a la fuente de Transparencia UPC; el texto legado se conserva para
  compatibilidad.
- `EspacioUPC`: catálogo idempotente con ubicación, aforo, reserva, tiempo
  máximo, fuente y fecha de verificación.
- `ParticipacionUPC`: vida universitaria por tipo, rol, campus, periodo y
  créditos ya confirmados por el alumno.
- `MetaCursoUPC`: intención y urgencia por curso, usada para formar parejas de
  mentoría, práctica o proyecto.

Todas son tablas aditivas; no se modifica el esquema de las tablas originales
del MVP.

## Señales del matching

Las tres señales originales siguen disponibles: cursos, horarios e intereses.
Cuando ambos alumnos completan el contexto necesario se incorporan campus,
contexto académico, estilo/objetivo, vida universitaria y metas por curso. Los
pesos activos se normalizan a 100 %, los datos ausentes no penalizan y cada
señal produce razones explicables para Jinja2.

Los intereses utilizan una taxonomía de producto de 50 opciones agrupadas en
siete categorías. La semejanza combina 80 % de Jaccard exacto y 20 % de
Jaccard entre categorías. Cada resultado expone el porcentaje de cada señal y
una comparación por interés. La probabilidad de emparejamiento se estima con
`0.50 + (afinidad - 0.50) × cobertura`: reduce el exceso de certeza cuando el
perfil está incompleto. Está marcada como no calibrada hasta contar con
resultados históricos de invitaciones aceptadas y encuentros exitosos.

## Fuentes

- Campus: https://upc.edu.pe/nosotros/campus/
- Aulas, laboratorios y direcciones: https://www.upc.edu.pe/servicios/contacto-para-alumnos-upc/aulas-y-laboratorios/
- Bibliotecas: https://www.upc.edu.pe/servicios/contacto-para-alumnos-upc/horarios-de-atencion/
- Cubículos y aforos: https://explora.upc.edu.pe/es_ES/reserva-de-cub%C3%ADculos-y-computadoras
- Servicios de biblioteca: https://explora.upc.edu.pe/es_ES/79939-biblioteca
- Viernes Culturales: https://www.upc.edu.pe/servicios/vida-universitaria/viernes-culturales/
- Vida Universitaria: https://www.upc.edu.pe/servicios/vida-universitaria/
- Créditos extraacadémicos: https://www.upc.edu.pe/servicios/vida-universitaria/acerca-de-vida-universitaria/creditos-extraacademicos/
- Grupos UPC: https://www.upc.edu.pe/servicios/vida-universitaria/grupos-upc/
- Mallas y facultades: https://upc.edu.pe/transparencia-upc/mallas-curriculares/
- Ingeniería Civil: https://pregrado.upc.edu.pe/facultad-de-ingenieria/ingenieria-civil/malla-curricular/
- Ingeniería de Software: https://pregrado.upc.edu.pe/carrera-de-ingenieria-de-software/malla-curricular/
- Medicina (14 semestres): https://pregrado.upc.edu.pe/facultad-de-ciencias-de-la-salud/medicina/
- Prerrequisitos: https://explora.upc.edu.pe/77753-permisos-pregrado/%C2%BFpuedo-pedir-permiso-para-llevar-cursos-que-no-cumplo-los-requisitos-
