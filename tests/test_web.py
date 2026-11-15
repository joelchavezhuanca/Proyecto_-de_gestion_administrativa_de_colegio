"""Pruebas de integración de las interfaces web Flask.

Verifican que la presentación reutiliza los servicios de dominio y que las
operaciones protegidas respetan la matriz RBAC existente.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.infraestructura.modelos import (
    AsistenciaModel,
    CierreDiarioModel,
    ConfiguracionModel,
    EstudianteModel,
    JustificacionModel,
    UsuarioModel,
)
from src.presentacion import create_app

CREDENCIALES_ADMIN = {"username": "admin_general", "password": "DemoSavio2026!"}
CREDENCIALES_COORD = {"username": "coord_secundaria", "password": "DemoSavio2026!"}
FECHA_PRUEBA = date(2026, 11, 11)
MOMENTO_PRUEBA = datetime(2026, 11, 11, 7, 10, 0)


@pytest.fixture()
def app(tmp_path):
    base_datos = tmp_path / "demo_test.db"
    aplicacion = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "clave-de-prueba",
            "DATABASE_URL": f"sqlite:///{base_datos.as_posix()}",
            "SEED_DEMO": True,
            "RELOJ": lambda: MOMENTO_PRUEBA,
        }
    )
    yield aplicacion
    aplicacion.extensions["colegio_engine"].dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app) -> Session:
    engine = create_engine(app.config["DATABASE_URL"])
    with Session(engine) as sesion:
        yield sesion
    engine.dispose()


def iniciar_sesion(client, credenciales=None):
    return client.post(
        "/login",
        data=credenciales or CREDENCIALES_ADMIN,
        follow_redirects=True,
    )


def alumno_sin_asistencia_hoy(db: Session) -> EstudianteModel:
    registrados = set(
        db.scalars(
            select(AsistenciaModel.estudiante_id).where(
                AsistenciaModel.fecha_escolar == FECHA_PRUEBA
            )
        ).all()
    )
    alumnos = db.scalars(select(EstudianteModel).order_by(EstudianteModel.id)).all()
    return next(alumno for alumno in alumnos if alumno.id not in registrados)


def test_ruta_protegida_redirige_al_login(client) -> None:
    respuesta = client.get("/aforo")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_login_con_credenciales_invalidas_muestra_banner(client) -> None:
    respuesta = client.post(
        "/login",
        data={"username": "admin_general", "password": "incorrecta"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Credenciales incorrectas" in respuesta.get_data(as_text=True)
    assert "admin_general" in respuesta.get_data(as_text=True)


def test_login_admin_accede_al_dashboard(client) -> None:
    respuesta = iniciar_sesion(client)
    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    assert "Dashboard de aforo" in texto
    assert "Matriculados" in texto


def test_registro_puntual_por_carnet_persiste_asistencia(client, db) -> None:
    iniciar_sesion(client)
    alumno = alumno_sin_asistencia_hoy(db)
    respuesta = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "PUNTUAL" in respuesta.get_data(as_text=True)

    db.expire_all()
    registro = db.scalars(
        select(AsistenciaModel).where(
            AsistenciaModel.estudiante_id == alumno.id,
            AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
        )
    ).first()
    assert registro is not None
    assert registro.estado == "PUNTUAL"
    assert registro.metodo == "CARNET"


def test_vista_normal_de_asistencia_no_muestra_motivo_de_correccion(client) -> None:
    iniciar_sesion(client)
    texto = client.get("/asistencia").get_data(as_text=True)
    assert 'name="motivo"' not in texto
    assert "data-camara-select" in texto
    assert "html5-qrcode.min.js" in texto


def test_libreria_qr_se_sirve_localmente(client) -> None:
    respuesta = client.get("/static/js/vendor/html5-qrcode.min.js")
    assert respuesta.status_code == 200
    assert len(respuesta.data) > 100_000


def test_registro_por_fetch_devuelve_json_de_confirmacion(client, db) -> None:
    iniciar_sesion(client)
    alumno = alumno_sin_asistencia_hoy(db)
    respuesta = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        headers={"X-Requested-With": "fetch"},
    )
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["ok"] is True
    assert datos["estado"] == "PUNTUAL"
    assert datos["alumno"]["codigo"] == alumno.codigo


def test_correccion_de_ausente_exige_motivo_y_actualiza_estado(client, db) -> None:
    iniciar_sesion(client)
    ausencia = db.scalars(
        select(AsistenciaModel).where(
            AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
            AsistenciaModel.estado == "AUSENTE",
        )
    ).first()
    alumno = db.get(EstudianteModel, ausencia.estudiante_id)

    primera = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        headers={"X-Requested-With": "fetch"},
    )
    assert primera.status_code == 409
    contexto = primera.get_json()
    assert contexto["requiere_motivo"] is True
    assert contexto["asistencia"]["estado"] == "AUSENTE"

    correccion = client.post(
        "/asistencia/registrar",
        data={
            "metodo": "CARNET",
            "identificador": alumno.carnet_codigo,
            "motivo": "Olvido de carnet al ingresar",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert correccion.status_code == 200
    assert correccion.get_json()["ok"] is True

    db.expire_all()
    actualizada = db.get(AsistenciaModel, ausencia.id)
    assert actualizada.estado in ("PUNTUAL", "TARDANZA")
    assert actualizada.estado_anterior == "AUSENTE"
    assert actualizada.motivo_correccion == "Olvido de carnet al ingresar"


def test_formulario_html_muestra_correccion_solo_para_ausente(client, db) -> None:
    iniciar_sesion(client)
    ausencia = db.scalars(
        select(AsistenciaModel).where(
            AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
            AsistenciaModel.estado == "AUSENTE",
        )
    ).first()
    alumno = db.get(EstudianteModel, ausencia.estudiante_id)

    respuesta = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert 'id="motivo-correccion"' in texto
    assert 'name="motivo"' in texto


def test_registro_duplicado_muestra_advertencia(client, db) -> None:
    iniciar_sesion(client)
    existente = db.scalars(
        select(AsistenciaModel).where(
            AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
            AsistenciaModel.estado.in_(["PUNTUAL", "TARDANZA"]),
        )
    ).first()
    assert existente is not None
    alumno = db.get(EstudianteModel, existente.estudiante_id)
    respuesta = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "ya cuenta con asistencia" in respuesta.get_data(as_text=True)


def test_justificaciones_solo_para_roles_gestores(client) -> None:
    iniciar_sesion(client, CREDENCIALES_COORD)
    respuesta = client.get("/justificaciones")
    assert respuesta.status_code == 403


def test_wizard_de_justificaciones_incluye_tarjeta_de_contexto(client, db) -> None:
    iniciar_sesion(client)
    texto = client.get("/justificaciones?fecha=2026-11-11").get_data(as_text=True)
    assert "data-tarjeta-contexto" in texto
    assert "data-nombre=" in texto
    assert "data-salon=" in texto
    assert "data-estado=\"AUSENTE\"" in texto


def test_admin_registra_justificacion_medica(client, db) -> None:
    iniciar_sesion(client)
    ausencia = db.scalars(
        select(AsistenciaModel).where(
            AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
            AsistenciaModel.estado == "AUSENTE",
        )
    ).first()
    assert ausencia is not None
    respuesta = client.post(
        "/justificaciones/registrar",
        data={
            "asistencia_id": ausencia.id,
            "categoria": "MEDICA",
            "fecha_solicitud": FECHA_PRUEBA.isoformat(),
            "motivo": "Reposo médico certificado por pediatría",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "JUSTIFICADO" in respuesta.get_data(as_text=True)

    db.expire_all()
    actualizada = db.get(AsistenciaModel, ausencia.id)
    assert actualizada.estado == "JUSTIFICADO"
    assert actualizada.estado_anterior == "AUSENTE"
    assert db.scalars(select(JustificacionModel)).first() is not None


def test_gestion_usuarios_es_exclusiva_de_admin(client) -> None:
    iniciar_sesion(client, CREDENCIALES_COORD)
    respuesta = client.get("/usuarios")
    assert respuesta.status_code == 403


def test_admin_crea_usuario_con_password_hasheada(client, db) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/nuevo",
        data={
            "nombre_completo": "Usuario de Prueba",
            "username": "usuario_prueba",
            "rol": "ADMIN_STAFF",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "estado": "ACTIVO",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Usuario de Prueba" in respuesta.get_data(as_text=True)

    db.expire_all()
    creado = db.scalars(
        select(UsuarioModel).where(UsuarioModel.username == "usuario_prueba")
    ).first()
    assert creado is not None
    assert creado.password_hash != "ClaveSegura123"
    assert creado.salt


def test_cierre_diario_persiste_ausencias_y_evento(client, db) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/aforo/cierre",
        data={"confirmo": "si"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    db.expire_all()
    assert db.scalars(select(CierreDiarioModel)).first() is not None
    assert (
        db.scalars(
            select(AsistenciaModel).where(
                AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
                AsistenciaModel.motivo_correccion == "CIERRE_AUTOMATICO_JORNADA",
            )
        ).first()
        is not None
    )


def test_configurar_hora_cierre_es_exclusivo_de_admin(client) -> None:
    iniciar_sesion(client, CREDENCIALES_COORD)
    respuesta = client.post("/aforo/hora-cierre", data={"hora_cierre": "08:45"})
    assert respuesta.status_code == 403


def test_coordinador_no_puede_ejecutar_cierre(client) -> None:
    iniciar_sesion(client, CREDENCIALES_COORD)
    respuesta = client.post("/aforo/cierre", data={"confirmo": "si"})
    assert respuesta.status_code == 403


def test_admin_configura_hora_de_cierre(client, db) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/aforo/hora-cierre", data={"hora_cierre": "08:45"}, follow_redirects=True
    )
    assert respuesta.status_code == 200
    assert "08:45" in respuesta.get_data(as_text=True)

    db.expire_all()
    configuracion = db.get(ConfiguracionModel, "hora_cierre")
    assert configuracion is not None
    assert configuracion.valor == "08:45"


def test_admin_edita_datos_y_rol_de_usuario(client, db) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/2/editar",
        data={"nombre_completo": "Coordinación Actualizada", "rol": "COORDINADOR"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Coordinación Actualizada" in respuesta.get_data(as_text=True)

    db.expire_all()
    usuario = db.get(UsuarioModel, 2)
    assert usuario.nombre_completo == "Coordinación Actualizada"
    assert usuario.rol == "COORDINADOR"


def test_admin_restablece_password_sin_ver_la_anterior(client, db) -> None:
    from src.dominio.usuarios import verificar_password

    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/3/password",
        data={"password": "NuevaClave2026", "password_confirm": "NuevaClave2026"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "credencial de la cuenta 'jluna_qa' se restableció" in (
        respuesta.get_data(as_text=True).lower()
    )

    db.expire_all()
    usuario = db.get(UsuarioModel, 3)
    assert usuario is not None
    assert verificar_password("NuevaClave2026", usuario.password_hash, usuario.salt or "")


def assert_modal_confirmacion(html: str, mensaje: str) -> None:
    """Comprueba el modal de confirmación y que el mensaje no se duplique como alerta."""
    assert "data-modal-confirmacion" in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="modal-confirmacion-titulo"' in html
    assert "Entendido" in html
    assert mensaje in html
    assert html.count(mensaje) == 1


def test_crear_usuario_redirige_al_listado_y_muestra_modal(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/nuevo",
        data={
            "nombre_completo": "Cuenta Modal",
            "username": "cuenta_modal",
            "rol": "ADMIN_STAFF",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "estado": "ACTIVO",
        },
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios")

    html = client.get("/usuarios").get_data(as_text=True)
    assert_modal_confirmacion(html, "La cuenta 'cuenta_modal' se creó correctamente.")


def test_crear_usuario_con_error_conserva_el_formulario(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/nuevo",
        data={
            "nombre_completo": "Cuenta Fallida",
            "username": "cuenta_fallida",
            "rol": "ADMIN_STAFF",
            "password": "ClaveSegura123",
            "password_confirm": "OtraClave456",
            "estado": "ACTIVO",
        },
    )
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "Las contraseñas no coinciden." in html
    assert 'value="Cuenta Fallida"' in html
    assert 'value="cuenta_fallida"' in html
    assert "data-modal-confirmacion" not in html


def test_editar_usuario_redirige_al_listado_y_muestra_modal(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/2/editar",
        data={"nombre_completo": "Coordinación Modal", "rol": "COORDINADOR"},
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios")

    html = client.get("/usuarios").get_data(as_text=True)
    assert_modal_confirmacion(
        html, "La cuenta 'coord_secundaria' se actualizó correctamente."
    )


def test_editar_usuario_con_nombre_vacio_permanece_en_detalle(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/2/editar",
        data={"nombre_completo": "   ", "rol": "COORDINADOR"},
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios/2")


def test_editar_usuario_con_rol_invalido_permanece_en_detalle(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/2/editar",
        data={"nombre_completo": "Coordinación Académica", "rol": "SUPERADMIN"},
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios/2")


def test_cambiar_estado_redirige_al_listado_y_muestra_modal(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post("/usuarios/3/estado", data={"nuevo_estado": "INACTIVO"})
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios")

    html = client.get("/usuarios").get_data(as_text=True)
    assert_modal_confirmacion(html, "El estado de la cuenta 'jluna_qa' cambió a INACTIVO.")


def test_cambiar_estado_invalido_permanece_en_detalle(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post("/usuarios/3/estado", data={"nuevo_estado": "SUSPENDIDO"})
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios/3")


def test_restablecer_password_redirige_al_listado_y_muestra_modal(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/3/password",
        data={"password": "NuevaClave2026", "password_confirm": "NuevaClave2026"},
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios")

    html = client.get("/usuarios").get_data(as_text=True)
    assert_modal_confirmacion(
        html, "La credencial de la cuenta 'jluna_qa' se restableció correctamente."
    )


def test_restablecer_password_con_error_permanece_en_detalle(client) -> None:
    iniciar_sesion(client)
    respuesta = client.post(
        "/usuarios/3/password",
        data={"password": "NuevaClave2026", "password_confirm": "OtraClave2026"},
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/usuarios/3")


def test_mensajes_normales_siguen_apareciendo_en_el_flash_stack(client) -> None:
    html = iniciar_sesion(client).get_data(as_text=True)
    assert "Bienvenido(a), admin_general." in html
    assert "data-modal-confirmacion" not in html


def test_anular_justificacion_restaura_estado_anterior(client, db) -> None:
    iniciar_sesion(client)
    justificacion = db.scalars(
        select(JustificacionModel).where(JustificacionModel.estado == "APROBADA")
    ).first()
    assert justificacion is not None
    asistencia_id = justificacion.asistencia_id
    codigo = justificacion.codigo

    respuesta = client.post(f"/justificaciones/{codigo}/anular", follow_redirects=True)
    assert respuesta.status_code == 200
    assert "se anuló" in respuesta.get_data(as_text=True)

    db.expire_all()
    asistencia = db.get(AsistenciaModel, asistencia_id)
    assert asistencia.estado in ("AUSENTE", "TARDANZA")
    anulada = db.scalars(
        select(JustificacionModel).where(JustificacionModel.codigo == codigo)
    ).first()
    assert anulada.estado == "RECHAZADA"


def test_fecha_de_justificacion_futura_es_rechazada(client, db) -> None:
    iniciar_sesion(client)
    ausencia = db.scalars(
        select(AsistenciaModel).where(
            AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
            AsistenciaModel.estado == "AUSENTE",
        )
    ).first()
    manana = date.fromordinal(FECHA_PRUEBA.toordinal() + 1)
    respuesta = client.post(
        "/justificaciones/registrar",
        data={
            "asistencia_id": ausencia.id,
            "categoria": "OTRA",
            "fecha_solicitud": manana.isoformat(),
            "motivo": "Motivo suficientemente largo para la prueba",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "fecha futura" in respuesta.get_data(as_text=True)
