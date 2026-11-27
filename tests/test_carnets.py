"""Pruebas BDD y unitarias del PBI-06: Emisión y Anulación de Carnet Escolar QR."""

import re
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from src.dominio.asistencia import UsuarioOperador
from src.dominio.carnets import (
    AlumnoNoHabilitadoCarnetException,
    CarnetEscolar,
    CarnetException,
    CarnetInactivoOAnuladoException,
    CarnetNoEncontradoException,
    CarnetYaAnuladoException,
    EstadoCarnet,
    MotivoAnulacionCarnet,
    MotivoAnulacionRequeridoException,
    PermisoCarnetException,
    ResultadoEmisionCarnet,
    ServicioCarnets,
)
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.usuarios import PermisoOperacion, Rol, RolUsuario

FECHA_HORA = datetime(2026, 3, 10, 8, 0)


def _crear_carnet(
    *,
    id: str = "car-000000000001",
    alumno_id: int = 10,
    codigo_qr: str = "DSV-2026-AAAAAAAAAAAA",
    estado: EstadoCarnet = EstadoCarnet.ACTIVO,
    emitido_por: int = 1,
    emitido_en: datetime = FECHA_HORA,
    anulado_en: datetime | None = None,
    motivo_anulacion: MotivoAnulacionCarnet | None = None,
    detalle_anulacion: str | None = None,
) -> CarnetEscolar:
    return CarnetEscolar(
        id=id,
        alumno_id=alumno_id,
        codigo_qr=codigo_qr,
        estado=estado,
        emitido_por=emitido_por,
        emitido_en=emitido_en,
        anulado_en=anulado_en,
        motivo_anulacion=motivo_anulacion,
        detalle_anulacion=detalle_anulacion,
    )


def _fijar_token_qr(monkeypatch: pytest.MonkeyPatch, *tokens: str) -> None:
    secuencia = iter(tokens)
    monkeypatch.setattr(
        "src.dominio.carnets.secrets.token_hex",
        lambda _longitud: next(secuencia),
    )


@pytest.fixture
def operador_admin() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=True)


@pytest.fixture
def operador_inactivo() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="admin_off", rol=RolUsuario.ADMIN, activo=False)


@pytest.fixture
def operador_sin_permiso() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="consulta", rol="CONSULTA")


@pytest.fixture
def rol_gestor_carnets() -> Rol:
    return Rol(
        codigo="GESTOR_CARNETS",
        nombre="Gestor de carnets",
        descripcion="Emite y anula carnets escolares",
        permisos=frozenset({PermisoOperacion.GESTIONAR_CARNETS}),
    )


@pytest.fixture
def rol_sin_permiso() -> Rol:
    return Rol(
        codigo="CONSULTA",
        nombre="Consulta",
        descripcion="Solo consulta fichas de alumnos",
        permisos=frozenset({PermisoOperacion.CONSULTAR_FICHA_ALUMNO}),
    )


# ---------------------------------------------------------------------------
# Generación de código QR (RN-05)
# ---------------------------------------------------------------------------


def test_generar_codigo_qr_tiene_formato_opaco() -> None:
    codigo = ServicioCarnets.generar_codigo_qr(2026)

    assert re.fullmatch(r"DSV-2026-[0-9A-F]{12}", codigo)


def test_generar_codigo_qr_reintenta_ante_colision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    codigo = ServicioCarnets.generar_codigo_qr(2026, ["DSV-2026-AAAAAAAAAAAA"])

    assert codigo == "DSV-2026-BBBBBBBBBBBB"


# ---------------------------------------------------------------------------
# Escenario 1: emitir el primer carnet a un alumno ACTIVO
# ---------------------------------------------------------------------------


def test_escenario_01_emitir_primer_carnet_activo(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "abcdef123456")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=FECHA_HORA,
    )

    assert isinstance(resultado, ResultadoEmisionCarnet)
    assert resultado.carnet_anulado is None
    carnet = resultado.carnet_nuevo
    assert carnet.estado == EstadoCarnet.ACTIVO
    assert carnet.alumno_id == 10
    assert carnet.emitido_por == operador_admin.id
    assert carnet.emitido_en == FECHA_HORA
    assert carnet.anulado_en is None
    assert carnet.motivo_anulacion is None
    assert carnet.detalle_anulacion is None
    assert carnet.codigo_qr == "DSV-2026-ABCDEF123456"


