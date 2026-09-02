"""Reglas transparentes de afinidad para el MVP de Socialite."""

PESO_MISMO_CURSO = 0.5
PESO_HORAS_COMPARTIDAS = 0.3
PESO_INTERESES = 0.2


def score(mismo_curso, horas_compartidas, intereses_comunes):
    """Devuelve una afinidad entre 0 y 1.

    Dos horas libres y tres intereses compartidos alcanzan el maximo de sus
    respectivos componentes. Esto evita que muchos bloques inflen el puntaje.
    """
    cursos = 1.0 if mismo_curso else 0.0
    horarios = min(max(horas_compartidas, 0) / 2, 1.0)
    intereses = min(max(intereses_comunes, 0) / 3, 1.0)
    return round(
        PESO_MISMO_CURSO * cursos
        + PESO_HORAS_COMPARTIDAS * horarios
        + PESO_INTERESES * intereses,
        4,
    )


def ordenar_candidatos(candidatos):
    """Ordena candidatos por afinidad y usa el nombre como desempate."""
    return sorted(
        candidatos,
        key=lambda candidato: (-candidato["score"], candidato["usuario"].nombre.lower()),
    )
