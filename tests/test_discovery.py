import unittest

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models.entities import Bloqueo, Conexion, Mensaje, Notificacion, Usuario


class DiscoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            'TESTING': True, 'APP_ENV': 'development',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SECRET_KEY': 'discovery-test', 'SYNC_UPC_CATALOG': False,
            'EMAIL_VERIFICATION_REQUIRED': False, 'CSRF_ENABLED': False,
            'SOCKETIO_ASYNC_MODE': 'threading', 'REDIS_URL': None,
        })
        with self.app.app_context():
            for name in ('Ana', 'Bruno', 'Carla'):
                user = Usuario(nombre=name, correo_institucional=f'{name.lower()}@upc.edu.pe')
                user.set_password('test-password')
                db.session.add(user)
            db.session.commit()
        self.client = self.app.test_client()
        self.login(1)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session['usuario_id'] = user_id

    def test_home_enters_personal_panel_and_keeps_explicit_json(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/panel'))
        self.assertIn('metricas', self.client.get('/panel', headers={'Accept':'application/json'}).json)

    def test_plan_is_persisted_without_creating_a_message_or_auto_accepting(self):
        response = self.client.post('/companeros/2/conectar', data={'plan':'social'})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            connection = Conexion.query.one()
            self.assertEqual(connection.plan_tipo, 'social')
            self.assertEqual(connection.plan_tema, 'Conversar y conocerse')
            self.assertEqual(connection.estado, 'pendiente')
            self.assertEqual(Notificacion.query.count(), 1)
        self.client.post('/companeros/2/conectar', data={'plan':'estudio'})
        with self.app.app_context():
            self.assertEqual(Conexion.query.count(), 1)
            self.assertEqual(Conexion.query.one().plan_tipo, 'social')
            self.assertEqual(Notificacion.query.count(), 1)

    def test_invalid_or_stale_plan_cannot_create_connection(self):
        self.assertEqual(self.client.post('/companeros/2/conectar', data={'plan':'invalid'}).status_code, 400)
        self.assertEqual(self.client.post('/companeros/2/conectar', data={
            'plan':'social', 'plan_tema':'Un tema manipulado',
        }).status_code, 409)
        with self.app.app_context():
            self.assertEqual(Conexion.query.count(), 0)

    def test_only_recipient_can_accept_and_retries_do_not_duplicate_alerts(self):
        self.client.post('/companeros/2/conectar', data={'plan':'estudio'})
        self.login(3)
        self.assertEqual(self.client.post('/conexiones/1/aceptar').status_code, 403)
        self.login(2)
        self.client.post('/conexiones/1/aceptar')
        self.client.post('/conexiones/1/aceptar')
        with self.app.app_context():
            self.assertEqual(Conexion.query.one().estado, 'aceptada')
            self.assertEqual(Notificacion.query.count(), 2)

    def test_opposite_invitation_remains_pending_and_json_reports_no_match(self):
        self.client.post('/companeros/2/conectar', data={'plan':'social'})
        self.login(2)
        response = self.client.post('/companeros/1/conectar', data={'plan':'estudio'},
                                    headers={'Accept':'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['match'])
        with self.app.app_context():
            self.assertEqual(Conexion.query.one().remitente_id, 1)
            self.assertEqual(Conexion.query.one().estado, 'pendiente')
            self.assertEqual(Notificacion.query.count(), 1)
            self.assertEqual(Mensaje.query.count(), 0)

    def test_blocked_invitation_cannot_be_accepted_rejected_or_cancelled(self):
        self.client.post('/companeros/2/conectar', data={'plan':'social'})
        with self.app.app_context():
            db.session.add(Bloqueo(bloqueador_id=1, bloqueado_id=2))
            db.session.commit()
        self.login(2)
        for action in ('aceptar', 'rechazar'):
            self.assertEqual(self.client.post(f'/conexiones/1/{action}').status_code, 403)
        self.login(1)
        self.assertEqual(self.client.post('/conexiones/1/cancelar').status_code, 403)
        with self.app.app_context():
            self.assertEqual(Conexion.query.one().estado, 'pendiente')
            self.assertEqual(Notificacion.query.count(), 1)

    def test_notification_storage_failure_rolls_back_invitation(self):
        with self.app.app_context():
            db.session.execute(text("""
                CREATE TRIGGER fail_notification BEFORE INSERT ON notificaciones
                BEGIN SELECT RAISE(ABORT, 'notification storage unavailable'); END
            """))
            db.session.commit()
        with self.assertRaises(IntegrityError):
            self.client.post('/companeros/2/conectar', data={'plan':'social'})
        with self.app.app_context():
            self.assertEqual(Conexion.query.count(), 0)
            self.assertEqual(Notificacion.query.count(), 0)

    def test_enhanced_request_requires_session_and_csrf(self):
        self.app.config['CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/companeros/2/conectar', data={'plan':'social'},
                                         headers={'Accept':'application/json'}).status_code, 400)
        self.app.config['CSRF_ENABLED'] = False
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.post('/companeros/2/conectar', data={'plan':'social'},
                                    headers={'Accept':'application/json'})
        self.assertIn(response.status_code, (302, 401))
        with self.app.app_context():
            self.assertEqual(Conexion.query.count(), 0)

    def test_legacy_invitation_and_acceptance_keep_general_context(self):
        self.client.post('/companeros/2/conectar')
        self.login(2)
        response = self.client.post('/conexiones/1/aceptar', headers={'Accept':'application/json'})
        self.assertTrue(response.json['match'])
        repeat = self.client.post('/conexiones/1/aceptar', headers={'Accept':'application/json'})
        self.assertFalse(repeat.json['match'])
        with self.app.app_context():
            self.assertIsNone(Conexion.query.one().plan_tipo)
            self.assertEqual(Notificacion.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
