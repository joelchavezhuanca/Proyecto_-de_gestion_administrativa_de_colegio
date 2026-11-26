"""Pruebas BDD y unitarias del PBI-08: Control de Estados Académicos de Acceso."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from src.dominio.asistencia import RolUsuario, UsuarioOperador
from src.dominio.estados_academicos import (
    ESTADOS_QUE_ANULAN_CARNET,
    TRANSICIONES_VALIDAS,
    EstadoAcademico,
    EstadoAcademicoException,
    HistorialEstadoAlumno,
    MotivoObligatorioException,
    PermisoEstadoAcademicoException,
    RangoSuspensionInvalidoException,
    ResultadoCambioEstado,
    ServicioEstadosAcademicos,
    TransicionEstadoInvalidaException,
)
from src.dominio.usuarios import PermisoOperacion, Rol

ZONA_LIMA = timezone(timedelta(hours=-5))
FECHA_HORA_LIMA = datetime(2026, 11, 25, 10, 30, 0, tzinfo=ZONA_LIMA)


@pytest.fixture
def admin_op() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_academico", rol=RolUsuario.ADMIN)


@pytest.fixture
def coord_op() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="coord_academico", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def staff_op() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="staff_academico", rol=RolUsuario.ADMIN_STAFF)


def test_enums_constantes_y_jerarquia_excepciones() -> None:
    assert set(EstadoAcademico) == {
        EstadoAcademico.ACTIVO,
        EstadoAcademico.SUSPENDIDO,
        EstadoAcademico.RETIRADO,
        EstadoAcademico.TRASLADADO,
        EstadoAcademico.EGRESADO,
    }
    assert frozenset({
        EstadoAcademico.RETIRADO,
        EstadoAcademico.TRASLADADO,
        EstadoAcademico.EGRESADO,
    }) == ESTADOS_QUE_ANULAN_CARNET
    assert TRANSICIONES_VALIDAS == {
        EstadoAcademico.ACTIVO: frozenset({
            EstadoAcademico.SUSPENDIDO,
            EstadoAcademico.RETIRADO,
            EstadoAcademico.TRASLADADO,
            EstadoAcademico.EGRESADO,
        }),
        EstadoAcademico.SUSPENDIDO: frozenset({
            EstadoAcademico.ACTIVO,
            EstadoAcademico.RETIRADO,
            EstadoAcademico.TRASLADADO,
        }),
        EstadoAcademico.RETIRADO: frozenset({EstadoAcademico.ACTIVO}),
        EstadoAcademico.TRASLADADO: frozenset({EstadoAcademico.ACTIVO}),
        EstadoAcademico.EGRESADO: frozenset(),
    }
    assert issubclass(PermisoEstadoAcademicoException, EstadoAcademicoException)
    assert issubclass(TransicionEstadoInvalidaException, EstadoAcademicoException)
    assert issubclass(MotivoObligatorioException, EstadoAcademicoException)
    assert issubclass(RangoSuspensionInvalidoException, EstadoAcademicoException)


def test_escenario_1_suspender_alumno_activo_bloquea_asistencia_sin_anular_carnet(
    admin_op: UsuarioOperador,
) -> None:
    inicio = date(2026, 11, 25)
    fin = date(2026, 11, 27)

    resultado = ServicioEstadosAcademicos.cambiar_estado(
        operador=admin_op,
        alumno_id=101,
        estado_actual=EstadoAcademico.ACTIVO,
        nuevo_estado=EstadoAcademico.SUSPENDIDO,
        motivo="  Falta disciplinaria grave  ",
        fecha_hora=FECHA_HORA_LIMA,
        fecha_inicio_suspension=inicio,
        fecha_fin_suspension=fin,
    )

    assert isinstance(resultado, ResultadoCambioEstado)
    assert resultado.alumno_id == 101
    assert resultado.estado_actual == EstadoAcademico.SUSPENDIDO
    assert resultado.debe_anular_carnet is False
    assert isinstance(resultado.historial, HistorialEstadoAlumno)
    assert resultado.historial.id
    assert resultado.historial.alumno_id == 101
    assert resultado.historial.estado_anterior == EstadoAcademico.ACTIVO
    assert resultado.historial.estado_nuevo == EstadoAcademico.SUSPENDIDO
    assert resultado.historial.motivo == "Falta disciplinaria grave"
    assert resultado.historial.usuario_id == admin_op.id
    assert resultado.historial.rol_usuario == "ADMIN"
    assert resultado.historial.fecha_hora == FECHA_HORA_LIMA
    assert resultado.historial.fecha_inicio_suspension == inicio
    assert resultado.historial.fecha_fin_suspension == fin

    assert (
        ServicioEstadosAcademicos.estado_efectivo(
            EstadoAcademico.SUSPENDIDO, date(2026, 11, 25), inicio, fin
        )
        == EstadoAcademico.SUSPENDIDO
    )
    assert (
        ServicioEstadosAcademicos.puede_registrar_asistencia(
            EstadoAcademico.SUSPENDIDO, date(2026, 11, 27), inicio, fin
        )
        is False
    )


def test_suspension_un_solo_dia_es_valida_y_vence_al_dia_siguiente(
    admin_op: UsuarioOperador,
) -> None:
    fecha = date(2026, 11, 25)

    resultado = ServicioEstadosAcademicos.cambiar_estado(
        operador=admin_op,
        alumno_id=102,
        estado_actual=EstadoAcademico.ACTIVO,
        nuevo_estado=EstadoAcademico.SUSPENDIDO,
        motivo="Suspensión preventiva de un día",
        fecha_hora=FECHA_HORA_LIMA,
        fecha_inicio_suspension=fecha,
        fecha_fin_suspension=fecha,
    )

    assert resultado.estado_actual == EstadoAcademico.SUSPENDIDO
    assert (
        ServicioEstadosAcademicos.puede_registrar_asistencia(
            EstadoAcademico.SUSPENDIDO, fecha, fecha, fecha
        )
        is False
    )
    assert (
        ServicioEstadosAcademicos.estado_efectivo(
            EstadoAcademico.SUSPENDIDO, date(2026, 11, 26), fecha, fecha
        )
        == EstadoAcademico.ACTIVO
    )
    assert (
        ServicioEstadosAcademicos.puede_registrar_asistencia(
            EstadoAcademico.SUSPENDIDO, date(2026, 11, 26), fecha, fecha
        )
        is True
    )


@pytest.mark.parametrize(
    ("estado_origen", "estado_destino", "anula_carnet"),
    [
        (EstadoAcademico.ACTIVO, EstadoAcademico.RETIRADO, True),
        (EstadoAcademico.ACTIVO, EstadoAcademico.TRASLADADO, True),
        (EstadoAcademico.ACTIVO, EstadoAcademico.EGRESADO, True),
        (EstadoAcademico.SUSPENDIDO, EstadoAcademico.ACTIVO, False),
        (EstadoAcademico.SUSPENDIDO, EstadoAcademico.RETIRADO, True),
        (EstadoAcademico.SUSPENDIDO, EstadoAcademico.TRASLADADO, True),
        (EstadoAcademico.RETIRADO, EstadoAcademico.ACTIVO, False),
        (EstadoAcademico.TRASLADADO, EstadoAcademico.ACTIVO, False),
    ],
)
def test_todas_las_transiciones_no_suspension_validas_y_anulacion_carnet(
    admin_op: UsuarioOperador,
    estado_origen: EstadoAcademico,
    estado_destino: EstadoAcademico,
    anula_carnet: bool,
) -> None:
    resultado = ServicioEstadosAcademicos.cambiar_estado(
        operador=admin_op,
        alumno_id=200,
        estado_actual=estado_origen,
        nuevo_estado=estado_destino,
        motivo="Resolución administrativa oficial",
        fecha_hora=FECHA_HORA_LIMA,
    )

    assert resultado.estado_actual == estado_destino
    assert resultado.debe_anular_carnet is anula_carnet
    assert resultado.historial.estado_anterior == estado_origen
    assert resultado.historial.estado_nuevo == estado_destino
    assert resultado.historial.fecha_inicio_suspension is None
    assert resultado.historial.fecha_fin_suspension is None
    assert (
        ServicioEstadosAcademicos.puede_registrar_asistencia(
            resultado.estado_actual, date(2026, 11, 25)
        )
        is (estado_destino == EstadoAcademico.ACTIVO)
    )


@pytest.mark.parametrize(
    ("estado_origen", "estado_destino"),
    [
        (EstadoAcademico.ACTIVO, EstadoAcademico.ACTIVO),
        (EstadoAcademico.SUSPENDIDO, EstadoAcademico.SUSPENDIDO),
        (EstadoAcademico.SUSPENDIDO, EstadoAcademico.EGRESADO),
        (EstadoAcademico.RETIRADO, EstadoAcademico.RETIRADO),
        (EstadoAcademico.RETIRADO, EstadoAcademico.SUSPENDIDO),
        (EstadoAcademico.RETIRADO, EstadoAcademico.TRASLADADO),
        (EstadoAcademico.RETIRADO, EstadoAcademico.EGRESADO),
        (EstadoAcademico.TRASLADADO, EstadoAcademico.TRASLADADO),
        (EstadoAcademico.TRASLADADO, EstadoAcademico.SUSPENDIDO),
        (EstadoAcademico.TRASLADADO, EstadoAcademico.RETIRADO),
        (EstadoAcademico.TRASLADADO, EstadoAcademico.EGRESADO),
        (EstadoAcademico.EGRESADO, EstadoAcademico.ACTIVO),
        (EstadoAcademico.EGRESADO, EstadoAcademico.SUSPENDIDO),
        (EstadoAcademico.EGRESADO, EstadoAcademico.RETIRADO),
        (EstadoAcademico.EGRESADO, EstadoAcademico.TRASLADADO),
        (EstadoAcademico.EGRESADO, EstadoAcademico.EGRESADO),
    ],
)
def test_transiciones_invalidas_y_estado_terminal_egresado_son_rechazados(
    admin_op: UsuarioOperador,
    estado_origen: EstadoAcademico,
    estado_destino: EstadoAcademico,
) -> None:
    with pytest.raises(TransicionEstadoInvalidaException):
        ServicioEstadosAcademicos.cambiar_estado(
            operador=admin_op,
            alumno_id=300,
            estado_actual=estado_origen,
            nuevo_estado=estado_destino,
            motivo="Intento de transición no permitida",
            fecha_hora=FECHA_HORA_LIMA,
            fecha_inicio_suspension=date(2026, 11, 25),
            fecha_fin_suspension=date(2026, 11, 26),
        )


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [
        (None, None),
        (date(2026, 11, 25), None),
        (None, date(2026, 11, 26)),
        (date(2026, 11, 28), date(2026, 11, 26)),
    ],
)
def test_suspension_rechaza_rango_fechas_invalido_o_incompleto(
    admin_op: UsuarioOperador,
    inicio: date | None,
    fin: date | None,
) -> None:
    with pytest.raises(RangoSuspensionInvalidoException):
        ServicioEstadosAcademicos.cambiar_estado(
            operador=admin_op,
            alumno_id=400,
            estado_actual=EstadoAcademico.ACTIVO,
            nuevo_estado=EstadoAcademico.SUSPENDIDO,
            motivo="Suspensión con rango inválido",
            fecha_hora=FECHA_HORA_LIMA,
            fecha_inicio_suspension=inicio,
            fecha_fin_suspension=fin,
        )


@pytest.mark.parametrize("motivo_invalido", ["", "   ", "\t\n"])
def test_rechaza_cambio_estado_sin_motivo_obligatorio(
    admin_op: UsuarioOperador,
    motivo_invalido: str,
) -> None:
    with pytest.raises(MotivoObligatorioException):
        ServicioEstadosAcademicos.cambiar_estado(
            operador=admin_op,
            alumno_id=500,
            estado_actual=EstadoAcademico.ACTIVO,
            nuevo_estado=EstadoAcademico.RETIRADO,
            motivo=motivo_invalido,
            fecha_hora=FECHA_HORA_LIMA,
        )


def test_deniega_operador_inactivo_y_roles_base_sin_permiso(
    coord_op: UsuarioOperador,
    staff_op: UsuarioOperador,
) -> None:
    admin_inactivo = UsuarioOperador(
        id=99,
        username="admin_off",
        rol=RolUsuario.ADMIN,
        activo=False,
    )

    for operador in (admin_inactivo, coord_op, staff_op):
        with pytest.raises(PermisoEstadoAcademicoException):
            ServicioEstadosAcademicos.validar_operador(operador)
        with pytest.raises(PermisoEstadoAcademicoException):
            ServicioEstadosAcademicos.cambiar_estado(
                operador=operador,
                alumno_id=600,
                estado_actual=EstadoAcademico.ACTIVO,
                nuevo_estado=EstadoAcademico.RETIRADO,
                motivo="Retiro voluntario",
                fecha_hora=FECHA_HORA_LIMA,
            )


def test_permisos_dinamicos_rol_personalizado_autorizado_y_no_autorizado() -> None:
    rol_autorizado = Rol(
        codigo="GESTOR_ESTADOS",
        nombre="Gestor de estados",
        descripcion="Permite cambiar estados académicos",
        permisos=frozenset({PermisoOperacion.GESTIONAR_ESTADOS_ACADEMICOS}),
    )
    rol_sin_permiso = Rol(
        codigo="SOLO_LECTURA",
        nombre="Solo lectura",
        descripcion="Consulta fichas sin modificar estados",
        permisos=frozenset({PermisoOperacion.CONSULTAR_FICHA_ALUMNO}),
    )
    rol_inactivo = Rol(
        codigo="GESTOR_INACTIVO",
        nombre="Gestor inactivo",
        descripcion="Rol desactivado",
        permisos=frozenset({PermisoOperacion.GESTIONAR_ESTADOS_ACADEMICOS}),
        activo=False,
    )
    roles = [rol_autorizado, rol_sin_permiso, rol_inactivo]

    op_ok = UsuarioOperador(
        id=10,
        username="gestor_ok",
        rol="GESTOR_ESTADOS",  # type: ignore[arg-type]
    )
    resultado = ServicioEstadosAcademicos.cambiar_estado(
        operador=op_ok,
        alumno_id=700,
        estado_actual=EstadoAcademico.ACTIVO,
        nuevo_estado=EstadoAcademico.TRASLADADO,
        motivo="Traslado a otra institución",
        fecha_hora=FECHA_HORA_LIMA,
        roles=roles,
    )
    assert resultado.historial.rol_usuario == "GESTOR_ESTADOS"
    assert resultado.debe_anular_carnet is True

    for codigo_rol in ("SOLO_LECTURA", "GESTOR_INACTIVO", "ROL_INEXISTENTE"):
        op_denegado = UsuarioOperador(
            id=11,
            username=f"user_{codigo_rol.lower()}",
            rol=codigo_rol,  # type: ignore[arg-type]
        )
        with pytest.raises(PermisoEstadoAcademicoException):
            ServicioEstadosAcademicos.validar_operador(op_denegado, roles=roles)


def test_normaliza_fecha_hora_a_america_lima_e_inmutabilidad(
    admin_op: UsuarioOperador,
) -> None:
    fecha_utc = datetime(2026, 11, 26, 2, 15, 0, tzinfo=UTC)
    resultado_utc = ServicioEstadosAcademicos.cambiar_estado(
        operador=admin_op,
        alumno_id=800,
        estado_actual=EstadoAcademico.ACTIVO,
        nuevo_estado=EstadoAcademico.EGRESADO,
        motivo="Culminó el quinto de secundaria",
        fecha_hora=fecha_utc,
    )
    assert resultado_utc.historial.fecha_hora == datetime(
        2026, 11, 25, 21, 15, 0, tzinfo=ZONA_LIMA
    )
    assert resultado_utc.historial.fecha_hora.utcoffset() == timedelta(hours=-5)

    fecha_naive = datetime(2026, 11, 25, 14, 0, 0)
    resultado_naive = ServicioEstadosAcademicos.cambiar_estado(
        operador=admin_op,
        alumno_id=801,
        estado_actual=EstadoAcademico.ACTIVO,
        nuevo_estado=EstadoAcademico.RETIRADO,
        motivo="Retiro familiar",
        fecha_hora=fecha_naive,
    )
    assert resultado_naive.historial.fecha_hora == datetime(
        2026, 11, 25, 14, 0, 0, tzinfo=ZONA_LIMA
    )
    assert resultado_naive.historial.fecha_hora.utcoffset() == timedelta(hours=-5)

    with pytest.raises(FrozenInstanceError):
        resultado_naive.estado_actual = EstadoAcademico.ACTIVO  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resultado_naive.historial.motivo = "Otro"  # type: ignore[misc]


def test_estado_efectivo_suspendido_sin_fecha_fin_sigue_suspendido() -> None:
    assert (
        ServicioEstadosAcademicos.estado_efectivo(
            EstadoAcademico.SUSPENDIDO, date(2026, 12, 1), None, None
        )
        == EstadoAcademico.SUSPENDIDO
    )
    assert (
        ServicioEstadosAcademicos.puede_registrar_asistencia(
            EstadoAcademico.SUSPENDIDO, date(2026, 12, 1), None, None
        )
        is False
    )
