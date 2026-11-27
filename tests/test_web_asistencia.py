"""Pruebas de integración Flask del módulo web de Asistencia (PBI-01, PBI-03, PBI-04).

Cubren, contra los servicios de aplicación reales sobre SQLite temporal:
- Éxito de cada caso de uso (HTML con PRG y JSON).
- Validación de errores de entrada y de dominio → HTTP 400/404/409 con flash.
- Protección CSRF en todos los POST.
- 401 sin sesión y 403 con roles base y personalizados.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from io import BytesIO

import pytest
from flask import Flask, g
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.aplicacion.servicios_asistencia import ServicioAsistencia
from src.aplicacion.servicios_seguridad import ServicioSeguridad
from src.dominio.aforo import CierreYaEjecutadoException, PermisoAforoException
from src.dominio.asistencia import (
    AlumnoNoEncontradoException,
    DniInvalidoException,
    RegistroDuplicadoException,
)
from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.justificaciones import PermisoJustificacionException
from src.dominio.usuarios import (
    AccesoDenegadoException,
    EstadoUsuario,
    PermisoOperacion,
    SesionUsuario,
    Usuario,
    hashear_password,
)
from src.infraestructura.base_datos import crear_motor, crear_session_factory, inicializar_bd
from src.infraestructura.modelos import (
    ApoderadoModel,
    AsistenciaModel,
    ConfiguracionSistemaModel,
    EstudianteApoderadoModel,
    EstudianteModel,
    JustificacionModel,
    PeriodoAcademicoModel,
    RolModel,
    UsuarioModel,
)
from src.presentacion.app import crear_app
from src.presentacion.bp_asistencia import (
    EXTENSION_SERVICIO_ASISTENCIA,
    MENSAJE_NO_ENCONTRADO,
    MENSAJE_PROHIBIDO,
    SolicitudInvalidaError,
    registrar_modulo_asistencia,
    traducir_error,
)

FabricaSesiones = sessionmaker[Session]
RELOJ = datetime(2026, 11, 26, 7, 5, 0, tzinfo=ZONA_HORARIA_LIMA)
FECHA = RELOJ.date()
CSRF = "token-csrf-de-prueba"
CARNET = "CRN-72945734"
DNI = "72945734"


# ---------------------------------------------------------------------------
# Siembra de datos
# ---------------------------------------------------------------------------


def _crear_usuario(fabrica: FabricaSesiones, username: str, rol: str) -> Usuario:
    password_hash, salt = hashear_password("Clave12345")
    with fabrica() as session:
        rol_modelo = session.scalars(select(RolModel).filter_by(codigo=rol)).one()
        modelo = UsuarioModel(
            username=username,
            nombre_completo=f"Usuario {username}",
            password_hash=password_hash,
            salt=salt,
            rol=rol,
            rol_id=rol_modelo.id,
            estado="ACTIVO",
            activo=True,
        )
        session.add(modelo)
        session.commit()
        session.refresh(modelo)
        return Usuario(
            id=modelo.id,
            username=username,
            password_hash=password_hash,
            salt=salt,
            nombre_completo=modelo.nombre_completo,
            rol=rol,
        )


def _crear_alumno(
    fabrica: FabricaSesiones,
    *,
    codigo: str = "ALU-2026-001",
    dni: str = DNI,
    carnet: str = CARNET,
    nombres: str = "Eduardo",
    apellidos: str = "Luna Lezano",
) -> int:
    with fabrica() as session:
        modelo = EstudianteModel(
            codigo=codigo,
            dni=dni,
            nombres=nombres,
            apellidos=apellidos,
            fecha_nacimiento=date(2015, 4, 12),
            nivel="Primaria",
            grado="3ro",
            seccion="A",
            carnet_codigo=carnet,
            estado="ACTIVO",
        )
        session.add(modelo)
        session.flush()
        apoderado = ApoderadoModel(
            nombres="Rosa",
            apellidos="Lezano",
            documento=f"DOC-{dni}",
            parentesco="MADRE",
            telefono_whatsapp="+51987654321",
            activo=True,
        )
        session.add(apoderado)
        session.flush()
        session.add(
            EstudianteApoderadoModel(
                estudiante_id=modelo.id, apoderado_id=apoderado.id, es_principal=True
            )
        )
        session.commit()
        return modelo.id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fabrica(tmp_path) -> Iterator[FabricaSesiones]:  # noqa: ANN001
    motor = crear_motor(f"sqlite:///{(tmp_path / 'web.db').as_posix()}")
    inicializar_bd(motor)
    try:
        yield crear_session_factory(motor)
    finally:
        motor.dispose()


@pytest.fixture
def usuarios(fabrica: FabricaSesiones) -> dict[str, Usuario]:
    admin = _crear_usuario(fabrica, "admin", "ADMIN")
    seguridad = ServicioSeguridad(fabrica, reloj=lambda: RELOJ)
    seguridad.crear_rol(
        admin.id,
        codigo="AUXILIAR",
        nombre="Auxiliar de puerta",
        descripcion="Registra asistencia en la entrada",
        permisos=[PermisoOperacion.REGISTRAR_ASISTENCIA],
    )
    seguridad.crear_rol(
        admin.id,
        codigo="MONITOR",
        nombre="Monitor de aforo",
        descripcion="Solo consulta el dashboard de aforo",
        permisos=[PermisoOperacion.CONSULTAR_DASHBOARD_AFORO],
    )
    return {
        "admin": admin,
        "coordinador": _crear_usuario(fabrica, "coord", "COORDINADOR"),
        "staff": _crear_usuario(fabrica, "staff", "ADMIN_STAFF"),
        "auxiliar": _crear_usuario(fabrica, "auxiliar", "AUXILIAR"),
        "monitor": _crear_usuario(fabrica, "monitor", "MONITOR"),
    }


@pytest.fixture
def alumno_id(fabrica: FabricaSesiones) -> int:
    return _crear_alumno(fabrica)


@pytest.fixture
def servicio(fabrica: FabricaSesiones) -> Iterator[ServicioAsistencia]:
    instancia = ServicioAsistencia(fabrica, reloj=lambda: RELOJ)
    try:
        yield instancia
    finally:
        instancia.cerrar()


def _crear_app_web(
    fabrica: FabricaSesiones, servicio: ServicioAsistencia, *, con_seguridad: bool = True
) -> Flask:
    app = crear_app({"SECRET_KEY": "clave-de-prueba", "TESTING": True, "RELOJ": lambda: RELOJ})
    seguridad = ServicioSeguridad(fabrica, reloj=lambda: RELOJ) if con_seguridad else None
    registrar_modulo_asistencia(app, servicio, seguridad)
    return app


@pytest.fixture
def app(fabrica: FabricaSesiones, servicio: ServicioAsistencia, usuarios) -> Flask:
    return _crear_app_web(fabrica, servicio)


def _login(app: Flask, usuario: Usuario) -> FlaskClient:
    """Abre una sesión en el almacén del servidor y la asocia a un cliente de pruebas."""
    sesion = SesionUsuario(
        token=f"tok-{usuario.username}",
        usuario_id=usuario.id,
        username=usuario.username,
        rol=usuario.rol,
        fecha_inicio=RELOJ,
        fecha_expiracion=RELOJ + timedelta(hours=8),
    )
    app.extensions["almacen_sesiones"].guardar(sesion, usuario)
    cliente = app.test_client()
    with cliente.session_transaction() as datos:
        datos["token"] = sesion.token
        datos["_csrf_token"] = CSRF
    return cliente


@pytest.fixture
def admin(app: Flask, usuarios) -> FlaskClient:
    return _login(app, usuarios["admin"])


def _post(cliente: FlaskClient, url: str, data: dict | None = None, **kwargs):
    return cliente.post(url, data={"csrf_token": CSRF, **(data or {})}, **kwargs)


def _post_json(cliente: FlaskClient, url: str, cuerpo: dict):
    return cliente.post(url, json=cuerpo, headers={"X-CSRF-Token": CSRF})


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def _contar(fabrica: FabricaSesiones, modelo) -> int:  # noqa: ANN001
    with fabrica() as session:
        return len(session.scalars(select(modelo)).all())


def _crear_periodo(cliente: FlaskClient, **cambios) -> object:
    datos = {
        "nombre": "Bimestre IV 2026",
        "tipo_periodo": "BIMESTRE",
        "orden": "4",
        "anio_lectivo": "2026",
        "fecha_inicio": "2026-10-01",
        "fecha_fin": "2026-12-20",
        "fecha_limite_notas": "2026-12-27",
    }
    datos.update(cambios)
    return _post(cliente, "/periodos", datos)


# ---------------------------------------------------------------------------
# Autenticación, registro del módulo y navegación
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["/asistencia", "/asistencia/historial", "/aforo", "/justificaciones", "/periodos"]
)
def test_rutas_protegidas_exigen_sesion(app: Flask, url: str) -> None:
    respuesta = app.test_client().get(url)
    assert respuesta.status_code == 401


def test_registrar_modulo_inyecta_servicio(app: Flask, servicio: ServicioAsistencia) -> None:
    assert app.extensions[EXTENSION_SERVICIO_ASISTENCIA] is servicio
    assert {"asistencia", "justificaciones"} <= set(app.blueprints)


def test_navegacion_resuelve_endpoints_del_modulo(admin: FlaskClient) -> None:
    html = _texto(admin.get("/asistencia"))
    assert 'href="/asistencia"' in html
    assert 'href="/justificaciones"' in html
    assert 'aria-current="page"' in html


# ---------------------------------------------------------------------------
# PBI-01: registro unificado
# ---------------------------------------------------------------------------


def test_pagina_de_registro_incluye_formulario_con_csrf(admin: FlaskClient) -> None:
    respuesta = admin.get("/asistencia")
    html = _texto(respuesta)
    assert respuesta.status_code == 200
    assert 'action="/asistencia/registrar"' in html
    assert f'name="csrf_token" value="{CSRF}"' in html
    assert "js/asistencia.js" in html
    assert "Historial de modificaciones" in html


def test_registrar_por_formulario_redirige_con_flash(
    admin: FlaskClient, fabrica: FabricaSesiones, alumno_id: int
) -> None:
    respuesta = _post(admin, "/asistencia/registrar", {"metodo": "CARNET", "valor": CARNET})
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/asistencia")
    assert "Asistencia registrada: PUNTUAL a las 07:05." in _texto(admin.get("/asistencia"))
    with fabrica() as session:
        assert session.scalars(select(AsistenciaModel)).one().estudiante_id == alumno_id


def test_registrar_por_json_devuelve_201(admin: FlaskClient, alumno_id: int) -> None:
    respuesta = _post_json(admin, "/asistencia/registrar", {"metodo": "MANUAL_DNI", "valor": DNI})
    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["asistencia"]["alumno_id"] == alumno_id
    assert cuerpo["asistencia"]["estado"] == "PUNTUAL"
    assert cuerpo["asistencia"]["hora_efectiva"] == "07:05:00"
    assert cuerpo["asistencia"]["seccion"] == "A"


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"metodo": "MANUAL_BUSQUEDA", "valor": "Luna"},
        {"metodo": "manual_busqueda", "alumno_id": "__ID__"},
    ],
)
def test_registrar_por_busqueda_o_id(admin: FlaskClient, alumno_id: int, cuerpo: dict) -> None:
    datos = {k: (str(alumno_id) if v == "__ID__" else v) for k, v in cuerpo.items()}
    respuesta = _post_json(admin, "/asistencia/registrar", datos)
    assert respuesta.status_code == 201
    assert respuesta.get_json()["asistencia"]["alumno_id"] == alumno_id


def test_registrar_sin_csrf_es_rechazado(
    admin: FlaskClient, fabrica: FabricaSesiones, alumno_id: int
) -> None:
    sin_token = admin.post("/asistencia/registrar", data={"metodo": "CARNET", "valor": CARNET})
    token_falso = admin.post(
        "/asistencia/registrar",
        json={"metodo": "CARNET", "valor": CARNET},
        headers={"X-CSRF-Token": "falso"},
    )
    assert sin_token.status_code == 400
    assert token_falso.status_code == 400
    assert _contar(fabrica, AsistenciaModel) == 0


@pytest.mark.parametrize(
    ("datos", "fragmento"),
    [
        ({"valor": CARNET}, "Método"),
        ({"metodo": "TELEPATIA", "valor": CARNET}, "no es una opción válida"),
        ({"metodo": "CARNET"}, "Código de carnet"),
        ({"metodo": "MANUAL_DNI", "valor": "123"}, "DNI"),
        ({"metodo": "MANUAL_BUSQUEDA", "alumno_id": "abc"}, "número entero"),
    ],
)
def test_registrar_formulario_invalido_responde_400_con_flash(
    admin: FlaskClient, alumno_id: int, datos: dict, fragmento: str
) -> None:
    respuesta = _post(admin, "/asistencia/registrar", datos)
    assert respuesta.status_code == 400
    html = _texto(respuesta)
    assert "alert-error" in html
    assert fragmento in html
    assert "Traceback" not in html


def test_registrar_alumno_inexistente_responde_404(admin: FlaskClient, alumno_id: int) -> None:
    respuesta = _post_json(admin, "/asistencia/registrar", {"metodo": "CARNET", "valor": "NADA"})
    assert respuesta.status_code == 404
    assert respuesta.get_json()["ok"] is False


def test_registro_duplicado_responde_409(admin: FlaskClient, alumno_id: int) -> None:
    cuerpo = {"metodo": "CARNET", "valor": CARNET}
    assert _post_json(admin, "/asistencia/registrar", cuerpo).status_code == 201
    duplicado = _post_json(admin, "/asistencia/registrar", cuerpo)
    assert duplicado.status_code == 409
    assert duplicado.get_json()["error"]


def test_registrar_json_no_objeto_responde_400(admin: FlaskClient) -> None:
    respuesta = admin.post(
        "/asistencia/registrar",
        data="[1, 2]",
        content_type="application/json",
        headers={"X-CSRF-Token": CSRF},
    )
    assert respuesta.status_code == 400
    assert "Método" in respuesta.get_json()["error"]


# ---------------------------------------------------------------------------
# Historial de modificaciones
# ---------------------------------------------------------------------------


def test_historial_lista_correcciones(
    admin: FlaskClient, servicio: ServicioAsistencia, usuarios, alumno_id: int
) -> None:
    servicio.ejecutar_cierre_diario(usuarios["admin"].id, fecha_escolar=FECHA)
    vacio = admin.get("/asistencia/historial", query_string={"alumno_id": 999})
    assert vacio.status_code == 200
    assert "No hay modificaciones" in _texto(vacio)

    respuesta = admin.get(
        "/asistencia/historial",
        query_string={"fecha_desde": "2026-11-01", "fecha_hasta": "2026-11-30"},
    )
    assert respuesta.status_code == 200
    assert "Correcciones registradas" in _texto(respuesta)


def test_historial_con_fecha_invalida_responde_400(admin: FlaskClient) -> None:
    respuesta = admin.get("/asistencia/historial", query_string={"fecha_desde": "26/11/2026"})
    assert respuesta.status_code == 400
    assert "AAAA-MM-DD" in _texto(respuesta)


# ---------------------------------------------------------------------------
# PBI-03: dashboard de aforo y cierre
# ---------------------------------------------------------------------------


def test_dashboard_de_aforo_muestra_kpis_y_detalle(admin: FlaskClient, alumno_id: int) -> None:
    _post_json(admin, "/asistencia/registrar", {"metodo": "CARNET", "valor": CARNET})
    general = admin.get("/aforo")
    assert general.status_code == 200
    html = _texto(general)
    assert 'data-kpi="aforo_actual_plantel">1<' in html
    assert "Asistencia por salón" in html
    assert "Hora oficial de cierre" in html

    detalle = admin.get(
        "/aforo",
        query_string={"nivel": "Primaria", "grado": "3ro", "seccion": "A", "fecha": "2026-11-26"},
    )
    assert detalle.status_code == 200
    assert "Luna Lezano" in _texto(detalle)


def test_metricas_aforo_en_json(admin: FlaskClient, alumno_id: int) -> None:
    respuesta = admin.get("/aforo/metricas")
    assert respuesta.status_code == 200
    metricas = respuesta.get_json()["metricas"]
    assert metricas["total_matriculados"] == 1
    assert metricas["pendientes"] == 1
    assert metricas["hora_cierre_oficial"] == "09:00:00"


@pytest.mark.parametrize("url", ["/aforo", "/aforo/metricas"])
def test_aforo_con_fecha_invalida_responde_400(admin: FlaskClient, url: str) -> None:
    respuesta = admin.get(url, query_string={"fecha": "ayer"})
    assert respuesta.status_code == 400


def test_configurar_hora_de_cierre(admin: FlaskClient, fabrica: FabricaSesiones) -> None:
    respuesta = _post(admin, "/aforo/hora-cierre", {"hora_cierre": "08:30"})
    assert respuesta.status_code == 302
    with fabrica() as session:
        assert session.get(ConfiguracionSistemaModel, "hora_cierre_oficial").valor == "08:30:00"
    assert "08:30" in _texto(admin.get("/aforo"))


@pytest.mark.parametrize("hora", ["", "25:99"])
def test_configurar_hora_invalida_responde_400(admin: FlaskClient, hora: str) -> None:
    respuesta = _post(admin, "/aforo/hora-cierre", {"hora_cierre": hora})
    assert respuesta.status_code == 400


def test_ejecutar_cierre_de_jornada(
    admin: FlaskClient, fabrica: FabricaSesiones, alumno_id: int
) -> None:
    respuesta = _post(admin, "/aforo/cierre", {"fecha": "2026-11-26"})
    assert respuesta.status_code == 302
    assert "1 alumno(s) marcados como ausentes" in _texto(admin.get("/aforo"))
    with fabrica() as session:
        assert session.scalars(select(AsistenciaModel)).one().estado == "AUSENTE"


def test_ejecutar_cierre_con_fecha_invalida(admin: FlaskClient) -> None:
    assert _post(admin, "/aforo/cierre", {"fecha": "x"}).status_code == 400


# ---------------------------------------------------------------------------
# PBI-04: justificaciones
# ---------------------------------------------------------------------------


@pytest.fixture
def asistencia_ausente(admin: FlaskClient, fabrica: FabricaSesiones, alumno_id: int) -> str:
    assert _crear_periodo(admin).status_code == 302
    assert _post(admin, "/aforo/cierre", {"fecha": "2026-11-26"}).status_code == 302
    with fabrica() as session:
        return session.scalars(select(AsistenciaModel)).one().id


def test_registrar_y_anular_justificacion(
    admin: FlaskClient, fabrica: FabricaSesiones, asistencia_ausente: str
) -> None:
    respuesta = _post(
        admin,
        "/justificaciones",
        {
            "asistencia_id": asistencia_ausente,
            "categoria": "MEDICA",
            "motivo": "Reposo médico",
            "adjuntos": (BytesIO(b"%PDF-1.4"), "certificado.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 302
    listado = admin.get("/justificaciones", query_string={"estado": "APROBADA"})
    html = _texto(listado)
    assert "Reposo médico" in html
    assert "Justificación aprobada" in html
    with fabrica() as session:
        justificacion = session.scalars(select(JustificacionModel)).one()
        assert session.get(AsistenciaModel, asistencia_ausente).estado == "JUSTIFICADO"

    anulada = _post(admin, f"/justificaciones/{justificacion.id}/anular")
    assert anulada.status_code == 302
    with fabrica() as session:
        assert session.get(AsistenciaModel, asistencia_ausente).estado == "AUSENTE"
        assert session.get(JustificacionModel, justificacion.id).estado == "RECHAZADA"


def test_justificacion_ignora_campo_de_archivo_vacio(
    admin: FlaskClient, fabrica: FabricaSesiones, asistencia_ausente: str
) -> None:
    # El navegador envía la parte "adjuntos" sin nombre cuando no se elige archivo.
    respuesta = _post(
        admin,
        "/justificaciones",
        {
            "asistencia_id": asistencia_ausente,
            "categoria": "PERMISO_FAMILIAR",
            "motivo": "Viaje familiar",
            "adjuntos": (BytesIO(b""), ""),
        },
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 302
    assert _contar(fabrica, JustificacionModel) == 1


def test_justificacion_con_adjunto_invalido_responde_400(
    admin: FlaskClient, asistencia_ausente: str
) -> None:
    respuesta = _post(
        admin,
        "/justificaciones",
        {
            "asistencia_id": asistencia_ausente,
            "categoria": "MEDICA",
            "motivo": "Reposo",
            "adjuntos": (BytesIO(b"MZ"), "virus.exe"),
        },
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 400


@pytest.mark.parametrize(
    "datos",
    [
        {"categoria": "MEDICA", "motivo": "x"},
        {"asistencia_id": "a", "categoria": "INVENTADA", "motivo": "x"},
        {"asistencia_id": "a", "categoria": "MEDICA"},
        {"asistencia_id": "a", "categoria": "MEDICA", "motivo": "x", "periodo_id": "uno"},
    ],
)
def test_justificacion_con_datos_invalidos_responde_400(admin: FlaskClient, datos: dict) -> None:
    assert _post(admin, "/justificaciones", datos).status_code == 400


def test_justificacion_de_asistencia_inexistente_responde_404_sin_exponer_id(
    admin: FlaskClient,
) -> None:
    respuesta = _post(
        admin,
        "/justificaciones",
        {"asistencia_id": "id-secreto-123", "categoria": "MEDICA", "motivo": "x"},
    )
    assert respuesta.status_code == 404
    html = _texto(respuesta)
    assert MENSAJE_NO_ENCONTRADO in html
    assert "id-secreto-123" not in html


def test_anular_justificacion_inexistente_responde_404(admin: FlaskClient) -> None:
    assert _post(admin, "/justificaciones/no-existe/anular").status_code == 404


def test_filtros_de_justificaciones(admin: FlaskClient) -> None:
    vacio = admin.get("/justificaciones", query_string={"categoria": "MEDICA"})
    assert vacio.status_code == 200
    assert "No hay justificaciones" in _texto(vacio)
    invertido = admin.get(
        "/justificaciones",
        query_string={"fecha_desde": "2026-12-01", "fecha_hasta": "2026-11-01"},
    )
    assert invertido.status_code == 400
    assert admin.get("/justificaciones", query_string={"estado": "X"}).status_code == 400


# ---------------------------------------------------------------------------
# PBI-04: períodos académicos
# ---------------------------------------------------------------------------


def test_crud_de_periodos(admin: FlaskClient, fabrica: FabricaSesiones) -> None:
    assert _crear_periodo(admin).status_code == 302
    listado = admin.get("/periodos", query_string={"anio_lectivo": "2026"})
    assert listado.status_code == 200
    assert "Bimestre IV 2026" in _texto(listado)
    with fabrica() as session:
        periodo_id = session.scalars(select(PeriodoAcademicoModel)).one().id

    prorroga = _post(
        admin, f"/periodos/{periodo_id}/fecha-limite", {"fecha_limite_notas": "2027-01-05"}
    )
    assert prorroga.status_code == 302
    assert "05/01/2027" in _texto(admin.get("/periodos"))

    assert _post(admin, f"/periodos/{periodo_id}/estado", {"cerrado": "1"}).status_code == 302
    with fabrica() as session:
        assert session.get(PeriodoAcademicoModel, periodo_id).cerrado is True
    assert "Reabrir" in _texto(admin.get("/periodos"))
    assert _post(admin, f"/periodos/{periodo_id}/estado", {"cerrado": "0"}).status_code == 302

    assert _post(admin, f"/periodos/{periodo_id}/eliminar").status_code == 302
    assert _contar(fabrica, PeriodoAcademicoModel) == 0


def test_periodo_solapado_responde_409(admin: FlaskClient) -> None:
    assert _crear_periodo(admin).status_code == 302
    assert _crear_periodo(admin, nombre="Otro").status_code == 409


@pytest.mark.parametrize(
    "cambios",
    [
        {"fecha_inicio": "2026-12-31"},
        {"fecha_fin": "fin"},
        {"tipo_periodo": "ANUAL"},
        {"orden": ""},
    ],
)
def test_crear_periodo_invalido_responde_400(admin: FlaskClient, cambios: dict) -> None:
    assert _crear_periodo(admin, **cambios).status_code == 400


@pytest.mark.parametrize(
    ("url", "datos"),
    [
        ("/periodos/999/estado", {"cerrado": "1"}),
        ("/periodos/999/fecha-limite", {"fecha_limite_notas": "2027-01-01"}),
        ("/periodos/999/eliminar", {}),
    ],
)
def test_operar_periodo_inexistente_responde_404(admin: FlaskClient, url: str, datos: dict) -> None:
    assert _post(admin, url, datos).status_code == 404


def test_prorroga_sin_fecha_responde_400(admin: FlaskClient) -> None:
    assert _post(admin, "/periodos/1/fecha-limite", {}).status_code == 400


def test_periodos_con_anio_invalido_responde_400(admin: FlaskClient) -> None:
    assert admin.get("/periodos", query_string={"anio_lectivo": "dos mil"}).status_code == 400


def test_eliminar_periodo_con_justificaciones_responde_409(
    admin: FlaskClient, fabrica: FabricaSesiones, asistencia_ausente: str
) -> None:
    _post(
        admin,
        "/justificaciones",
        {"asistencia_id": asistencia_ausente, "categoria": "MEDICA", "motivo": "Reposo"},
    )
    with fabrica() as session:
        periodo_id = session.scalars(select(PeriodoAcademicoModel)).one().id
    assert _post(admin, f"/periodos/{periodo_id}/eliminar").status_code == 409


# ---------------------------------------------------------------------------
# CSRF en todos los formularios POST del módulo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "/asistencia/registrar",
        "/aforo/hora-cierre",
        "/aforo/cierre",
        "/justificaciones",
        "/justificaciones/x/anular",
        "/periodos",
        "/periodos/1/estado",
        "/periodos/1/fecha-limite",
        "/periodos/1/eliminar",
    ],
)
def test_todos_los_post_exigen_csrf(admin: FlaskClient, url: str) -> None:
    respuesta = admin.post(url, data={"campo": "valor"})
    assert respuesta.status_code == 400
    assert "CSRF" in _texto(respuesta)


@pytest.mark.parametrize("url", ["/asistencia", "/aforo", "/justificaciones", "/periodos"])
def test_formularios_post_incluyen_token_csrf(admin: FlaskClient, url: str) -> None:
    html = _texto(admin.get(url))
    assert html.count('method="post"') == html.count(f'name="csrf_token" value="{CSRF}"')


# ---------------------------------------------------------------------------
# 403 con roles base y personalizados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "metodo", "url"),
    [
        ("coordinador", "POST", "/aforo/hora-cierre"),
        ("coordinador", "POST", "/aforo/cierre"),
        ("coordinador", "GET", "/periodos"),
        ("coordinador", "POST", "/periodos"),
        ("staff", "GET", "/periodos"),
        ("staff", "POST", "/periodos/1/eliminar"),
        ("auxiliar", "GET", "/aforo"),
        ("auxiliar", "GET", "/justificaciones"),
        ("auxiliar", "GET", "/asistencia/historial"),
        ("monitor", "GET", "/asistencia"),
        ("monitor", "POST", "/asistencia/registrar"),
        ("monitor", "POST", "/justificaciones"),
    ],
)
def test_denegacion_403_por_rol(app: Flask, usuarios, rol: str, metodo: str, url: str) -> None:
    cliente = _login(app, usuarios[rol])
    if metodo == "GET":
        respuesta = cliente.get(url)
    else:
        respuesta = _post(cliente, url, {"metodo": "CARNET", "valor": CARNET})
    assert respuesta.status_code == 403
    assert "Acceso restringido" in _texto(respuesta)


def test_roles_base_con_permiso_acceden(app: Flask, usuarios) -> None:
    for rol in ("coordinador", "staff"):
        cliente = _login(app, usuarios[rol])
        for url in ("/asistencia", "/aforo", "/justificaciones"):
            assert cliente.get(url).status_code == 200, (rol, url)


def test_rol_personalizado_con_permiso_registra(app: Flask, usuarios, alumno_id: int) -> None:
    auxiliar = _login(app, usuarios["auxiliar"])
    pagina = auxiliar.get("/asistencia")
    assert pagina.status_code == 200
    assert "Historial de modificaciones" not in _texto(pagina)
    respuesta = _post_json(auxiliar, "/asistencia/registrar", {"metodo": "CARNET", "valor": CARNET})
    assert respuesta.status_code == 201

    monitor = _login(app, usuarios["monitor"])
    aforo = monitor.get("/aforo")
    assert aforo.status_code == 200
    assert "Ejecutar cierre" not in _texto(aforo)


def test_sin_servicio_de_seguridad_los_roles_personalizados_se_deniegan(
    fabrica: FabricaSesiones, servicio: ServicioAsistencia, usuarios
) -> None:
    app = _crear_app_web(fabrica, servicio, con_seguridad=False)
    assert _login(app, usuarios["auxiliar"]).get("/asistencia").status_code == 403
    assert _login(app, usuarios["admin"]).get("/asistencia").status_code == 200


def test_roles_precargados_en_g_se_respetan(
    fabrica: FabricaSesiones, servicio: ServicioAsistencia, usuarios
) -> None:
    app = _crear_app_web(fabrica, servicio, con_seguridad=True)

    @app.before_request
    def _sin_roles_personalizados() -> None:
        g.roles_disponibles = []

    assert _login(app, usuarios["auxiliar"]).get("/asistencia").status_code == 403


def test_usuario_inactivo_recibe_401(app: Flask, usuarios) -> None:
    inactivo = Usuario(
        id=usuarios["staff"].id,
        username="staff",
        password_hash="x",
        salt="y",
        nombre_completo="Staff",
        rol="ADMIN_STAFF",
        estado=EstadoUsuario.INACTIVO,
    )
    cliente = _login(app, inactivo)
    assert cliente.get("/asistencia").status_code == 401


# ---------------------------------------------------------------------------
# Traducción de errores de dominio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "codigo", "mensaje"),
    [
        (AccesoDenegadoException("rol X sin permiso"), 403, MENSAJE_PROHIBIDO),
        (PermisoAforoException("detalle interno"), 403, MENSAJE_PROHIBIDO),
        (PermisoJustificacionException("detalle"), 403, MENSAJE_PROHIBIDO),
        (RegistroDuplicadoException("Ya registrado"), 409, "Ya registrado"),
        (CierreYaEjecutadoException("Cierre ya hecho"), 409, "Cierre ya hecho"),
        (AlumnoNoEncontradoException("No encontrado"), 404, "No encontrado"),
        (DniInvalidoException("DNI inválido"), 400, "DNI inválido"),
        (SolicitudInvalidaError("Campo"), 400, "Campo"),
        (ValueError("La asistencia abc no existe."), 404, MENSAJE_NO_ENCONTRADO),
    ],
)
def test_traducir_error(error: Exception, codigo: int, mensaje: str) -> None:
    resultado = traducir_error(error)
    assert (resultado.codigo, resultado.mensaje) == (codigo, mensaje)


def test_error_de_permiso_de_dominio_en_json_responde_403(admin: FlaskClient, app: Flask) -> None:
    class ServicioQueDeniega:
        def consultar_metricas_aforo(self, *_args, **_kwargs):
            raise PermisoAforoException("El rol X no puede consultar el aforo.")

    app.extensions[EXTENSION_SERVICIO_ASISTENCIA] = ServicioQueDeniega()
    respuesta = admin.get("/aforo/metricas")
    assert respuesta.status_code == 403
    assert respuesta.get_json() == {"ok": False, "error": MENSAJE_PROHIBIDO}
