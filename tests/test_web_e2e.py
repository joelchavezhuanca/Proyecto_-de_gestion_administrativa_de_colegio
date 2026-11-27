"""Pruebas E2E de la capa web integrada (Ola 4 - Miembro 5).

Cubre de punta a punta, sobre SQLite en memoria y a través de ``crear_app``:

- Autenticación validada en servidor, protección CSRF y respuestas 401.
- Roles base (ADMIN, COORDINADOR, ADMIN_STAFF) y roles personalizados
  (DOCENTE, TESORERIA) con accesos permitidos y denegaciones estrictas 403.
- Ficha informativa consolidada (PBI-12) con segregación financiera.
- Exportación real de listas de asistencia en CSV y XLSX (PBI-13).
- Emisión y descarga de boletas preliminares y oficiales (PBI-14).

Los blueprints de asistencia, alumnos y académico aún no forman parte de
``main`` al momento de esta rama; la verificación de registro comprueba que
``crear_app`` los integre automáticamente en cuanto estén disponibles.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.aplicacion.servicios_academico import ServicioAcademico
from src.aplicacion.servicios_asistencia import ServicioAsistencia
from src.aplicacion.servicios_seguridad import ServicioSeguridad
from src.dominio.exportacion_asistencia import ExportacionException
from src.dominio.usuarios import (
    AccesoDenegadoException,
    PermisoOperacion,
    hashear_password,
)
from src.infraestructura.base_datos import (
    crear_motor,
    crear_session_factory,
    inicializar_bd,
)
from src.infraestructura.modelos import (
    ActividadEvaluableModel,
    ApoderadoModel,
    AsignacionDocenteModel,
    AsistenciaModel,
    CalificacionModel,
    CursoModel,
    EstudianteApoderadoModel,
    EstudianteModel,
    ObligacionPagoModel,
    PeriodoAcademicoModel,
    RolModel,
    RolPermisoModel,
    RubroEvaluacionModel,
    SalonModel,
    UsuarioModel,
)
from src.presentacion.app import crear_app
from src.presentacion.bp_reportes import registrar_blueprints_reportes
from src.presentacion.tiempo import ZONA_HORARIA_LIMA

PASSWORD = "ClaveSegura123"
RELOJ_FIJO = datetime(2026, 11, 27, 10, 0, tzinfo=ZONA_HORARIA_LIMA)
PATRON_CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')
PATRON_DESCARGA = re.compile(r'href="([^"]*/reportes/boletas/[^"/]+/descargar)"')

PERMISOS_DOCENTE = {
    PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
    PermisoOperacion.EXPORTAR_ASISTENCIAS,
    PermisoOperacion.REGISTRAR_ASISTENCIA,
    PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
}
PERMISOS_TESORERIA = {
    PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
    PermisoOperacion.GESTIONAR_PAGOS,
    PermisoOperacion.VER_ALERTA_PAGOS,
}


# ---------------------------------------------------------------------------
# Infraestructura de pruebas
# ---------------------------------------------------------------------------


def _crear_rol_personalizado(
    session: Session,
    codigo: str,
    permisos: set[PermisoOperacion],
) -> RolModel:
    rol = RolModel(
        codigo=codigo,
        nombre=f"Rol {codigo}",
        descripcion=f"Rol personalizado {codigo}",
        es_sistema=False,
        activo=True,
    )
    session.add(rol)
    session.flush()
    for permiso in permisos:
        session.add(RolPermisoModel(rol_id=rol.id, permiso_codigo=permiso.value))
    session.flush()
    return rol


def _crear_usuario(
    session: Session,
    username: str,
    rol: str,
    rol_id: int,
    *,
    nombre_completo: str = "Usuario de Prueba",
) -> UsuarioModel:
    password_hash, salt = hashear_password(PASSWORD)
    usuario = UsuarioModel(
        username=username,
        nombre_completo=nombre_completo,
        password_hash=password_hash,
        salt=salt,
        rol=rol,
        rol_id=rol_id,
        estado="ACTIVO",
        activo=True,
    )
    session.add(usuario)
    session.flush()
    return usuario


def _sembrar_datos(fabrica: sessionmaker[Session]) -> SimpleNamespace:
    """Siembra usuarios, roles personalizados, estructura académica y notas."""
    with fabrica() as session:
        base = {rol.codigo: rol for rol in session.scalars(select(RolModel)).all()}
        rol_docente = _crear_rol_personalizado(session, "DOCENTE", PERMISOS_DOCENTE)
        rol_tesoreria = _crear_rol_personalizado(session, "TESORERIA", PERMISOS_TESORERIA)

        admin = _crear_usuario(session, "admin", "ADMIN", base["ADMIN"].id)
        coordinador = _crear_usuario(session, "coordinador", "COORDINADOR", base["COORDINADOR"].id)
        staff = _crear_usuario(session, "staff", "ADMIN_STAFF", base["ADMIN_STAFF"].id)
        docente = _crear_usuario(session, "docente", "DOCENTE", rol_docente.id)
        tesoreria = _crear_usuario(session, "tesoreria", "TESORERIA", rol_tesoreria.id)

        salon = SalonModel(
            anio_lectivo=2026,
            nivel="Primaria",
            grado="3ro",
            seccion="A",
            capacidad_maxima=30,
            activo=True,
        )
        curso = CursoModel(
            anio_lectivo=2026,
            nivel="Primaria",
            grado="3ro",
            codigo="MAT-3",
            nombre="Matemática",
            area_curricular="Matemática",
            horas_semanales=5,
            activo=True,
        )
        session.add_all([salon, curso])
        session.flush()

        asignacion = AsignacionDocenteModel(
            id="asig-e2e-1",
            usuario_docente_id=docente.id,
            curso_id=curso.id,
            salon_id=salon.id,
            anio_lectivo=2026,
            activa=True,
            asignado_por=admin.id,
        )
        alumno = EstudianteModel(
            codigo="ALU-2026-001",
            dni="72945734",
            nombres="Eduardo",
            apellidos="Luna Lezano",
            fecha_nacimiento=date(2015, 4, 12),
            salon_id=salon.id,
            nivel="Primaria",
            grado="3ro",
            seccion="A",
            carnet_codigo="CRN-72945734",
            estado="ACTIVO",
        )
        session.add_all([asignacion, alumno])
        session.flush()

        apoderado = ApoderadoModel(
            nombres="Rosa",
            apellidos="Lezano",
            documento="44556677",
            parentesco="MADRE",
            telefono_whatsapp="+51987654321",
            activo=True,
        )
        session.add(apoderado)
        session.flush()
        session.add(
            EstudianteApoderadoModel(
                estudiante_id=alumno.id,
                apoderado_id=apoderado.id,
                es_principal=True,
            )
        )

        session.add(
            AsistenciaModel(
                id="asis-e2e-1",
                estudiante_id=alumno.id,
                usuario_id=admin.id,
                fecha_escolar=date(2026, 11, 26),
                hora_efectiva=time(8, 0),
                estado="PUNTUAL",
                minutos_tardanza=0,
                metodo="MANUAL_DNI",
                rol_usuario="ADMIN",
                nivel_snapshot="Primaria",
                grado_snapshot="3ro",
                seccion_snapshot="A",
            )
        )
        session.add(
            ObligacionPagoModel(
                id="obl-e2e-1",
                estudiante_id=alumno.id,
                concepto="Pensión noviembre",
                monto=Decimal("150.00"),
                fecha_vencimiento=date(2026, 10, 31),
                estado="PENDIENTE",
            )
        )

        periodo_abierto = PeriodoAcademicoModel(
            anio_lectivo=2026,
            tipo_periodo="BIMESTRE",
            orden=3,
            nombre="2026-B3",
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 12, 20),
            cerrado=False,
        )
        periodo_cerrado = PeriodoAcademicoModel(
            anio_lectivo=2026,
            tipo_periodo="BIMESTRE",
            orden=2,
            nombre="2026-B2",
            fecha_inicio=date(2026, 4, 1),
            fecha_fin=date(2026, 7, 31),
            cerrado=True,
        )
        session.add_all([periodo_abierto, periodo_cerrado])
        session.flush()

        for periodo in (periodo_abierto, periodo_cerrado):
            rubro = RubroEvaluacionModel(
                id=f"rub-e2e-{periodo.id}",
                asignacion_docente_id=asignacion.id,
                periodo_id=periodo.id,
                nombre="Evaluación única",
                peso_porcentaje=Decimal("100.00"),
                activo=True,
            )
            session.add(rubro)
            session.flush()
            actividad = ActividadEvaluableModel(
                id=f"act-e2e-{periodo.id}",
                rubro_id=rubro.id,
                titulo="Examen bimestral",
                fecha=date(2026, 6, 15),
                activo=True,
            )
            session.add(actividad)
            session.flush()
            session.add(
                CalificacionModel(
                    id=f"cal-e2e-{periodo.id}",
                    actividad_id=actividad.id,
                    estudiante_id=alumno.id,
                    nota=Decimal("16.00"),
                    usuario_id=docente.id,
                )
            )

        session.commit()
        return SimpleNamespace(
            admin_id=admin.id,
            coordinador_id=coordinador.id,
            staff_id=staff.id,
            docente_id=docente.id,
            tesoreria_id=tesoreria.id,
            alumno_id=alumno.id,
            salon_id=salon.id,
            curso_id=curso.id,
            periodo_abierto_id=periodo_abierto.id,
            periodo_cerrado_id=periodo_cerrado.id,
        )


@pytest.fixture
def entorno() -> Iterator[SimpleNamespace]:
    engine = crear_motor("sqlite:///:memory:")
    inicializar_bd(engine)
    fabrica = crear_session_factory(engine)
    datos = _sembrar_datos(fabrica)

    app = crear_app(
        {
            "SECRET_KEY": "clave-e2e-reportes-2026",
            "WTF_CSRF_ENABLED": True,
            "CSRF_ENABLED": True,
            "SESSION_FACTORY": fabrica,
            "RELOJ": lambda: RELOJ_FIJO,
            "TESTING": True,
        }
    )
    try:
        yield SimpleNamespace(app=app, fabrica=fabrica, datos=datos)
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Helpers de autenticación y CSRF
# ---------------------------------------------------------------------------


def _token_csrf(cliente) -> str:  # noqa: ANN001
    with cliente.session_transaction() as session:
        return session["_csrf_token"]


def _loguear(entorno: SimpleNamespace, username: str):
    cliente = entorno.app.test_client()
    respuesta_get = cliente.get("/login")
    assert respuesta_get.status_code == 200
    token = PATRON_CSRF.search(respuesta_get.get_data(as_text=True)).group(1)
    respuesta = cliente.post(
        "/login",
        data={
            "username": username,
            "password": PASSWORD,
            "csrf_token": token,
        },
    )
    assert respuesta.status_code == 303
    return cliente


def _url_ficha(datos: SimpleNamespace) -> str:
    return f"/reportes/ficha/{datos.alumno_id}"


# ---------------------------------------------------------------------------
# Registro e inyección de dependencias en crear_app
# ---------------------------------------------------------------------------


def test_crear_app_registra_blueprints_y_servicios(entorno: SimpleNamespace) -> None:
    app = entorno.app

    assert "reportes" in app.blueprints
    assert "auth" in app.blueprints
    assert "usuarios" in app.blueprints
    assert "roles" in app.blueprints
    assert "auditoria" in app.blueprints

    assert app.extensions["session_factory"] is entorno.fabrica
    assert isinstance(app.extensions["servicio_seguridad"], ServicioSeguridad)
    assert isinstance(app.extensions["servicio_academico"], ServicioAcademico)
    assert isinstance(app.extensions["servicio_asistencia"], ServicioAsistencia)


def test_crear_app_no_exige_argumentos_extra() -> None:
    app = crear_app({"SECRET_KEY": "solo-clave"})
    assert app.config["SECRET_KEY"] == "solo-clave"
    assert "reportes" in app.blueprints


# ---------------------------------------------------------------------------
# Autenticación en servidor, CSRF y 401
# ---------------------------------------------------------------------------


def test_rutas_de_reportes_sin_sesion_devuelven_401(entorno: SimpleNamespace) -> None:
    cliente = entorno.app.test_client()
    for url in (
        _url_ficha(entorno.datos),
        "/reportes/ficha",
        "/reportes/asistencias/exportar",
        "/reportes/boletas",
    ):
        respuesta = cliente.get(url)
        assert respuesta.status_code == 401, url


def test_post_sin_sesion_pero_con_csrf_devuelve_401(entorno: SimpleNamespace) -> None:
    cliente = entorno.app.test_client()
    respuesta_get = cliente.get("/login")
    token = PATRON_CSRF.search(respuesta_get.get_data(as_text=True)).group(1)

    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={
            "csrf_token": token,
            "fecha_desde": "2026-11-01",
            "fecha_hasta": "2026-11-30",
            "formato": "CSV",
        },
    )
    assert respuesta.status_code == 401


def test_post_sin_csrf_devuelve_400(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={"fecha_desde": "2026-11-01", "fecha_hasta": "2026-11-30"},
    )
    assert respuesta.status_code == 400
    assert "CSRF" in respuesta.get_data(as_text=True)


def test_login_exitoso_habilita_la_ficha(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get(_url_ficha(entorno.datos))
    assert respuesta.status_code == 200
    assert "ALU-2026-001" in respuesta.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Roles base y roles personalizados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("username", "ficha", "exportar", "boletas"),
    [
        ("admin", 200, 200, 200),
        ("coordinador", 200, 200, 403),
        ("staff", 200, 200, 200),
        ("docente", 200, 200, 403),
        ("tesoreria", 200, 403, 403),
    ],
)
def test_matriz_de_acceso_por_rol(
    entorno: SimpleNamespace,
    username: str,
    ficha: int,
    exportar: int,
    boletas: int,
) -> None:
    cliente = _loguear(entorno, username)

    assert cliente.get(_url_ficha(entorno.datos)).status_code == ficha
    assert cliente.get("/reportes/asistencias/exportar").status_code == exportar
    assert cliente.get("/reportes/boletas").status_code == boletas


def test_roles_personalizados_no_heredan_permisos_de_base(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "docente")
    token = _token_csrf(cliente)
    respuesta = cliente.post(
        "/reportes/boletas/individual",
        data={
            "csrf_token": token,
            "alumno_id": str(entorno.datos.alumno_id),
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# PBI-12: ficha informativa con segregación financiera
# ---------------------------------------------------------------------------


def test_ficha_admin_incluye_bloque_financiero(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    html = cliente.get(_url_ficha(entorno.datos)).get_data(as_text=True)

    assert "Luna Lezano" in html
    assert "Resumen financiero" in html
    assert "150.00" in html
    assert "Rosa" in html
    assert "100.00" in html


def test_ficha_coordinador_oculta_bloque_financiero(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "coordinador")
    html = cliente.get(_url_ficha(entorno.datos)).get_data(as_text=True)

    assert "Resumen de asistencia" in html
    assert "Resumen financiero" not in html
    assert "150.00" not in html
    assert "Pensión" not in html


def test_ficha_docente_oculta_bloque_financiero(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "docente")
    html = cliente.get(_url_ficha(entorno.datos)).get_data(as_text=True)

    assert "Resumen de asistencia" in html
    assert "Resumen financiero" not in html
    assert "150.00" not in html


def test_ficha_tesoreria_muestra_bloque_financiero(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "tesoreria")
    html = cliente.get(_url_ficha(entorno.datos)).get_data(as_text=True)

    assert "Resumen financiero" in html
    assert "150.00" in html


def test_ficha_busqueda_sin_alumno_muestra_formulario(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get("/reportes/ficha")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Consultar ficha" in html
    assert "Resumen financiero" not in html


def test_ficha_busqueda_con_alumno_valido(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get(
        "/reportes/ficha", query_string={"alumno_id": str(entorno.datos.alumno_id)}
    )
    assert respuesta.status_code == 200
    assert "ALU-2026-001" in respuesta.get_data(as_text=True)


def test_ficha_busqueda_con_identificador_invalido_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get("/reportes/ficha", query_string={"alumno_id": "abc"})
    assert respuesta.status_code == 400
    assert "identificador" in respuesta.get_data(as_text=True).lower()


def test_ficha_alumno_inexistente_devuelve_404(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get("/reportes/ficha/999999")
    assert respuesta.status_code == 404
    assert "no existe" in respuesta.get_data(as_text=True).lower()


# ---------------------------------------------------------------------------
# PBI-13: exportación de asistencias
# ---------------------------------------------------------------------------


def _datos_exportacion(**extra: str) -> dict[str, str]:
    datos = {
        "fecha_desde": "2026-11-01",
        "fecha_hasta": "2026-11-30",
        "nivel": "Primaria",
        "grado": "3ro",
        "seccion": "A",
        "formato": "CSV",
    }
    datos.update(extra)
    return datos


def test_formulario_exportacion_incluye_csrf_y_filtros(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get("/reportes/asistencias/exportar")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert 'name="csrf_token"' in html
    assert 'name="fecha_desde"' in html
    assert 'name="formato"' in html
    assert "Primaria" in html


def test_exportacion_csv_descarga_real(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={"csrf_token": _token_csrf(cliente), **_datos_exportacion()},
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert "attachment" in respuesta.headers["Content-Disposition"]
    assert ".csv" in respuesta.headers["Content-Disposition"]

    contenido = respuesta.data.decode("utf-8-sig")
    assert "codigo_alumno" in contenido
    assert "ALU-2026-001" in contenido
    assert "PUNTUAL" in contenido


def test_exportacion_xlsx_descarga_real(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={
            "csrf_token": _token_csrf(cliente),
            **_datos_exportacion(formato="XLSX"),
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in respuesta.headers["Content-Disposition"]
    assert ".xlsx" in respuesta.headers["Content-Disposition"]
    assert respuesta.data[:4] == b"PK\x03\x04"


def test_exportacion_con_rango_invalido_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={
            "csrf_token": _token_csrf(cliente),
            **_datos_exportacion(fecha_desde="2026-12-01", fecha_hasta="2026-11-01"),
        },
    )
    assert respuesta.status_code == 400
    assert "posterior" in respuesta.get_data(as_text=True).lower()


def test_exportacion_con_fecha_invalida_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={
            "csrf_token": _token_csrf(cliente),
            **_datos_exportacion(fecha_desde="fecha-mala"),
        },
    )
    assert respuesta.status_code == 400
    assert "fecha" in respuesta.get_data(as_text=True).lower()


def test_exportacion_con_formato_no_soportado_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={
            "csrf_token": _token_csrf(cliente),
            **_datos_exportacion(formato="PDF"),
        },
    )
    assert respuesta.status_code == 400
    assert "formato" in respuesta.get_data(as_text=True).lower()


def test_exportacion_sin_fechas_devuelve_400(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={"csrf_token": _token_csrf(cliente), "formato": "CSV"},
    )
    assert respuesta.status_code == 400
    assert "fecha" in respuesta.get_data(as_text=True).lower()


# ---------------------------------------------------------------------------
# PBI-14: emisión y descarga de boletas
# ---------------------------------------------------------------------------


def _emitir_individual(
    cliente,  # noqa: ANN001
    datos: SimpleNamespace,
    periodo_id: int,
):
    return cliente.post(
        "/reportes/boletas/individual",
        data={
            "csrf_token": _token_csrf(cliente),
            "alumno_id": str(datos.alumno_id),
            "periodo_id": str(periodo_id),
        },
    )


def test_formulario_boletas_muestra_salones_y_periodos(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get("/reportes/boletas")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert 'name="csrf_token"' in html
    assert "2026-B3" in html
    assert "Primaria" in html
    assert "Emisión individual" in html
    assert "Emisión masiva" in html


def test_boleta_preliminar_y_su_descarga(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = _emitir_individual(cliente, entorno.datos, entorno.datos.periodo_abierto_id)
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "PRELIMINAR" in html
    assert "BOL-" not in html

    enlace = PATRON_DESCARGA.search(html)
    assert enlace is not None

    descarga = cliente.get(enlace.group(1))
    assert descarga.status_code == 200
    assert descarga.headers["Content-Type"].startswith("text/plain")
    assert "attachment" in descarga.headers["Content-Disposition"]
    texto = descarga.data.decode("utf-8")
    assert "Boleta de Calificaciones - BORRADOR / PRELIMINAR" in texto
    assert "NO OFICIAL" in texto
    assert "Matemática" in texto


def test_boleta_oficial_incluye_codigo_verificador(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = _emitir_individual(cliente, entorno.datos, entorno.datos.periodo_cerrado_id)
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "OFICIAL" in html
    codigo = re.search(r"BOL-[A-Z0-9]{12}", html)
    assert codigo is not None

    enlace = PATRON_DESCARGA.search(html)
    assert enlace is not None
    descarga = cliente.get(enlace.group(1))
    assert descarga.status_code == 200
    texto = descarga.data.decode("utf-8")
    assert "Boleta de Calificaciones - OFICIAL" in texto
    assert codigo.group(0) in texto


def test_emision_masiva_por_salon(entorno: SimpleNamespace) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/salon",
        data={
            "csrf_token": _token_csrf(cliente),
            "anio_lectivo": "2026",
            "nivel": "Primaria",
            "grado": "3ro",
            "seccion": "A",
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "PRELIMINAR" in html
    assert f"Alumno {entorno.datos.alumno_id}" in html


def test_emision_masiva_con_salon_inexistente_devuelve_404(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/salon",
        data={
            "csrf_token": _token_csrf(cliente),
            "anio_lectivo": "2026",
            "nivel": "Primaria",
            "grado": "6to",
            "seccion": "Z",
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    assert respuesta.status_code == 404


def test_emision_individual_con_alumno_inexistente_devuelve_404(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/individual",
        data={
            "csrf_token": _token_csrf(cliente),
            "alumno_id": "999999",
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    assert respuesta.status_code == 404


def test_emision_individual_con_datos_incompletos_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/individual",
        data={"csrf_token": _token_csrf(cliente), "alumno_id": "x", "periodo_id": ""},
    )
    assert respuesta.status_code == 400


def test_descarga_de_boleta_inexistente_devuelve_404(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.get("/reportes/boletas/bol-inexistente/descargar")
    assert respuesta.status_code == 404


def test_boleta_no_es_accesible_por_otro_operador(entorno: SimpleNamespace) -> None:
    cliente_admin = _loguear(entorno, "admin")
    respuesta = _emitir_individual(cliente_admin, entorno.datos, entorno.datos.periodo_abierto_id)
    enlace = PATRON_DESCARGA.search(respuesta.get_data(as_text=True))
    assert enlace is not None

    cliente_staff = _loguear(entorno, "staff")
    assert cliente_staff.get(enlace.group(1)).status_code == 404


# ---------------------------------------------------------------------------
# Rutas defensivas y ramas de error adicionales
# ---------------------------------------------------------------------------


def test_registrar_blueprints_reportes_es_idempotente(
    entorno: SimpleNamespace,
) -> None:
    registrar_blueprints_reportes(entorno.app)
    registrar_blueprints_reportes(entorno.app)
    assert entorno.app.extensions["blueprints_reportes_registrados"] is True


def test_emision_individual_sin_alumno_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/individual",
        data={
            "csrf_token": _token_csrf(cliente),
            "alumno_id": "",
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    assert respuesta.status_code == 400
    assert "alumno_id" in respuesta.get_data(as_text=True)


def test_emision_masiva_con_anio_invalido_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/salon",
        data={
            "csrf_token": _token_csrf(cliente),
            "anio_lectivo": "",
            "nivel": "Primaria",
            "grado": "3ro",
            "seccion": "A",
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    assert respuesta.status_code == 400
    assert "anio_lectivo" in respuesta.get_data(as_text=True)


def test_emision_masiva_sin_ubicacion_devuelve_400(
    entorno: SimpleNamespace,
) -> None:
    cliente = _loguear(entorno, "admin")
    respuesta = cliente.post(
        "/reportes/boletas/salon",
        data={
            "csrf_token": _token_csrf(cliente),
            "anio_lectivo": "2026",
            "nivel": "",
            "grado": "",
            "seccion": "",
            "periodo_id": str(entorno.datos.periodo_abierto_id),
        },
    )
    assert respuesta.status_code == 400
    assert "salón" in respuesta.get_data(as_text=True)


class _ServicioQueFalla:
    """Doble de servicio que lanza una excepción de dominio controlada."""

    def __init__(self, excepcion: Exception) -> None:
        self._excepcion = excepcion

    def construir_ficha_alumno(self, *_args: object) -> None:
        raise self._excepcion

    def exportar_asistencias(self, *_args: object) -> None:
        raise self._excepcion


def test_ficha_con_acceso_denegado_de_servicio_devuelve_403(
    entorno: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente = _loguear(entorno, "admin")
    monkeypatch.setitem(
        entorno.app.extensions,
        "servicio_academico",
        _ServicioQueFalla(AccesoDenegadoException("Denegado por el dominio.")),
    )
    respuesta = cliente.get(_url_ficha(entorno.datos))
    assert respuesta.status_code == 403


def test_ficha_con_error_de_dominio_generico_devuelve_400(
    entorno: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente = _loguear(entorno, "admin")
    monkeypatch.setitem(
        entorno.app.extensions,
        "servicio_academico",
        _ServicioQueFalla(ValueError("Datos académicos inconsistentes.")),
    )
    respuesta = cliente.get(_url_ficha(entorno.datos))
    assert respuesta.status_code == 400
    assert "inconsistentes" in respuesta.get_data(as_text=True)


def test_exportacion_con_fallo_de_servicio_devuelve_400(
    entorno: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente = _loguear(entorno, "admin")
    monkeypatch.setitem(
        entorno.app.extensions,
        "servicio_academico",
        _ServicioQueFalla(ExportacionException("No fue posible exportar.")),
    )
    respuesta = cliente.post(
        "/reportes/asistencias/exportar",
        data={"csrf_token": _token_csrf(cliente), **_datos_exportacion()},
    )
    assert respuesta.status_code == 400
    assert "exportar" in respuesta.get_data(as_text=True)
