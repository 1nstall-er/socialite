"""Logica de matching para grupos de estudio y contactos.

El scoring es intencionalmente simple para el MVP. Se puede reemplazar
por algo mas sofisticado una vez que haya datos reales de que grupos
funcionan (se reunen mas de una vez).
"""

PESO_MISMO_CURSO = 0.5
PESO_HORAS_COMPARTIDAS = 0.3
PESO_INTERESES = 0.2


def score(mismo_curso, horas_compartidas, intereses_comunes):
    puntaje = 0.0
    if mismo_curso:
        puntaje += PESO_MISMO_CURSO
    puntaje += PESO_HORAS_COMPARTIDAS * horas_compartidas
    puntaje += PESO_INTERESES * intereses_comunes
    return puntaje


def ordenar_candidatos(candidatos):
    """Ordena candidatos de mayor a menor puntaje.
    Cada candidato es un dict con la clave 'score'.
    """
    return sorted(candidatos, key=lambda c: c["score"], reverse=True)
