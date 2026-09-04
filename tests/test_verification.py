import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.verification import (
    MAX_INTENTOS,
    ResultadoVerificacion,
    completar_verificacion,
    preparar_reto,
    segundos_para_reenviar,
    validar_codigo,
)


@dataclass
class UsuarioFalso:
    id: int = 7
    correo_institucional: str = "u20260001@upc.edu.pe"
    correo_verificado_en: datetime | None = None
    verificacion_codigo_hash: str | None = None
    verificacion_expira_en: datetime | None = None
    verificacion_enviada_en: datetime | None = None
    verificacion_intentos: int = 0


class VerificacionTestCase(unittest.TestCase):
    secreto = "secreto-de-prueba"
    instante = datetime(2026, 9, 2, 16, 0)

    def test_codigo_se_guarda_como_hmac_y_expira(self):
        usuario = UsuarioFalso()
        codigo = preparar_reto(usuario, self.secreto, self.instante)
        self.assertNotEqual(usuario.verificacion_codigo_hash, codigo)
        self.assertEqual(len(usuario.verificacion_codigo_hash or ""), 64)
        self.assertEqual(
            validar_codigo(
                usuario,
                self.secreto,
                codigo,
                self.instante + timedelta(minutes=15),
            ),
            ResultadoVerificacion.EXPIRADO,
        )

    def test_bloquea_el_reto_al_agotar_intentos(self):
        usuario = UsuarioFalso()
        codigo = preparar_reto(usuario, self.secreto, self.instante)
        for _ in range(MAX_INTENTOS):
            resultado = validar_codigo(
                usuario, self.secreto, "999999", self.instante
            )
        self.assertEqual(resultado, ResultadoVerificacion.AGOTADO)
        self.assertEqual(
            validar_codigo(usuario, self.secreto, codigo, self.instante),
            ResultadoVerificacion.AGOTADO,
        )

    def test_reenvio_tiene_cooldown_y_completar_invalida_codigo(self):
        usuario = UsuarioFalso()
        codigo = preparar_reto(usuario, self.secreto, self.instante)
        self.assertEqual(segundos_para_reenviar(usuario, self.instante), 60)
        self.assertEqual(
            segundos_para_reenviar(usuario, self.instante + timedelta(seconds=61)),
            0,
        )
        completar_verificacion(usuario, self.instante)
        self.assertIsNotNone(usuario.correo_verificado_en)
        self.assertIsNone(usuario.verificacion_codigo_hash)
        self.assertEqual(
            validar_codigo(usuario, self.secreto, codigo, self.instante),
            ResultadoVerificacion.EXPIRADO,
        )


if __name__ == "__main__":
    unittest.main()
