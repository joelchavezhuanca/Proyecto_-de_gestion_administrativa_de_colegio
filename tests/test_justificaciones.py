"""Pruebas BDD/unitarias del PBI-04: justificaciones y períodos académicos."""

from dataclasses import replace
from datetime import date, datetime, time

import pytest

from src.dominio.asistencia import (
    Alumno,
    EstadoAlumno,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
)
from src.dominio.justificaciones import (
    AdjuntoInvalidoException,
    AdjuntoJustificacion,
    CategoriaJustificacion,
    EstadoJustificacion,
    FechaInvalidaException,
    FiltroJustificaciones,
    Justificacion,
    JustificacionException,
    PeriodoAcademico,
    PeriodoAcademicoCerradoException,
    PeriodoConUsoException,
    PeriodoInvalidoException,
    PeriodoSolapadoException,
    PermisoJustificacionException,
    ResultadoOperacionJustificacion,
    ServicioJustificaciones,
    ServicioPeriodosAcademicos,
    TipoPeriodo,
)
from src.dominio.usuarios import PermisoOperacion, Rol

FECHA_SOLICITUD = date(2026, 11, 2)
FECHA_ACTUAL = date(2026, 11, 2)


@pytest.fixture
def admin_op() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_just", rol=RolUsuario.ADMIN)


@pytest.fixture
def coord_op() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="coord_just", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def staff_op() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="staff_just", rol=RolUsuario.ADMIN_STAFF)


@pytest.fixture
def alumno() -> Alumno:
    return Alumno(
        id=101,
        codigo="SEC-3A-01",
        dni="10000001",
        nombres="Ana",
        apellidos="Pérez",
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        carnet_codigo="CRN-01",
    )


@pytest.fixture
def alumno_primaria() -> Alumno:
    return Alumno(
        id=102,
        codigo="PRI-1B-01",
        dni="10000002",
        nombres="Luis",
        apellidos="Rojas",
        nivel="Primaria",
        grado="1ro",
        seccion="B",
        carnet_codigo="CRN-02",
    )


@pytest.fixture
def periodo() -> PeriodoAcademico:
    return PeriodoAcademico(
        id=1,
        nombre="Bimestre I - 2026",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 12, 20),
        anio_lectivo=2026,
        tipo_periodo=TipoPeriodo.BIMESTRE,
        orden=1,
        fecha_limite_notas=date(2026, 6, 30),
    )


@pytest.fixture
def asistencia_ausente(alumno: Alumno, staff_op: UsuarioOperador) -> RegistroAsistencia:
    return RegistroAsistencia(
        id="ast-aus-001",
        alumno_id=alumno.id,
        fecha_escolar=FECHA_SOLICITUD,
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )


@pytest.fixture
def asistencia_tardanza(alumno: Alumno, staff_op: UsuarioOperador) -> RegistroAsistencia:
    return RegistroAsistencia(
        id="ast-tar-001",
        alumno_id=alumno.id,
        fecha_escolar=FECHA_SOLICITUD,
        hora_efectiva=time(7, 30, 0),
        estado=EstadoAsistencia.TARDANZA,
        minutos_tardanza=12,
        metodo=MetodoRegistro.CARNET,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )


def _registrar(
    operador: UsuarioOperador,
    alumno: Alumno | None,
    asistencia: RegistroAsistencia,
    periodo: PeriodoAcademico,
    **cambios: object,
) -> ResultadoOperacionJustificacion:
    datos = {
        "operador": operador,
        "alumno": alumno,
        "asistencia": asistencia,
        "fecha_solicitud": FECHA_SOLICITUD,
        "fecha_actual": FECHA_ACTUAL,
        "categoria": CategoriaJustificacion.MEDICA,
        "motivo": "Justificación válida con sustento",
        "periodo": periodo,
    }
    datos.update(cambios)
    return ServicioJustificaciones.registrar_y_aprobar_justificacion(**datos)


def _justificacion_compat(**cambios: object) -> Justificacion:
    datos = {
        "id": "just-compat",
        "asistencia_id": "ast-compat",
        "alumno_id": 101,
        "fecha_solicitud": FECHA_SOLICITUD,
        "categoria": CategoriaJustificacion.OTRA,
        "motivo": "Compatibilidad",
        "estado": EstadoJustificacion.APROBADA,
        "usuario_id": 1,
        "rol_usuario": RolUsuario.ADMIN,
    }
    datos.update(cambios)
    return Justificacion(**datos)