def test_emision_acepta_estado_como_string_activo(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "dddddddddddd")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno="ACTIVO",
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=FECHA_HORA,
    )

    assert resultado.carnet_nuevo.estado == EstadoCarnet.ACTIVO


# ---------------------------------------------------------------------------
# Escenario 2: reemitir carnet anulando automáticamente el anterior
# ---------------------------------------------------------------------------


def test_escenario_02_reemitir_carnet_por_extravio_anula_el_anterior(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anterior = _crear_carnet(codigo_qr="DSV-2026-AAAAAAAAAAAA")
    _fijar_token_qr(monkeypatch, "bbbbbbbbbbbb")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno="ACTIVO",
        anio_lectivo=2026,
        carnets_existentes=[anterior],
        fecha_hora=FECHA_HORA,
        motivo_reposicion=MotivoAnulacionCarnet.EXTRAVIO,
        detalle_anulacion="Robo en la calle",
    )

    anulado = resultado.carnet_anulado
    assert anulado is not None
    assert anulado.id == anterior.id
    assert anulado.estado == EstadoCarnet.ANULADO
    assert anulado.anulado_en == FECHA_HORA
    assert anulado.motivo_anulacion == MotivoAnulacionCarnet.EXTRAVIO
    assert anulado.detalle_anulacion == "Robo en la calle"
    assert resultado.carnet_nuevo.estado == EstadoCarnet.ACTIVO
    assert resultado.carnet_nuevo.codigo_qr == "DSV-2026-BBBBBBBBBBBB"
    assert resultado.carnet_nuevo.codigo_qr != anterior.codigo_qr
    assert anterior.estado == EstadoCarnet.ACTIVO


def test_reposicion_acepta_motivo_como_string_mayusculas(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anterior = _crear_carnet()
    _fijar_token_qr(monkeypatch, "eeeeeeeeeeee")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[anterior],
        fecha_hora=FECHA_HORA,
        motivo_reposicion="EXTRAVIO",
    )

    assert resultado.carnet_anulado is not None
    assert resultado.carnet_anulado.motivo_anulacion == MotivoAnulacionCarnet.EXTRAVIO


def test_reposicion_sin_motivo_lanza_excepcion(
    operador_admin: UsuarioOperador,
) -> None:
    anterior = _crear_carnet()

    with pytest.raises(MotivoAnulacionRequeridoException):
        ServicioCarnets.emitir_carnet(
            operador=operador_admin,
            alumno_id=10,
            estado_alumno=EstadoAcademico.ACTIVO,
            anio_lectivo=2026,
            carnets_existentes=[anterior],
            fecha_hora=FECHA_HORA,
        )


def test_reposicion_con_motivo_invalido_lanza_excepcion(
    operador_admin: UsuarioOperador,
) -> None:
    anterior = _crear_carnet()

    with pytest.raises(MotivoAnulacionRequeridoException):
        ServicioCarnets.emitir_carnet(
            operador=operador_admin,
            alumno_id=10,
            estado_alumno=EstadoAcademico.ACTIVO,
            anio_lectivo=2026,
            carnets_existentes=[anterior],
            fecha_hora=FECHA_HORA,
            motivo_reposicion="ROBO",
        )


def test_emision_con_carnet_anulado_previo_no_exige_motivo(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anterior = _crear_carnet(
        estado=EstadoCarnet.ANULADO,
        anulado_en=FECHA_HORA,
        motivo_anulacion=MotivoAnulacionCarnet.EXTRAVIO,
    )
    _fijar_token_qr(monkeypatch, "333333333333")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[anterior],
        fecha_hora=FECHA_HORA,
    )

    assert resultado.carnet_anulado is None
    assert resultado.carnet_nuevo.codigo_qr != anterior.codigo_qr


