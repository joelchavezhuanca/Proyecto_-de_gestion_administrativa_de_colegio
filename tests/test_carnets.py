"""Pruebas BDD y unitarias del PBI-06: Emisión y Anulación de Carnet Escolar QR."""

import re
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from src.dominio.asistencia import EstadoAlumno, UsuarioOperador
from src.dominio.carnets import (
    MAX_INTENTOS_GENERACION_QR,
    ZONA_HORARIA_LIMA,
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

FECHA_HORA = datetime(2026, 3, 10, 8, 0, tzinfo=ZONA_HORARIA_LIMA)


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


def test_generar_codigo_qr_compara_sin_distinguir_mayusculas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    codigo = ServicioCarnets.generar_codigo_qr(2026, ["dsv-2026-aaaaaaaaaaaa"])

    assert codigo == "DSV-2026-BBBBBBBBBBBB"


def test_generar_codigo_qr_falla_tras_agotar_intentos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, *(["aaaaaaaaaaaa"] * MAX_INTENTOS_GENERACION_QR))

    with pytest.raises(CarnetException):
        ServicioCarnets.generar_codigo_qr(2026, {"DSV-2026-AAAAAAAAAAAA"})


@pytest.mark.parametrize("anio_lectivo", [0, -1, True, "2026"])
def test_generar_codigo_qr_rechaza_anio_invalido(anio_lectivo: object) -> None:
    with pytest.raises(CarnetException):
        ServicioCarnets.generar_codigo_qr(anio_lectivo)  # type: ignore[arg-type]


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


def test_emision_acepta_estado_alumno_de_pbi01(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "dddddddddddd")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAlumno.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=FECHA_HORA,
    )

    assert resultado.carnet_nuevo.estado == EstadoCarnet.ACTIVO


def test_emision_normaliza_estado_en_minusculas(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "eeeeeeeeeeee")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=" activo ",
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=FECHA_HORA,
    )

    assert resultado.carnet_nuevo.estado == EstadoCarnet.ACTIVO


def test_emision_normaliza_fecha_naive_a_zona_lima(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "ffffffffffff")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=datetime(2026, 3, 10, 8, 0),
    )

    assert resultado.carnet_nuevo.emitido_en.utcoffset() == timedelta(hours=-5)


def test_emision_convierte_fecha_utc_a_zona_lima(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "111111111111")

    resultado = ServicioCarnets.emitir_carnet(
        operador=operador_admin,
        alumno_id=10,
        estado_alumno=EstadoAcademico.ACTIVO,
        anio_lectivo=2026,
        carnets_existentes=[],
        fecha_hora=datetime(2026, 3, 10, 13, 0, tzinfo=UTC),
    )

    assert resultado.carnet_nuevo.emitido_en.hour == 8
    assert resultado.carnet_nuevo.emitido_en.utcoffset() == timedelta(hours=-5)


