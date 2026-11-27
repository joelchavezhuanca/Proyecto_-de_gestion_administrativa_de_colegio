"""Pruebas BDD y unitarias del PBI-10: Calificaciones y Promedios (Libro de 3 Niveles)."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.dominio.asistencia import UsuarioOperador
from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.calificaciones import (
    ActividadEvaluable,
    ActividadInvalidaException,
    Calificacion,
    CalificacionException,
    EscalaLiteral,
    FechaLimiteNotasVencidaException,
    NotaFueraDeRangoException,
    PeriodoCalificacionCerradoException,
    PermisoCalificacionException,
    PesosRubrosInvalidosException,
    PromedioPeriodo,
    PromedioRubro,
    RubroEvaluacion,
    ServicioCalificaciones,
)
from src.dominio.docentes import AccesoAmbitoDocenteDenegadoException, AsignacionDocente
from src.dominio.justificaciones import PeriodoAcademico, TipoPeriodo
from src.dominio.usuarios import EstadoUsuario, PermisoOperacion, Rol, RolUsuario, Usuario

ANIO = 2026
FECHA_ACTUAL = date(2026, 4, 10)
FECHA_HORA = datetime(2026, 4, 10, 10, 30, tzinfo=ZONA_HORARIA_LIMA)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rol_docente() -> Rol:
    return Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Registra calificaciones de sus grupos asignados",
        permisos=frozenset(
            {
                PermisoOperacion.REGISTRAR_CALIFICACIONES,
                PermisoOperacion.CONSULTAR_CALIFICACIONES,
            }
        ),
    )


@pytest.fixture
def roles(rol_docente: Rol) -> tuple[Rol, ...]:
    return (rol_docente,)


def _usuario(id_: int, rol: RolUsuario | str, estado=EstadoUsuario.ACTIVO) -> Usuario:
    return Usuario(
        id=id_,
        username=f"user{id_}",
        password_hash="hash",
        salt="salt",
        nombre_completo=f"Usuario {id_}",
        rol=rol,
        estado=estado,
    )


@pytest.fixture
def docente() -> Usuario:
    return _usuario(10, "DOCENTE")


@pytest.fixture
def otro_docente() -> Usuario:
    return _usuario(11, "DOCENTE")


@pytest.fixture
def admin() -> Usuario:
    return _usuario(1, RolUsuario.ADMIN)


@pytest.fixture
def asignacion() -> AsignacionDocente:
    return AsignacionDocente(
        id="asg-1",
        usuario_docente_id=10,
        curso_id=5,
        salon_id=7,
        anio_lectivo=ANIO,
    )


@pytest.fixture
def asignaciones(asignacion: AsignacionDocente) -> tuple[AsignacionDocente, ...]:
    return (asignacion,)


@pytest.fixture
def periodo() -> PeriodoAcademico:
    return PeriodoAcademico(
        id=1,
        nombre="I Bimestre",
        fecha_inicio=date(2026, 3, 2),
        fecha_fin=date(2026, 5, 8),
        anio_lectivo=ANIO,
        tipo_periodo=TipoPeriodo.BIMESTRE,
        orden=1,
        fecha_limite_notas=date(2026, 5, 15),
    )


@pytest.fixture
def rubros(docente, asignacion, periodo, asignaciones, roles) -> tuple[RubroEvaluacion, ...]:
    return ServicioCalificaciones.configurar_rubros(
        docente,
        asignacion,
        periodo,
        [
            ("Exámenes", Decimal("50")),
            ("Prácticas", Decimal("30")),
            ("Tareas", Decimal("20")),
        ],
        FECHA_ACTUAL,
        asignaciones,
        roles=roles,
    )


@pytest.fixture
def actividad(docente, asignacion, periodo, rubros, asignaciones, roles) -> ActividadEvaluable:
    return ServicioCalificaciones.crear_actividad(
        docente,
        asignacion,
        periodo,
        rubros[0],
        "Examen parcial",
        date(2026, 4, 8),
        FECHA_ACTUAL,
        asignaciones,
        roles=roles,
    )


def _actividad(id_: str, rubro_id: str, activo: bool = True) -> ActividadEvaluable:
    return ActividadEvaluable(
        id=id_, rubro_id=rubro_id, titulo=f"Act {id_}", fecha=date(2026, 4, 1), activo=activo
    )


def _nota(actividad_id: str, alumno_id: int, nota: str) -> Calificacion:
    return Calificacion(
        id=f"cal-{actividad_id}-{alumno_id}",
        actividad_id=actividad_id,
        alumno_id=alumno_id,
        nota=Decimal(nota),
        usuario_id=10,
        actualizado_en=FECHA_HORA,
    )


# ---------------------------------------------------------------------------
# Escala literal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nota", "esperado"),
    [
        ("20", EscalaLiteral.AD),
        ("18", EscalaLiteral.AD),
        ("17.99", EscalaLiteral.A),
        ("14", EscalaLiteral.A),
        ("13.99", EscalaLiteral.B),
        ("11", EscalaLiteral.B),
        ("10.99", EscalaLiteral.C),
        ("0", EscalaLiteral.C),
    ],
)
def test_convertir_a_literal(nota: str, esperado: EscalaLiteral) -> None:
    assert ServicioCalificaciones.convertir_a_literal(Decimal(nota)) is esperado


def test_escala_literal_es_str_enum() -> None:
    assert EscalaLiteral.AD == "AD"
    assert [e.value for e in EscalaLiteral] == ["AD", "A", "B", "C"]


@pytest.mark.parametrize("nota", [Decimal("-0.01"), Decimal("20.01"), 15.0, "15", True])
def test_convertir_a_literal_rechaza_valores_invalidos(nota: object) -> None:
    with pytest.raises(NotaFueraDeRangoException):
        ServicioCalificaciones.convertir_a_literal(nota)  # type: ignore[arg-type]


def test_convertir_a_literal_acepta_enteros() -> None:
    assert ServicioCalificaciones.convertir_a_literal(14) is EscalaLiteral.A  # type: ignore[arg-type]


def test_convertir_a_literal_rechaza_nan() -> None:
    with pytest.raises(NotaFueraDeRangoException):
        ServicioCalificaciones.convertir_a_literal(Decimal("NaN"))


# ---------------------------------------------------------------------------
# Escenario 1 y 2: configuración de rubros
# ---------------------------------------------------------------------------


def test_configurar_rubros_suma_100(rubros, asignacion, periodo) -> None:
    assert [r.nombre for r in rubros] == ["Exámenes", "Prácticas", "Tareas"]
    assert sum(r.peso_porcentaje for r in rubros) == Decimal("100")
    assert all(r.asignacion_docente_id == asignacion.id for r in rubros)
    assert all(r.periodo_id == periodo.id for r in rubros)
    assert all(r.activo for r in rubros)
    assert len({r.id for r in rubros}) == 3
    assert isinstance(rubros, tuple)


@pytest.mark.parametrize(
    "pesos",
    [
        (Decimal("50"), Decimal("30"), Decimal("10")),  # 90 %
        (Decimal("50"), Decimal("30"), Decimal("30")),  # 110 %
    ],
)
def test_rechaza_rubros_que_no_suman_100(
    docente, asignacion, periodo, asignaciones, roles, pesos
) -> None:
    propuestos = list(zip(("Exámenes", "Prácticas", "Tareas"), pesos, strict=True))
    with pytest.raises(PesosRubrosInvalidosException):
        ServicioCalificaciones.configurar_rubros(
            docente, asignacion, periodo, propuestos, FECHA_ACTUAL, asignaciones, roles=roles
        )


@pytest.mark.parametrize(
    "propuestos",
    [
        [],
        [("Exámenes", Decimal("0")), ("Tareas", Decimal("100"))],
        [("Exámenes", Decimal("-10")), ("Tareas", Decimal("110"))],
        [("Exámenes", 100.0)],
        [("Exámenes", "100")],
        [("Exámenes", Decimal("Infinity"))],
    ],
)
def test_rechaza_pesos_invalidos(
    docente, asignacion, periodo, asignaciones, roles, propuestos
) -> None:
    with pytest.raises(PesosRubrosInvalidosException):
        ServicioCalificaciones.configurar_rubros(
            docente, asignacion, periodo, propuestos, FECHA_ACTUAL, asignaciones, roles=roles
        )


def test_acepta_pesos_enteros_y_decimales(docente, asignacion, periodo, asignaciones, roles):
    rubros = ServicioCalificaciones.configurar_rubros(
        docente,
        asignacion,
        periodo,
        [("Exámenes", 60), ("Tareas", Decimal("33.33")), ("Orales", Decimal("6.67"))],
        FECHA_ACTUAL,
        asignaciones,
        roles=roles,
    )
    assert rubros[0].peso_porcentaje == Decimal("60")
    assert isinstance(rubros[0].peso_porcentaje, Decimal)


def test_rechaza_nombres_de_rubro_duplicados(docente, asignacion, periodo, asignaciones, roles):
    with pytest.raises(CalificacionException, match="únic"):
        ServicioCalificaciones.configurar_rubros(
            docente,
            asignacion,
            periodo,
            [("Tareas", Decimal("50")), ("  tareas ", Decimal("50"))],
            FECHA_ACTUAL,
            asignaciones,
            roles=roles,
        )


def test_rechaza_nombre_de_rubro_vacio(docente, asignacion, periodo, asignaciones, roles):
    with pytest.raises(CalificacionException):
        ServicioCalificaciones.configurar_rubros(
            docente,
            asignacion,
            periodo,
            [("   ", Decimal("100"))],
            FECHA_ACTUAL,
            asignaciones,
            roles=roles,
        )


def test_rechaza_periodo_de_otro_anio_lectivo(docente, asignacion, asignaciones, roles):
    periodo_2025 = PeriodoAcademico(
        id=9,
        nombre="IV Bimestre 2025",
        fecha_inicio=date(2025, 10, 1),
        fecha_fin=date(2025, 12, 15),
        anio_lectivo=2025,
    )
    with pytest.raises(CalificacionException, match="año lectivo"):
        ServicioCalificaciones.configurar_rubros(
            docente,
            asignacion,
            periodo_2025,
            [("Exámenes", Decimal("100"))],
            date(2025, 11, 1),
            asignaciones,
            roles=roles,
        )


# ---------------------------------------------------------------------------
# Escenario 4 y 5: período cerrado / fecha límite / prórroga
# ---------------------------------------------------------------------------


def test_bloquea_rubros_si_periodo_cerrado(docente, asignacion, periodo, asignaciones, roles):
    cerrado = PeriodoAcademico(
        id=periodo.id,
        nombre=periodo.nombre,
        fecha_inicio=periodo.fecha_inicio,
        fecha_fin=periodo.fecha_fin,
        anio_lectivo=ANIO,
        cerrado=True,
        fecha_limite_notas=periodo.fecha_limite_notas,
    )
    with pytest.raises(PeriodoCalificacionCerradoException):
        ServicioCalificaciones.configurar_rubros(
            docente,
            asignacion,
            cerrado,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            asignaciones,
            roles=roles,
        )


def test_bloquea_rubros_tras_fecha_limite(docente, asignacion, periodo, asignaciones, roles):
    with pytest.raises(FechaLimiteNotasVencidaException):
        ServicioCalificaciones.configurar_rubros(
            docente,
            asignacion,
            periodo,
            [("Exámenes", Decimal("100"))],
            date(2026, 5, 16),
            asignaciones,
            roles=roles,
        )


def test_permite_operar_el_mismo_dia_de_la_fecha_limite(
    docente, asignacion, periodo, asignaciones, roles
):
    rubros = ServicioCalificaciones.configurar_rubros(
        docente,
        asignacion,
        periodo,
        [("Exámenes", Decimal("100"))],
        date(2026, 5, 15),
        asignaciones,
        roles=roles,
    )
    assert len(rubros) == 1


def test_periodo_sin_fecha_limite_no_bloquea(docente, asignacion, asignaciones, roles):
    sin_limite = PeriodoAcademico(
        id=2,
        nombre="II Bimestre",
        fecha_inicio=date(2026, 5, 18),
        fecha_fin=date(2026, 7, 24),
        anio_lectivo=ANIO,
    )
    rubros = ServicioCalificaciones.configurar_rubros(
        docente,
        asignacion,
        sin_limite,
        [("Exámenes", Decimal("100"))],
        date(2027, 1, 1),
        asignaciones,
        roles=roles,
    )
    assert rubros[0].periodo_id == 2


def test_fecha_hora_utc_se_evalua_en_hora_lima(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    # 2026-05-16 03:00 UTC == 2026-05-15 22:00 en Lima -> aún dentro del plazo.
    dentro = datetime(2026, 5, 16, 3, 0, tzinfo=UTC)
    cal = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, periodo, actividad, 100, Decimal("15"), dentro, asignaciones,
        roles=roles,
    )
    assert cal.actualizado_en.utcoffset() == ZONA_HORARIA_LIMA.utcoffset(None)

    # 2026-05-16 05:30 UTC == 2026-05-16 00:30 en Lima -> plazo vencido.
    fuera = datetime(2026, 5, 16, 5, 30, tzinfo=UTC)
    with pytest.raises(FechaLimiteNotasVencidaException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, Decimal("15"), fuera, asignaciones,
            roles=roles,
        )


def test_prorroga_de_fecha_limite_permite_regularizar(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    fecha_vencida = datetime(2026, 5, 20, 9, 0, tzinfo=ZONA_HORARIA_LIMA)
    with pytest.raises(FechaLimiteNotasVencidaException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, Decimal("12"), fecha_vencida,
            asignaciones, roles=roles,
        )

    prorrogado = PeriodoAcademico(
        id=periodo.id,
        nombre=periodo.nombre,
        fecha_inicio=periodo.fecha_inicio,
        fecha_fin=periodo.fecha_fin,
        anio_lectivo=ANIO,
        fecha_limite_notas=date(2026, 5, 22),
    )
    cal = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, prorrogado, actividad, 100, Decimal("12"), fecha_vencida,
        asignaciones, roles=roles,
    )
    assert cal.nota == Decimal("12.00")


# ---------------------------------------------------------------------------
# Escenario 6 y permisos
# ---------------------------------------------------------------------------


def test_docente_sin_asignacion_es_denegado(otro_docente, asignacion, periodo, asignaciones, roles):
    with pytest.raises(AccesoAmbitoDocenteDenegadoException):
        ServicioCalificaciones.configurar_rubros(
            otro_docente,
            asignacion,
            periodo,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            asignaciones,
            roles=roles,
        )


def test_docente_denegado_al_calificar_salon_ajeno(
    otro_docente, asignacion, periodo, actividad, asignaciones, roles
):
    with pytest.raises(AccesoAmbitoDocenteDenegadoException):
        ServicioCalificaciones.registrar_calificacion(
            otro_docente, asignacion, periodo, actividad, 100, Decimal("15"), FECHA_HORA,
            asignaciones, roles=roles,
        )


def test_docente_con_asignacion_ajena_del_mismo_grupo_es_denegado(
    docente, periodo, roles
):
    # El docente tiene asignación activa propia, pero se presenta otra asignación (ajena).
    propia = AsignacionDocente(
        id="asg-propia", usuario_docente_id=10, curso_id=5, salon_id=7, anio_lectivo=ANIO
    )
    ajena = AsignacionDocente(
        id="asg-ajena", usuario_docente_id=99, curso_id=5, salon_id=7, anio_lectivo=ANIO
    )
    with pytest.raises(PermisoCalificacionException):
        ServicioCalificaciones.configurar_rubros(
            docente,
            ajena,
            periodo,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            (propia, ajena),
            roles=roles,
        )


def test_usuario_sin_permiso_registrar_calificaciones(asignacion, periodo, asignaciones):
    coordinador = _usuario(20, RolUsuario.COORDINADOR)
    with pytest.raises(PermisoCalificacionException):
        ServicioCalificaciones.configurar_rubros(
            coordinador,
            asignacion,
            periodo,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            asignaciones,
        )


def test_usuario_inactivo_es_denegado(asignacion, periodo, asignaciones, roles):
    inactivo = _usuario(10, "DOCENTE", estado=EstadoUsuario.INACTIVO)
    with pytest.raises(PermisoCalificacionException):
        ServicioCalificaciones.configurar_rubros(
            inactivo,
            asignacion,
            periodo,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            asignaciones,
            roles=roles,
        )


def test_rol_personalizado_desconocido_sin_catalogo_es_denegado(
    docente, asignacion, periodo, asignaciones
):
    with pytest.raises(PermisoCalificacionException):
        ServicioCalificaciones.configurar_rubros(
            docente,
            asignacion,
            periodo,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            asignaciones,
        )


def test_asignacion_revocada_es_denegada(docente, periodo, roles):
    revocada = AsignacionDocente(
        id="asg-1",
        usuario_docente_id=10,
        curso_id=5,
        salon_id=7,
        anio_lectivo=ANIO,
        activa=False,
    )
    with pytest.raises(PermisoCalificacionException):
        ServicioCalificaciones.configurar_rubros(
            docente,
            revocada,
            periodo,
            [("Exámenes", Decimal("100"))],
            FECHA_ACTUAL,
            (revocada,),
            roles=roles,
        )


def test_admin_no_requiere_asignacion_propia(admin, asignacion, periodo):
    rubros = ServicioCalificaciones.configurar_rubros(
        admin,
        asignacion,
        periodo,
        [("Exámenes", Decimal("100"))],
        FECHA_ACTUAL,
        (),
    )
    assert rubros[0].asignacion_docente_id == asignacion.id


@pytest.mark.parametrize(("activo", "permitido"), [(True, True), (False, False)])
def test_operador_de_asistencia_admin(asignacion, periodo, activo, permitido):
    operador = UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=activo)
    propuestos = [("Exámenes", Decimal("100"))]
    if permitido:
        rubros = ServicioCalificaciones.configurar_rubros(
            operador, asignacion, periodo, propuestos, FECHA_ACTUAL, ()
        )
        assert len(rubros) == 1
    else:
        with pytest.raises(PermisoCalificacionException):
            ServicioCalificaciones.configurar_rubros(
                operador, asignacion, periodo, propuestos, FECHA_ACTUAL, ()
            )


# ---------------------------------------------------------------------------
# Actividades evaluables
# ---------------------------------------------------------------------------


def test_crear_actividad(actividad, rubros) -> None:
    assert actividad.rubro_id == rubros[0].id
    assert actividad.titulo == "Examen parcial"
    assert actividad.fecha == date(2026, 4, 8)
    assert actividad.activo is True
    assert actividad.id


def test_crear_actividad_con_fecha_en_prorroga_de_notas(
    docente, asignacion, periodo, rubros, asignaciones, roles
):
    # Después de fecha_fin pero antes de fecha_limite_notas (regularización).
    act = ServicioCalificaciones.crear_actividad(
        docente, asignacion, periodo, rubros[1], "Práctica de recuperación",
        date(2026, 5, 12), date(2026, 5, 12), asignaciones, roles=roles,
    )
    assert act.fecha == date(2026, 5, 12)


def test_crear_actividad_acepta_datetime_y_lo_normaliza(
    docente, asignacion, periodo, rubros, asignaciones, roles
):
    act = ServicioCalificaciones.crear_actividad(
        docente, asignacion, periodo, rubros[2], "Tarea 1",
        datetime(2026, 4, 2, 3, 0, tzinfo=UTC), FECHA_HORA, asignaciones, roles=roles,
    )
    assert act.fecha == date(2026, 4, 1)
    assert type(act.fecha) is date


@pytest.mark.parametrize("fecha", [date(2026, 3, 1), date(2026, 5, 16)])
def test_crear_actividad_fuera_del_periodo(
    docente, asignacion, periodo, rubros, asignaciones, roles, fecha
):
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.crear_actividad(
            docente, asignacion, periodo, rubros[0], "Examen", fecha, FECHA_ACTUAL,
            asignaciones, roles=roles,
        )


def test_crear_actividad_titulo_vacio(docente, asignacion, periodo, rubros, asignaciones, roles):
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.crear_actividad(
            docente, asignacion, periodo, rubros[0], "  ", date(2026, 4, 1), FECHA_ACTUAL,
            asignaciones, roles=roles,
        )


def test_crear_actividad_rubro_inactivo(docente, asignacion, periodo, asignaciones, roles):
    inactivo = RubroEvaluacion(
        id="rub-x",
        asignacion_docente_id=asignacion.id,
        periodo_id=periodo.id,
        nombre="Tareas",
        peso_porcentaje=Decimal("20"),
        activo=False,
    )
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.crear_actividad(
            docente, asignacion, periodo, inactivo, "Tarea", date(2026, 4, 1), FECHA_ACTUAL,
            asignaciones, roles=roles,
        )


@pytest.mark.parametrize(
    ("asignacion_id", "periodo_id"),
    [("asg-otra", 1), ("asg-1", 2)],
)
def test_crear_actividad_rubro_de_otro_contexto(
    docente, asignacion, periodo, asignaciones, roles, asignacion_id, periodo_id
):
    ajeno = RubroEvaluacion(
        id="rub-y",
        asignacion_docente_id=asignacion_id,
        periodo_id=periodo_id,
        nombre="Tareas",
        peso_porcentaje=Decimal("20"),
    )
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.crear_actividad(
            docente, asignacion, periodo, ajeno, "Tarea", date(2026, 4, 1), FECHA_ACTUAL,
            asignaciones, roles=roles,
        )


def test_crear_actividad_fecha_invalida(docente, asignacion, periodo, rubros, asignaciones, roles):
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.crear_actividad(
            docente, asignacion, periodo, rubros[0], "Tarea", "2026-04-01", FECHA_ACTUAL,  # type: ignore[arg-type]
            asignaciones, roles=roles,
        )


def test_crear_actividad_bloqueada_tras_fecha_limite(
    docente, asignacion, periodo, rubros, asignaciones, roles
):
    with pytest.raises(FechaLimiteNotasVencidaException):
        ServicioCalificaciones.crear_actividad(
            docente, asignacion, periodo, rubros[0], "Tarea", date(2026, 4, 1),
            date(2026, 6, 1), asignaciones, roles=roles,
        )


# ---------------------------------------------------------------------------
# Escenario 3: registro de calificaciones
# ---------------------------------------------------------------------------


def test_registrar_calificacion(docente, asignacion, periodo, actividad, asignaciones, roles):
    cal = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, periodo, actividad, 100, Decimal("16.5"), FECHA_HORA,
        asignaciones, observacion="  Buen desempeño ", roles=roles,
    )
    assert cal.actividad_id == actividad.id
    assert cal.alumno_id == 100
    assert cal.nota == Decimal("16.50")
    assert cal.usuario_id == docente.id
    assert cal.actualizado_en == FECHA_HORA
    assert cal.observacion == "Buen desempeño"
    assert cal.nota_anterior is None
    assert cal.motivo_modificacion is None


def test_registrar_calificacion_redondea_half_up(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    cal = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, periodo, actividad, 100, Decimal("14.125"), FECHA_HORA,
        asignaciones, roles=roles,
    )
    assert cal.nota == Decimal("14.13")


def test_registrar_calificacion_naive_se_asume_lima(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    cal = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, periodo, actividad, 100, 15, datetime(2026, 4, 10, 8, 0),
        asignaciones, roles=roles,
    )
    assert cal.actualizado_en.tzinfo is not None
    assert cal.nota == Decimal("15.00")


@pytest.mark.parametrize("nota", [Decimal("-1"), Decimal("21"), 15.5, "15", None])
def test_rechaza_nota_fuera_de_rango_o_tipo(
    docente, asignacion, periodo, actividad, asignaciones, roles, nota
):
    with pytest.raises(NotaFueraDeRangoException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, nota, FECHA_HORA, asignaciones,
            roles=roles,
        )


def test_modificar_nota_exige_motivo_y_conserva_anterior(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    original = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, periodo, actividad, 100, Decimal("11"), FECHA_HORA, asignaciones,
        roles=roles,
    )
    with pytest.raises(CalificacionException, match="motivo"):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, Decimal("14"), FECHA_HORA,
            asignaciones, calificacion_existente=original, roles=roles,
        )
    with pytest.raises(CalificacionException, match="motivo"):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, Decimal("14"), FECHA_HORA,
            asignaciones, calificacion_existente=original, motivo_modificacion="   ",
            roles=roles,
        )

    modificada = ServicioCalificaciones.registrar_calificacion(
        docente, asignacion, periodo, actividad, 100, Decimal("14"), FECHA_HORA, asignaciones,
        calificacion_existente=original, motivo_modificacion=" Revisión de examen ",
        roles=roles,
    )
    assert modificada.id == original.id
    assert modificada.nota == Decimal("14.00")
    assert modificada.nota_anterior == Decimal("11.00")
    assert modificada.motivo_modificacion == "Revisión de examen"


@pytest.mark.parametrize(("actividad_id", "alumno_id"), [("otra", 100), (None, 999)])
def test_modificar_nota_de_otra_actividad_o_alumno(
    docente, asignacion, periodo, actividad, asignaciones, roles, actividad_id, alumno_id
):
    existente = _nota(actividad_id or actividad.id, alumno_id, "10")
    with pytest.raises(CalificacionException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, Decimal("14"), FECHA_HORA,
            asignaciones, calificacion_existente=existente, motivo_modificacion="Error",
            roles=roles,
        )


def test_registrar_calificacion_actividad_inactiva(
    docente, asignacion, periodo, asignaciones, roles
):
    inactiva = _actividad("act-x", "rub-1", activo=False)
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, inactiva, 100, Decimal("14"), FECHA_HORA,
            asignaciones, roles=roles,
        )


@pytest.mark.parametrize("alumno_id", [0, -5, True, "100"])
def test_registrar_calificacion_alumno_invalido(
    docente, asignacion, periodo, actividad, asignaciones, roles, alumno_id
):
    with pytest.raises(CalificacionException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, alumno_id, Decimal("14"), FECHA_HORA,
            asignaciones, roles=roles,
        )


def test_registrar_calificacion_periodo_cerrado(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    cerrado = PeriodoAcademico(
        id=periodo.id,
        nombre=periodo.nombre,
        fecha_inicio=periodo.fecha_inicio,
        fecha_fin=periodo.fecha_fin,
        anio_lectivo=ANIO,
        cerrado=True,
    )
    with pytest.raises(PeriodoCalificacionCerradoException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, cerrado, actividad, 100, Decimal("14"), FECHA_HORA,
            asignaciones, roles=roles,
        )


def test_registrar_calificacion_fecha_hora_invalida(
    docente, asignacion, periodo, actividad, asignaciones, roles
):
    with pytest.raises(CalificacionException):
        ServicioCalificaciones.registrar_calificacion(
            docente, asignacion, periodo, actividad, 100, Decimal("14"), date(2026, 4, 10),  # type: ignore[arg-type]
            asignaciones, roles=roles,
        )


# ---------------------------------------------------------------------------
# Escenario 1: promedio de período (Decimal exacto, sin EXONERADO)
# ---------------------------------------------------------------------------


@pytest.fixture
def libro_completo(rubros):
    examenes, practicas, tareas = rubros
    actividades = (
        _actividad("ex1", examenes.id),
        _actividad("ex2", examenes.id),
        _actividad("pr1", practicas.id),
        _actividad("ta1", tareas.id),
        _actividad("ta2", tareas.id),
        _actividad("ta3", tareas.id),
    )
    calificaciones = (
        _nota("ex1", 100, "15"),
        _nota("ex2", 100, "18"),
        _nota("pr1", 100, "14"),
        _nota("ta1", 100, "20"),
        _nota("ta2", 100, "17"),
        _nota("ta3", 100, "16"),
        _nota("ex1", 200, "05"),  # otro alumno, no debe interferir
    )
    return rubros, actividades, calificaciones


def test_calcular_promedio_periodo_exacto(libro_completo) -> None:
    rubros, actividades, calificaciones = libro_completo
    resultado = ServicioCalificaciones.calcular_promedio_periodo(
        100, 5, 1, rubros, actividades, calificaciones
    )
    assert isinstance(resultado, PromedioPeriodo)
    assert resultado.alumno_id == 100
    assert resultado.curso_id == 5
    assert resultado.periodo_id == 1
    # Exámenes: (15 + 18) / 2 = 16.50 ; Prácticas: 14.00 ; Tareas: 53 / 3 = 17.666.. -> 17.67
    assert [p.promedio for p in resultado.desglose_rubros] == [
        Decimal("16.50"),
        Decimal("14.00"),
        Decimal("17.67"),
    ]
    assert all(isinstance(p, PromedioRubro) for p in resultado.desglose_rubros)
    assert resultado.desglose_rubros[0].nombre_rubro == "Exámenes"
    assert resultado.desglose_rubros[0].peso_porcentaje == Decimal("50")
    # 16.50*0.5 + 14.00*0.3 + 17.67*0.2 = 8.25 + 4.20 + 3.534 = 15.984 -> 15.98
    assert resultado.nota_final == Decimal("15.98")
    assert resultado.escala_literal is EscalaLiteral.A


def test_promedio_actividad_sin_nota_cuenta_como_cero(libro_completo) -> None:
    rubros, actividades, calificaciones = libro_completo
    sin_ta3 = tuple(c for c in calificaciones if c.actividad_id != "ta3")
    resultado = ServicioCalificaciones.calcular_promedio_periodo(
        100, 5, 1, rubros, actividades, sin_ta3
    )
    # Tareas: (20 + 17 + 0) / 3 = 12.333.. -> 12.33
    assert resultado.desglose_rubros[2].promedio == Decimal("12.33")
    # 8.25 + 4.20 + 2.466 = 14.916 -> 14.92
    assert resultado.nota_final == Decimal("14.92")


def test_promedio_falta_nota_lanza_si_no_se_trata_como_cero(libro_completo) -> None:
    rubros, actividades, calificaciones = libro_completo
    sin_ta3 = tuple(c for c in calificaciones if c.actividad_id != "ta3")
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.calcular_promedio_periodo(
            100, 5, 1, rubros, actividades, sin_ta3, tratar_faltante_como_cero=False
        )


def test_promedio_ignora_actividades_inactivas_y_rubros_de_otro_periodo(libro_completo):
    rubros, actividades, calificaciones = libro_completo
    otro_periodo = RubroEvaluacion(
        id="rub-otro",
        asignacion_docente_id="asg-1",
        periodo_id=2,
        nombre="Otro",
        peso_porcentaje=Decimal("100"),
    )
    rubro_inactivo = RubroEvaluacion(
        id="rub-inact",
        asignacion_docente_id="asg-1",
        periodo_id=1,
        nombre="Viejo",
        peso_porcentaje=Decimal("40"),
        activo=False,
    )
    extra = (*actividades, _actividad("ta-borrada", rubros[2].id, activo=False))
    resultado = ServicioCalificaciones.calcular_promedio_periodo(
        100, 5, 1, (*rubros, otro_periodo, rubro_inactivo), extra, calificaciones
    )
    assert len(resultado.desglose_rubros) == 3
    assert resultado.nota_final == Decimal("15.98")


def test_promedio_rubros_no_suman_100(libro_completo) -> None:
    rubros, actividades, calificaciones = libro_completo
    with pytest.raises(PesosRubrosInvalidosException):
        ServicioCalificaciones.calcular_promedio_periodo(
            100, 5, 1, rubros[:2], actividades, calificaciones
        )


def test_promedio_sin_rubros(libro_completo) -> None:
    _, actividades, calificaciones = libro_completo
    with pytest.raises(PesosRubrosInvalidosException):
        ServicioCalificaciones.calcular_promedio_periodo(
            100, 5, 1, (), actividades, calificaciones
        )


def test_promedio_rubro_sin_actividades(libro_completo) -> None:
    rubros, actividades, calificaciones = libro_completo
    sin_tareas = tuple(a for a in actividades if a.rubro_id != rubros[2].id)
    with pytest.raises(ActividadInvalidaException):
        ServicioCalificaciones.calcular_promedio_periodo(
            100, 5, 1, rubros, sin_tareas, calificaciones
        )


def test_promedio_nota_perfecta_y_nula() -> None:
    rubro = RubroEvaluacion(
        id="r", asignacion_docente_id="a", periodo_id=1, nombre="Único",
        peso_porcentaje=Decimal("100"),
    )
    acts = (_actividad("a1", "r"),)
    veinte = ServicioCalificaciones.calcular_promedio_periodo(
        1, 5, 1, (rubro,), acts, (_nota("a1", 1, "20"),)
    )
    cero = ServicioCalificaciones.calcular_promedio_periodo(1, 5, 1, (rubro,), acts, ())
    assert veinte.nota_final == Decimal("20.00")
    assert veinte.escala_literal is EscalaLiteral.AD
    assert cero.nota_final == Decimal("0.00")
    assert cero.escala_literal is EscalaLiteral.C


# ---------------------------------------------------------------------------
# Promedio anual
# ---------------------------------------------------------------------------


def _promedio_periodo(periodo_id: int, nota: str, alumno_id: int = 100, curso_id: int = 5):
    return PromedioPeriodo(
        alumno_id=alumno_id,
        curso_id=curso_id,
        periodo_id=periodo_id,
        desglose_rubros=(),
        nota_final=Decimal(nota),
        escala_literal=ServicioCalificaciones.convertir_a_literal(Decimal(nota)),
    )


def test_calcular_promedio_anual() -> None:
    periodos = (
        _promedio_periodo(1, "15.98"),
        _promedio_periodo(2, "12.50"),
        _promedio_periodo(3, "17.01"),
        _promedio_periodo(4, "10.00"),
    )
    anual = ServicioCalificaciones.calcular_promedio_anual(100, 5, ANIO, periodos)
    # (15.98 + 12.50 + 17.01 + 10.00) / 4 = 55.49 / 4 = 13.8725 -> 13.87
    assert anual.promedio_anual == Decimal("13.87")
    assert anual.escala_literal is EscalaLiteral.B
    assert anual.promedios_periodo == periodos
    assert (anual.alumno_id, anual.curso_id, anual.anio_lectivo) == (100, 5, ANIO)


def test_promedio_anual_half_up() -> None:
    periodos = (_promedio_periodo(1, "13.99"), _promedio_periodo(2, "14.00"))
    # 27.99 / 2 = 13.995 -> 14.00 (ROUND_HALF_UP)
    anual = ServicioCalificaciones.calcular_promedio_anual(100, 5, ANIO, periodos)
    assert anual.promedio_anual == Decimal("14.00")
    assert anual.escala_literal is EscalaLiteral.A


def test_promedio_anual_sin_periodos() -> None:
    with pytest.raises(CalificacionException):
        ServicioCalificaciones.calcular_promedio_anual(100, 5, ANIO, ())


@pytest.mark.parametrize(
    "periodos",
    [
        (_promedio_periodo(1, "15"), _promedio_periodo(2, "15", alumno_id=200)),
        (_promedio_periodo(1, "15"), _promedio_periodo(2, "15", curso_id=6)),
        (_promedio_periodo(1, "15"), _promedio_periodo(1, "12")),
    ],
)
def test_promedio_anual_inconsistente(periodos) -> None:
    with pytest.raises(CalificacionException):
        ServicioCalificaciones.calcular_promedio_anual(100, 5, ANIO, periodos)


# ---------------------------------------------------------------------------
# Entidades inmutables y validaciones de construcción
# ---------------------------------------------------------------------------


def test_entidades_son_inmutables(rubros, actividad) -> None:
    with pytest.raises(FrozenInstanceError):
        rubros[0].peso_porcentaje = Decimal("10")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        actividad.titulo = "Otro"  # type: ignore[misc]
    cal = _nota("a", 1, "10")
    with pytest.raises(FrozenInstanceError):
        cal.nota = Decimal("20")  # type: ignore[misc]


def test_jerarquia_de_excepciones() -> None:
    for exc in (
        PermisoCalificacionException,
        NotaFueraDeRangoException,
        PesosRubrosInvalidosException,
        PeriodoCalificacionCerradoException,
        FechaLimiteNotasVencidaException,
        ActividadInvalidaException,
    ):
        assert issubclass(exc, CalificacionException)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": " "},
        {"asignacion_docente_id": ""},
        {"periodo_id": 0},
        {"nombre": ""},
        {"activo": "si"},
    ],
)
def test_rubro_invalido(kwargs) -> None:
    base = {
        "id": "r",
        "asignacion_docente_id": "a",
        "periodo_id": 1,
        "nombre": "Tareas",
        "peso_porcentaje": Decimal("20"),
    }
    with pytest.raises(CalificacionException):
        RubroEvaluacion(**(base | kwargs))


def test_rubro_peso_mayor_a_100() -> None:
    with pytest.raises(PesosRubrosInvalidosException):
        RubroEvaluacion(
            id="r", asignacion_docente_id="a", periodo_id=1, nombre="X",
            peso_porcentaje=Decimal("100.01"),
        )


@pytest.mark.parametrize(
    "kwargs",
    [{"id": ""}, {"rubro_id": " "}, {"titulo": ""}, {"fecha": None}, {"activo": 1}],
)
def test_actividad_invalida(kwargs) -> None:
    base = {"id": "a", "rubro_id": "r", "titulo": "T", "fecha": date(2026, 4, 1)}
    with pytest.raises(ActividadInvalidaException):
        ActividadEvaluable(**(base | kwargs))


@pytest.mark.parametrize(
    ("kwargs", "excepcion"),
    [
        ({"id": ""}, CalificacionException),
        ({"actividad_id": ""}, CalificacionException),
        ({"usuario_id": 0}, CalificacionException),
        ({"actualizado_en": "hoy"}, CalificacionException),
        ({"nota": Decimal("25")}, NotaFueraDeRangoException),
        ({"nota_anterior": Decimal("-3")}, NotaFueraDeRangoException),
        ({"motivo_modificacion": "  "}, CalificacionException),
        ({"observacion": 5}, CalificacionException),
    ],
)
def test_calificacion_invalida(kwargs, excepcion) -> None:
    base = {
        "id": "c",
        "actividad_id": "a",
        "alumno_id": 1,
        "nota": Decimal("10"),
        "usuario_id": 10,
        "actualizado_en": FECHA_HORA,
    }
    with pytest.raises(excepcion):
        Calificacion(**(base | kwargs))


def test_calificacion_observacion_vacia_se_normaliza_a_none() -> None:
    cal = Calificacion(
        id="c", actividad_id="a", alumno_id=1, nota=Decimal("10"), usuario_id=10,
        actualizado_en=FECHA_HORA, observacion="   ",
    )
    assert cal.observacion is None