def test_emision_no_anula_carnet_de_otro_alumno(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    otro = _crear_carnet(id="car-otro", alumno_id=99)
    _fijar_token_qr(monkeypatch, "444444444444")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[otro],
        fecha_hora=FECHA_HORA,
    )

    assert resultado.carnet_anulado is None
    assert otro.estado == EstadoCarnet.ACTIVO


# ---------------------------------------------------------------------------
# Escenario 3: anulación manual
# ---------------------------------------------------------------------------


def test_escenario_03_anular_carnet_manual(operador_admin: UsuarioOperador) -> None:
    carnet = _crear_carnet()

    anulado = ServicioCarnets.anular_carnet(
        operador=operador_admin,
        carnet=carnet,
        motivo=MotivoAnulacionCarnet.DANO,
        fecha_hora=FECHA_HORA,
        detalle="Pantalla rota",
    )

    assert anulado.estado == EstadoCarnet.ANULADO
    assert anulado.anulado_en == FECHA_HORA
    assert anulado.motivo_anulacion == MotivoAnulacionCarnet.DANO
    assert anulado.detalle_anulacion == "Pantalla rota"
    assert carnet.estado == EstadoCarnet.ACTIVO


def test_anular_rechaza_carnet_ya_anulado(operador_admin: UsuarioOperador) -> None:
    anulado = _crear_carnet(
        estado=EstadoCarnet.ANULADO,
        anulado_en=FECHA_HORA,
        motivo_anulacion=MotivoAnulacionCarnet.EXTRAVIO,
    )

    with pytest.raises(CarnetYaAnuladoException):
        ServicioCarnets.anular_carnet(
            operador=operador_admin,
            carnet=anulado,
            motivo=MotivoAnulacionCarnet.DANO,
            fecha_hora=FECHA_HORA,
        )


def test_anular_valida_y_normaliza_motivo(operador_admin: UsuarioOperador) -> None:
    carnet = _crear_carnet()

    anulado = ServicioCarnets.anular_carnet(
        operador=operador_admin,
        carnet=carnet,
        motivo="DANO",
        fecha_hora=FECHA_HORA,
    )
    assert anulado.motivo_anulacion is MotivoAnulacionCarnet.DANO

    for motivo_invalido in (None, "", "   ", "INVALIDO"):
        with pytest.raises(MotivoAnulacionRequeridoException):
            ServicioCarnets.anular_carnet(
                operador=operador_admin,
                carnet=carnet,
                motivo=motivo_invalido,  # type: ignore[arg-type]
                fecha_hora=FECHA_HORA,
            )


def test_anular_sin_permiso(
    operador_sin_permiso: UsuarioOperador,
    rol_sin_permiso: Rol,
) -> None:
    with pytest.raises(PermisoCarnetException):
        ServicioCarnets.anular_carnet(
            operador=operador_sin_permiso,
            carnet=_crear_carnet(),
            motivo=MotivoAnulacionCarnet.OTRO,
            fecha_hora=FECHA_HORA,
            roles=[rol_sin_permiso],
        )


# ---------------------------------------------------------------------------
# Escenario 4: alumnos no habilitados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "estado",
    [
        EstadoAcademico.SUSPENDIDO,
        EstadoAcademico.RETIRADO,
        EstadoAcademico.TRASLADADO,
        EstadoAcademico.EGRESADO,
        "INACTIVO",
        None,
    ],
)
def test_escenario_04_rechaza_emision_para_alumno_no_activo(
    operador_admin: UsuarioOperador,
    estado: object,
) -> None:
    with pytest.raises(AlumnoNoHabilitadoCarnetException):
        ServicioCarnets.emitir_carnet(
            operador=operador_admin,
            alumno_id=10,
            estado_alumno=estado,  # type: ignore[arg-type]
            anio_lectivo=2026,
            carnets_existentes=[],
            fecha_hora=FECHA_HORA,
        )


# ---------------------------------------------------------------------------
# Escenario 5: permisos y roles personalizados
# ---------------------------------------------------------------------------


def test_escenario_05_deniega_emision_sin_permiso(
    operador_sin_permiso: UsuarioOperador,
    rol_sin_permiso: Rol,
) -> None:
    with pytest.raises(PermisoCarnetException):
        ServicioCarnets.emitir_carnet(
            operador=operador_sin_permiso,
            alumno_id=10,
            estado_alumno=EstadoAcademico.ACTIVO,
            anio_lectivo=2026,
            carnets_existentes=[],
            fecha_hora=FECHA_HORA,
            roles=[rol_sin_permiso],
        )


