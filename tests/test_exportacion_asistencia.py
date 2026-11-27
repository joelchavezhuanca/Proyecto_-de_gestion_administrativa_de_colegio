"""Pruebas BDD y unitarias del PBI-13: Exportación de Listas de Asistencia."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from src.dominio.asistencia import (
    Alumno,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
)
from src.dominio.exportacion_asistencia import (
    ENCABEZADOS_EXPORTACION,
    DocumentoExportacionAsistencia,
    ExportacionException,
    FilaExportacionAsistencia,
    FiltroExportacionAsistencia,
    FiltroExportacionInvalidoException,
    FormatoExportacion,
    PermisoExportacionException,
    ServicioExportacionAsistencia,
    sanitizar_celda_tabular,
)
from src.dominio.usuarios import PermisoOperacion, Rol

ZONA_LIMA = timezone(timedelta(hours=-5))
FECHA_GEN_LIMA = datetime(2026, 11, 10, 10, 30, 0, tzinfo=ZONA_LIMA)


@pytest.fixture
def admin_op() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_exp", rol=RolUsuario.ADMIN)


@pytest.fixture
def coord_op() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="coord_exp", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def staff_op() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="staff_exp", rol=RolUsuario.ADMIN_STAFF)


@pytest.fixture
def alumnos_muestra() -> list[Alumno]:
    return [
        Alumno(
            id=101,
            codigo="PRI-3A-01",
            dni="71000001",
            nombres="Camila",
            apellidos="Vargas",
            nivel="Primaria",
            grado="3ro",
            seccion="A",
            carnet_codigo="DSV-2026-0001",
        ),
        Alumno(
            id=102,
            codigo="PRI-3A-02",
            dni="71000002",
            nombres="Andrés",
            apellidos="Alarcón",
            nivel="Primaria",
            grado="3ro",
            seccion="A",
            carnet_codigo="DSV-2026-0002",
        ),
        Alumno(
            id=103,
            codigo="PRI-3B-01",
            dni="71000003",
            nombres="Sofía",
            apellidos="Mendoza",
            nivel="Primaria",
            grado="3ro",
            seccion="B",
            carnet_codigo="DSV-2026-0003",
        ),
        Alumno(
            id=104,
            codigo="SEC-5A-01",
            dni="71000004",
            nombres="Mateo",
            apellidos="Rojas",
            nivel="Secundaria",
            grado="5to",
            seccion="A",
            carnet_codigo="DSV-2026-0004",
        ),
    ]


@pytest.fixture
def asistencias_muestra() -> list[RegistroAsistencia]:
    return [
        RegistroAsistencia(
            id="ast-1",
            alumno_id=101,
            fecha_escolar=date(2026, 11, 2),
            hora_efectiva=time(7, 10, 0),
            estado=EstadoAsistencia.PUNTUAL,
            minutos_tardanza=0,
            metodo=MetodoRegistro.CARNET,
            usuario_id=3,
            rol_usuario=RolUsuario.ADMIN_STAFF,
            nivel="Primaria",
            grado="3ro",
            seccion="A",
        ),
        RegistroAsistencia(
            id="ast-2",
            alumno_id=102,
            fecha_escolar=date(2026, 11, 2),
            hora_efectiva=time(7, 25, 0),
            estado=EstadoAsistencia.TARDANZA,
            minutos_tardanza=10,
            metodo=MetodoRegistro.MANUAL_DNI,
            usuario_id=2,
            rol_usuario=RolUsuario.COORDINADOR,
            nivel="Primaria",
            grado="3ro",
            seccion="A",
        ),
        RegistroAsistencia(
            id="ast-3",
            alumno_id=103,
            fecha_escolar=date(2026, 11, 2),
            hora_efectiva=time(9, 0, 0),
            estado=EstadoAsistencia.AUSENTE,
            minutos_tardanza=0,
            metodo=MetodoRegistro.MANUAL_BUSQUEDA,
            usuario_id=0,
            rol_usuario="SYSTEM_CRON",
            nivel="Primaria",
            grado="3ro",
            seccion="B",
        ),
        RegistroAsistencia(
            id="ast-4",
            alumno_id=104,
            fecha_escolar=date(2026, 11, 3),
            hora_efectiva=time(7, 5, 0),
            estado=EstadoAsistencia.PUNTUAL,
            minutos_tardanza=0,
            metodo=MetodoRegistro.CARNET,
            usuario_id=99,
            rol_usuario=RolUsuario.ADMIN,
        ),
        RegistroAsistencia(
            id="ast-5",
            alumno_id=101,
            fecha_escolar=date(2026, 10, 15),
            hora_efectiva=time(7, 8, 0),
            estado=EstadoAsistencia.PUNTUAL,
            minutos_tardanza=0,
            metodo=MetodoRegistro.CARNET,
            usuario_id=3,
            rol_usuario=RolUsuario.ADMIN_STAFF,
            nivel="Primaria",
            grado="3ro",
            seccion="A",
        ),
    ]


@pytest.fixture
def usuarios_mapa() -> dict[int, str]:
    return {
        1: "admin_exp",
        2: "coord_exp",
        3: "staff_exp",
    }


def test_enums_excepciones_y_encabezados() -> None:
    assert set(FormatoExportacion) == {
        FormatoExportacion.CSV,
        FormatoExportacion.XLSX,
        FormatoExportacion.PDF,
    }
    assert issubclass(PermisoExportacionException, ExportacionException)
    assert issubclass(FiltroExportacionInvalidoException, ExportacionException)
    assert len(ENCABEZADOS_EXPORTACION) == 12
    assert ENCABEZADOS_EXPORTACION == (
        "codigo_alumno",
        "dni",
        "apellidos_nombres",
        "nivel",
        "grado",
        "seccion",
        "fecha_escolar",
        "hora_efectiva",
        "estado",
        "minutos_tardanza",
        "metodo",
        "usuario_responsable",
    )


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("=SUM(A1:A10)", "'=SUM(A1:A10)"),
        ("  =1+1", "'  =1+1"),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-10+20", "'-10+20"),
        ("@SUM(1,2)", "'@SUM(1,2)"),
        ("   \t@malicioso", "'   \t@malicioso"),
        ("Quispe, Ana", "Quispe, Ana"),
        ("3ro - A", "3ro - A"),
        ("", ""),
        ("   ", "   "),
    ],
)
def test_sanitizar_celda_tabular_previene_formula_injection(
    entrada: str, esperado: str
) -> None:
    assert sanitizar_celda_tabular(entrada) == esperado


def test_filtro_exportacion_normaliza_y_valida_invariantes() -> None:
    filtro = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2027, 1, 2),  # exactamente 366 días
        formato=FormatoExportacion.XLSX,
        nivel="  Primaria ",
        grado=" 3ro ",
        seccion=" a ",
        estado=EstadoAsistencia.PUNTUAL,
        alumno_id=101,
    )
    assert filtro.nivel == "Primaria"
    assert filtro.grado == "3ro"
    assert filtro.seccion == "a"
    assert filtro.formato == FormatoExportacion.XLSX

    filtro_espacios = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2026, 11, 1),
        nivel="   ",
        grado="",
        seccion="  ",
    )
    assert filtro_espacios.nivel is None
    assert filtro_espacios.grado is None
    assert filtro_espacios.seccion is None

    with pytest.raises(FrozenInstanceError):
        filtro.nivel = "Secundaria"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fecha_desde": date(2026, 11, 10), "fecha_hasta": date(2026, 11, 1)},
        {"fecha_desde": date(2026, 1, 1), "fecha_hasta": date(2027, 1, 3)},  # 367 días
        {"fecha_desde": datetime(2026, 11, 1, 8, 0), "fecha_hasta": date(2026, 11, 2)},
        {"fecha_desde": date(2026, 11, 1), "fecha_hasta": "2026-11-02"},
        {"formato": "DOCX"},
        {"estado": "PUNTUAL"},
        {"alumno_id": 0},
        {"alumno_id": -2},
        {"alumno_id": True},
        {"nivel": 123},
        {"grado": 3},
        {"seccion": ["A"]},
    ],
)
def test_escenario_2_filtro_rechaza_rango_o_parametros_invalidos(
    kwargs: dict[str, object],
) -> None:
    base: dict[str, object] = {
        "fecha_desde": date(2026, 11, 1),
        "fecha_hasta": date(2026, 11, 30),
    }
    base.update(kwargs)
    with pytest.raises(FiltroExportacionInvalidoException):
        FiltroExportacionAsistencia(**base)  # type: ignore[arg-type]


def test_escenario_1_exportar_por_salon_sin_mezclar_secciones_y_ordenado(
    coord_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    asistencias_muestra: list[RegistroAsistencia],
    usuarios_mapa: dict[int, str],
) -> None:
    filtro = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2026, 11, 5),
        formato=FormatoExportacion.CSV,
        nivel="primaria",
        grado="3RO",
        seccion="a",
    )

    doc = ServicioExportacionAsistencia.preparar_exportacion(
        operador=coord_op,
        filtro=filtro,
        alumnos=alumnos_muestra,
        asistencias=asistencias_muestra,
        usuarios_por_id=usuarios_mapa,
        fecha_generacion=datetime(2026, 11, 10, 15, 30, 0, tzinfo=UTC),
    )

    assert isinstance(doc, DocumentoExportacionAsistencia)
    assert doc.formato == FormatoExportacion.CSV
    assert doc.generado_por_id == coord_op.id
    assert doc.generado_por_username == coord_op.username
    assert doc.fecha_generacion == FECHA_GEN_LIMA
    assert doc.filtro == filtro
    assert doc.total_filas == 2
    assert len(doc.filas) == 2

    # Ordenado por (fecha_escolar, nivel, grado, seccion, apellidos_nombres)
    fila_0, fila_1 = doc.filas
    assert isinstance(fila_0, FilaExportacionAsistencia)
    assert fila_0.codigo_alumno == "PRI-3A-02"
    assert fila_0.apellidos_nombres == "Alarcón, Andrés"
    assert fila_0.estado == EstadoAsistencia.TARDANZA
    assert fila_0.minutos_tardanza == 10
    assert fila_0.metodo == MetodoRegistro.MANUAL_DNI
    assert fila_0.usuario_responsable == "coord_exp"
    assert fila_0.a_tupla() == (
        "PRI-3A-02",
        "71000002",
        "Alarcón, Andrés",
        "Primaria",
        "3ro",
        "A",
        "2026-11-02",
        "07:25:00",
        "TARDANZA",
        "10",
        "MANUAL_DNI",
        "coord_exp",
    )

    assert fila_1.codigo_alumno == "PRI-3A-01"
    assert fila_1.apellidos_nombres == "Vargas, Camila"
    assert fila_1.usuario_responsable == "staff_exp"

    with pytest.raises(FrozenInstanceError):
        doc.total_filas = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        fila_0.dni = "00000000"  # type: ignore[misc]


def test_exportar_usa_snapshot_academico_historico_y_fallback_del_alumno(
    admin_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    asistencias_muestra: list[RegistroAsistencia],
    usuarios_mapa: dict[int, str],
) -> None:
    # Alumno 101 fue trasladado después a 3ro B, pero su asistencia ast-1 conserva snapshot 3ro A
    alumnos_trasladados = [
        replace(al, seccion="B") if al.id == 101 else al for al in alumnos_muestra
    ]
    asistencia_sin_alumno = RegistroAsistencia(
        id="ast-huerfana",
        alumno_id=999,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 15, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=1,
        rol_usuario=RolUsuario.ADMIN,
    )

    filtro_todos = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2026, 11, 5),
        formato=FormatoExportacion.XLSX,
    )

    doc = ServicioExportacionAsistencia.preparar_exportacion(
        operador=admin_op,
        filtro=filtro_todos,
        alumnos={al.id: al for al in alumnos_trasladados},
        asistencias=[*asistencias_muestra, asistencia_sin_alumno],
        usuarios_por_id=usuarios_mapa,
        fecha_generacion=datetime(2026, 11, 10, 10, 30, 0),  # naive -> Lima
    )

    assert doc.fecha_generacion == FECHA_GEN_LIMA
    assert doc.total_filas == 4
    por_codigo = {f.codigo_alumno: f for f in doc.filas}
    # Conserva snapshot "A" aunque el alumno actual esté en "B"
    assert por_codigo["PRI-3A-01"].seccion == "A"
    # Alumno 104 tenía snapshot None -> toma datos del alumno
    assert por_codigo["SEC-5A-01"].nivel == "Secundaria"
    assert por_codigo["SEC-5A-01"].grado == "5to"
    assert por_codigo["SEC-5A-01"].seccion == "A"
    assert por_codigo["SEC-5A-01"].usuario_responsable == "usuario:99"
    # Cierre automático con usuario_id=0 usa rol_usuario ("SYSTEM_CRON")
    assert por_codigo["PRI-3B-01"].usuario_responsable == "SYSTEM_CRON"


def test_filtros_por_estado_y_alumno_id(
    staff_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    asistencias_muestra: list[RegistroAsistencia],
    usuarios_mapa: dict[int, str],
) -> None:
    filtro_estado = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2026, 11, 5),
        estado=EstadoAsistencia.AUSENTE,
    )
    doc_estado = ServicioExportacionAsistencia.preparar_exportacion(
        operador=staff_op,
        filtro=filtro_estado,
        alumnos=alumnos_muestra,
        asistencias=asistencias_muestra,
        usuarios_por_id=usuarios_mapa,
        fecha_generacion=FECHA_GEN_LIMA,
    )
    assert [f.codigo_alumno for f in doc_estado.filas] == ["PRI-3B-01"]

    filtro_alumno = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 10, 1),
        fecha_hasta=date(2026, 11, 30),
        alumno_id=101,
    )
    doc_alumno = ServicioExportacionAsistencia.preparar_exportacion(
        operador=staff_op,
        filtro=filtro_alumno,
        alumnos=alumnos_muestra,
        asistencias=asistencias_muestra,
        usuarios_por_id=usuarios_mapa,
        fecha_generacion=FECHA_GEN_LIMA,
    )
    assert [f.fecha_escolar for f in doc_alumno.filas] == [
        date(2026, 10, 15),
        date(2026, 11, 2),
    ]


def test_escenario_3_formula_injection_sanitizada_en_csv_xlsx_y_no_en_pdf(
    admin_op: UsuarioOperador,
) -> None:
    alumno_malicioso = Alumno(
        id=500,
        codigo="=CMD()",
        dni="75555555",
        nombres="@nombre",
        apellidos="+SUM(A1:A2)",
        nivel="Secundaria",
        grado="4to",
        seccion="A",
        carnet_codigo="DSV-2026-500",
    )
    asistencia = RegistroAsistencia(
        id="ast-mal",
        alumno_id=500,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=10,
        rol_usuario=RolUsuario.ADMIN,
        nivel="Secundaria",
        grado="4to",
        seccion="A",
    )

    for formato in (FormatoExportacion.CSV, FormatoExportacion.XLSX):
        doc = ServicioExportacionAsistencia.preparar_exportacion(
            operador=admin_op,
            filtro=FiltroExportacionAsistencia(
                fecha_desde=date(2026, 11, 1),
                fecha_hasta=date(2026, 11, 5),
                formato=formato,
            ),
            alumnos=[alumno_malicioso],
            asistencias=[asistencia],
            usuarios_por_id={10: "-operador"},
            fecha_generacion=FECHA_GEN_LIMA,
        )
        fila = doc.filas[0]
        assert fila.codigo_alumno == "'=CMD()"
        assert fila.apellidos_nombres == "'+SUM(A1:A2), @nombre"
        assert fila.usuario_responsable == "'-operador"

    doc_pdf = ServicioExportacionAsistencia.preparar_exportacion(
        operador=admin_op,
        filtro=FiltroExportacionAsistencia(
            fecha_desde=date(2026, 11, 1),
            fecha_hasta=date(2026, 11, 5),
            formato=FormatoExportacion.PDF,
        ),
        alumnos=[alumno_malicioso],
        asistencias=[asistencia],
        usuarios_por_id={10: "-operador"},
        fecha_generacion=FECHA_GEN_LIMA,
    )
    fila_pdf = doc_pdf.filas[0]
    assert fila_pdf.codigo_alumno == "=CMD()"
    assert fila_pdf.apellidos_nombres == "+SUM(A1:A2), @nombre"
    assert fila_pdf.usuario_responsable == "-operador"


def test_escenario_4_permisos_roles_dinamicos_y_validaciones_entrada(
    admin_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    asistencias_muestra: list[RegistroAsistencia],
    usuarios_mapa: dict[int, str],
) -> None:
    filtro = FiltroExportacionAsistencia(
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2026, 11, 5),
    )

    # Operador inactivo rechazado
    inactivo = replace(admin_op, activo=False)
    with pytest.raises(PermisoExportacionException, match="cuenta activa"):
        ServicioExportacionAsistencia.preparar_exportacion(
            operador=inactivo,
            filtro=filtro,
            alumnos=alumnos_muestra,
            asistencias=asistencias_muestra,
            usuarios_por_id=usuarios_mapa,
            fecha_generacion=FECHA_GEN_LIMA,
        )

    # Rol personalizado sin EXPORTAR_ASISTENCIAS rechazado
    rol_docente = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Solo calificaciones",
        permisos=frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
    )
    rol_reportes = Rol(
        codigo="ANALISTA_REPORTES",
        nombre="Analista de Reportes",
        descripcion="Puede exportar listas de asistencia",
        permisos=frozenset({PermisoOperacion.EXPORTAR_ASISTENCIAS}),
    )
    op_docente = UsuarioOperador(id=20, username="docente", rol="DOCENTE")
    op_reportes = UsuarioOperador(id=21, username="analista", rol="ANALISTA_REPORTES")

    with pytest.raises(PermisoExportacionException, match="no está autorizado"):
        ServicioExportacionAsistencia.preparar_exportacion(
            operador=op_docente,
            filtro=filtro,
            alumnos=alumnos_muestra,
            asistencias=asistencias_muestra,
            usuarios_por_id=usuarios_mapa,
            fecha_generacion=FECHA_GEN_LIMA,
            roles=[rol_docente, rol_reportes],
        )

    doc_custom = ServicioExportacionAsistencia.preparar_exportacion(
        operador=op_reportes,
        filtro=filtro,
        alumnos=alumnos_muestra,
        asistencias=asistencias_muestra,
        usuarios_por_id=usuarios_mapa,
        fecha_generacion=FECHA_GEN_LIMA,
        roles=[rol_docente, rol_reportes],
    )
    assert doc_custom.generado_por_username == "analista"
    assert doc_custom.total_filas == 4

    # Filtro o fecha_generacion inválidos
    with pytest.raises(FiltroExportacionInvalidoException):
        ServicioExportacionAsistencia.preparar_exportacion(
            operador=admin_op,
            filtro="invalido",  # type: ignore[arg-type]
            alumnos=alumnos_muestra,
            asistencias=asistencias_muestra,
            usuarios_por_id=usuarios_mapa,
            fecha_generacion=FECHA_GEN_LIMA,
        )

    with pytest.raises(ExportacionException, match="fecha de generación"):
        ServicioExportacionAsistencia.preparar_exportacion(
            operador=admin_op,
            filtro=filtro,
            alumnos=alumnos_muestra,
            asistencias=asistencias_muestra,
            usuarios_por_id=usuarios_mapa,
            fecha_generacion="2026-11-10",  # type: ignore[arg-type]
        )
