import unittest
from io import BytesIO
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from PIL import Image
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from matching import (
    calcular_afinidad,
    minutos_compartidos,
    rankear_candidatos_paginado,
)
from models import (
    Bloqueo,
    CampusUPC,
    CarreraUPC,
    Conexion,
    Curso,
    EspacioUPC,
    EstadoReporte,
    EstiloEstudio,
    FacultadUPC,
    Grupo,
    Horario,
    Mensaje,
    MetaCursoUPC,
    ObjetivoSocialite,
    ParticipacionUPC,
    PerfilUPC,
    Reporte,
    RolActividadUPC,
    RolCursoUPC,
    TipoActividadUPC,
    Usuario,
    db,
    sincronizar_catalogo_upc,
)
from verification import completar_verificacion


class FakeS3Client:
    def __init__(self):
        self.uploads: list[dict[str, Any]] = []
        self.deletes: list[dict[str, str]] = []

    def upload_fileobj(self, stream, bucket, key, ExtraArgs):
        self.uploads.append(
            {
                "bytes": stream.read(),
                "bucket": bucket,
                "key": key,
                "args": ExtraArgs,
            }
        )

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)


class SocialiteTestCase(unittest.TestCase):
    def setUp(self):
        self.directorio_temporal = TemporaryDirectory()
        self.s3 = FakeS3Client()
        self.s3_patcher = patch("media.boto3.client", return_value=self.s3)
        self.s3_patcher.start()
        self.addCleanup(self.s3_patcher.stop)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "CSRF_ENABLED": False,
                "AVATAR_UPLOAD_FOLDER": self.directorio_temporal.name,
                "EMAIL_VERIFICATION_REQUIRED": False,
                "MAIL_BACKEND": "memory",
                "AWS_ACCESS_KEY_ID": "test-access-key",
                "AWS_SECRET_ACCESS_KEY": "test-secret-key",
                "AWS_REGION": "us-east-1",
                "AWS_S3_BUCKET": "socialite-test-media",
                "S3_PUBLIC_BASE_URL": "https://media.example.com",
                "S3_AVATAR_PREFIX": "avatars",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.directorio_temporal.cleanup()

    @staticmethod
    def foto_prueba(color=(31, 107, 79), formato="PNG"):
        contenido = BytesIO()
        Image.new("RGB", (420, 300), color).save(contenido, formato)
        contenido.seek(0)
        return contenido, f"perfil.{formato.lower()}"

    def registrar(self, nombre="Ana", correo="ana@upc.edu.pe", password="segura1234"):
        return self.client.post(
            "/registro",
            data={
                "nombre": nombre,
                "correo": correo,
                "password": password,
                "foto": self.foto_prueba(),
                "carrera": "Ingenieria de Software",
                "ciclo": "5",
            },
            follow_redirects=True,
        )

    def test_registro_requiere_correo_upc_y_guarda_password_seguro(self):
        respuesta = self.registrar(correo="ana@gmail.com")
        self.assertIn("Usa tu correo institucional", respuesta.get_data(as_text=True))

        respuesta = self.registrar(correo="ana@externo.com@upc.edu.pe")
        self.assertIn("Usa tu correo institucional", respuesta.get_data(as_text=True))

        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Mi perfil", respuesta.get_data(as_text=True))
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertNotEqual(usuario.password_hash, "segura1234")
            self.assertTrue(usuario.check_password("segura1234"))

    def test_verificacion_de_correo_activa_la_cuenta_con_codigo_de_un_solo_uso(self):
        self.app.config["EMAIL_VERIFICATION_REQUIRED"] = True
        respuesta = self.registrar()
        html = respuesta.get_data(as_text=True)
        self.assertIn("Revisa tu correo", html)
        self.assertIn("ana@upc.edu.pe", html)
        with self.client.session_transaction() as sesion:
            self.assertNotIn("usuario_id", sesion)
            self.assertIn("verificacion_usuario_id", sesion)

        codigo = self.app.extensions["mail_outbox"][-1]["codigo"]
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertFalse(usuario.correo_verificado)
            self.assertNotEqual(usuario.verificacion_codigo_hash, codigo)

        respuesta = self.client.post(
            "/verificar-correo", data={"codigo": "111111"}, follow_redirects=True
        )
        self.assertIn("no coincide", respuesta.get_data(as_text=True))
        respuesta = self.client.post(
            "/verificar-correo", data={"codigo": codigo}, follow_redirects=True
        )
        self.assertIn("Correo UPC verificado", respuesta.get_data(as_text=True))
        with self.client.session_transaction() as sesion:
            self.assertIn("usuario_id", sesion)
            self.assertNotIn("verificacion_usuario_id", sesion)
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertTrue(usuario.correo_verificado)
            self.assertIsNone(usuario.verificacion_codigo_hash)

    def test_registro_renderiza_catalogos_y_guarda_selectores(self):
        pagina = self.client.get("/registro").get_data(as_text=True)
        self.assertIn('name="carrera_upc_id"', pagina)
        self.assertEqual(pagina.count("data-ciclos="), 59)
        self.assertEqual(pagina.count('type="checkbox" name="intereses"'), 50)
        self.assertIn("profile-form.js", pagina)

        with self.app.app_context():
            software_id = CarreraUPC.query.filter_by(
                clave="ingenieria-de-software"
            ).one().id
        respuesta = self.client.post(
            "/registro",
            data={
                "nombre": "Ana",
                "correo": "ana@upc.edu.pe",
                "password": "segura1234",
                "foto": self.foto_prueba(),
                "carrera_upc_id": str(software_id),
                "ciclo": "5",
                "intereses": ["programacion", "musica", "futbol"],
            },
            follow_redirects=True,
        )
        self.assertIn("Mi perfil", respuesta.get_data(as_text=True))
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertEqual(usuario.carrera, "Ingeniería de Software")
            self.assertTrue(usuario.foto_archivo.endswith(".jpg"))
            self.assertEqual(
                usuario.lista_intereses, ["Programación", "Música", "Fútbol"]
            )

    def test_registro_exige_foto_valida_y_la_normaliza(self):
        sin_foto = self.client.post(
            "/registro",
            data={
                "nombre": "Ana",
                "correo": "ana@upc.edu.pe",
                "password": "segura1234",
            },
            follow_redirects=True,
        )
        self.assertIn("Selecciona una foto de perfil", sin_foto.get_data(as_text=True))

        falsa = self.client.post(
            "/registro",
            data={
                "nombre": "Ana",
                "correo": "ana@upc.edu.pe",
                "password": "segura1234",
                "foto": (BytesIO(b"esto no es una imagen"), "foto.jpg"),
            },
            follow_redirects=True,
        )
        self.assertIn("imagen válida", falsa.get_data(as_text=True))

        respuesta = self.registrar()
        self.assertIn("Mi perfil", respuesta.get_data(as_text=True))
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertTrue(
                usuario.foto_archivo.startswith("https://media.example.com/avatars/")
            )
            self.assertEqual(usuario.foto_url, usuario.foto_archivo)
        with Image.open(BytesIO(self.s3.uploads[-1]["bytes"])) as avatar:
            self.assertEqual(avatar.format, "JPEG")
            self.assertEqual(avatar.size, (640, 640))

    def test_perfil_reemplaza_foto_y_elimina_version_anterior(self):
        self.registrar()
        with self.app.app_context():
            anterior = Usuario.query.one().foto_archivo

        respuesta = self.client.post(
            "/perfil",
            data={
                "nombre": "Ana Actualizada",
                "biografia": "Me gustan los proyectos interdisciplinarios.",
                "carrera": "Ingenieria de Software",
                "ciclo": "6",
                "foto": self.foto_prueba(color=(215, 237, 134), formato="JPEG"),
            },
            follow_redirects=True,
        )
        self.assertIn("Perfil actualizado", respuesta.get_data(as_text=True))
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertNotEqual(usuario.foto_archivo, anterior)
            self.assertEqual(
                usuario.biografia, "Me gustan los proyectos interdisciplinarios."
            )
            self.assertTrue(
                usuario.foto_archivo.startswith("https://media.example.com/avatars/")
            )
            self.assertEqual(len(self.s3.uploads), 2)
            self.assertEqual(
                self.s3.deletes,
                [
                    {
                        "Bucket": "socialite-test-media",
                        "Key": anterior.removeprefix("https://media.example.com/"),
                    }
                ],
            )

    def test_usuario_acepta_avatar_https_y_preserva_url_legada(self):
        with self.app.app_context():
            remoto = Usuario(
                nombre="Remota",
                correo_institucional="remota@upc.edu.pe",
                password_hash="hash",
                foto_archivo="https://media.example.com/avatars/" + "a" * 32 + ".jpg",
            )
            self.assertEqual(remoto.foto_url, remoto.foto_archivo)
            legado = Usuario(
                nombre="Legada",
                correo_institucional="legada@upc.edu.pe",
                password_hash="hash",
                foto_archivo="a" * 32 + ".jpg",
            )
            self.assertEqual(
                legado.foto_url, "/media/avatares/" + legado.foto_archivo
            )
            self.assertEqual(Usuario.__table__.c.foto_archivo.type.length, 500)

    def test_registro_compensa_carga_nueva_si_falla_el_commit(self):
        remoto = "https://media.example.com/avatars/" + "b" * 32 + ".jpg"
        with (
            patch("app.upload_image", return_value=remoto),
            patch("app.delete_image") as eliminar,
            patch.object(
                db.session,
                "commit",
                side_effect=SQLAlchemyError("database unavailable"),
            ),
        ):
            respuesta = self.registrar()

        self.assertIn(
            "No pudimos crear tu cuenta", respuesta.get_data(as_text=True)
        )
        eliminar.assert_called_once_with(remoto)
        with self.app.app_context():
            self.assertEqual(Usuario.query.count(), 0)

    def test_perfil_elimina_avatar_anterior_solo_despues_del_commit(self):
        self.registrar()
        with self.app.app_context():
            anterior = Usuario.query.one().foto_archivo

        reemplazo = "https://media.example.com/avatars/" + "d" * 32 + ".jpg"
        eventos: list[str] = []
        commit_real = db.session.commit

        def subir(_archivo):
            eventos.append("upload")
            return reemplazo

        def confirmar():
            eventos.append("commit")
            return commit_real()

        def eliminar(url):
            self.assertEqual(url, anterior)
            eventos.append("delete-old")

        with (
            patch("app.upload_image", side_effect=subir),
            patch("app.delete_image", side_effect=eliminar),
            patch.object(db.session, "commit", side_effect=confirmar),
        ):
            respuesta = self.client.post(
                "/perfil",
                data={
                    "nombre": "Ana Actualizada",
                    "carrera": "Ingenieria de Software",
                    "ciclo": "6",
                    "foto": self.foto_prueba(formato="JPEG"),
                },
                follow_redirects=True,
            )

        self.assertIn("Perfil actualizado", respuesta.get_data(as_text=True))
        self.assertEqual(eventos, ["upload", "commit", "delete-old"])

    def test_perfil_compensa_reemplazo_si_falla_el_commit(self):
        self.registrar()
        with self.app.app_context():
            anterior = Usuario.query.one().foto_archivo

        reemplazo = "https://media.example.com/avatars/" + "e" * 32 + ".jpg"
        with (
            patch("app.upload_image", return_value=reemplazo),
            patch("app.delete_image") as eliminar,
            patch.object(
                db.session,
                "commit",
                side_effect=SQLAlchemyError("database unavailable"),
            ),
        ):
            respuesta = self.client.post(
                "/perfil",
                data={
                    "nombre": "Ana Actualizada",
                    "carrera": "Ingenieria de Software",
                    "ciclo": "6",
                    "foto": self.foto_prueba(formato="JPEG"),
                },
                follow_redirects=True,
            )

        self.assertIn(
            "No pudimos guardar los cambios", respuesta.get_data(as_text=True)
        )
        eliminar.assert_called_once_with(reemplazo)
        with self.app.app_context():
            self.assertEqual(Usuario.query.one().foto_archivo, anterior)

    def test_formularios_rechazan_envios_sin_token_csrf(self):
        self.app.config["CSRF_ENABLED"] = True
        respuesta = self.client.post(
            "/registro",
            data={
                "nombre": "Ana",
                "correo": "ana@upc.edu.pe",
                "password": "segura1234",
            },
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_usuario_puede_salir_y_volver_a_ingresar(self):
        self.registrar()
        self.client.post("/salir")
        respuesta = self.client.get("/perfil")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/ingresar", respuesta.headers["Location"])

        respuesta = self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
            follow_redirects=True,
        )
        self.assertIn("Bienvenido de nuevo", respuesta.get_data(as_text=True))
        with self.client.session_transaction() as sesion:
            self.assertIn("usuario_id", sesion)

    def test_login_limita_tres_fallos_por_ip(self):
        self.registrar()
        self.client.post("/salir")
        for _ in range(3):
            respuesta = self.client.post(
                "/ingresar",
                data={"correo": "ana@upc.edu.pe", "password": "incorrecta1"},
            )
            self.assertEqual(respuesta.status_code, 200)

        bloqueada = self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
        )
        self.assertEqual(bloqueada.status_code, 429)
        self.assertIn("Retry-After", bloqueada.headers)

        permitida = self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
            environ_overrides={"REMOTE_ADDR": "192.0.2.2"},
        )
        self.assertEqual(permitida.status_code, 302)

    def test_perfil_agrega_curso_y_horario(self):
        self.registrar()
        self.client.post(
            "/perfil/cursos",
            data={"codigo": "ma101", "nombre_curso": "Calculo I"},
        )
        self.client.post(
            "/perfil/horarios",
            data={"dia": "Martes", "hora_inicio": "10:00", "hora_fin": "12:00"},
        )
        self.client.post(
            "/perfil/horarios",
            data={"dia": "Martes", "hora_inicio": "25:00", "hora_fin": "26:00"},
        )

        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertEqual(usuario.cursos[0].codigo, "MA101")
            self.assertEqual(usuario.horarios[0].dia, "Martes")
            self.assertEqual(len(usuario.horarios), 1)

    def test_crear_unirse_y_respetar_capacidad_del_grupo(self):
        self.registrar()
        self.client.post(
            "/perfil/cursos",
            data={"codigo": "MA101", "nombre_curso": "Calculo I"},
        )
        with self.app.app_context():
            curso_id = Curso.query.one().id

        respuesta = self.client.post(
            "/grupos",
            data={
                "tipo": "estudio",
                "curso_id": str(curso_id),
                "lugar": "Biblioteca, piso 3",
                "dia": "Martes",
                "hora_inicio": "10:00",
                "hora_fin": "12:00",
                "max_miembros": "2",
            },
            follow_redirects=True,
        )
        self.assertIn("Grupo creado", respuesta.get_data(as_text=True))

        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        respuesta = self.client.post("/grupos/1/unirse", follow_redirects=True)
        self.assertIn("Te uniste", respuesta.get_data(as_text=True))

        self.client.post("/salir")
        self.registrar(nombre="Carla", correo="carla@upc.edu.pe")
        respuesta = self.client.post("/grupos/1/unirse", follow_redirects=True)
        self.assertIn("capacidad maxima", respuesta.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(len(Grupo.query.one().miembros), 2)

    def test_matching_muestra_razones_de_afinidad(self):
        with self.app.app_context():
            curso = Curso(codigo="MA101", nombre="Calculo I")
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                carrera="Software",
                intereses="fotografia, futbol",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                carrera="Sistemas",
                intereses="fotografia, musica",
            )
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
            completar_verificacion(ana)
            completar_verificacion(bruno)
            ana.cursos.append(curso)
            bruno.cursos.append(curso)
            ana.horarios.append(Horario(dia="Lunes", hora_inicio="10:00", hora_fin="12:00"))
            bruno.horarios.append(Horario(dia="Lunes", hora_inicio="11:00", hora_fin="13:00"))
            db.session.add_all([ana, bruno])
            db.session.commit()
            ana_id = ana.id

        with self.client.session_transaction() as sesion:
            sesion["usuario_id"] = ana_id
        respuesta = self.client.get("/companeros")
        pagina = respuesta.get_data(as_text=True)
        self.assertIn("Bruno", pagina)
        self.assertIn("1 curso en común", pagina)
        self.assertIn("1.0 h disponibles juntos", pagina)
        self.assertIn("fotografia", pagina)
        self.assertIn("Probabilidad estimada", pagina)
        self.assertIn("Ver desglose matemático", pagina)
        self.assertIn("Quiero conectar", pagina)
        self.assertIn("Aplicar filtros", pagina)

    def test_matching_fusiona_bloques_y_no_duplica_minutos(self):
        propios = [
            Horario(dia="Lunes", hora_inicio="10:00", hora_fin="12:00"),
            Horario(dia="Lunes", hora_inicio="11:00", hora_fin="13:00"),
        ]
        ajenos = [Horario(dia="Lunes", hora_inicio="11:00", hora_fin="12:00")]
        self.assertEqual(minutos_compartidos(propios, ajenos), 60)

    def test_matching_sin_evidencia_no_inventa_probabilidad(self):
        ana = Usuario(nombre="Ana", correo_institucional="ana@upc.edu.pe")
        bruno = Usuario(nombre="Bruno", correo_institucional="bruno@upc.edu.pe")

        resultado = calcular_afinidad(ana, bruno)

        self.assertEqual(resultado["confianza"], 0)
        self.assertIsNone(resultado["probabilidad_emparejamiento"])
        self.assertEqual(resultado["componentes"], {})

    def test_ranking_paginado_es_estable_y_ajusta_paginas_fuera_de_rango(self):
        principal = Usuario(nombre="Principal", correo_institucional="p@upc.edu.pe")
        candidatos = [
            Usuario(id=indice, nombre=nombre, correo_institucional=f"{indice}@upc.edu.pe")
            for indice, nombre in enumerate(
                ["Eva", "Bruno", "Diana", "Ana", "Carla"], start=1
            )
        ]

        segunda = rankear_candidatos_paginado(
            principal, candidatos, pagina=2, por_pagina=2
        )
        self.assertEqual(segunda["total"], 5)
        self.assertEqual(
            [item["usuario"].nombre for item in segunda["items"]],
            ["Carla", "Diana"],
        )

        ultima = rankear_candidatos_paginado(
            principal, candidatos, pagina=99, por_pagina=2
        )
        self.assertEqual(ultima["pagina"], 3)
        self.assertEqual(
            [item["usuario"].nombre for item in ultima["items"]], ["Eva"]
        )

    def test_matching_entrega_desglose_explicable(self):
        with self.app.app_context():
            curso = Curso(codigo="SW201", nombre="Programacion Web")
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                intereses="fotografia, musica",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                intereses="Fotografía, futbol",
            )
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
            ana.cursos.append(curso)
            bruno.cursos.append(curso)
            ana.horarios.append(
                Horario(dia="Martes", hora_inicio="10:00", hora_fin="12:00")
            )
            bruno.horarios.append(
                Horario(dia="Martes", hora_inicio="10:30", hora_fin="12:30")
            )
            db.session.add_all([ana, bruno])
            db.session.commit()

            resultado = calcular_afinidad(ana, bruno)
            self.assertEqual(resultado["porcentaje"], 70)
            self.assertEqual(resultado["horas"], 1.5)
            self.assertEqual(resultado["intereses"], ["fotografia"])
            self.assertEqual(set(resultado["componentes"]), {"cursos", "horarios", "intereses"})
            self.assertEqual(
                resultado["componentes"]["intereses"]["porcentaje_similitud"],
                36.7,
            )
            self.assertEqual(resultado["probabilidad_emparejamiento"], 63.8)
            self.assertFalse(
                resultado["modelo_probabilidad"]["calibrada_con_datos_historicos"]
            )
            self.assertEqual(
                resultado["intereses_detalle"]["porcentaje_jaccard_exacto"],
                33.3,
            )

    def test_api_companeros_expone_contrato_paginado(self):
        self.registrar()
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        self.client.post("/salir")
        self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
        )

        respuesta = self.client.get("/api/v1/companeros?por_pagina=1")
        datos = respuesta.get_json()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(datos["paginacion"]["por_pagina"], 1)
        self.assertEqual(datos["paginacion"]["total"], 1)
        self.assertIn("componentes", datos["resultados"][0])
        self.assertIn("probabilidad_emparejamiento", datos["resultados"][0])
        self.assertIn("modelo_probabilidad", datos["resultados"][0])
        self.assertNotIn("correo_institucional", datos["resultados"][0]["usuario"])

        top = self.client.get("/api/v1/companeros/top").get_json()
        self.assertEqual(top["algoritmo"]["estructura"], "max_heap")
        self.assertEqual(top["algoritmo"]["grafo_max_grado"], 2)
        self.assertLessEqual(len(top["resultados"]), 10)

    def test_flujo_de_conexion_revela_email_solo_al_aceptar(self):
        self.registrar()
        with self.app.app_context():
            ana_id = Usuario.query.filter_by(correo_institucional="ana@upc.edu.pe").one().id
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        with self.app.app_context():
            bruno_id = Usuario.query.filter_by(correo_institucional="bruno@upc.edu.pe").one().id

        respuesta = self.client.get(f"/personas/{ana_id}")
        self.assertNotIn("correo_institucional", respuesta.get_json()["persona"])
        self.client.post(f"/companeros/{ana_id}/conectar")
        with self.app.app_context():
            conexion_id = Conexion.query.one().id

        self.client.post("/salir")
        self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
        )
        self.client.post(f"/conexiones/{conexion_id}/aceptar")
        respuesta = self.client.get(f"/personas/{bruno_id}")
        self.assertEqual(
            respuesta.get_json()["persona"]["correo_institucional"],
            "bruno@upc.edu.pe",
        )
        conexiones = self.client.get("/conexiones")
        self.assertEqual(conexiones.status_code, 200)
        self.assertIn("Mis contactos", conexiones.get_data(as_text=True))
        self.assertIn("bruno@upc.edu.pe", conexiones.get_data(as_text=True))

    def test_chat_solo_entre_conexiones_y_marca_mensajes_como_leidos(self):
        self.registrar()
        with self.app.app_context():
            ana_id = Usuario.query.one().id
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        with self.app.app_context():
            bruno_id = Usuario.query.filter_by(
                correo_institucional="bruno@upc.edu.pe"
            ).one().id
        self.client.post(f"/companeros/{ana_id}/conectar")
        with self.app.app_context():
            conexion_id = Conexion.query.one().id

        self.client.post("/salir")
        self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
        )
        self.client.post(f"/conexiones/{conexion_id}/aceptar")
        respuesta = self.client.post(
            f"/mensajes/{bruno_id}", data={"texto": "¿Estudiamos mañana?"}
        )
        self.assertEqual(respuesta.status_code, 303)
        with self.app.app_context():
            mensaje = Mensaje.query.one()
            self.assertEqual(mensaje.emisor_id, ana_id)
            self.assertEqual(mensaje.receptor_id, bruno_id)
            self.assertFalse(mensaje.leido)

        self.client.post("/salir")
        self.client.post(
            "/ingresar",
            data={"correo": "bruno@upc.edu.pe", "password": "segura1234"},
        )
        bandeja = self.client.get("/mensajes").get_data(as_text=True)
        self.assertIn("¿Estudiamos mañana?", bandeja)
        chat = self.client.get(f"/mensajes/{ana_id}")
        self.assertIn("¿Estudiamos mañana?", chat.get_data(as_text=True))
        with self.app.app_context():
            mensaje = Mensaje.query.one()
            self.assertTrue(mensaje.leido)
            self.assertIsNotNone(mensaje.leido_en)

    def test_bloqueo_corta_conexion_y_excluye_el_matching(self):
        self.registrar()
        with self.app.app_context():
            ana_id = Usuario.query.filter_by(
                correo_institucional="ana@upc.edu.pe"
            ).one().id
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        self.client.post(f"/companeros/{ana_id}/conectar")

        respuesta = self.client.post(
            f"/personas/{ana_id}/bloquear", follow_redirects=True
        )
        self.assertIn("Bloqueaste a Ana", respuesta.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(Bloqueo.query.count(), 1)
            self.assertEqual(Conexion.query.count(), 0)
        self.assertEqual(
            self.client.get("/api/v1/companeros").get_json()["paginacion"]["total"],
            0,
        )

        with self.app.app_context():
            bloqueo_id = Bloqueo.query.one().id
        self.client.post(f"/bloqueos/{bloqueo_id}/eliminar")
        self.assertEqual(
            self.client.get("/api/v1/companeros").get_json()["paginacion"]["total"],
            1,
        )

    def test_reporte_es_privado_validado_y_no_se_duplica_mientras_esta_abierto(self):
        self.registrar()
        with self.app.app_context():
            ana_id = Usuario.query.one().id
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")

        datos = {"motivo": "acoso", "detalle": "Mensajes insistentes"}
        respuesta = self.client.post(
            f"/personas/{ana_id}/reportar", data=datos, follow_redirects=True
        )
        self.assertIn("Recibimos tu reporte", respuesta.get_data(as_text=True))
        self.client.post(f"/personas/{ana_id}/reportar", data=datos)
        with self.app.app_context():
            self.assertEqual(Reporte.query.count(), 1)
            reporte = Reporte.query.one()
            self.assertEqual(reporte.estado, EstadoReporte.PENDIENTE)
            self.assertEqual(reporte.detalle, "Mensajes insistentes")

    def test_respuestas_incluyen_cabeceras_de_seguridad(self):
        respuesta = self.client.get("/")
        self.assertEqual(respuesta.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", respuesta.headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", respuesta.headers["Content-Security-Policy"])
        self.assertIn(
            "img-src 'self' data: https://media.example.com",
            respuesta.headers["Content-Security-Policy"],
        )

    def test_matching_evitar_n_mas_uno_al_crecer_candidatos(self):
        with self.app.app_context():
            principal = Usuario(
                nombre="Principal",
                correo_institucional="principal@upc.edu.pe",
                intereses="tecnologia",
            )
            principal.set_password("segura1234")
            completar_verificacion(principal)
            db.session.add(principal)
            for indice in range(12):
                candidato = Usuario(
                    nombre=f"Candidato {indice}",
                    correo_institucional=f"candidato{indice}@upc.edu.pe",
                    intereses="tecnologia",
                )
                candidato.set_password("segura1234")
                completar_verificacion(candidato)
                candidato.horarios.append(
                    Horario(
                        dia="Lunes", hora_inicio="10:00", hora_fin="11:00"
                    )
                )
                db.session.add(candidato)
            db.session.commit()
            principal_id = principal.id
            motor = db.engine

        with self.client.session_transaction() as sesion:
            sesion["usuario_id"] = principal_id
        consultas = []

        def registrar_consulta(conn, cursor, sentencia, parametros, contexto, muchos):
            if sentencia.lstrip().upper().startswith("SELECT"):
                consultas.append(sentencia)

        event.listen(motor, "before_cursor_execute", registrar_consulta)
        try:
            respuesta = self.client.get("/api/v1/companeros?por_pagina=12")
        finally:
            event.remove(motor, "before_cursor_execute", registrar_consulta)

        self.assertEqual(respuesta.status_code, 200)
        # Es un número fijo aunque crezca la cantidad de candidatos. Las
        # colecciones se cargan por separado para evitar un producto cartesiano.
        self.assertLessEqual(len(consultas), 12)

    def test_rutas_sin_template_entregan_contrato_json(self):
        self.registrar()
        respuesta = self.client.get("/panel")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["template_pendiente"], "panel.html")
        self.assertIn("metricas", respuesta.get_json())

        respuesta = self.client.get("/grupos/nuevo")
        self.assertEqual(respuesta.get_json()["limites"]["max_miembros"], 12)

    def test_catalogo_upc_verificado_es_idempotente(self):
        respuesta = self.client.get("/api/v1/catalogo-upc")
        catalogo = respuesta.get_json()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            {campus["valor"] for campus in catalogo["campus"]},
            {"monterrico", "villa", "san_isidro", "san_miguel"},
        )
        self.assertEqual(len(catalogo["facultades"]), 13)
        self.assertEqual(len(catalogo["carreras"]), 59)
        self.assertEqual(len(catalogo["ciclos"]), 14)
        self.assertEqual(
            sum(
                len(grupo["carreras"])
                for grupo in catalogo["carreras_por_facultad"]
            ),
            59,
        )
        self.assertIn(
            "Ingeniería de Software",
            {carrera["nombre"] for carrera in catalogo["carreras"]},
        )
        medicina = next(
            carrera
            for carrera in catalogo["carreras"]
            if carrera["clave"] == "medicina"
        )
        software = next(
            carrera
            for carrera in catalogo["carreras"]
            if carrera["clave"] == "ingenieria-de-software"
        )
        self.assertEqual(medicina["duracion_ciclos"], 14)
        self.assertEqual(software["duracion_ciclos"], 10)
        self.assertEqual(len(catalogo["intereses"]), 50)
        self.assertEqual(len(catalogo["intereses_por_categoria"]), 7)
        self.assertEqual(catalogo["limites"]["max_intereses"], 12)
        self.assertEqual(catalogo["viernes_cultural"]["hora_inicio"], "13:00")
        self.assertEqual(catalogo["creditos_extraacademicos_requeridos"], 4)

        with self.app.app_context():
            total_inicial = EspacioUPC.query.count()
            self.assertEqual(total_inicial, 13)
            self.assertEqual(sincronizar_catalogo_upc(), 0)
            self.assertEqual(EspacioUPC.query.count(), total_inicial)
            cubiculo = EspacioUPC.query.filter_by(
                clave="cubiculos-san-isidro-b"
            ).one()
            self.assertEqual(cubiculo.aforo_maximo, 7)
            self.assertEqual(cubiculo.max_minutos_diarios, 120)

    def test_perfil_upc_y_vida_universitaria_exponen_contrato_privado(self):
        self.registrar()
        with self.app.app_context():
            espacio_id = EspacioUPC.query.filter_by(
                clave="cubiculos-san-miguel-a"
            ).one().id
            carrera_id = CarreraUPC.query.filter_by(
                clave="ingenieria-de-software"
            ).one().id

        respuesta = self.client.post(
            "/perfil/upc",
            data={
                "campus": "san_miguel",
                "facultad": "ingenieria",
                "carrera_upc_id": str(carrera_id),
                "ciclo": "5",
                "modalidad": "presencial",
                "objetivo": "proyectos",
                "estilo_estudio": "practico",
                "viernes_cultural_disponible": "si",
                "acepta_intercampus": "1",
                "espacio_preferido_id": str(espacio_id),
                "intereses": ["programacion", "musica"],
            },
            follow_redirects=True,
        )
        self.assertIn("Contexto UPC actualizado", respuesta.get_data(as_text=True))

        respuesta = self.client.post(
            "/perfil/participaciones",
            data={
                "tipo": "grupo_upc",
                "nombre": "Comunidad de Programacion Competitiva",
                "rol": "coordinador",
                "campus": "san_miguel",
                "periodo": "2026-2",
                "creditos_confirmados": "1",
                "activa": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("Actividad UPC agregada", respuesta.get_data(as_text=True))

        contrato = self.client.get("/api/v1/perfil").get_json()["perfil"]
        self.assertEqual(contrato["perfil_upc"]["campus"], "san_miguel")
        self.assertEqual(contrato["ciclo"], 5)
        self.assertEqual(contrato["intereses"], ["Programación", "Música"])
        self.assertEqual(
            [item["clave"] for item in contrato["intereses_detalle"]],
            ["programacion", "musica"],
        )
        self.assertEqual(
            contrato["perfil_upc"]["carrera"]["nombre"],
            "Ingeniería de Software",
        )
        self.assertEqual(
            contrato["perfil_upc"]["espacio_preferido"]["aforo_maximo"], 6
        )
        self.assertEqual(contrato["creditos_extraacademicos"]["confirmados"], 1)
        self.assertEqual(contrato["creditos_extraacademicos"]["pendientes"], 3)
        self.assertEqual(contrato["participaciones_upc"][0]["tipo"], "grupo_upc")

    def test_validaciones_upc_rechazan_periodos_y_prioridades_invalidas(self):
        with self.app.app_context():
            usuario = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
            )
            usuario.set_password("segura1234")
            curso = Curso(codigo="MA420", nombre="Matematica Basica")
            with self.assertRaisesRegex(ValueError, "formato AAAA-1"):
                ParticipacionUPC(
                    usuario=usuario,
                    tipo=TipoActividadUPC.TALLER,
                    nombre="Teatro",
                    rol=RolActividadUPC.PARTICIPANTE,
                    periodo="2026-3",
                )
            with self.assertRaisesRegex(ValueError, "prioridad"):
                MetaCursoUPC(
                    usuario=usuario,
                    curso=curso,
                    rol=RolCursoUPC.REFORZAR,
                    prioridad=6,
                )

    def test_ciclos_dependen_de_la_carrera_e_intereses_son_controlados(self):
        self.registrar()
        with self.app.app_context():
            medicina_id = CarreraUPC.query.filter_by(clave="medicina").one().id
            software_id = CarreraUPC.query.filter_by(
                clave="ingenieria-de-software"
            ).one().id

        respuesta = self.client.post(
            "/perfil/upc",
            data={
                "campus": "villa",
                "carrera_upc_id": str(medicina_id),
                "ciclo": "14",
                "intereses": ["investigacion", "voluntariado"],
            },
            follow_redirects=True,
        )
        self.assertIn("Contexto UPC actualizado", respuesta.get_data(as_text=True))

        respuesta = self.client.post(
            "/perfil/upc",
            data={
                "campus": "san_miguel",
                "carrera_upc_id": str(software_id),
                "ciclo": "11",
            },
            follow_redirects=True,
        )
        self.assertIn("entre 1 y 10", respuesta.get_data(as_text=True))

        respuesta = self.client.post(
            "/perfil",
            data={
                "nombre": "Ana",
                "carrera_upc_id": str(software_id),
                "ciclo": "5",
                "intereses": ["interes inventado"],
            },
            follow_redirects=True,
        )
        self.assertIn("intereses del catálogo", respuesta.get_data(as_text=True))

    def test_matching_upc_activa_senales_contextuales_explicables(self):
        with self.app.app_context():
            espacio = EspacioUPC.query.filter_by(
                clave="cubiculos-san-isidro-b"
            ).one()
            curso = Curso(codigo="MA420", nombre="Matematica Basica")
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                carrera="Ingenieria de Software",
                intereses="programacion, musica",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                carrera="Ingenieria de Sistemas de Informacion",
                intereses="programacion, deporte",
            )
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
            completar_verificacion(ana)
            completar_verificacion(bruno)
            for usuario in (ana, bruno):
                usuario.cursos.append(curso)
                usuario.horarios.append(
                    Horario(
                        dia="Viernes", hora_inicio="13:00", hora_fin="15:00"
                    )
                )
                usuario.perfil_upc = PerfilUPC(
                    campus=CampusUPC.SAN_ISIDRO,
                    facultad=FacultadUPC.INGENIERIA,
                    objetivo=ObjetivoSocialite.PROYECTOS,
                    estilo_estudio=EstiloEstudio.PRACTICO,
                    viernes_cultural_disponible=True,
                    espacio_preferido=espacio,
                )
                usuario.participaciones_upc.append(
                    ParticipacionUPC(
                        tipo=TipoActividadUPC.GRUPO_UPC,
                        nombre="Programacion Competitiva",
                        rol=RolActividadUPC.PARTICIPANTE,
                        campus=CampusUPC.SAN_ISIDRO,
                        periodo="2026-2",
                    )
                )
            ana.metas_curso.append(
                MetaCursoUPC(
                    curso=curso,
                    rol=RolCursoUPC.ENSENAR,
                    prioridad=5,
                    busca_equipo=True,
                )
            )
            bruno.metas_curso.append(
                MetaCursoUPC(
                    curso=curso,
                    rol=RolCursoUPC.REFORZAR,
                    prioridad=5,
                    busca_equipo=True,
                )
            )
            db.session.add_all([ana, bruno])
            db.session.commit()

            resultado = calcular_afinidad(ana, bruno)
            self.assertGreaterEqual(resultado["porcentaje"], 80)
            self.assertEqual(
                set(resultado["componentes"]),
                {
                    "cursos",
                    "horarios",
                    "intereses",
                    "campus",
                    "contexto_academico",
                    "estilo_objetivo",
                    "vida_universitaria",
                    "metas_curso",
                },
            )
            tipos_razon = {razon["tipo"] for razon in resultado["razones"]}
            self.assertIn("viernes_cultural", tipos_razon)
            self.assertIn("metas_curso", tipos_razon)
            self.assertEqual(
                resultado["contexto_upc"]["campus"]["espacio"],
                "Cubículos - Biblioteca Pabellón B",
            )


if __name__ == "__main__":
    unittest.main()
