"""Pruebas del aviso de ingreso al apoderado por WhatsApp (PBI-17).

Ninguna prueba sale a internet: se usa un notificador falso que captura los
mensajes, o se reemplaza la llamada HTTP.
"""

import sqlite3
from datetime import date, datetime, time

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from src.aplicacion.mensajes_apoderado import construir_mensaje_ingreso
from src.dominio.asistencia import Alumno, EstadoAsistencia
from src.infraestructura import whatsapp
from src.infraestructura.base_datos import crear_engine
from src.infraestructura.modelos import (
    AsistenciaModel,
    EstudianteModel,
    NotificacionWhatsappModel,
)
from src.infraestructura.whatsapp import (
    MensajeWhatsApp,
    NotificadorMetaCloud,
    NotificadorSimulado,
    NotificadorTwilio,
    ResultadoEnvio,
    crear_notificador_desde_entorno,
)
from src.presentacion import create_app
from src.presentacion.rutas import enmascarar_celular

CREDENCIALES_ADMIN = {"username": "admin_general", "password": "DemoSavio2026!"}
FECHA_PRUEBA = date(2026, 11, 11)
MOMENTO_PRUEBA = datetime(2026, 11, 11, 7, 10, 0)
CABECERA_FETCH = {"X-Requested-With": "fetch"}

ALUMNO = Alumno(
    id=1,
    codigo="ALU-2026-001",
    dni="70000001",
    nombres="Ana",
    apellidos="Mamani",
    nivel="Primaria",
    grado="1ro",
    seccion="A",
    carnet_codigo="CRN-EDU-70000001",
)


class NotificadorFalso:
    proveedor = "FALSO"

    def __init__(self, falla: bool = False) -> None:
        self.enviados: list[MensajeWhatsApp] = []
        self.falla = falla

    def enviar(self, mensaje: MensajeWhatsApp) -> ResultadoEnvio:
        if self.falla:
            raise RuntimeError("proveedor caído")
        self.enviados.append(mensaje)
        return ResultadoEnvio(estado="ENVIADO", proveedor=self.proveedor, referencia="msg-1")


def _crear_app(tmp_path, notificador):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "clave-de-prueba",
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'demo_test.db').as_posix()}",
            "SEED_DEMO": True,
            "RELOJ": lambda: MOMENTO_PRUEBA,
            "WHATSAPP_NOTIFICADOR": notificador,
        }
    )


@pytest.fixture()
def notificador():
    return NotificadorFalso()


@pytest.fixture()
def app(tmp_path, notificador):
    aplicacion = _crear_app(tmp_path, notificador)
    yield aplicacion
    aplicacion.extensions["colegio_engine"].dispose()


@pytest.fixture()
def client(app):
    cliente = app.test_client()
    cliente.post("/login", data=CREDENCIALES_ADMIN, follow_redirects=True)
    return cliente


@pytest.fixture()
def db(app):
    engine = create_engine(app.config["DATABASE_URL"])
    with Session(engine) as sesion:
        yield sesion
    engine.dispose()


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


# ----------------------------------------------------------------------
# Mensaje
# ----------------------------------------------------------------------
def test_mensaje_puntual_indica_ingreso_y_hora() -> None:
    texto, variables = construir_mensaje_ingreso(
        ALUMNO, "Rosa Mamani", FECHA_PRUEBA, time(7, 8), EstadoAsistencia.PUNTUAL, 0
    )
    assert "Estimado(a) Rosa Mamani" in texto
    assert "Ana Mamani" in texto
    assert "ya ingresó al colegio hoy 11/11/2026 a las 07:08" in texto
    assert "Estado: Puntual" in texto
    assert variables == ("Ana Mamani", "11/11/2026", "07:08", "Puntual")


def test_mensaje_con_tardanza_indica_minutos() -> None:
    texto, _ = construir_mensaje_ingreso(
        ALUMNO, None, FECHA_PRUEBA, time(7, 25), EstadoAsistencia.TARDANZA, 10
    )
    assert "Estimado(a) apoderado(a)" in texto
    assert "a las 07:25" in texto
    assert "Tardanza (10 min)" in texto


