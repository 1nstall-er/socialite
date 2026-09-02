import unittest

from auth import crear_limitador_login, registrar_login_fallido
from rate_limit import LimitadorVentanaDeslizante
from verification import crear_limitador_reenvio, limitar_reenvio


class RateLimitTestCase(unittest.TestCase):
    def test_ventana_deslizante_libera_eventos_al_expirar(self):
        limitador = LimitadorVentanaDeslizante(2, 60)
        self.assertTrue(limitador.consultar("ip", consumir=True, instante=0).permitido)
        self.assertTrue(limitador.consultar("ip", consumir=True, instante=1).permitido)
        decision = limitador.consultar("ip", instante=2)
        self.assertFalse(decision.permitido)
        self.assertEqual(decision.reintentar_en, 58)
        self.assertTrue(limitador.consultar("ip", instante=61).permitido)

    def test_login_permite_tres_fallos_por_ip(self):
        limitador = crear_limitador_login()
        for _ in range(3):
            registrar_login_fallido(limitador, "192.0.2.1")
        self.assertFalse(limitador.consultar("192.0.2.1").permitido)
        self.assertTrue(limitador.consultar("192.0.2.2").permitido)

    def test_reenvio_admite_un_evento_por_usuario_e_ip(self):
        limitador = crear_limitador_reenvio()
        self.assertTrue(limitar_reenvio(limitador, 10, "192.0.2.1").permitido)
        self.assertFalse(limitar_reenvio(limitador, 10, "192.0.2.1").permitido)
        self.assertTrue(limitar_reenvio(limitador, 11, "192.0.2.1").permitido)


if __name__ == "__main__":
    unittest.main()