# ----------------------------------------------------------------------
# Registro y anulación
# ----------------------------------------------------------------------
def test_coordinador_registra_y_aprueba_justificacion(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)

    assert resultado.asistencia_actualizada.estado == EstadoAsistencia.JUSTIFICADO
    assert resultado.asistencia_actualizada.estado_anterior == EstadoAsistencia.AUSENTE
    assert resultado.justificacion.estado == EstadoJustificacion.APROBADA
    assert resultado.justificacion.nivel == "Secundaria"
    assert resultado.justificacion.grado == "3ro"
    assert resultado.justificacion.seccion == "A"


def test_anulacion_de_tardanza_restaura_minutos_originales(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_tardanza: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_tardanza, periodo)

    assert resultado.justificacion.minutos_tardanza_original == 12
    assert resultado.asistencia_actualizada.minutos_tardanza == 0

    restaurada = ServicioJustificaciones.anular_justificacion(
        operador=coord_op,
        justificacion=resultado.justificacion,
        asistencia=resultado.asistencia_actualizada,
        periodo=periodo,
    )

    assert restaurada.estado == EstadoAsistencia.TARDANZA
    assert restaurada.minutos_tardanza == 12


def test_rechaza_alumno_inexistente_o_inactivo(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    with pytest.raises(JustificacionException, match="no existe"):
        _registrar(coord_op, None, asistencia_ausente, periodo)

    inactivo = replace(alumno, estado=EstadoAlumno.INACTIVO)
    with pytest.raises(JustificacionException, match="ACTIVO"):
        _registrar(coord_op, inactivo, asistencia_ausente, periodo)


# ----------------------------------------------------------------------
# Adjuntos
# ----------------------------------------------------------------------
def test_adjunto_valido_se_conserva_en_la_justificacion(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    adjunto = AdjuntoJustificacion("certificado_medico.pdf", 1024)

    resultado = _registrar(
        coord_op,
        alumno,
        asistencia_ausente,
        periodo,
        adjuntos=[adjunto],
    )

    assert adjunto.extension == "pdf"
    assert resultado.justificacion.adjuntos == (adjunto,)


@pytest.mark.parametrize(
    ("nombre", "tamano"),
    [
        ("malware.exe", 100),
        ("foto.jpg", 5_242_881),
        ("sin_extension", 100),
        ("documento.pdf", 0),
    ],
)
def test_adjunto_invalido_es_rechazado(nombre: str, tamano: int) -> None:
    with pytest.raises(AdjuntoInvalidoException):
        AdjuntoJustificacion(nombre, tamano)


def test_rechaza_mas_de_tres_adjuntos(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    adjuntos = [AdjuntoJustificacion(f"anexo_{indice}.pdf", 100) for indice in range(4)]

    with pytest.raises(AdjuntoInvalidoException, match="3"):
        _registrar(
            coord_op,
            alumno,
            asistencia_ausente,
            periodo,
            adjuntos=adjuntos,
        )


# ----------------------------------------------------------------------
# Modificación
# ----------------------------------------------------------------------
def test_modificar_conserva_adjuntos_previos_y_agrega_nuevos(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    adjunto_previo = AdjuntoJustificacion("certificado.pdf", 1024)
    resultado = _registrar(
        coord_op,
        alumno,
        asistencia_ausente,
        periodo,
        adjuntos=[adjunto_previo],
    )
    adjunto_nuevo = AdjuntoJustificacion("radiografia.jpg", 2048)

    modificada = ServicioJustificaciones.modificar_justificacion(
        operador=coord_op,
        justificacion=resultado.justificacion,
        asistencia=resultado.asistencia_actualizada,
        periodo=periodo,
        categoria=CategoriaJustificacion.PERMISO_FAMILIAR,
        motivo="Permiso familiar actualizado",
        nuevos_adjuntos=[adjunto_nuevo],
        fecha_hora=datetime(2026, 11, 2, 10, 0, 0),
    )

    assert modificada.justificacion.adjuntos == (adjunto_previo, adjunto_nuevo)
    assert modificada.justificacion.categoria == CategoriaJustificacion.PERMISO_FAMILIAR
    assert modificada.justificacion.motivo == "Permiso familiar actualizado"


def test_modificar_rechaza_superar_el_maximo_de_adjuntos(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    adjuntos = [AdjuntoJustificacion(f"anexo_{indice}.pdf", 100) for indice in range(3)]
    resultado = _registrar(
        coord_op,
        alumno,
        asistencia_ausente,
        periodo,
        adjuntos=adjuntos,
    )

    with pytest.raises(AdjuntoInvalidoException, match="3"):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo,
            nuevos_adjuntos=[AdjuntoJustificacion("extra.pdf", 100)],
        )


def test_periodo_cerrado_bloquea_creacion_modificacion_y_anulacion(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    periodo_cerrado = replace(periodo, cerrado=True)

    with pytest.raises(PeriodoAcademicoCerradoException):
        _registrar(coord_op, alumno, asistencia_ausente, periodo_cerrado)

    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)

    with pytest.raises(PeriodoAcademicoCerradoException):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo_cerrado,
            motivo="No debe permitirse",
        )

    with pytest.raises(PeriodoAcademicoCerradoException):
        ServicioJustificaciones.anular_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo_cerrado,
        )


# ----------------------------------------------------------------------
# Servicio de períodos académicos
# ----------------------------------------------------------------------
def test_admin_crea_periodo_con_fecha_limite_notas(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    creado = ServicioPeriodosAcademicos.crear_periodo(admin_op, periodo, [])

    assert creado == periodo
    assert creado.fecha_limite_notas == date(2026, 6, 30)


def test_administrar_periodos_requiere_permiso_exclusivo(
    coord_op: UsuarioOperador, staff_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    for operador in (coord_op, staff_op):
        with pytest.raises(PermisoJustificacionException):
            ServicioPeriodosAcademicos.crear_periodo(operador, periodo, [])


def test_rol_personalizado_con_permiso_puede_administrar_periodos(
    periodo: PeriodoAcademico,
) -> None:
    rol = Rol(
        codigo="GESTOR_PERIODOS",
        nombre="Gestor de períodos",
        descripcion="Rol con permiso para administrar períodos",
        permisos=frozenset({PermisoOperacion.ADMINISTRAR_PERIODOS}),
    )
    operador = UsuarioOperador(
        id=50,
        username="gestor_periodos",
        rol="GESTOR_PERIODOS",  # type: ignore[arg-type]
    )

    creado = ServicioPeriodosAcademicos.crear_periodo(
        operador,
        periodo,
        [],
        roles=[rol],
    )

    assert creado == periodo


def test_rechaza_periodos_solapados(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    solapado = replace(
        periodo,
        id=2,
        nombre="Bimestre II - 2026",
        fecha_inicio=date(2026, 6, 1),
        fecha_fin=date(2026, 7, 31),
        fecha_limite_notas=date(2026, 7, 15),
    )

    with pytest.raises(PeriodoSolapadoException):
        ServicioPeriodosAcademicos.crear_periodo(admin_op, solapado, [periodo])


def test_rechaza_nombre_de_periodo_duplicado(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    duplicado = replace(
        periodo,
        id=2,
        fecha_inicio=date(2027, 1, 1),
        fecha_fin=date(2027, 2, 28),
        fecha_limite_notas=date(2027, 2, 15),
    )

    with pytest.raises(PeriodoInvalidoException):
        ServicioPeriodosAcademicos.crear_periodo(admin_op, duplicado, [periodo])


def test_modificar_cerrar_y_reabrir_periodo(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    modificado = ServicioPeriodosAcademicos.modificar_periodo(
        admin_op,
        periodo,
        [periodo],
        nombre="Bimestre I Actualizado",
    )

    assert modificado.nombre == "Bimestre I Actualizado"

    cerrado = ServicioPeriodosAcademicos.cambiar_estado_periodo(
        admin_op,
        modificado,
        cerrado=True,
    )
    assert cerrado.cerrado is True

    reabierto = ServicioPeriodosAcademicos.cambiar_estado_periodo(
        admin_op,
        cerrado,
        cerrado=False,
    )
    assert reabierto.cerrado is False


def test_eliminar_periodo_sin_uso(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    restantes = ServicioPeriodosAcademicos.eliminar_periodo(
        admin_op,
        periodo,
        [periodo],
        justificaciones=[],
    )

    assert restantes == []


def test_no_elimina_periodo_con_justificaciones(
    admin_op: UsuarioOperador,
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)

    with pytest.raises(PeriodoConUsoException, match="justificaciones"):
        ServicioPeriodosAcademicos.eliminar_periodo(
            admin_op,
            periodo,
            [periodo],
            justificaciones=[resultado.justificacion],
        )


def test_no_elimina_periodo_con_calificaciones(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    with pytest.raises(PeriodoConUsoException, match="calificaciones"):
        ServicioPeriodosAcademicos.eliminar_periodo(
            admin_op,
            periodo,
            [periodo],
            justificaciones=[],
            tiene_calificaciones=True,
        )


# ----------------------------------------------------------------------
# Consulta filtrada del historial
# ----------------------------------------------------------------------
def test_consultar_justificaciones_filtra_por_contexto_y_criterios(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    alumno_primaria: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    asistencia_primaria = replace(
        asistencia_ausente,
        id="ast-aus-002",
        alumno_id=alumno_primaria.id,
        fecha_escolar=date(2026, 11, 3),
    )
    primera = _registrar(coord_op, alumno, asistencia_ausente, periodo).justificacion
    segunda = _registrar(
        coord_op,
        alumno_primaria,
        asistencia_primaria,
        periodo,
        fecha_solicitud=date(2026, 11, 3),
        fecha_actual=date(2026, 11, 3),
    ).justificacion

    por_contexto = ServicioJustificaciones.consultar_justificaciones(
        [primera, segunda],
        FiltroJustificaciones(nivel="Secundaria", grado="3ro", seccion="A"),
        operador=coord_op,
    )
    por_alumno = ServicioJustificaciones.consultar_justificaciones(
        [primera, segunda],
        FiltroJustificaciones(alumno_id=alumno_primaria.id),
        operador=coord_op,
    )
    por_categoria = ServicioJustificaciones.consultar_justificaciones(
        [primera, segunda],
        FiltroJustificaciones(categoria=CategoriaJustificacion.MEDICA),
        operador=coord_op,
    )
    por_estado = ServicioJustificaciones.consultar_justificaciones(
        [primera, segunda],
        FiltroJustificaciones(estado=EstadoJustificacion.APROBADA),
        operador=coord_op,
    )
    por_fechas = ServicioJustificaciones.consultar_justificaciones(
        [primera, segunda],
        FiltroJustificaciones(
            fecha_desde=date(2026, 11, 3),
            fecha_hasta=date(2026, 11, 3),
        ),
        operador=coord_op,
    )

    assert [justificacion.id for justificacion in por_contexto] == [primera.id]
    assert [justificacion.id for justificacion in por_alumno] == [segunda.id]
    assert len(por_categoria) == 2
    assert len(por_estado) == 2
    assert [justificacion.id for justificacion in por_fechas] == [segunda.id]


def test_consultar_justificaciones_requiere_operador_activo(
    coord_op: UsuarioOperador,
) -> None:
    inactivo = replace(coord_op, activo=False)

    with pytest.raises(PermisoJustificacionException, match="cuenta activa"):
        ServicioJustificaciones.consultar_justificaciones(
            [],
            operador=inactivo,
        )


def test_rol_personalizado_con_permiso_puede_gestionar_justificaciones(
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    rol = Rol(
        codigo="AUX_JUSTIFICACIONES",
        nombre="Auxiliar de justificaciones",
        descripcion="Rol con permiso para gestionar justificaciones",
        permisos=frozenset({PermisoOperacion.GESTIONAR_JUSTIFICACIONES}),
    )
    operador = UsuarioOperador(
        id=60,
        username="aux_justificaciones",
        rol="AUX_JUSTIFICACIONES",  # type: ignore[arg-type]
    )

    resultado = _registrar(
        operador,
        alumno,
        asistencia_ausente,
        periodo,
        roles=[rol],
    )

    assert resultado.asistencia_actualizada.estado == EstadoAsistencia.JUSTIFICADO


# ----------------------------------------------------------------------
# Validaciones de período y compatibilidad
# ----------------------------------------------------------------------
def test_periodo_rechaza_fechas_invertidas_y_limite_fuera_de_rango() -> None:
    with pytest.raises(PeriodoInvalidoException):
        PeriodoAcademico(
            id=1,
            nombre="Periodo inválido",
            fecha_inicio=date(2026, 12, 1),
            fecha_fin=date(2026, 11, 1),
        )

    with pytest.raises(PeriodoInvalidoException):
        PeriodoAcademico(
            id=1,
            nombre="Periodo inválido",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 20),
            fecha_limite_notas=date(2027, 1, 10),
        )


def test_filtro_rechaza_rango_invertido() -> None:
    with pytest.raises(JustificacionException, match="rango"):
        FiltroJustificaciones(
            fecha_desde=date(2026, 11, 5),
            fecha_hasta=date(2026, 11, 1),
        )


def test_justificacion_mantiene_compatibilidad_con_campos_nuevos() -> None:
    justificacion = Justificacion(
        id="just-compat",
        asistencia_id="ast-compat",
        alumno_id=101,
        fecha_solicitud=FECHA_SOLICITUD,
        categoria=CategoriaJustificacion.OTRA,
        motivo="Compatibilidad",
        estado=EstadoJustificacion.APROBADA,
        usuario_id=1,
        rol_usuario=RolUsuario.ADMIN,
    )

    assert justificacion.adjuntos == ()
    assert justificacion.minutos_tardanza_original == 0
    assert justificacion.nivel == ""
    assert justificacion.grado == ""
    assert justificacion.seccion == ""


def test_fecha_futura_sigue_siendo_rechazada(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    with pytest.raises(FechaInvalidaException, match="fecha futura"):
        _registrar(
            coord_op,
            alumno,
            asistencia_ausente,
            periodo,
            fecha_solicitud=date(2026, 11, 10),
        )


# ----------------------------------------------------------------------
# Cobertura de validaciones defensivas (REFACTOR)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("nombre", "tamano"),
    [
        ("", 100),
        ("documento.pdf", "100"),
        ("documento.pdf", True),
    ],
)
def test_adjunto_rechaza_nombre_vacio_o_tamano_no_entero(
    nombre: str, tamano: object
) -> None:
    with pytest.raises(AdjuntoInvalidoException):
        AdjuntoJustificacion(nombre, tamano)  # type: ignore[arg-type]


def test_justificacion_rechaza_adjuntos_no_sequence_o_item_invalido() -> None:
    with pytest.raises(AdjuntoInvalidoException, match="colección"):
        _justificacion_compat(adjuntos="archivo.pdf")

    with pytest.raises(AdjuntoInvalidoException, match="AdjuntoJustificacion"):
        _justificacion_compat(adjuntos=(object(),))


def test_periodo_rechaza_nombre_vacio_anio_negativo_y_orden_invalido() -> None:
    with pytest.raises(PeriodoInvalidoException):
        PeriodoAcademico(
            id=1,
            nombre="",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 20),
        )

    with pytest.raises(PeriodoInvalidoException):
        PeriodoAcademico(
            id=1,
            nombre="Periodo",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 20),
            anio_lectivo=-1,
        )

    with pytest.raises(PeriodoInvalidoException):
        PeriodoAcademico(
            id=1,
            nombre="Periodo",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 20),
            orden=0,
        )


def test_periodo_convierte_tipo_y_rechaza_tipo_invalido() -> None:
    periodo = PeriodoAcademico(
        id=1,
        nombre="Trimestre I",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 7, 31),
        tipo_periodo="trimestre",  # type: ignore[arg-type]
    )
    assert periodo.tipo_periodo == TipoPeriodo.TRIMESTRE

    with pytest.raises(PeriodoInvalidoException):
        PeriodoAcademico(
            id=2,
            nombre="Periodo inválido",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 7, 31),
            tipo_periodo="ANUAL",  # type: ignore[arg-type]
        )


def test_justificacion_rechaza_minutos_negativos() -> None:
    with pytest.raises(JustificacionException):
        _justificacion_compat(minutos_tardanza_original=-1)


def test_justificacion_denegada_sin_permiso_personalizado(
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    rol = Rol(
        codigo="SOLO_LECTURA",
        nombre="Solo lectura",
        descripcion="Rol sin permiso para justificar",
        permisos=frozenset({PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA}),
    )
    operador = UsuarioOperador(
        id=70,
        username="lector",
        rol="SOLO_LECTURA",  # type: ignore[arg-type]
    )

    with pytest.raises(PermisoJustificacionException, match="no está autorizado"):
        _registrar(
            operador,
            alumno,
            asistencia_ausente,
            periodo,
            roles=[rol],
        )


def test_anular_rechaza_fecha_fuera_del_periodo(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)
    periodo_otro = replace(
        periodo,
        fecha_inicio=date(2027, 1, 1),
        fecha_fin=date(2027, 2, 28),
        fecha_limite_notas=date(2027, 2, 15),
    )

    with pytest.raises(JustificacionException, match="fuera del período"):
        ServicioJustificaciones.anular_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo_otro,
        )


def test_modificar_rechaza_fecha_fuera_del_periodo(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)
    periodo_otro = replace(
        periodo,
        fecha_inicio=date(2027, 1, 1),
        fecha_fin=date(2027, 2, 28),
        fecha_limite_notas=date(2027, 2, 15),
    )

    with pytest.raises(JustificacionException, match="fuera del período"):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo_otro,
        )


def test_modificar_rechaza_asistencia_no_justificada(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)
    asistencia_original = replace(
        resultado.asistencia_actualizada,
        estado=EstadoAsistencia.AUSENTE,
        estado_anterior=None,
    )

    with pytest.raises(JustificacionException, match="JUSTIFICADO"):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=asistencia_original,
            periodo=periodo,
        )


def test_modificar_rechaza_justificacion_no_aprobada(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)
    pendiente = replace(resultado.justificacion, estado=EstadoJustificacion.PENDIENTE)

    with pytest.raises(JustificacionException, match="aprobadas"):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=pendiente,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo,
        )


def test_modificar_acepta_categoria_como_texto_y_rechaza_invalida(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)

    modificada = ServicioJustificaciones.modificar_justificacion(
        operador=coord_op,
        justificacion=resultado.justificacion,
        asistencia=resultado.asistencia_actualizada,
        periodo=periodo,
        categoria="otra",  # type: ignore[arg-type]
    )
    assert modificada.justificacion.categoria == CategoriaJustificacion.OTRA

    with pytest.raises(JustificacionException, match="inválida"):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo,
            categoria="INVALIDA",  # type: ignore[arg-type]
        )


def test_modificar_rechaza_motivo_vacio(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    resultado = _registrar(coord_op, alumno, asistencia_ausente, periodo)

    with pytest.raises(JustificacionException, match="motivo"):
        ServicioJustificaciones.modificar_justificacion(
            operador=coord_op,
            justificacion=resultado.justificacion,
            asistencia=resultado.asistencia_actualizada,
            periodo=periodo,
            motivo="   ",
        )


def test_consultar_excluye_por_grado_seccion_categoria_estado_y_fecha_hasta(
    coord_op: UsuarioOperador,
    alumno: Alumno,
    asistencia_ausente: RegistroAsistencia,
    periodo: PeriodoAcademico,
) -> None:
    justificacion = _registrar(
        coord_op, alumno, asistencia_ausente, periodo
    ).justificacion
    criterios = [
        FiltroJustificaciones(grado="9no"),
        FiltroJustificaciones(seccion="Z"),
        FiltroJustificaciones(categoria=CategoriaJustificacion.OTRA),
        FiltroJustificaciones(estado=EstadoJustificacion.RECHAZADA),
        FiltroJustificaciones(fecha_hasta=date(2026, 1, 1)),
    ]

    for criterio in criterios:
        assert (
            ServicioJustificaciones.consultar_justificaciones(
                [justificacion],
                criterio,
                operador=coord_op,
            )
            == []
        )


def test_servicio_periodos_rechaza_operador_inactivo(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    inactivo = replace(admin_op, activo=False)

    with pytest.raises(PermisoJustificacionException, match="cuenta activa"):
        ServicioPeriodosAcademicos.crear_periodo(inactivo, periodo, [])


def test_servicio_periodos_rechaza_anio_cero_y_limite_notas_none(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    with pytest.raises(PeriodoInvalidoException, match="año lectivo"):
        ServicioPeriodosAcademicos.crear_periodo(
            admin_op,
            replace(periodo, anio_lectivo=0),
            [],
        )

    with pytest.raises(PeriodoInvalidoException, match="fecha límite"):
        ServicioPeriodosAcademicos.crear_periodo(
            admin_op,
            replace(periodo, fecha_limite_notas=None),
            [],
        )


def test_modificar_periodo_cambia_fechas_limite_y_estado(
    admin_op: UsuarioOperador, periodo: PeriodoAcademico
) -> None:
    modificado = ServicioPeriodosAcademicos.modificar_periodo(
        admin_op,
        periodo,
        [periodo],
        fecha_inicio=date(2026, 3, 2),
        fecha_fin=date(2026, 12, 19),
        fecha_limite_notas=date(2026, 7, 1),
        cerrado=True,
    )

    assert modificado.fecha_inicio == date(2026, 3, 2)
    assert modificado.fecha_fin == date(2026, 12, 19)
    assert modificado.fecha_limite_notas == date(2026, 7, 1)
    assert modificado.cerrado is True