def test_emision_rechaza_fecha_hora_invalida(
    operador_admin: UsuarioOperador,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fijar_token_qr(monkeypatch, "222222222222")

    with pytest.raises(CarnetException):
        ServicioCarnets.emitir_carnet(
            operador=operador_admin,
            alumno_id=10,
            estado_alumno=EstadoAcademico.ACTIVO,
            anio_lectivo=2026,
            carnets_existentes=[],
            fecha_hora="2026-03-10",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("alumno_id", [0, -1, True, "10"])
def test_emision_rechaza_alumno_id_invalido(
    operador_admin: UsuarioOperador,
    alumno_id: object,
) -> None:
    with pytest.raises(CarnetException):
        ServicioCarnets.emitir_carnet(
            operador=operador_admin,
            alumno_id=alumno_id,  # type: ignore[arg-type]
            estado_alumno=EstadoAcademico.ACTIVO,
            anio_lectivo=2026,
            carnets_existentes=[],
            fecha_hora=FECHA_HORA,
        )


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
        motivo_reposicion="extravio",
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


@pytest.mark.parametrize("motivo", [None, "", "ROBO"])
def test_reposicion_exige_motivo_de_anulacion_valido(
    operador_admin: UsuarioOperador,
    motivo: object,
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
            motivo_reposicion=motivo,  # type: ignore[arg-type]
        )


def test_emision_rechaza_multiples_carnets_activos(
    operador_admin: UsuarioOperador,
) -> None:
    primero = _crear_carnet(id="car-1", codigo_qr="DSV-2026-AAAAAAAAAAAA")
    segundo = _crear_carnet(id="car-2", codigo_qr="DSV-2026-BBBBBBBBBBBB")

    with pytest.raises(CarnetException):
        ServicioCarnets.emitir_carnet(
            operador=operador_admin,
            alumno_id=10,
            estado_alumno=EstadoAcademico.ACTIVO,
            anio_lectivo=2026,
            carnets_existentes=[primero, segundo],
            fecha_hora=FECHA_HORA,
            motivo_reposicion=MotivoAnulacionCarnet.EXTRAVIO,
        )


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


def test_anular_normaliza_detalle_vacio(operador_admin: UsuarioOperador) -> None:
    anulado = ServicioCarnets.anular_carnet(
        operador=operador_admin,
        carnet=_crear_carnet(),
        motivo=MotivoAnulacionCarnet.OTRO,
        fecha_hora=FECHA_HORA,
        detalle="   ",
    )

    assert anulado.detalle_anulacion is None


def test_anular_normaliza_fecha_naive(operador_admin: UsuarioOperador) -> None:
    anulado = ServicioCarnets.anular_carnet(
        operador=operador_admin,
        carnet=_crear_carnet(),
        motivo="extravio",
        fecha_hora=datetime(2026, 3, 10, 8, 0),
    )

    assert anulado.anulado_en is not None
    assert anulado.anulado_en.utcoffset() == timedelta(hours=-5)


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


def test_anular_rechaza_carnet_invalido(operador_admin: UsuarioOperador) -> None:
    with pytest.raises(CarnetException):
        ServicioCarnets.anular_carnet(
            operador=operador_admin,
            carnet=None,  # type: ignore[arg-type]
            motivo=MotivoAnulacionCarnet.OTRO,
            fecha_hora=FECHA_HORA,
        )


@pytest.mark.parametrize("motivo", [None, "", "ROBO"])
def test_anular_exige_motivo_valido(
    operador_admin: UsuarioOperador,
    motivo: object,
) -> None:
    with pytest.raises(MotivoAnulacionRequeridoException):
        ServicioCarnets.anular_carnet(
            operador=operador_admin,
            carnet=_crear_carnet(),
            motivo=motivo,  # type: ignore[arg-type]
            fecha_hora=FECHA_HORA,
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
        EstadoAlumno.INACTIVO,
        "INACTIVO",
        None,
        123,
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


def test_deniega_anulacion_sin_permiso(
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


def test_rechaza_operador_none() -> None:
    with pytest.raises(PermisoCarnetException):
        ServicioCarnets.validar_operador(None)  # type: ignore[arg-type]


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
        ServicioCarnets.validar_carnet_para_ingreso(carnet.codigo_qr, [carnet]) is carnet
    )


def test_validar_carnet_recorre_varios_hasta_encontrar() -> None:
    otro = _crear_carnet(
        id="car-otro",
        alumno_id=99,
        codigo_qr="DSV-2026-BBBBBBBBBBBB",
    )
    carnet = _crear_carnet(codigo_qr="DSV-2026-AAAAAAAAAAAA")

    assert (
        ServicioCarnets.validar_carnet_para_ingreso(
            carnet.codigo_qr, [otro, carnet]
        )
        is carnet
    )


def test_validar_carnet_ignora_mayusculas_y_espacios() -> None:
    carnet = _crear_carnet(codigo_qr="DSV-2026-AAAAAAAAAAAA")

    assert (
        ServicioCarnets.validar_carnet_para_ingreso(
            "  dsv-2026-aaaaaaaaaaaa  ", [carnet]
        )
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


def test_validar_carnet_inexistente_lanza_excepcion() -> None:
    with pytest.raises(CarnetNoEncontradoException):
        ServicioCarnets.validar_carnet_para_ingreso("DSV-2026-999999999999", [])


@pytest.mark.parametrize("codigo_qr", ["", "   ", None])
def test_validar_codigo_vacio_lanza_excepcion(codigo_qr: object) -> None:
    with pytest.raises(CarnetNoEncontradoException):
        ServicioCarnets.validar_carnet_para_ingreso(codigo_qr, [])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Invariantes de las entidades
# ---------------------------------------------------------------------------


def test_carnet_normaliza_textos_y_estado() -> None:
    carnet = _crear_carnet(
        id="  car-1  ",
        codigo_qr="  dsv-2026-aaaaaaaaaaaa  ",
        estado="anulado",  # type: ignore[arg-type]
        anulado_en=FECHA_HORA,
        motivo_anulacion="extravio",  # type: ignore[arg-type]
        detalle_anulacion="   ",
    )

    assert carnet.id == "car-1"
    assert carnet.codigo_qr == "DSV-2026-AAAAAAAAAAAA"
    assert carnet.estado is EstadoCarnet.ANULADO
    assert carnet.motivo_anulacion is MotivoAnulacionCarnet.EXTRAVIO
    assert carnet.detalle_anulacion is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": ""},
        {"alumno_id": 0},
        {"alumno_id": True},
        {"codigo_qr": ""},
        {"emitido_por": 0},
        {"emitido_en": "2026-03-10"},
        {"estado": "INVALIDO"},
        {"estado": 123},
        {"estado": EstadoCarnet.ANULADO, "anulado_en": FECHA_HORA},
        {
            "estado": EstadoCarnet.ANULADO,
            "motivo_anulacion": MotivoAnulacionCarnet.EXTRAVIO,
        },
        {"anulado_en": FECHA_HORA},
        {"motivo_anulacion": MotivoAnulacionCarnet.EXTRAVIO},
        {"detalle_anulacion": "algo"},
        {
            "estado": EstadoCarnet.ANULADO,
            "anulado_en": FECHA_HORA,
            "motivo_anulacion": "ROBO",
        },
        {
            "estado": EstadoCarnet.ANULADO,
            "anulado_en": "2026-03-10",
            "motivo_anulacion": MotivoAnulacionCarnet.EXTRAVIO,
        },
        {
            "estado": EstadoCarnet.ANULADO,
            "anulado_en": FECHA_HORA,
            "motivo_anulacion": 123,
        },
        {
            "estado": EstadoCarnet.ANULADO,
            "anulado_en": FECHA_HORA,
            "motivo_anulacion": MotivoAnulacionCarnet.OTRO,
            "detalle_anulacion": 123,
        },
    ],
)
def test_carnet_rechaza_datos_invalidos(kwargs: dict[str, object]) -> None:
    with pytest.raises(CarnetException):
        _crear_carnet(**kwargs)  # type: ignore[arg-type]


def test_carnet_es_inmutable() -> None:
    carnet = _crear_carnet()

    with pytest.raises(FrozenInstanceError):
        carnet.estado = EstadoCarnet.ANULADO  # type: ignore[misc]


def test_resultado_emision_es_inmutable() -> None:
    carnet = _crear_carnet()
    resultado = ResultadoEmisionCarnet(carnet_nuevo=carnet, carnet_anulado=None)

    with pytest.raises(FrozenInstanceError):
        resultado.carnet_nuevo = carnet  # type: ignore[misc]


def test_resultado_emision_rechaza_carnet_nuevo_invalido() -> None:
    with pytest.raises(CarnetException):
        ResultadoEmisionCarnet(carnet_nuevo="x", carnet_anulado=None)  # type: ignore[arg-type]


def test_resultado_emision_rechaza_carnet_anulado_invalido() -> None:
    with pytest.raises(CarnetException):
        ResultadoEmisionCarnet(
            carnet_nuevo=_crear_carnet(),
            carnet_anulado="x",  # type: ignore[arg-type]
        )


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
