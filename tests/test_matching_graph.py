import unittest
from dataclasses import dataclass
from typing import Any

from app.services.matching import (
    GrafoAfinidadUPC,
    MaxHeapAfinidad,
    rankear_top_candidatos,
)


@dataclass
class PerfilFalso:
    campus: str
    facultad: str
    carrera_upc: None = None
    modalidad: None = None
    objetivo: None = None
    estilo_estudio: None = None
    viernes_cultural_disponible: None = None
    acepta_intercampus: bool = False
    espacio_preferido: None = None


@dataclass
class UsuarioFalso:
    id: int
    nombre: str
    campus: str
    facultad: str
    carrera: None = None
    cursos: tuple[Any, ...] = ()
    horarios: tuple[Any, ...] = ()
    lista_intereses: tuple[str, ...] = ()
    intereses_catalogados: tuple[Any, ...] = ()
    participaciones_upc: tuple[Any, ...] = ()
    metas_curso: tuple[Any, ...] = ()

    @property
    def perfil_upc(self) -> PerfilFalso:
        return PerfilFalso(self.campus, self.facultad)


class GrafoMatchingTestCase(unittest.TestCase):
    def test_bfs_detecta_primer_y_segundo_grado_sin_clique_materializada(self):
        origen = UsuarioFalso(1, "Origen", "monterrico", "ingenieria")
        puente = UsuarioFalso(2, "Puente", "monterrico", "diseno")
        segundo = UsuarioFalso(3, "Segundo", "villa", "diseno")
        aislado = UsuarioFalso(4, "Aislado", "san_miguel", "derecho")
        grafo = GrafoAfinidadUPC([origen, puente, segundo, aislado])

        contextos = grafo.contextos_desde(origen.id)
        self.assertEqual(contextos[puente.id]["grado"], 1)
        self.assertEqual(contextos[segundo.id]["grado"], 2)
        self.assertEqual(contextos[segundo.id]["intermediario_id"], puente.id)
        self.assertEqual(contextos[aislado.id]["tipo"], "fuera_de_red")
        self.assertIn("campus:monterrico", contextos[segundo.id]["via"])
        self.assertIn("facultad:diseno", contextos[segundo.id]["via"])

    def test_max_heap_extrae_afinidades_en_orden_descendente(self):
        usuarios = [
            UsuarioFalso(indice, f"U{indice}", "villa", "ingenieria")
            for indice in range(1, 5)
        ]
        resultados = [
            {"usuario": usuario, "score": score}
            for usuario, score in zip(usuarios, (0.25, 0.92, 0.61, 0.80), strict=True)
        ]
        heap = MaxHeapAfinidad(resultados)
        extraidos = [heap.extraer_maximo()["score"] for _ in range(len(heap))]
        self.assertEqual(extraidos, [0.92, 0.80, 0.61, 0.25])

    def test_top_candidatos_limita_a_diez_e_incluye_senal_de_grafo(self):
        origen = UsuarioFalso(1, "Origen", "villa", "ingenieria")
        candidatos = [
            UsuarioFalso(indice, f"Candidato {indice:02d}", "villa", "ingenieria")
            for indice in range(2, 17)
        ]
        grafo = GrafoAfinidadUPC([origen, *candidatos])
        mejores = rankear_top_candidatos(origen, candidatos, grafo=grafo)

        self.assertEqual(len(mejores), 10)
        self.assertTrue(
            all("proximidad_grafo" in item["componentes"] for item in mejores)
        )
        self.assertTrue(
            all(item["contexto_upc"]["grafo"]["grado"] == 1 for item in mejores)
        )


if __name__ == "__main__":
    unittest.main()
