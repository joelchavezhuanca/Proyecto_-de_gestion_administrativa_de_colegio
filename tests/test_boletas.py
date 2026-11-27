"""Pruebas BDD y unitarias del PBI-14: Emisión de Boletas de Calificaciones."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from src.dominio.asistencia import (
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
)
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    RegistroAuditoria,
    ResultadoAuditoria,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.boletas import (
    ETIQUETA_OFICIAL,
    ETIQUETA_PRELIMINAR,
    NOMBRE_INSTITUCION,
    BoletaCalificaciones,
    BoletaException,
    BoletaIncompletaException,
    LineaCursoBoleta,
    PermisoBoletaException,
    ResumenAsistenciaPeriodo,
    ServicioBoletas,
)
from src.dominio.calificaciones import EscalaLiteral, PromedioPeriodo
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.justificaciones import PeriodoAcademico
from src.dominio.malla_curricular import Curso, NivelEducativo, Salon
from src.dominio.matricula import Apoderado, FichaMatricula
from src.dominio.usuarios import EstadoUsuario, PermisoOperacion, Rol, Usuario

ANIO = 2026
FECHA_EMISION = datetime(2026, 5, 20, 10, 0, tzinfo=ZONA_HORARIA_LIMA)


# ---------------------------------------------------------------------------
# Fixtures y fábricas
# ---------------------------------------------------------------------------


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
def staff() -> Usuario:
    return _usuario(3, RolUsuario.ADMIN_STAFF)


@pytest.fixture
def apoderado() -> Apoderado:
    return Apoderado(
        id=1,
        nombres="María",
        apellidos="Quispe",
        documento="40123456",
        parentesco="Madre",
        telefono_whatsapp="987654321",
        es_principal=True,
    )


def _ficha(
    apoderado: Apoderado,
    alumno_id: int,
    apellidos: str,
    *,
    salon_id: int = 10,
    estado: EstadoAcademico = EstadoAcademico.ACTIVO,
    anio: int = ANIO,
    dni: str | None = None,
) -> FichaMatricula:
    return FichaMatricula(
        id=f"mat-{alumno_id}",
        alumno_id=alumno_id,
        codigo_estudiante=f"EST-{alumno_id}",
        dni=dni or f"7{alumno_id:07d}",
        nombres="Alumno",
        apellidos=apellidos,
        fecha_nacimiento=date(2012, 1, 1),
        anio_lectivo=anio,
        salon_id=salon_id,
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        apoderados=(apoderado,),
        estado=estado,
    )


@pytest.fixture
def ficha(apoderado: Apoderado) -> FichaMatricula:
    return _ficha(apoderado, 100, "Pérez")


@pytest.fixture
def salon() -> Salon:
    return Salon(
        id=10, anio_lectivo=ANIO, nivel=NivelEducativo.SECUNDARIA, grado="3ro", seccion="A"
    )


def _curso(id_: int, codigo: str, nombre: str, activo: bool = True) -> Curso:
    return Curso(
        id=id_,
        anio_lectivo=ANIO,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo=codigo,
        nombre=nombre,
        area_curricular="Ciencias",
        horas_semanales=4,
        activo=activo,
    )


@pytest.fixture
def cursos() -> tuple[Curso, ...]:
    return (
        _curso(1, "MAT", "Matemática"),
        _curso(2, "COM", "Comunicación"),
        _curso(3, "CTA", "Ciencia y Tecnología"),
    )


def _periodo(cerrado: bool, anio: int = ANIO) -> PeriodoAcademico:
    return PeriodoAcademico(
        id=1,
        nombre="I Bimestre",
        fecha_inicio=date(anio, 3, 2),
        fecha_fin=date(anio, 5, 8),
        cerrado=cerrado,
        anio_lectivo=anio,
        fecha_limite_notas=date(anio, 5, 15),
    )


@pytest.fixture
def periodo_cerrado() -> PeriodoAcademico:
    return _periodo(True)


@pytest.fixture
def periodo_abierto() -> PeriodoAcademico:
    return _periodo(False)


def _promedio(curso_id: int, nota: str, alumno_id: int = 100, periodo_id: int = 1):
    valor = Decimal(nota)
    return PromedioPeriodo(
        alumno_id=alumno_id,
        curso_id=curso_id,
        periodo_id=periodo_id,
        desglose_rubros=(),
        nota_final=valor,
        escala_literal=EscalaLiteral.A,
    )


@pytest.fixture
def promedios() -> tuple[PromedioPeriodo, ...]:
    return (_promedio(1, "15.98"), _promedio(2, "12.50"), _promedio(3, "18.00"))


def _asistencia(
    alumno_id: int, dia: date, estado: EstadoAsistencia, id_: str | None = None
) -> RegistroAsistencia:
    return RegistroAsistencia(
        id=id_ or f"as-{alumno_id}-{dia.isoformat()}",
        alumno_id=alumno_id,
        fecha_escolar=dia,
        hora_efectiva=time(7, 50),
        estado=estado,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=3,
        rol_usuario=RolUsuario.ADMIN_STAFF,
    )


@pytest.fixture
def asistencias() -> tuple[RegistroAsistencia, ...]:
    return (
        _asistencia(100, date(2026, 3, 2), EstadoAsistencia.PUNTUAL),
        _asistencia(100, date(2026, 3, 3), EstadoAsistencia.PUNTUAL),
        _asistencia(100, date(2026, 3, 4), EstadoAsistencia.TARDANZA),
        _asistencia(100, date(2026, 3, 5), EstadoAsistencia.AUSENTE),
        _asistencia(100, date(2026, 3, 6), EstadoAsistencia.JUSTIFICADO),
        _asistencia(100, date(2026, 5, 8), EstadoAsistencia.PUNTUAL),
        _asistencia(100, date(2026, 3, 9), EstadoAsistencia.PENDIENTE),  # no cuenta
        _asistencia(100, date(2026, 5, 11), EstadoAsistencia.AUSENTE),  # fuera de período
        _asistencia(100, date(2026, 2, 27), EstadoAsistencia.AUSENTE),  # fuera de período
        _asistencia(200, date(2026, 3, 2), EstadoAsistencia.AUSENTE),  # otro alumno
    )


# ---------------------------------------------------------------------------
# Escenario 1: boleta oficial en período cerrado
# ---------------------------------------------------------------------------


def test_emitir_boleta_oficial(staff, ficha, periodo_cerrado, cursos, promedios, asistencias):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_cerrado, cursos, promedios, asistencias, FECHA_EMISION
    )
    assert isinstance(boleta, BoletaCalificaciones)
    assert boleta.es_oficial is True
    assert boleta.etiqueta == ETIQUETA_OFICIAL == "OFICIAL"
    assert boleta.codigo_verificacion is not None
    assert boleta.codigo_verificacion.startswith(f"BOL-{ANIO}-")
    assert len(boleta.codigo_verificacion) == len("BOL-2026-") + 12

    # Datos institucionales, del alumno y académicos (RN-02)
    assert boleta.institucion == NOMBRE_INSTITUCION == "Colegio Domingo Savio S.A.C."
    assert boleta.alumno_id == 100
    assert boleta.codigo_estudiante == "EST-100"
    assert boleta.nombre_completo_alumno == "Pérez, Alumno"
    assert boleta.dni == ficha.dni
    assert (boleta.anio_lectivo, boleta.salon_id) == (ANIO, 10)
    assert (boleta.nivel, boleta.grado, boleta.seccion) == ("Secundaria", "3ro", "A")
    assert (boleta.periodo_id, boleta.periodo_nombre) == (1, "I Bimestre")
    assert boleta.emitido_por == staff.id
    assert boleta.fecha_emision == FECHA_EMISION

    # Tabla de cursos, en el orden de la malla
    assert [linea.codigo_curso for linea in boleta.lineas] == ["MAT", "COM", "CTA"]
    assert [linea.nota for linea in boleta.lineas] == [
        Decimal("15.98"),
        Decimal("12.50"),
        Decimal("18.00"),
    ]
    assert [linea.escala_literal for linea in boleta.lineas] == [
        EscalaLiteral.A,
        EscalaLiteral.B,
        EscalaLiteral.AD,
    ]
    assert all(isinstance(linea, LineaCursoBoleta) for linea in boleta.lineas)
    assert boleta.lineas[0].nombre_curso == "Matemática"

    # (15.98 + 12.50 + 18.00) / 3 = 46.48 / 3 = 15.4933.. -> 15.49
    assert boleta.promedio_general == Decimal("15.49")
    assert boleta.escala_literal_general is EscalaLiteral.A

    resumen = boleta.resumen_asistencia
    assert isinstance(resumen, ResumenAsistenciaPeriodo)
    assert (resumen.puntual, resumen.tardanza, resumen.ausente, resumen.justificado) == (
        3,
        1,
        1,
        1,
    )
    assert resumen.total == 6


def test_boleta_oficial_se_audita(staff, ficha, periodo_cerrado, cursos, promedios, asistencias):
    persistidos: list[RegistroAuditoria] = []
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff,
        ficha,
        periodo_cerrado,
        cursos,
        promedios,
        asistencias,
        FECHA_EMISION,
        persistir_auditoria=persistidos.append,
    )
    auditoria = boleta.auditoria
    assert auditoria is not None
    assert persistidos == [auditoria]
    assert auditoria.operacion == TipoOperacionAuditoria.EMITIR_BOLETA
    assert auditoria.resultado == ResultadoAuditoria.CONFIRMADA
    assert auditoria.usuario_id == staff.id
    assert auditoria.rol_ejecutante == "ADMIN_STAFF"
    assert auditoria.entidad == "BOLETA_CALIFICACIONES"
    assert auditoria.entidad_id == boleta.codigo_verificacion
    assert auditoria.alumno_id == 100
    assert auditoria.detalle["codigo_verificacion"] == boleta.codigo_verificacion
    assert auditoria.detalle["periodo_id"] == 1
    assert auditoria.contexto_academico is not None
    assert auditoria.contexto_academico.seccion == "A"


def test_auditoria_encadena_con_eventos_existentes(
    staff, ficha, periodo_cerrado, cursos, promedios
):
    previo = ServicioAuditoria.registrar_evento(
        usuario_id=1,
        rol_ejecutante="ADMIN",
        operacion=TipoOperacionAuditoria.CREAR_USUARIO,
        entidad="USUARIO",
        entidad_id="1",
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=FECHA_EMISION,
    )
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff,
        ficha,
        periodo_cerrado,
        cursos,
        promedios,
        (),
        FECHA_EMISION,
        eventos_auditoria_existentes=(previo,),
    )
    assert boleta.auditoria is not None
    assert boleta.auditoria.secuencia == previo.secuencia + 1
    assert boleta.auditoria.hash_anterior == previo.hash_integridad


def test_codigos_de_verificacion_unicos(staff, ficha, periodo_cerrado, cursos, promedios):
    codigos = {
        ServicioBoletas.emitir_boleta_individual(
            staff, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
        ).codigo_verificacion
        for _ in range(20)
    }
    assert len(codigos) == 20


def test_codigo_regenera_si_colisiona_con_existentes(
    staff, ficha, periodo_cerrado, cursos, promedios, monkeypatch
):
    tokens = iter(["AAAAAAAAAAAA", "AAAAAAAAAAAA", "BBBBBBBBBBBB"])
    monkeypatch.setattr("src.dominio.boletas.secrets.token_hex", lambda _n: next(tokens))
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff,
        ficha,
        periodo_cerrado,
        cursos,
        promedios,
        (),
        FECHA_EMISION,
        codigos_existentes={"BOL-2026-AAAAAAAAAAAA"},
    )
    assert boleta.codigo_verificacion == "BOL-2026-BBBBBBBBBBBB"


def test_promedio_general_redondea_half_up(staff, ficha, periodo_cerrado):
    cursos = (_curso(1, "MAT", "Matemática"), _curso(2, "COM", "Comunicación"))
    # (13.99 + 14.00) / 2 = 13.995 -> 14.00 (ROUND_HALF_UP)
    promedios = (_promedio(1, "13.99"), _promedio(2, "14.00"))
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
    )
    assert boleta.promedio_general == Decimal("14.00")
    assert boleta.escala_literal_general is EscalaLiteral.A


def test_sin_asistencias_el_resumen_queda_en_cero(
    staff, ficha, periodo_cerrado, cursos, promedios
):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
    )
    assert boleta.resumen_asistencia == ResumenAsistenciaPeriodo(0, 0, 0, 0)
    assert boleta.resumen_asistencia.total == 0


def test_ignora_promedios_de_cursos_fuera_de_la_malla_y_cursos_inactivos(
    staff, ficha, periodo_cerrado, cursos, promedios
):
    con_inactivo = (*cursos, _curso(4, "ART", "Arte", activo=False))
    extra = (*promedios, _promedio(99, "05.00"))
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_cerrado, con_inactivo, extra, (), FECHA_EMISION
    )
    assert [linea.curso_id for linea in boleta.lineas] == [1, 2, 3]
    assert boleta.promedio_general == Decimal("15.49")


def test_fecha_emision_utc_se_normaliza_a_lima(staff, ficha, periodo_cerrado, cursos, promedios):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff,
        ficha,
        periodo_cerrado,
        cursos,
        promedios,
        (),
        datetime(2026, 5, 20, 15, 0, tzinfo=UTC),
    )
    assert boleta.fecha_emision == datetime(2026, 5, 20, 10, 0, tzinfo=ZONA_HORARIA_LIMA)
    assert boleta.fecha_emision.utcoffset() == ZONA_HORARIA_LIMA.utcoffset(None)


def test_fecha_emision_naive_se_asume_lima(staff, ficha, periodo_cerrado, cursos, promedios):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_cerrado, cursos, promedios, (), datetime(2026, 5, 20, 10, 0)
    )
    assert boleta.fecha_emision.tzinfo is not None


# ---------------------------------------------------------------------------
# Escenario 2: boleta preliminar en período abierto
# ---------------------------------------------------------------------------


def test_emitir_boleta_preliminar(staff, ficha, periodo_abierto, cursos, promedios, asistencias):
    persistidos: list[RegistroAuditoria] = []
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff,
        ficha,
        periodo_abierto,
        cursos,
        promedios,
        asistencias,
        FECHA_EMISION,
        persistir_auditoria=persistidos.append,
    )
    assert boleta.es_oficial is False
    assert boleta.etiqueta == ETIQUETA_PRELIMINAR == "BORRADOR / PRELIMINAR"
    assert "PRELIMINAR" in boleta.etiqueta
    assert boleta.codigo_verificacion is None
    assert boleta.auditoria is None
    assert persistidos == []
    assert boleta.promedio_general == Decimal("15.49")


def test_boleta_preliminar_admite_cursos_sin_nota(staff, ficha, periodo_abierto, cursos):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_abierto, cursos, (_promedio(1, "16.00"),), (), FECHA_EMISION
    )
    assert [linea.nota for linea in boleta.lineas] == [Decimal("16.00"), None, None]
    assert [linea.escala_literal for linea in boleta.lineas] == [EscalaLiteral.A, None, None]
    # El promedio preliminar solo considera los cursos ya calificados.
    assert boleta.promedio_general == Decimal("16.00")


def test_boleta_preliminar_sin_ninguna_nota(staff, ficha, periodo_abierto, cursos):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_abierto, cursos, (), (), FECHA_EMISION
    )
    assert boleta.promedio_general is None
    assert boleta.escala_literal_general is None


# ---------------------------------------------------------------------------
# Escenario 4: boleta oficial incompleta
# ---------------------------------------------------------------------------


def test_rechaza_boleta_oficial_si_falta_curso_obligatorio(
    staff, ficha, periodo_cerrado, cursos, promedios
):
    persistidos: list[RegistroAuditoria] = []
    with pytest.raises(BoletaIncompletaException, match="COM"):
        ServicioBoletas.emitir_boleta_individual(
            staff,
            ficha,
            periodo_cerrado,
            cursos,
            (promedios[0], promedios[2]),
            (),
            FECHA_EMISION,
            persistir_auditoria=persistidos.append,
        )
    assert persistidos == []


def test_rechaza_boleta_oficial_sin_ninguna_nota(staff, ficha, periodo_cerrado, cursos):
    with pytest.raises(BoletaIncompletaException):
        ServicioBoletas.emitir_boleta_individual(
            staff, ficha, periodo_cerrado, cursos, (), (), FECHA_EMISION
        )


# ---------------------------------------------------------------------------
# Escenario 5: permisos
# ---------------------------------------------------------------------------


def test_deniega_usuario_sin_permiso_emitir_boletas(
    ficha, periodo_cerrado, cursos, promedios
):
    coordinador = _usuario(2, RolUsuario.COORDINADOR)
    with pytest.raises(PermisoBoletaException):
        ServicioBoletas.emitir_boleta_individual(
            coordinador, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
        )


def test_deniega_usuario_inactivo(ficha, periodo_cerrado, cursos, promedios):
    inactivo = _usuario(3, RolUsuario.ADMIN_STAFF, estado=EstadoUsuario.INACTIVO)
    with pytest.raises(PermisoBoletaException):
        ServicioBoletas.emitir_boleta_individual(
            inactivo, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
        )


@pytest.mark.parametrize(("activo", "permitido"), [(True, True), (False, False)])
def test_operador_de_asistencia(ficha, periodo_cerrado, cursos, promedios, activo, permitido):
    operador = UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=activo)
    if permitido:
        boleta = ServicioBoletas.emitir_boleta_individual(
            operador, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
        )
        assert boleta.emitido_por == 1
        assert boleta.auditoria is not None
        assert boleta.auditoria.rol_ejecutante == "ADMIN"
    else:
        with pytest.raises(PermisoBoletaException):
            ServicioBoletas.emitir_boleta_individual(
                operador, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
            )


def test_rol_personalizado_con_permiso(ficha, periodo_cerrado, cursos, promedios):
    secretaria = Rol(
        codigo="SECRETARIA",
        nombre="Secretaría",
        descripcion="Emite boletas",
        permisos=frozenset({PermisoOperacion.EMITIR_BOLETAS}),
    )
    usuario = _usuario(7, "SECRETARIA")
    boleta = ServicioBoletas.emitir_boleta_individual(
        usuario, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION, roles=(secretaria,)
    )
    assert boleta.es_oficial is True
    with pytest.raises(PermisoBoletaException):
        ServicioBoletas.emitir_boleta_individual(
            usuario, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
        )


# ---------------------------------------------------------------------------
# Validaciones de consistencia
# ---------------------------------------------------------------------------


def test_rechaza_periodo_de_otro_anio(staff, ficha, cursos):
    periodo_2025 = _periodo(True, anio=2025)
    with pytest.raises(BoletaException, match="año lectivo"):
        ServicioBoletas.emitir_boleta_individual(
            staff, ficha, periodo_2025, cursos, (), (), FECHA_EMISION
        )


def test_acepta_periodo_sin_anio_lectivo(staff, ficha, cursos, promedios):
    sin_anio = PeriodoAcademico(
        id=1,
        nombre="I Bimestre",
        fecha_inicio=date(2026, 3, 2),
        fecha_fin=date(2026, 5, 8),
        cerrado=True,
    )
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, sin_anio, cursos, promedios, (), FECHA_EMISION
    )
    assert boleta.codigo_verificacion is not None
    assert boleta.codigo_verificacion.startswith("BOL-2026-")


def test_rechaza_sin_cursos_obligatorios_activos(staff, ficha, periodo_cerrado):
    with pytest.raises(BoletaException, match="curso"):
        ServicioBoletas.emitir_boleta_individual(
            staff,
            ficha,
            periodo_cerrado,
            (_curso(4, "ART", "Arte", activo=False),),
            (),
            (),
            FECHA_EMISION,
        )


def test_rechaza_curso_de_otro_anio_lectivo(staff, ficha, periodo_cerrado):
    curso_2025 = Curso(
        id=1,
        anio_lectivo=2025,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo="MAT",
        nombre="Matemática",
        area_curricular="Ciencias",
        horas_semanales=4,
    )
    with pytest.raises(BoletaException, match="año lectivo"):
        ServicioBoletas.emitir_boleta_individual(
            staff, ficha, periodo_cerrado, (curso_2025,), (_promedio(1, "15"),), (),
            FECHA_EMISION,
        )


@pytest.mark.parametrize(
    "promedio_ajeno",
    [_promedio(1, "15", alumno_id=200), _promedio(1, "15", periodo_id=2)],
)
def test_rechaza_promedio_de_otro_alumno_o_periodo(
    staff, ficha, periodo_cerrado, cursos, promedios, promedio_ajeno
):
    with pytest.raises(BoletaException):
        ServicioBoletas.emitir_boleta_individual(
            staff,
            ficha,
            periodo_cerrado,
            cursos,
            (*promedios[1:], promedio_ajeno),
            (),
            FECHA_EMISION,
        )


def test_rechaza_promedios_duplicados_por_curso(
    staff, ficha, periodo_cerrado, cursos, promedios
):
    with pytest.raises(BoletaException, match="duplicado"):
        ServicioBoletas.emitir_boleta_individual(
            staff,
            ficha,
            periodo_cerrado,
            cursos,
            (*promedios, _promedio(1, "10")),
            (),
            FECHA_EMISION,
        )


def test_rechaza_fecha_emision_invalida(staff, ficha, periodo_cerrado, cursos, promedios):
    with pytest.raises(BoletaException):
        ServicioBoletas.emitir_boleta_individual(
            staff, ficha, periodo_cerrado, cursos, promedios, (), date(2026, 5, 20)  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Escenario 3: emisión masiva por salón
# ---------------------------------------------------------------------------


@pytest.fixture
def fichas_salon(apoderado: Apoderado) -> tuple[FichaMatricula, ...]:
    return (
        _ficha(apoderado, 102, "Zapata"),
        _ficha(apoderado, 100, "Pérez"),
        _ficha(apoderado, 101, "Álvarez"),
        _ficha(apoderado, 103, "Retirado", estado=EstadoAcademico.RETIRADO),
        _ficha(apoderado, 104, "Otro Salón", salon_id=11),
        _ficha(apoderado, 105, "Año Pasado", anio=2025),
    )


def _promedios_de(alumno_ids: tuple[int, ...]) -> tuple[PromedioPeriodo, ...]:
    return tuple(
        _promedio(curso_id, "14.00", alumno_id=alumno_id)
        for alumno_id in alumno_ids
        for curso_id in (1, 2, 3)
    )


def test_emitir_boletas_salon(staff, salon, fichas_salon, periodo_cerrado, cursos, asistencias):
    persistidos: list[RegistroAuditoria] = []
    boletas = ServicioBoletas.emitir_boletas_salon(
        staff,
        salon,
        fichas_salon,
        periodo_cerrado,
        cursos,
        _promedios_de((100, 101, 102)),
        asistencias,
        FECHA_EMISION,
        persistir_auditoria=persistidos.append,
    )
    assert isinstance(boletas, list)
    # Una boleta por alumno ACTIVO matriculado en el salón, ordenadas por apellido.
    assert [b.alumno_id for b in boletas] == [101, 100, 102]
    assert all(b.es_oficial for b in boletas)
    assert all(b.salon_id == salon.id for b in boletas)
    assert len({b.codigo_verificacion for b in boletas}) == 3
    # Cada alumno recibe solo su propia asistencia.
    assert boletas[1].resumen_asistencia.total == 6
    assert boletas[0].resumen_asistencia.total == 0
    # Auditoría encadenada: una por boleta oficial.
    assert [a.secuencia for a in persistidos] == [1, 2, 3]
    assert persistidos[1].hash_anterior == persistidos[0].hash_integridad
    assert [b.auditoria for b in boletas] == persistidos


def test_emision_masiva_es_atomica_si_un_alumno_esta_incompleto(
    staff, salon, fichas_salon, periodo_cerrado, cursos
):
    persistidos: list[RegistroAuditoria] = []
    with pytest.raises(BoletaIncompletaException, match="102"):
        ServicioBoletas.emitir_boletas_salon(
            staff,
            salon,
            fichas_salon,
            periodo_cerrado,
            cursos,
            _promedios_de((100, 101)),
            (),
            FECHA_EMISION,
            persistir_auditoria=persistidos.append,
        )
    assert persistidos == []


def test_emitir_boletas_salon_preliminar(staff, salon, fichas_salon, periodo_abierto, cursos):
    boletas = ServicioBoletas.emitir_boletas_salon(
        staff, salon, fichas_salon, periodo_abierto, cursos, (), (), FECHA_EMISION
    )
    assert len(boletas) == 3
    assert all(not b.es_oficial and b.codigo_verificacion is None for b in boletas)


def test_emitir_boletas_salon_vacio(staff, salon, periodo_cerrado, cursos):
    assert (
        ServicioBoletas.emitir_boletas_salon(
            staff, salon, (), periodo_cerrado, cursos, (), (), FECHA_EMISION
        )
        == []
    )


def test_emitir_boletas_salon_sin_permiso(salon, fichas_salon, periodo_cerrado, cursos):
    coordinador = _usuario(2, RolUsuario.COORDINADOR)
    with pytest.raises(PermisoBoletaException):
        ServicioBoletas.emitir_boletas_salon(
            coordinador, salon, fichas_salon, periodo_cerrado, cursos, (), (), FECHA_EMISION
        )


# ---------------------------------------------------------------------------
# Inmutabilidad y jerarquía
# ---------------------------------------------------------------------------


def test_value_objects_inmutables(staff, ficha, periodo_cerrado, cursos, promedios):
    boleta = ServicioBoletas.emitir_boleta_individual(
        staff, ficha, periodo_cerrado, cursos, promedios, (), FECHA_EMISION
    )
    with pytest.raises(FrozenInstanceError):
        boleta.es_oficial = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        boleta.lineas[0].nota = Decimal("20")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        boleta.resumen_asistencia.ausente = 0  # type: ignore[misc]
    assert isinstance(boleta.lineas, tuple)


def test_jerarquia_de_excepciones() -> None:
    assert issubclass(PermisoBoletaException, BoletaException)
    assert issubclass(BoletaIncompletaException, BoletaException)
