"""Propuestas breves derivadas de coincidencias, sin cambiar el ranking."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PLANES = frozenset({'estudio', 'proyecto', 'social'})


def construir_propuesta(plan: str, resultado: Mapping[str, Any]) -> dict[str, str]:
    """Describe una invitación; no afirma disponibilidad ni aceptación."""
    if plan not in PLANES:
        raise ValueError('Selecciona un plan válido.')
    cursos = resultado.get('cursos') or []
    curso = cursos[0] if cursos else None
    nombre = (curso.get('nombre') if isinstance(curso, Mapping) else getattr(curso, 'nombre', None))
    intereses = resultado.get('intereses') or []
    if plan == 'social':
        titulo = 'Conversar y conocerse'
        descripcion = ('Un buen comienzo: ' + ', '.join(str(x) for x in intereses[:3]) + '.') if intereses else 'Una conversación puede ser el comienzo de una buena amistad.'
        accion = 'Me gustaría conocerte'
        rompehielo = ('¡Hola! Vi que compartimos el interés por ' + str(intereses[0]) + '. ¿Qué es lo que más te gusta?') if intereses else '¡Hola! ¿Qué es lo que más te gusta de la vida en el campus?'
    elif plan == 'proyecto':
        titulo = f'Crear un equipo de {nombre}' if nombre else 'Avanzar un proyecto juntos'
        descripcion = 'Conozcan sus ideas y acuerden qué les gustaría construir en equipo.'
        accion = 'Hagamos equipo'
        rompehielo = f'¡Hola! ¿Tienes alguna idea para trabajar juntos en {nombre}?' if nombre else '¡Hola! ¿Qué proyecto te gustaría desarrollar en equipo?'
    else:
        titulo = f'Repasar {nombre}' if nombre else 'Organizar un repaso'
        descripcion = 'Compartan dudas y coordinen un momento para estudiar.'
        accion = 'Hagamos equipo'
        rompehielo = f'¡Hola! ¿Qué tema de {nombre} te gustaría repasar?' if nombre else '¡Hola! ¿Qué te gustaría repasar y cuándo te viene bien?'
    return {'tipo': plan, 'titulo': titulo[:120], 'descripcion': descripcion,
            'accion': accion, 'rompehielo': rompehielo}
