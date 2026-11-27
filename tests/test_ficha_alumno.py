"""Pruebas BDD y unitarias del PBI-12: Ficha Informativa del Alumno."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from src.dominio.asistencia import (
    AlumnoNoEncontradoException,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    UsuarioOperador,
)
from src.dominio.calificaciones import EscalaLiteral, PromedioPeriodo
from src.dominio.carnets import CarnetEscolar, EstadoCarnet
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.ficha_alumno import (
    FichaAlumnoException,
    FichaInformativaAlumno,
    PermisoFichaAlumnoException,
    ResumenAsistenciaAlumno,
    ResumenPagosAlumno,
    ServicioFichaAlumno,
)
from src.dominio.matricula import Apoderado, FichaMatricula
from src.dominio.pagos import EstadoObligacion, ObligacionPago
from src.dominio.usuarios import PermisoOperacion, Rol, RolUsuario

FECHA_REFERENCIA = datetime(2026, 3, 31, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
ALUMNO_ID = 10


# ---------------------------------------------------------------------------
# Constructores auxiliares
# ---------------------------------------------------------------------------


def _crear_apoderado(*, principal: bool = True) -> Apoderado:
    return Apoderado(
        id=1,
        nombres="Rosa",
        apellidos="Quispe",
        documento="12345678",
        parentesco="Madre",
        telefono_whatsapp="987654321",
        es_principal=principal,
    )


def _crear_ficha(
    *,
    alumno_id: int = ALUMNO_ID,
    estado: EstadoAcademico = EstadoAcademico.ACTIVO,
) -> FichaMatricula:
    return FichaMatricula(
        id="mat-000000000010",
        alumno_id=alumno_id,
        codigo_estudiante="DSV-2026-0010",
        dni="76543210",
        nombres="Luis",
        apellidos="Paredes",
        fecha_nacimiento=date(2010, 5, 14),
        anio_lectivo=2026,
        salon_id=3,
        nivel="SECUNDARIA",
        grado="2",
        seccion="A",
        apoderados=(_crear_apoderado(),),
        estado=estado,
    )


def _crear_asistencia(
    *,
    indice: int = 1,
    estado: EstadoAsistencia = EstadoAsistencia.PUNTUAL,
    alumno_id: int = ALUMNO_ID,
) -> RegistroAsistencia:
    return RegistroAsistencia(
        id=f"asi-{indice:012d}",
        alumno_id=alumno_id,
        fecha_escolar=date(2026, 3, indice),
        hora_efectiva=time(7, 45),
        estado=estado,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=1,
        rol_usuario=RolUsuario.ADMIN,
    )


def _crear_promedio(*, curso_id: int = 101, alumno_id: int = ALUMNO_ID) -> PromedioPeriodo:
    return PromedioPeriodo(
        alumno_id=alumno_id,
        curso_id=curso_id,
        periodo_id=1,
        desglose_rubros=(),
        nota_final=Decimal("15.50"),
        escala_literal=EscalaLiteral.A,
    )


def _crear_obligacion(
    *,
    id: str,
    monto: str,
    fecha_vencimiento: date,
    estado: EstadoObligacion = EstadoObligacion.PENDIENTE,
    alumno_id: int = ALUMNO_ID,
) -> ObligacionPago:
    return ObligacionPago(
        id=id,
        alumno_id=alumno_id,
        concepto="Pensión mensual",
        monto=Decimal(monto),
        fecha_vencimiento=fecha_vencimiento,
        estado=estado,
    )


def _crear_carnet(
    *,
    alumno_id: int = ALUMNO_ID,
    estado: EstadoCarnet = EstadoCarnet.ACTIVO,
) -> CarnetEscolar:
    return CarnetEscolar(
        id="car-000000000010",
        alumno_id=alumno_id,
        codigo_qr="DSV-2026-AAAAAAAAAAAA",
        estado=estado,
        emitido_por=1,
        emitido_en=datetime(2026, 3, 1, 8, 0),
    )


def _construir_ficha(
    operador: UsuarioOperador,
    *,
    ficha: FichaMatricula | None = None,
    estado_actual: EstadoAcademico | str = EstadoAcademico.ACTIVO,
    carnet: CarnetEscolar | None = None,
    asistencias: tuple[RegistroAsistencia, ...] = (),
    promedios: tuple[PromedioPeriodo, ...] = (),
    obligaciones: tuple[ObligacionPago, ...] = (),
    fecha_referencia: datetime | None = FECHA_REFERENCIA,
    roles: tuple[Rol, ...] | None = None,
) -> FichaInformativaAlumno:
    return ServicioFichaAlumno.construir_ficha(
        operador=operador,
        ficha_matricula=ficha if ficha is not None else _crear_ficha(),
        estado_actual=estado_actual,
        carnet_activo=carnet,
        asistencias_alumno=asistencias,
        promedios_cursos=promedios,
        obligaciones_pago=obligaciones,
        fecha_referencia=fecha_referencia,
        roles=roles,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def operador_admin() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=True)


@pytest.fixture
def operador_coordinador() -> UsuarioOperador:
    return UsuarioOperador(
        id=2, username="coordinador", rol=RolUsuario.COORDINADOR, activo=True
    )


@pytest.fixture
def operador_admin_staff() -> UsuarioOperador:
    return UsuarioOperador(
        id=3, username="admin_staff", rol=RolUsuario.ADMIN_STAFF, activo=True
    )


@pytest.fixture
def operador_sin_permiso() -> UsuarioOperador:
    return UsuarioOperador(id=4, username="invitado", rol="INVITADO", activo=True)


@pytest.fixture
def operador_inactivo() -> UsuarioOperador:
    return UsuarioOperador(id=5, username="admin_off", rol=RolUsuario.ADMIN, activo=False)


@pytest.fixture
def rol_ver_alerta() -> Rol:
    return Rol(
        codigo="AUDITOR_FICHA",
        nombre="Auditor de fichas",
        descripcion="Consulta fichas con acceso a la alerta de pagos.",
        permisos=frozenset(
            {
                PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
                PermisoOperacion.VER_ALERTA_PAGOS,
            }
        ),
    )


@pytest.fixture
def rol_gestionar_pagos() -> Rol:
    return Rol(
        codigo="CAJERO_FICHA",
        nombre="Cajero de fichas",
        descripcion="Consulta fichas y gestiona pagos.",
        permisos=frozenset(
            {
                PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
                PermisoOperacion.GESTIONAR_PAGOS,
            }
        ),
    )


# ---------------------------------------------------------------------------
# RN-02: ensamblado de la ficha informativa
# ---------------------------------------------------------------------------


def test_construye_ficha_completa_con_bloque_financiero(
    operador_admin: UsuarioOperador,
) -> None:
    ficha = _crear_ficha()
    carnet = _crear_carnet()
    asistencias = (
        _crear_asistencia(indice=1, estado=EstadoAsistencia.PUNTUAL),
        _crear_asistencia(indice=2, estado=EstadoAsistencia.PUNTUAL),
        _crear_asistencia(indice=3, estado=EstadoAsistencia.TARDANZA),
        _crear_asistencia(indice=4, estado=EstadoAsistencia.AUSENTE),
        _crear_asistencia(indice=5, estado=EstadoAsistencia.JUSTIFICADO),
    )
    promedios = (_crear_promedio(),)
    obligaciones = (
        _crear_obligacion(
            id="obl-1",
            monto="100.00",
            fecha_vencimiento=date(2026, 3, 10),
            estado=EstadoObligacion.PAGADO,
        ),
        _crear_obligacion(
            id="obl-2",
            monto="50.00",
            fecha_vencimiento=date(2026, 3, 15),
        ),
        _crear_obligacion(
            id="obl-3",
            monto="30.00",
            fecha_vencimiento=date(2026, 4, 15),
        ),
        _crear_obligacion(
            id="obl-4",
            monto="20.00",
            fecha_vencimiento=date(2026, 4, 20),
            estado=EstadoObligacion.VENCIDO,
        ),
        _crear_obligacion(
            id="obl-5",
            monto="40.00",
            fecha_vencimiento=date(2026, 3, 1),
            estado=EstadoObligacion.EXONERADO,
        ),
    )

    resultado = _construir_ficha(
        operador_admin,
        ficha=ficha,
        carnet=carnet,
        asistencias=asistencias,
        promedios=promedios,
        obligaciones=obligaciones,
    )

    assert isinstance(resultado, FichaInformativaAlumno)
    assert resultado.ficha_matricula is ficha
    assert resultado.estado_actual is EstadoAcademico.ACTIVO
    assert resultado.carnet_activo is carnet
    assert resultado.promedios_cursos == promedios
    assert resultado.fecha_referencia == FECHA_REFERENCIA
    assert resultado.resumen_asistencia == ResumenAsistenciaAlumno(
        puntuales=2,
        tardanzas=1,
        ausentes=1,
        justificados=1,
        porcentaje_asistencia=Decimal("80.00"),
    )
    assert resultado.resumen_pagos == ResumenPagosAlumno(
        total_obligaciones=5,
        monto_total=Decimal("240.00"),
        monto_pagado=Decimal("100.00"),
        monto_pendiente=Decimal("100.00"),
        obligaciones_vencidas=2,
        monto_vencido=Decimal("70.00"),
    )


def test_expone_apoderados_de_la_matricula(operador_admin: UsuarioOperador) -> None:
    ficha = _crear_ficha()

    resultado = _construir_ficha(operador_admin, ficha=ficha)

    assert resultado.apoderados == ficha.apoderados
    assert resultado.apoderados[0].es_principal is True


def test_filtra_datos_de_otros_alumnos(operador_admin: UsuarioOperador) -> None:
    resultado = _construir_ficha(
        operador_admin,
        asistencias=(
            _crear_asistencia(indice=1, alumno_id=ALUMNO_ID),
            _crear_asistencia(indice=2, alumno_id=99),
        ),
        promedios=(
            _crear_promedio(curso_id=101, alumno_id=ALUMNO_ID),
            _crear_promedio(curso_id=202, alumno_id=99),
        ),
        obligaciones=(
            _crear_obligacion(
                id="obl-propia",
                monto="10.00",
                fecha_vencimiento=date(2026, 3, 10),
            ),
            _crear_obligacion(
                id="obl-ajena",
                monto="999.00",
                fecha_vencimiento=date(2026, 3, 10),
                alumno_id=99,
            ),
        ),
    )

    assert resultado.resumen_asistencia.puntuales == 1
    assert [promedio.curso_id for promedio in resultado.promedios_cursos] == [101]
    assert resultado.resumen_pagos is not None
    assert resultado.resumen_pagos.total_obligaciones == 1
    assert resultado.resumen_pagos.monto_total == Decimal("10.00")


# ---------------------------------------------------------------------------
# RN-02: métricas de asistencia
# ---------------------------------------------------------------------------


def test_resumen_asistencia_sin_registros(operador_admin: UsuarioOperador) -> None:
    resultado = _construir_ficha(operador_admin)

    assert resultado.resumen_asistencia == ResumenAsistenciaAlumno(
        puntuales=0,
        tardanzas=0,
        ausentes=0,
        justificados=0,
        porcentaje_asistencia=Decimal("0.00"),
    )


def test_ignora_asistencias_pendientes_en_el_porcentaje(
    operador_admin: UsuarioOperador,
) -> None:
    resultado = _construir_ficha(
        operador_admin,
        asistencias=(
            _crear_asistencia(indice=1, estado=EstadoAsistencia.PUNTUAL),
            _crear_asistencia(indice=2, estado=EstadoAsistencia.PENDIENTE),
        ),
    )

    assert resultado.resumen_asistencia.puntuales == 1
    assert resultado.resumen_asistencia.porcentaje_asistencia == Decimal("100.00")


def test_porcentaje_asistencia_redondea_half_up(operador_admin: UsuarioOperador) -> None:
    resultado = _construir_ficha(
        operador_admin,
        asistencias=(
            _crear_asistencia(indice=1, estado=EstadoAsistencia.PUNTUAL),
            _crear_asistencia(indice=2, estado=EstadoAsistencia.PUNTUAL),
            _crear_asistencia(indice=3, estado=EstadoAsistencia.AUSENTE),
        ),
    )

    assert resultado.resumen_asistencia.porcentaje_asistencia == Decimal("66.67")


# ---------------------------------------------------------------------------
# RN-03: segregación financiera
# ---------------------------------------------------------------------------


def test_oculta_bloque_financiero_sin_permisos_de_pagos(
    operador_coordinador: UsuarioOperador,
) -> None:
    resultado = _construir_ficha(
        operador_coordinador,
        obligaciones=(
            _crear_obligacion(
                id="obl-1",
                monto="50.00",
                fecha_vencimiento=date(2026, 3, 15),
            ),
        ),
    )

    assert resultado.resumen_pagos is None
    assert resultado.resumen_asistencia is not None


def test_admin_staff_ve_bloque_financiero(
    operador_admin_staff: UsuarioOperador,
) -> None:
    resultado = _construir_ficha(operador_admin_staff)

    assert resultado.resumen_pagos == ResumenPagosAlumno(
        total_obligaciones=0,
        monto_total=Decimal("0.00"),
        monto_pagado=Decimal("0.00"),
        monto_pendiente=Decimal("0.00"),
        obligaciones_vencidas=0,
        monto_vencido=Decimal("0.00"),
    )


def test_rol_personalizado_con_ver_alerta_ve_pagos(rol_ver_alerta: Rol) -> None:
    operador = UsuarioOperador(
        id=6, username="auditor", rol=rol_ver_alerta.codigo, activo=True
    )

    resultado = _construir_ficha(operador, roles=(rol_ver_alerta,))

    assert resultado.resumen_pagos is not None


def test_rol_personalizado_con_gestionar_pagos_ve_pagos(
    rol_gestionar_pagos: Rol,
) -> None:
    operador = UsuarioOperador(
        id=7, username="cajero", rol=rol_gestionar_pagos.codigo, activo=True
    )

    resultado = _construir_ficha(operador, roles=(rol_gestionar_pagos,))

    assert resultado.resumen_pagos is not None


# ---------------------------------------------------------------------------
# RN-04: alumnos históricos
# ---------------------------------------------------------------------------


def test_consulta_alumno_retirado_conserva_historial(
    operador_admin: UsuarioOperador,
) -> None:
    ficha = _crear_ficha(estado=EstadoAcademico.RETIRADO)
    carnet = _crear_carnet(estado=EstadoCarnet.ANULADO)

    resultado = _construir_ficha(
        operador_admin,
        ficha=ficha,
        estado_actual=EstadoAcademico.RETIRADO,
        carnet=carnet,
        asistencias=(_crear_asistencia(indice=1),),
        promedios=(_crear_promedio(),),
    )

    assert resultado.estado_actual is EstadoAcademico.RETIRADO
    assert resultado.ficha_matricula.estado is EstadoAcademico.RETIRADO
    assert resultado.carnet_activo is not None
    assert resultado.carnet_activo.estado is EstadoCarnet.ANULADO
    assert resultado.resumen_asistencia.puntuales == 1


def test_estado_historico_como_texto_se_normaliza(
    operador_admin: UsuarioOperador,
) -> None:
    resultado = _construir_ficha(operador_admin, estado_actual="TRASLADADO")

    assert resultado.estado_actual is EstadoAcademico.TRASLADADO


# ---------------------------------------------------------------------------
# RN-01 / RN-05: permisos y alumno inexistente
# ---------------------------------------------------------------------------


def test_operador_sin_permiso_lanza_excepcion(
    operador_sin_permiso: UsuarioOperador,
) -> None:
    with pytest.raises(PermisoFichaAlumnoException):
        _construir_ficha(operador_sin_permiso)


def test_operador_inactivo_lanza_excepcion(operador_inactivo: UsuarioOperador) -> None:
    with pytest.raises(PermisoFichaAlumnoException):
        _construir_ficha(operador_inactivo)


def test_operador_invalido_lanza_excepcion() -> None:
    with pytest.raises(PermisoFichaAlumnoException):
        ServicioFichaAlumno.construir_ficha(
            operador=object(),  # type: ignore[arg-type]
            ficha_matricula=_crear_ficha(),
            estado_actual=EstadoAcademico.ACTIVO,
            carnet_activo=None,
            asistencias_alumno=(),
            promedios_cursos=(),
        )


def test_alumno_inexistente_lanza_excepcion(
    operador_admin: UsuarioOperador,
) -> None:
    with pytest.raises(AlumnoNoEncontradoException):
        ServicioFichaAlumno.construir_ficha(
            operador=operador_admin,
            ficha_matricula=None,
            estado_actual=EstadoAcademico.ACTIVO,
            carnet_activo=None,
            asistencias_alumno=(),
            promedios_cursos=(),
        )


def test_estado_academico_invalido_lanza_excepcion(
    operador_admin: UsuarioOperador,
) -> None:
    with pytest.raises(FichaAlumnoException):
        _construir_ficha(operador_admin, estado_actual="NO_EXISTE")


# ---------------------------------------------------------------------------
# Fecha de referencia
# ---------------------------------------------------------------------------


def test_fecha_referencia_por_defecto_usa_hora_de_lima(
    operador_admin: UsuarioOperador,
) -> None:
    resultado = _construir_ficha(operador_admin, fecha_referencia=None)

    assert resultado.fecha_referencia.tzinfo is not None
    assert resultado.fecha_referencia.utcoffset() == timedelta(hours=-5)


def test_fecha_referencia_naive_se_normaliza_a_lima(
    operador_admin: UsuarioOperador,
) -> None:
    resultado = _construir_ficha(
        operador_admin, fecha_referencia=datetime(2026, 3, 31, 12, 0)
    )

    assert resultado.fecha_referencia.utcoffset() == timedelta(hours=-5)


def test_fecha_referencia_invalida_lanza_excepcion(
    operador_admin: UsuarioOperador,
) -> None:
    with pytest.raises(FichaAlumnoException):
        _construir_ficha(operador_admin, fecha_referencia="2026-03-31")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Inmutabilidad de los value objects
# ---------------------------------------------------------------------------


def test_ficha_informativa_es_inmutable(operador_admin: UsuarioOperador) -> None:
    resultado = _construir_ficha(operador_admin)

    with pytest.raises(FrozenInstanceError):
        resultado.estado_actual = EstadoAcademico.RETIRADO  # type: ignore[misc]


def test_resumen_asistencia_es_inmutable() -> None:
    resumen = ResumenAsistenciaAlumno(
        puntuales=1,
        tardanzas=0,
        ausentes=0,
        justificados=0,
        porcentaje_asistencia=Decimal("100.00"),
    )

    with pytest.raises(FrozenInstanceError):
        resumen.puntuales = 2  # type: ignore[misc]


def test_resumen_pagos_es_inmutable() -> None:
    resumen = ResumenPagosAlumno(
        total_obligaciones=0,
        monto_total=Decimal("0.00"),
        monto_pagado=Decimal("0.00"),
        monto_pendiente=Decimal("0.00"),
        obligaciones_vencidas=0,
        monto_vencido=Decimal("0.00"),
    )

    with pytest.raises(FrozenInstanceError):
        resumen.monto_total = Decimal("1.00")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validación defensiva de los value objects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("puntuales", -1),
        ("tardanzas", True),
        ("ausentes", "3"),
        ("justificados", 1.5),
    ],
)
def test_resumen_asistencia_rechaza_conteos_invalidos(campo: str, valor: object) -> None:
    datos: dict[str, object] = {
        "puntuales": 0,
        "tardanzas": 0,
        "ausentes": 0,
        "justificados": 0,
        "porcentaje_asistencia": Decimal("0.00"),
    }
    datos[campo] = valor

    with pytest.raises(FichaAlumnoException):
        ResumenAsistenciaAlumno(**datos)  # type: ignore[arg-type]


@pytest.mark.parametrize("porcentaje", [Decimal("-0.01"), Decimal("100.01"), "80"])
def test_resumen_asistencia_rechaza_porcentajes_invalidos(porcentaje: object) -> None:
    with pytest.raises(FichaAlumnoException):
        ResumenAsistenciaAlumno(
            puntuales=0,
            tardanzas=0,
            ausentes=0,
            justificados=0,
            porcentaje_asistencia=porcentaje,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("total_obligaciones", -1),
        ("obligaciones_vencidas", True),
        ("monto_total", "-1.00"),
        ("monto_pagado", 10.0),
        ("monto_pendiente", Decimal("NaN")),
        ("monto_vencido", None),
    ],
)
def test_resumen_pagos_rechaza_valores_invalidos(campo: str, valor: object) -> None:
    datos: dict[str, object] = {
        "total_obligaciones": 0,
        "monto_total": Decimal("0.00"),
        "monto_pagado": Decimal("0.00"),
        "monto_pendiente": Decimal("0.00"),
        "obligaciones_vencidas": 0,
        "monto_vencido": Decimal("0.00"),
    }
    datos[campo] = valor

    with pytest.raises(FichaAlumnoException):
        ResumenPagosAlumno(**datos)  # type: ignore[arg-type]


def _ficha_informativa_valida() -> FichaInformativaAlumno:
    return FichaInformativaAlumno(
        ficha_matricula=_crear_ficha(),
        estado_actual=EstadoAcademico.ACTIVO,
        carnet_activo=None,
        resumen_asistencia=ResumenAsistenciaAlumno(
            puntuales=0,
            tardanzas=0,
            ausentes=0,
            justificados=0,
            porcentaje_asistencia=Decimal("0.00"),
        ),
        promedios_cursos=(),
        resumen_pagos=None,
        fecha_referencia=FECHA_REFERENCIA,
    )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("ficha_matricula", object()),
        ("estado_actual", "ACTIVO"),
        ("carnet_activo", object()),
        ("resumen_asistencia", object()),
        ("resumen_pagos", object()),
        ("promedios_cursos", (object(),)),
        ("fecha_referencia", "2026-03-31"),
    ],
)
def test_ficha_informativa_rechaza_componentes_invalidos(
    campo: str, valor: object
) -> None:
    valida = _ficha_informativa_valida()
    datos: dict[str, object] = {
        "ficha_matricula": valida.ficha_matricula,
        "estado_actual": valida.estado_actual,
        "carnet_activo": valida.carnet_activo,
        "resumen_asistencia": valida.resumen_asistencia,
        "promedios_cursos": valida.promedios_cursos,
        "resumen_pagos": valida.resumen_pagos,
        "fecha_referencia": valida.fecha_referencia,
    }
    datos[campo] = valor

    with pytest.raises(FichaAlumnoException):
        FichaInformativaAlumno(**datos)  # type: ignore[arg-type]


def test_ficha_informativa_convierte_promedios_a_tupla(
    operador_admin: UsuarioOperador,
) -> None:
    ficha = _ficha_informativa_valida()
    promedio = _crear_promedio()

    resultado = FichaInformativaAlumno(
        ficha_matricula=ficha.ficha_matricula,
        estado_actual=ficha.estado_actual,
        carnet_activo=ficha.carnet_activo,
        resumen_asistencia=ficha.resumen_asistencia,
        promedios_cursos=[promedio],  # type: ignore[arg-type]
        resumen_pagos=None,
        fecha_referencia=ficha.fecha_referencia,
    )

    assert resultado.promedios_cursos == (promedio,)