def test_celular_enmascarado_oculta_los_digitos_centrales() -> None:
    assert enmascarar_celular("+51912345678") == "+51 912 *** 678"
    assert enmascarar_celular(None) == "—"


# ----------------------------------------------------------------------
# Selección de proveedor y adaptadores
# ----------------------------------------------------------------------
def test_proveedor_por_defecto_es_simulado() -> None:
    assert isinstance(crear_notificador_desde_entorno({}), NotificadorSimulado)


def test_proveedor_meta_sin_credenciales_vuelve_a_simulado() -> None:
    notificador = crear_notificador_desde_entorno({"WHATSAPP_PROVEEDOR": "meta"})
    assert isinstance(notificador, NotificadorSimulado)


def test_proveedores_reales_se_eligen_con_sus_variables() -> None:
    meta = crear_notificador_desde_entorno(
        {
            "WHATSAPP_PROVEEDOR": "meta",
            "META_WHATSAPP_TOKEN": "token-prueba",
            "META_WHATSAPP_PHONE_NUMBER_ID": "123",
        }
    )
    twilio = crear_notificador_desde_entorno(
        {
            "WHATSAPP_PROVEEDOR": "twilio",
            "TWILIO_ACCOUNT_SID": "AC-prueba",
            "TWILIO_AUTH_TOKEN": "token-prueba",
            "TWILIO_WHATSAPP_FROM": "+14155238886",
        }
    )
    assert isinstance(meta, NotificadorMetaCloud)
    assert isinstance(twilio, NotificadorTwilio)


def test_meta_con_plantilla_envia_las_variables_del_aviso() -> None:
    notificador = NotificadorMetaCloud("token", "123", plantilla="ingreso_alumno")
    cuerpo = notificador.construir_cuerpo(
        MensajeWhatsApp("+51912345678", "texto", ("Ana", "11/11/2026", "07:08", "Puntual"))
    )
    assert cuerpo["to"] == "51912345678"
    assert cuerpo["template"]["name"] == "ingreso_alumno"
    parametros = cuerpo["template"]["components"][0]["parameters"]
    assert [p["text"] for p in parametros] == ["Ana", "11/11/2026", "07:08", "Puntual"]


def test_fallo_http_del_proveedor_se_reporta_como_error(monkeypatch) -> None:
    def publicar_con_error(*_args, **_kwargs):
        raise OSError("sin conexión")

    monkeypatch.setattr(whatsapp, "_publicar", publicar_con_error)
    resultado = NotificadorTwilio("AC", "token", "+14155238886").enviar(
        MensajeWhatsApp("+51912345678", "hola")
    )
    assert resultado.estado == "ERROR"
    assert "sin conexión" in resultado.detalle


# ----------------------------------------------------------------------
# Integración con el registro de asistencia
# ----------------------------------------------------------------------
def test_registro_por_carnet_envia_whatsapp_al_apoderado(client, db, notificador) -> None:
    alumno = alumno_sin_asistencia_hoy(db)
    respuesta = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        headers=CABECERA_FETCH,
    )
    datos = respuesta.get_json()
    assert datos["ok"] is True
    assert datos["whatsapp"]["estado"] == "ENVIADO"
    assert datos["whatsapp"]["apoderado"] == alumno.apoderado_nombre

    assert len(notificador.enviados) == 1
    enviado = notificador.enviados[0]
    assert enviado.destino == alumno.apoderado_celular
    assert f"{alumno.nombres} {alumno.apellidos}" in enviado.texto
    assert "ya ingresó al colegio" in enviado.texto
    assert "a las 07:10" in enviado.texto

    db.expire_all()
    aviso = db.scalars(
        select(NotificacionWhatsappModel).where(
            NotificacionWhatsappModel.estudiante_id == alumno.id
        )
    ).one()
    assert aviso.estado == "ENVIADO"
    assert aviso.destino == alumno.apoderado_celular


