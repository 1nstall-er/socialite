import unittest

from matching import calcular_afinidad
from models import INTERESES_UPC, Usuario


class InteresesMatchingTestCase(unittest.TestCase):
    @staticmethod
    def usuario(intereses: str) -> Usuario:
        return Usuario(nombre="Prueba", intereses=intereses)

    def test_claves_de_catalogo_comparten_categoria_sin_error(self):
        resultado = calcular_afinidad(
            self.usuario("voluntariado"), self.usuario("impacto-social")
        )
        detalle = resultado["intereses_detalle"]
        self.assertEqual(detalle["jaccard_categorias"], 1.0)
        self.assertEqual(detalle["comparaciones"][0]["porcentaje_similitud"], 25)
        self.assertEqual(detalle["comparaciones"][0]["coincide_con"], "impacto-social")

    def test_clave_y_etiqueta_del_catalogo_son_el_mismo_interes(self):
        for interes in INTERESES_UPC:
            with self.subTest(interes=interes.clave):
                resultado = calcular_afinidad(
                    self.usuario(interes.clave), self.usuario(interes.etiqueta)
                )
                self.assertEqual(
                    resultado["intereses_detalle"]["porcentaje_similitud"], 100.0
                )


if __name__ == "__main__":
    unittest.main()
