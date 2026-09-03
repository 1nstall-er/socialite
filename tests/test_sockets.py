import unittest

from app import create_app
from models import Bloqueo, Conexion, Mensaje, Notificacion, Usuario, db
from sockets import socketio
from verification import completar_verificacion


class SocketSocialiteTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "socket-test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "CSRF_ENABLED": True,
                "EMAIL_VERIFICATION_REQUIRED": True,
                "SYNC_UPC_CATALOG": False,
                "SOCKET_MESSAGE_MAX": 3,
                "SOCKET_MESSAGE_WINDOW_SECONDS": 60,
            }
        )
        with self.app.app_context():
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                carrera="Ingeniería de Software",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                carrera="Ingeniería de Sistemas de Información",
            )
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
            completar_verificacion(ana)
            completar_verificacion(bruno)
            db.session.add_all([ana, bruno])
            db.session.flush()
            db.session.add(
                Conexion(
                    remitente_id=ana.id,
                    destinatario_id=bruno.id,
                    estado="aceptada",
                )
            )
            db.session.commit()
            self.ana_id = ana.id
            self.bruno_id = bruno.id

        self.ana_http = self._cliente_http(self.ana_id, "csrf-ana")
        self.bruno_http = self._cliente_http(self.bruno_id, "csrf-bruno")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _cliente_http(self, usuario_id, csrf_token):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion["usuario_id"] = usuario_id
            sesion["_csrf_token"] = csrf_token
        return cliente

    @staticmethod
    def _eventos(cliente, nombre):
        return [evento for evento in cliente.get_received() if evento["name"] == nombre]

    def test_socket_rechaza_anonimo_token_csrf_invalido_y_no_verificado(self):
        anonimo = socketio.test_client(self.app)
        self.assertFalse(anonimo.is_connected())

        csrf_invalido = socketio.test_client(
            self.app,
            flask_test_client=self.ana_http,
            auth={"csrf_token": "incorrecto"},
        )
        self.assertFalse(csrf_invalido.is_connected())

        with self.app.app_context():
            invitado = Usuario(
                nombre="Invitado",
                correo_institucional="invitado@upc.edu.pe",
            )
            invitado.set_password("segura1234")
            db.session.add(invitado)
            db.session.commit()
            invitado_id = invitado.id
        invitado_http = self._cliente_http(invitado_id, "csrf-invitado")
        no_verificado = socketio.test_client(
            self.app,
            flask_test_client=invitado_http,
            auth={"csrf_token": "csrf-invitado"},
        )
        self.assertFalse(no_verificado.is_connected())

    def test_mensaje_socket_es_atomico_y_notifica_al_destinatario_conectado(self):
        ana_socket = socketio.test_client(
            self.app,
            flask_test_client=self.ana_http,
            auth={"csrf_token": "csrf-ana"},
        )
        bruno_socket = socketio.test_client(
            self.app,
            flask_test_client=self.bruno_http,
            auth={"csrf_token": "csrf-bruno"},
        )
        self.assertTrue(ana_socket.is_connected())
        self.assertTrue(bruno_socket.is_connected())
        ana_socket.get_received()
        bruno_socket.get_received()

        self.assertTrue(
            ana_socket.emit("join_room", {"contacto_id": self.bruno_id}, callback=True)["ok"]
        )
        self.assertTrue(
            bruno_socket.emit("join_room", {"contacto_id": self.ana_id}, callback=True)["ok"]
        )
        respuesta = ana_socket.emit(
            "send_message",
            {"contacto_id": self.bruno_id, "texto": "¿Repasamos algoritmos?"},
            callback=True,
        )
        self.assertTrue(respuesta["ok"])

        eventos_bruno = bruno_socket.get_received()
        nombres = {evento["name"] for evento in eventos_bruno}
        self.assertIn("message_received", nombres)
        self.assertIn("notification_received", nombres)
        notificacion_evento = next(
            evento for evento in eventos_bruno if evento["name"] == "notification_received"
        )
        self.assertEqual(notificacion_evento["args"][0]["total_no_leidas"], 1)

        with self.app.app_context():
            mensaje = Mensaje.query.one()
            notificacion = Notificacion.query.one()
            self.assertEqual(mensaje.texto, "¿Repasamos algoritmos?")
            self.assertEqual(notificacion.mensaje_id, mensaje.id)
            self.assertEqual(notificacion.usuario_id, self.bruno_id)
            self.assertFalse(notificacion.leida)

        pagina_notificaciones = self.bruno_http.get("/notificaciones")
        self.assertEqual(pagina_notificaciones.status_code, 200)
        self.assertIn(
            "¿Repasamos algoritmos?", pagina_notificaciones.get_data(as_text=True)
        )
        api_notificaciones = self.bruno_http.get("/api/v1/notificaciones").get_json()
        self.assertEqual(api_notificaciones["total_no_leidas"], 1)
        self.assertEqual(api_notificaciones["notificaciones"][0]["tipo"], "mensaje")

        lectura = bruno_socket.emit("mark_read", {"contacto_id": self.ana_id}, callback=True)
        self.assertEqual(lectura["mensajes_marcados"], 1)
        self.assertEqual(lectura["notificaciones_marcadas"], 1)
        self.assertEqual(lectura["total_no_leidas"], 0)

    def test_socket_revalida_bloqueos_antes_de_cada_envio(self):
        ana_socket = socketio.test_client(
            self.app,
            flask_test_client=self.ana_http,
            auth={"csrf_token": "csrf-ana"},
        )
        with self.app.app_context():
            db.session.add(Bloqueo(bloqueador_id=self.bruno_id, bloqueado_id=self.ana_id))
            db.session.commit()

        respuesta = ana_socket.emit(
            "send_message",
            {"contacto_id": self.bruno_id, "texto": "No debe persistirse"},
            callback=True,
        )
        self.assertFalse(respuesta["ok"])
        self.assertEqual(respuesta["error"]["codigo"], "interaccion_bloqueada")
        with self.app.app_context():
            self.assertEqual(Mensaje.query.count(), 0)
            self.assertEqual(Notificacion.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
