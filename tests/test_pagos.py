"""Pruebas BDD y unitarias del PBI-07: Control de Pagos e Ingreso (Alerta Silenciosa)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from src.dominio.asistencia import (
    Alumno,
    EstadoAlumno,
    EstadoAsistencia,
    EventoAsistenciaConfirmada,
    MetodoRegistro,
    UsuarioOperador,
    registrar_asistencia_unificada,
)
from src.dominio.pagos import (
    AlertaSilenciosaPago,
    EstadoObligacion,
    ObligacionInvalidaException,
    ObligacionPago,
    PagoInvalidoException,
    PagosException,
    PermisoPagosException,
    ServicioPagos,
)
from src.dominio.usuarios import PermisoOperacion, Rol, RolUsuario

ZONA_LIMA = timezone(timedelta(hours=-5))
FECHA_HOY = date(2026, 11, 26)
AHORA_LIMA = datetime(2026, 11, 26, 7, 10, 0, tzinfo=ZONA_LIMA)


@pytest.fixture
def admin_op() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_tesoreria", rol=RolUsuario.ADMIN)


@pytest.fixture
def staff_op() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="staff_porteria", rol=RolUsuario.ADMIN_STAFF)


@pytest.fixture
def coord_op() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="coord_patio", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def rol_tesoreria() -> Rol:
    return Rol(
        codigo="TESORERIA",
        nombre="Tesorería",
        descripcion="Gestión de obligaciones, pagos y alertas",
        permisos=frozenset(
            {
                PermisoOperacion.GESTIONAR_PAGOS,
                PermisoOperacion.VER_ALERTA_PAGOS,
            }
        ),
    )


@pytest.fixture
def tesorero_op() -> UsuarioOperador:
    return UsuarioOperador(id=4, username="tesorero", rol="TESORERIA")


@pytest.fixture
def alumno_activo() -> Alumno:
    return Alumno(
        id=101,
        codigo="ALU-101",
        dni="72945734",
        nombres="Lucía",
        apellidos="Quispe Salas",
        nivel="Secundaria",
        grado="4to",
        seccion="A",
        carnet_codigo="CRN-101",
        estado=EstadoAlumno.ACTIVO,
    )


def _evento_asistencia(
    alumno_id: int = 101,
    fecha_escolar: date = FECHA_HOY,
    asistencia_id: str = "ast-001",
) -> EventoAsistenciaConfirmada:
    return EventoAsistenciaConfirmada(
        id="evt-001",
        asistencia_id=asistencia_id,
        alumno_id=alumno_id,
        fecha_escolar=fecha_escolar,
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=2,
    )


def test_enums_excepciones_e_inmutabilidad() -> None:
    assert set(EstadoObligacion) == {
        EstadoObligacion.PENDIENTE,
        EstadoObligacion.PAGADO,
        EstadoObligacion.VENCIDO,
        EstadoObligacion.EXONERADO,
    }
    assert issubclass(PermisoPagosException, PagosException)
    assert issubclass(ObligacionInvalidaException, PagosException)
    assert issubclass(PagoInvalidoException, PagosException)

    obligacion = ObligacionPago(
        id="obl-1",
        alumno_id=101,
        concepto="  Pensión Noviembre  ",
        monto=Decimal("350.50"),
        fecha_vencimiento=date(2026, 11, 10),
    )
    assert obligacion.concepto == "Pensión Noviembre"
    assert obligacion.estado == EstadoObligacion.PENDIENTE
    assert obligacion.pagado_en is None
    assert obligacion.motivo_exoneracion is None

    with pytest.raises(FrozenInstanceError):
        obligacion.estado = EstadoObligacion.PAGADO  # type: ignore[misc]

    alerta = AlertaSilenciosaPago(
        id="alr-1",
        alumno_id=101,
        asistencia_id="ast-1",
        fecha_escolar=FECHA_HOY,
        cantidad_obligaciones_vencidas=1,
        monto_vencido_total=Decimal("350.50"),
        creado_en=AHORA_LIMA,
    )
    assert alerta.revisada is False
    with pytest.raises(FrozenInstanceError):
        alerta.revisada = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": ""},
        {"id": "   "},
        {"alumno_id": 0},
        {"alumno_id": -5},
        {"alumno_id": True},
        {"concepto": ""},
        {"concepto": "   "},
        {"concepto": 123},
        {"monto": Decimal("0")},
        {"monto": Decimal("-10.00")},
        {"monto": Decimal("NaN")},
        {"monto": Decimal("Infinity")},
        {"monto": 100.50},
        {"monto": 100},
        {"monto": True},
        {"fecha_vencimiento": datetime(2026, 11, 10, 8, 0)},
        {"fecha_vencimiento": "2026-11-10"},
        {"estado": "PENDIENTE"},
    ],
)
def test_obligacion_pago_valida_invariantes(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "id": "obl-val",
        "alumno_id": 101,
        "concepto": "Pensión Octubre",
        "monto": Decimal("250.00"),
        "fecha_vencimiento": date(2026, 10, 31),
        "estado": EstadoObligacion.PENDIENTE,
    }
    base.update(kwargs)
    with pytest.raises(ObligacionInvalidaException):
        ObligacionPago(**base)  # type: ignore[arg-type]


def test_registrar_obligacion_permisos_y_creacion(
    admin_op: UsuarioOperador,
    staff_op: UsuarioOperador,
    coord_op: UsuarioOperador,
    tesorero_op: UsuarioOperador,
    rol_tesoreria: Rol,
) -> None:
    obligacion = ServicioPagos.registrar_obligacion(
        operador=admin_op,
        alumno_id=101,
        concepto="  Pensión Marzo 2026  ",
        monto=Decimal("420.00"),
        fecha_vencimiento=date(2026, 3, 31),
    )
    assert obligacion.id.startswith("obl-")
    assert obligacion.alumno_id == 101
    assert obligacion.concepto == "Pensión Marzo 2026"
    assert isinstance(obligacion.monto, Decimal)
    assert obligacion.monto == Decimal("420.00")
    assert obligacion.estado == EstadoObligacion.PENDIENTE

    obligacion_rol = ServicioPagos.registrar_obligacion(
        operador=tesorero_op,
        alumno_id=102,
        concepto="Matrícula",
        monto=Decimal("500.00"),
        fecha_vencimiento=date(2026, 2, 28),
        roles=[rol_tesoreria],
    )
    assert obligacion_rol.alumno_id == 102

    for op_sin_permiso in (staff_op, coord_op, UsuarioOperador(1, "inactivo", RolUsuario.ADMIN, False)):
        with pytest.raises(PermisoPagosException):
            ServicioPagos.registrar_obligacion(
                operador=op_sin_permiso,
                alumno_id=101,
                concepto="Pensión",
                monto=Decimal("100.00"),
                fecha_vencimiento=date(2026, 4, 30),
            )


def test_registrar_pago_transiciones_y_rechazos(
    admin_op: UsuarioOperador,
    staff_op: UsuarioOperador,
) -> None:
    pendiente = ServicioPagos.registrar_obligacion(
        operador=admin_op,
        alumno_id=101,
        concepto="Pensión Octubre",
        monto=Decimal("320.00"),
        fecha_vencimiento=date(2026, 10, 31),
    )
    pagada = ServicioPagos.registrar_pago(admin_op, pendiente, AHORA_LIMA)
    assert pagada.estado == EstadoObligacion.PAGADO
    assert pagada.pagado_en == AHORA_LIMA
    assert pendiente.estado == EstadoObligacion.PENDIENTE

    vencida = ObligacionPago(
        id="obl-venc",
        alumno_id=101,
        concepto="Pensión Setiembre",
        monto=Decimal("320.00"),
        fecha_vencimiento=date(2026, 9, 30),
        estado=EstadoObligacion.VENCIDO,
    )
    pagada_desde_vencida = ServicioPagos.registrar_pago(admin_op, vencida, AHORA_LIMA)
    assert pagada_desde_vencida.estado == EstadoObligacion.PAGADO

    with pytest.raises(PagoInvalidoException):
        ServicioPagos.registrar_pago(admin_op, pagada, AHORA_LIMA)

    exonerada = ServicioPagos.exonerar_obligacion(admin_op, pendiente, "Beca completa")
    with pytest.raises(PagoInvalidoException):
        ServicioPagos.registrar_pago(admin_op, exonerada, AHORA_LIMA)

    with pytest.raises(PagoInvalidoException):
        ServicioPagos.registrar_pago(admin_op, pendiente, "2026-11-26")  # type: ignore[arg-type]

    with pytest.raises(PagoInvalidoException):
        ServicioPagos.registrar_pago(admin_op, "no-obligacion", AHORA_LIMA)  # type: ignore[arg-type]

    with pytest.raises(PermisoPagosException):
        ServicioPagos.registrar_pago(staff_op, pendiente, AHORA_LIMA)


def test_exonerar_obligacion_reglas_y_validaciones(
    admin_op: UsuarioOperador,
    coord_op: UsuarioOperador,
) -> None:
    pendiente = ServicioPagos.registrar_obligacion(
        operador=admin_op,
        alumno_id=101,
        concepto="Pensión Noviembre",
        monto=Decimal("300.00"),
        fecha_vencimiento=date(2026, 11, 15),
    )
    exonerada = ServicioPagos.exonerar_obligacion(
        admin_op, pendiente, "  Beca por excelencia académica  "
    )
    assert exonerada.estado == EstadoObligacion.EXONERADO
    assert exonerada.motivo_exoneracion == "Beca por excelencia académica"

    with pytest.raises(ObligacionInvalidaException):
        ServicioPagos.exonerar_obligacion(admin_op, pendiente, "   ")

    with pytest.raises(ObligacionInvalidaException):
        ServicioPagos.exonerar_obligacion(admin_op, "invalida", "Motivo")  # type: ignore[arg-type]

    pagada = ServicioPagos.registrar_pago(admin_op, pendiente, AHORA_LIMA)
    with pytest.raises(PagoInvalidoException):
        ServicioPagos.exonerar_obligacion(admin_op, pagada, "Intento posterior")

    with pytest.raises(PermisoPagosException):
        ServicioPagos.exonerar_obligacion(coord_op, pendiente, "Motivo válido")


def test_obligaciones_vencidas_filtrado_exacto(admin_op: UsuarioOperador) -> None:
    vencida_estado = ObligacionPago(
        id="obl-1",
        alumno_id=101,
        concepto="Pensión Agosto",
        monto=Decimal("300.00"),
        fecha_vencimiento=date(2026, 12, 31),
        estado=EstadoObligacion.VENCIDO,
    )
    pendiente_vencida = ObligacionPago(
        id="obl-2",
        alumno_id=101,
        concepto="Pensión Octubre",
        monto=Decimal("310.50"),
        fecha_vencimiento=date(2026, 11, 25),
        estado=EstadoObligacion.PENDIENTE,
    )
    pendiente_vence_hoy = ObligacionPago(
        id="obl-3",
        alumno_id=101,
        concepto="Pensión Noviembre",
        monto=Decimal("320.00"),
        fecha_vencimiento=FECHA_HOY,
        estado=EstadoObligacion.PENDIENTE,
    )
    pagada_antigua = ObligacionPago(
        id="obl-4",
        alumno_id=101,
        concepto="Pensión Julio",
        monto=Decimal("300.00"),
        fecha_vencimiento=date(2026, 7, 31),
        estado=EstadoObligacion.PAGADO,
        pagado_en=AHORA_LIMA,
    )
    exonerada_antigua = ServicioPagos.exonerar_obligacion(
        admin_op,
        ObligacionPago(
            id="obl-5",
            alumno_id=101,
            concepto="Pensión Junio",
            monto=Decimal("300.00"),
            fecha_vencimiento=date(2026, 6, 30),
        ),
        "Beca socioeconómica",
    )
    otro_alumno = ObligacionPago(
        id="obl-6",
        alumno_id=202,
        concepto="Pensión Octubre",
        monto=Decimal("400.00"),
        fecha_vencimiento=date(2026, 10, 31),
        estado=EstadoObligacion.VENCIDO,
    )

    resultado = ServicioPagos.obligaciones_vencidas(
        alumno_id=101,
        obligaciones=[
            vencida_estado,
            pendiente_vencida,
            pendiente_vence_hoy,
            pagada_antigua,
            exonerada_antigua,
            otro_alumno,
        ],
        fecha_referencia=FECHA_HOY,
    )
    assert [o.id for o in resultado] == ["obl-1", "obl-2"]


def test_escenario_1_deuda_vencida_no_bloquea_asistencia_y_genera_alerta_silenciosa(
    staff_op: UsuarioOperador,
    alumno_activo: Alumno,
) -> None:
    resultado_asistencia = registrar_asistencia_unificada(
        operador=staff_op,
        alumno=alumno_activo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 10, 0),
        fecha_escolar=FECHA_HOY,
    )
    assert resultado_asistencia.asistencia.estado == EstadoAsistencia.PUNTUAL
    evento = resultado_asistencia.evento_whatsapp
    assert evento is not None

    obligaciones = [
        ObligacionPago(
            id="obl-1",
            alumno_id=101,
            concepto="Pensión Setiembre",
            monto=Decimal("350.25"),
            fecha_vencimiento=date(2026, 9, 30),
            estado=EstadoObligacion.VENCIDO,
        ),
        ObligacionPago(
            id="obl-2",
            alumno_id=101,
            concepto="Pensión Octubre",
            monto=Decimal("150.75"),
            fecha_vencimiento=date(2026, 10, 31),
            estado=EstadoObligacion.PENDIENTE,
        ),
    ]

    alerta = ServicioPagos.evaluar_alerta_silenciosa(
        evento=evento,
        obligaciones=obligaciones,
        alertas_existentes=[],
        ahora=AHORA_LIMA,
    )
    assert alerta is not None
    assert alerta.id.startswith("alr-")
    assert alerta.alumno_id == 101
    assert alerta.asistencia_id == resultado_asistencia.asistencia.id
    assert alerta.fecha_escolar == FECHA_HOY
    assert alerta.cantidad_obligaciones_vencidas == 2
    assert isinstance(alerta.monto_vencido_total, Decimal)
    assert alerta.monto_vencido_total == Decimal("501.00")
    assert alerta.revisada is False
    assert alerta.creado_en == AHORA_LIMA


def test_escenario_2_alumno_al_dia_o_exonerado_no_genera_alerta(
    admin_op: UsuarioOperador,
) -> None:
    evento = _evento_asistencia(alumno_id=101, fecha_escolar=FECHA_HOY)
    pendiente_futura = ObligacionPago(
        id="obl-fut",
        alumno_id=101,
        concepto="Pensión Diciembre",
        monto=Decimal("350.00"),
        fecha_vencimiento=date(2026, 12, 20),
    )
    exonerada = ServicioPagos.exonerar_obligacion(
        admin_op,
        ObligacionPago(
            id="obl-exo",
            alumno_id=101,
            concepto="Pensión Octubre",
            monto=Decimal("350.00"),
            fecha_vencimiento=date(2026, 10, 31),
        ),
        "Convenio familiar",
    )

    alerta = ServicioPagos.evaluar_alerta_silenciosa(
        evento=evento,
        obligaciones=[pendiente_futura, exonerada],
        alertas_existentes=[],
        ahora=AHORA_LIMA,
    )
    assert alerta is None


def test_escenario_4_pago_de_obligacion_vencida_deja_de_generar_alertas(
    admin_op: UsuarioOperador,
) -> None:
    vencida = ObligacionPago(
        id="obl-1",
        alumno_id=101,
        concepto="Pensión Octubre",
        monto=Decimal("350.00"),
        fecha_vencimiento=date(2026, 10, 31),
        estado=EstadoObligacion.VENCIDO,
    )
    alerta_dia_1 = ServicioPagos.evaluar_alerta_silenciosa(
        evento=_evento_asistencia(alumno_id=101, fecha_escolar=FECHA_HOY),
        obligaciones=[vencida],
        alertas_existentes=[],
        ahora=AHORA_LIMA,
    )
    assert alerta_dia_1 is not None

    pagada = ServicioPagos.registrar_pago(admin_op, vencida, AHORA_LIMA)
    assert pagada.estado == EstadoObligacion.PAGADO

    dia_siguiente = FECHA_HOY + timedelta(days=1)
    alerta_dia_2 = ServicioPagos.evaluar_alerta_silenciosa(
        evento=_evento_asistencia(alumno_id=101, fecha_escolar=dia_siguiente, asistencia_id="ast-2"),
        obligaciones=[pagada],
        alertas_existentes=[alerta_dia_1],
        ahora=AHORA_LIMA + timedelta(days=1),
    )
    assert alerta_dia_2 is None


def test_escenario_5_idempotencia_maximo_una_alerta_por_alumno_y_fecha() -> None:
    vencida = ObligacionPago(
        id="obl-1",
        alumno_id=101,
        concepto="Pensión Octubre",
        monto=Decimal("350.00"),
        fecha_vencimiento=date(2026, 10, 31),
        estado=EstadoObligacion.VENCIDO,
    )
    evento = _evento_asistencia(alumno_id=101, fecha_escolar=FECHA_HOY)
    primera = ServicioPagos.evaluar_alerta_silenciosa(
        evento=evento,
        obligaciones=[vencida],
        alertas_existentes=[],
        ahora=AHORA_LIMA,
    )
    assert primera is not None

    duplicada = ServicioPagos.evaluar_alerta_silenciosa(
        evento=_evento_asistencia(alumno_id=101, fecha_escolar=FECHA_HOY, asistencia_id="ast-2"),
        obligaciones=[vencida],
        alertas_existentes=[primera],
        ahora=AHORA_LIMA,
    )
    assert duplicada is None

    siguiente_dia = ServicioPagos.evaluar_alerta_silenciosa(
        evento=_evento_asistencia(
            alumno_id=101,
            fecha_escolar=FECHA_HOY + timedelta(days=1),
            asistencia_id="ast-3",
        ),
        obligaciones=[vencida],
        alertas_existentes=[primera],
        ahora=None,
    )
    assert siguiente_dia is not None
    assert siguiente_dia.creado_en is None


def test_regla_de_oro_evaluar_alerta_nunca_lanza_excepcion() -> None:
    def _generador_roto():
        raise RuntimeError("Fallo de lectura de base de datos")
        yield  # pragma: no cover

    alerta_error_iter = ServicioPagos.evaluar_alerta_silenciosa(
        evento=_evento_asistencia(),
        obligaciones=_generador_roto(),  # type: ignore[arg-type]
        alertas_existentes=[],
        ahora=AHORA_LIMA,
    )
    assert alerta_error_iter is None

    alerta_evento_nulo = ServicioPagos.evaluar_alerta_silenciosa(
        evento=None,  # type: ignore[arg-type]
        obligaciones=[],
        alertas_existentes=[],
        ahora=AHORA_LIMA,
    )
    assert alerta_evento_nulo is None


def test_escenario_3_consultar_y_marcar_alerta_revisada_permisos_y_filtros(
    admin_op: UsuarioOperador,
    staff_op: UsuarioOperador,
    coord_op: UsuarioOperador,
    tesorero_op: UsuarioOperador,
    rol_tesoreria: Rol,
) -> None:
    alerta_1 = AlertaSilenciosaPago(
        id="alr-1",
        alumno_id=101,
        asistencia_id="ast-1",
        fecha_escolar=FECHA_HOY,
        cantidad_obligaciones_vencidas=1,
        monto_vencido_total=Decimal("300.00"),
        revisada=False,
        creado_en=AHORA_LIMA,
    )
    alerta_2 = AlertaSilenciosaPago(
        id="alr-2",
        alumno_id=102,
        asistencia_id="ast-2",
        fecha_escolar=FECHA_HOY - timedelta(days=1),
        cantidad_obligaciones_vencidas=2,
        monto_vencido_total=Decimal("600.00"),
        revisada=True,
        creado_en=AHORA_LIMA - timedelta(days=1),
    )

    todas = ServicioPagos.consultar_alertas(staff_op, [alerta_1, alerta_2])
    assert [a.id for a in todas] == ["alr-1", "alr-2"]

    por_fecha = ServicioPagos.consultar_alertas(
        tesorero_op,
        [alerta_1, alerta_2],
        fecha=FECHA_HOY,
        solo_no_revisadas=True,
        roles=[rol_tesoreria],
    )
    assert [a.id for a in por_fecha] == ["alr-1"]

    solo_pendientes = ServicioPagos.consultar_alertas(
        admin_op, [alerta_1, alerta_2], solo_no_revisadas=True
    )
    assert [a.id for a in solo_pendientes] == ["alr-1"]

    with pytest.raises(PermisoPagosException):
        ServicioPagos.consultar_alertas(coord_op, [alerta_1])

    with pytest.raises(PermisoPagosException):
        ServicioPagos.consultar_alertas(
            UsuarioOperador(id=9, username="inactivo", rol=RolUsuario.ADMIN_STAFF, activo=False),
            [alerta_1],
        )

    revisada = ServicioPagos.marcar_alerta_revisada(staff_op, alerta_1)
    assert revisada.revisada is True
    assert alerta_1.revisada is False

    with pytest.raises(PermisoPagosException):
        ServicioPagos.marcar_alerta_revisada(coord_op, alerta_1)

    with pytest.raises(PagosException):
        ServicioPagos.marcar_alerta_revisada(admin_op, "alerta-invalida")  # type: ignore[arg-type]