def test_permite_operacion_con_rol_personalizado_autorizado(
    rol_gestor_carnets: Rol,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operador = UsuarioOperador(id=9, username="gestor", rol="GESTOR_CARNETS")
    _fijar_token_qr(monkeypatch, "cccccccccccc")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=FECHA_HORA,
        roles=[rol_gestor_carnets],
    )

    assert resultado.carnet_nuevo.emitido_por == 9


def test_rechaza_operador_inactivo(operador_inactivo: UsuarioOperador) -> None:
    with pytest.raises(PermisoCarnetException):
        ServicioCarnets.validar_operador(operador_inactivo)


def test_rechaza_rol_personalizado_inactivo() -> None:
    rol = Rol(
        codigo="GESTOR_INACTIVO",
        nombre="Gestor inactivo",
        descripcion="Rol desactivado",
        permisos=frozenset({PermisoOperacion.GESTIONAR_CARNETS}),
        activo=False,
    )
    operador = UsuarioOperador(id=11, username="gestor_off", rol="GESTOR_INACTIVO")

    with pytest.raises(PermisoCarnetException):
        ServicioCarnets.validar_operador(operador, roles=[rol])


# ---------------------------------------------------------------------------
# Validación del carnet en el ingreso (RN-06)
# ---------------------------------------------------------------------------


def test_validar_carnet_activo_retorna_el_carnet() -> None:
    carnet = _crear_carnet()

    assert (
        ServicioCarnets.validar_carnet_para_ingreso(carnet.codigo_qr, [carnet])
        is carnet
    )


def test_validar_carnet_recorre_varios_hasta_encontrar() -> None:
    otro = _crear_carnet(
        id="car-otro",
        alumno_id=99,
        codigo_qr="DSV-2026-BBBBBBBBBBBB",
    )
    carnet = _crear_carnet(codigo_qr="DSV-2026-AAAAAAAAAAAA")

    assert (
        ServicioCarnets.validar_carnet_para_ingreso(carnet.codigo_qr, [otro, carnet])
        is carnet
    )


def test_validar_carnet_anulado_lanza_excepcion() -> None:
    carnet = _crear_carnet(
        estado=EstadoCarnet.ANULADO,
        anulado_en=FECHA_HORA,
        motivo_anulacion=MotivoAnulacionCarnet.EXTRAVIO,
    )

    with pytest.raises(CarnetInactivoOAnuladoException):
        ServicioCarnets.validar_carnet_para_ingreso(carnet.codigo_qr, [carnet])


@pytest.mark.parametrize("codigo_qr", ["", None])
def test_validar_carnet_inexistente_lanza_excepcion(codigo_qr: object) -> None:
    with pytest.raises(CarnetNoEncontradoException):
        ServicioCarnets.validar_carnet_para_ingreso(
            codigo_qr,  # type: ignore[arg-type]
            [],
        )


# ---------------------------------------------------------------------------
# Invariantes de las entidades
# ---------------------------------------------------------------------------


def test_carnet_es_inmutable() -> None:
    carnet = _crear_carnet()

    with pytest.raises(FrozenInstanceError):
        carnet.estado = EstadoCarnet.ANULADO  # type: ignore[misc]


def test_resultado_emision_es_inmutable() -> None:
    carnet = _crear_carnet()
    resultado = ResultadoEmisionCarnet(carnet_nuevo=carnet, carnet_anulado=None)

    with pytest.raises(FrozenInstanceError):
        resultado.carnet_nuevo = carnet  # type: ignore[misc]


@pytest.mark.parametrize(
    "exc_cls",
    [
        PermisoCarnetException,
        AlumnoNoHabilitadoCarnetException,
        CarnetNoEncontradoException,
        CarnetYaAnuladoException,
        MotivoAnulacionRequeridoException,
        CarnetInactivoOAnuladoException,
    ],
)
def test_excepciones_heredan_de_carnet_exception(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, CarnetException)