def test_registro_por_dni_tambien_envia_whatsapp(client, db, notificador) -> None:
    alumno = alumno_sin_asistencia_hoy(db)
    client.post(
        "/asistencia/registrar",
        data={"metodo": "MANUAL_DNI", "identificador": alumno.dni},
        headers=CABECERA_FETCH,
    )
    assert [m.destino for m in notificador.enviados] == [alumno.apoderado_celular]


def test_registro_duplicado_no_reenvia_whatsapp(client, db, notificador) -> None:
    alumno = alumno_sin_asistencia_hoy(db)
    datos = {"metodo": "CARNET", "identificador": alumno.carnet_codigo}
    client.post("/asistencia/registrar", data=datos, headers=CABECERA_FETCH)
    segunda = client.post("/asistencia/registrar", data=datos, headers=CABECERA_FETCH)
    assert segunda.get_json()["ok"] is False
    assert len(notificador.enviados) == 1


def test_alumno_sin_celular_queda_registrado_sin_envio(client, db, notificador) -> None:
    alumno = alumno_sin_asistencia_hoy(db)
    alumno.apoderado_celular = None
    db.commit()

    datos = client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        headers=CABECERA_FETCH,
    ).get_json()
    assert datos["ok"] is True
    assert datos["whatsapp"]["estado"] == "SIN_CONTACTO"
    assert notificador.enviados == []


def test_falla_del_proveedor_no_impide_registrar_asistencia(tmp_path) -> None:
    aplicacion = _crear_app(tmp_path, NotificadorFalso(falla=True))
    try:
        cliente = aplicacion.test_client()
        cliente.post("/login", data=CREDENCIALES_ADMIN, follow_redirects=True)
        engine = create_engine(aplicacion.config["DATABASE_URL"])
        with Session(engine) as sesion:
            alumno = alumno_sin_asistencia_hoy(sesion)
            datos = cliente.post(
                "/asistencia/registrar",
                data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
                headers=CABECERA_FETCH,
            ).get_json()
            assert datos["ok"] is True
            assert datos["whatsapp"] is None
            sesion.expire_all()
            registro = sesion.scalars(
                select(AsistenciaModel).where(
                    AsistenciaModel.estudiante_id == alumno.id,
                    AsistenciaModel.fecha_escolar == FECHA_PRUEBA,
                )
            ).one()
            assert registro.estado == "PUNTUAL"
        engine.dispose()
    finally:
        aplicacion.extensions["colegio_engine"].dispose()


def test_pantalla_de_asistencia_muestra_bandeja_de_avisos(client, db) -> None:
    alumno = alumno_sin_asistencia_hoy(db)
    client.post(
        "/asistencia/registrar",
        data={"metodo": "CARNET", "identificador": alumno.carnet_codigo},
        headers=CABECERA_FETCH,
    )
    texto = client.get("/asistencia").get_data(as_text=True)
    assert "Avisos por WhatsApp a apoderados" in texto
    assert "ya ingresó al colegio" in texto
    assert enmascarar_celular(alumno.apoderado_celular) in texto


# ----------------------------------------------------------------------
# Base de datos existente
# ----------------------------------------------------------------------
def test_base_anterior_recibe_columnas_del_apoderado(tmp_path) -> None:
    ruta = tmp_path / "antigua.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        "CREATE TABLE estudiantes (id INTEGER PRIMARY KEY, codigo VARCHAR(20), "
        "dni VARCHAR(8), nombres VARCHAR(100), apellidos VARCHAR(100), nivel VARCHAR(20), "
        "grado VARCHAR(20), seccion VARCHAR(5), carnet_codigo VARCHAR(50), "
        "estado VARCHAR(20), creado_en DATETIME)"
    )
    conexion.commit()
    conexion.close()

    engine = crear_engine(f"sqlite:///{ruta.as_posix()}")
    columnas = {c["name"] for c in inspect(engine).get_columns("estudiantes")}
    engine.dispose()
    assert {"apoderado_nombre", "apoderado_celular"} <= columnas
