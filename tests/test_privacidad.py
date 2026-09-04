"""Pruebas del modulo de cumplimiento de datos personales.

Usan unittest para mantener el mismo runner que el resto del proyecto
(python -m unittest discover -s tests). No requieren base de datos: el
modulo de privacidad recibe las entidades por parametro.
"""

import os
import sys
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.privacy_policy import (
    DIAS_GRACIA_ELIMINACION,
    DIAS_RETENCION_REPORTES,
    VERSION_POLITICA_ACTUAL,
    RegistroAcceso,
    anonimizar_usuario,
    exportar_datos_usuario,
    fecha_purga,
    plan_eliminacion,
    purga_vencida,
    reporte_expirado,
    requiere_consentimiento,
)


def usuario_falso():
    """Usuario minimo con la forma que espera el modulo."""
    return SimpleNamespace(
        id=7,
        nombre="Ana",
        correo_institucional="ana@upc.edu.pe",
        biografia="Busco grupo de calculo",
        carrera="Ingenieria de Software",
        ciclo=5,
        creado_en=datetime(2026, 3, 1, tzinfo=UTC),
        foto_archivo="ana.jpg",
        password_hash="hash-secreto",
        lista_intereses=["programacion", "futbol"],
        cursos=[SimpleNamespace(codigo="MA101")],
        horarios=[SimpleNamespace(dia="Martes", hora_inicio="10:00", hora_fin="12:00")],
        activo=True,
    )


class ConsentimientoTest(unittest.TestCase):
    def test_sin_aceptar_nunca_requiere_consentimiento(self):
        self.assertTrue(requiere_consentimiento(None))

    def test_version_vieja_requiere_reaceptar(self):
        self.assertTrue(requiere_consentimiento("2020-01-01"))

    def test_version_vigente_no_requiere_nada(self):
        self.assertFalse(requiere_consentimiento(VERSION_POLITICA_ACTUAL))


class RetencionTest(unittest.TestCase):
    def test_purga_respeta_periodo_de_gracia(self):
        solicitado = datetime(2026, 1, 1, tzinfo=UTC)
        esperado = solicitado + timedelta(days=DIAS_GRACIA_ELIMINACION)
        self.assertEqual(fecha_purga(solicitado), esperado)

    def test_no_purga_antes_del_plazo(self):
        solicitado = datetime.now(UTC)
        self.assertFalse(purga_vencida(solicitado))

    def test_purga_cuando_vencio_el_plazo(self):
        solicitado = datetime.now(UTC) - timedelta(days=DIAS_GRACIA_ELIMINACION + 1)
        self.assertTrue(purga_vencida(solicitado))

    def test_reporte_expira_al_ano(self):
        viejo = datetime.now(UTC) - timedelta(days=DIAS_RETENCION_REPORTES + 1)
        reciente = datetime.now(UTC) - timedelta(days=10)
        self.assertTrue(reporte_expirado(viejo))
        self.assertFalse(reporte_expirado(reciente))


class ExportacionTest(unittest.TestCase):
    def test_exporta_perfil_cursos_y_horarios(self):
        paquete = exportar_datos_usuario(usuario_falso())
        self.assertEqual(paquete["formato"], "socialite-export-v1")
        self.assertEqual(paquete["titular_id"], 7)
        self.assertEqual(paquete["perfil"]["nombre"], "Ana")
        self.assertEqual(paquete["cursos"], ["MA101"])
        self.assertEqual(paquete["horarios"][0]["dia"], "Martes")
        self.assertIn("programacion", paquete["intereses"])

    def test_no_incluye_el_hash_de_la_password(self):
        paquete = exportar_datos_usuario(usuario_falso())
        self.assertNotIn("password_hash", paquete["perfil"])
        self.assertNotIn("hash-secreto", str(paquete))

    def test_solo_exporta_mensajes_propios(self):
        mensajes = [SimpleNamespace(creado_en=datetime.now(UTC), contenido="hola")]
        paquete = exportar_datos_usuario(usuario_falso(), mensajes=mensajes)
        self.assertEqual(len(paquete["mensajes_enviados"]), 1)
        self.assertEqual(paquete["mensajes_enviados"][0]["contenido"], "hola")

    def test_fechas_quedan_serializables(self):
        paquete = exportar_datos_usuario(usuario_falso())
        self.assertIsInstance(paquete["perfil"]["creado_en"], str)


class AnonimizacionTest(unittest.TestCase):
    def test_borra_la_pii_del_titular(self):
        usuario = usuario_falso()
        anonimizar_usuario(usuario, sufijo="7")

        self.assertEqual(usuario.nombre, "Cuenta eliminada")
        self.assertNotIn("ana", usuario.correo_institucional)
        self.assertIsNone(usuario.biografia)
        self.assertIsNone(usuario.foto_archivo)
        self.assertEqual(usuario.password_hash, "")
        self.assertEqual(usuario.lista_intereses, [])
        self.assertFalse(usuario.activo)

    def test_el_correo_resultante_no_es_reidentificable(self):
        usuario = usuario_falso()
        anonimizar_usuario(usuario, sufijo="7")
        self.assertTrue(usuario.correo_institucional.endswith("@invalido.local"))


class PlanEliminacionTest(unittest.TestCase):
    def test_elimina_dependencias_y_anonimiza(self):
        usuario = usuario_falso()
        borrados = []
        dependencias = {
            "mensajes": [SimpleNamespace(id=1), SimpleNamespace(id=2)],
            "conexiones": [SimpleNamespace(id=3)],
        }

        bitacora = plan_eliminacion(usuario, borrados.append, dependencias)

        self.assertEqual(len(borrados), 3)
        self.assertIn("mensajes: 2 registros eliminados", bitacora)
        self.assertIn("conexiones: 1 registros eliminados", bitacora)
        self.assertIn("perfil: PII anonimizada", bitacora)
        self.assertEqual(usuario.nombre, "Cuenta eliminada")

    def test_funciona_sin_dependencias(self):
        usuario = usuario_falso()
        bitacora = plan_eliminacion(usuario, lambda _: None)
        self.assertEqual(bitacora, ["perfil: PII anonimizada"])


class AuditoriaTest(unittest.TestCase):
    def test_registro_es_serializable(self):
        registro = RegistroAcceso(actor_id=1, titular_id=2, recurso="perfil")
        datos = registro.como_dict()
        self.assertEqual(datos["actor_id"], 1)
        self.assertEqual(datos["titular_id"], 2)
        self.assertEqual(datos["recurso"], "perfil")
        self.assertIsInstance(datos["momento"], str)


if __name__ == "__main__":
    unittest.main()
