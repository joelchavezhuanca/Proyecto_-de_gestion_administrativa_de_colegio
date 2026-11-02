from datetime import date, time

import pytest

try:
    from src.dominio.aforo import (
        PermisoAforoException,
        ServicioAforo,
    )
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
        CategoriaJustificacion,
        EstadoJustificacion,
        EstadoNoJustificableException,
        FechaInvalidaException,
        Justificacion,
        JustificacionException,
        PeriodoAcademico,
        PeriodoAcademicoCerradoException,
        PermisoJustificacionException,
        ServicioJustificaciones,
    )
except ImportError:
    from aforo_dominio import (  # type: ignore
        PermisoAforoException,
        ServicioAforo,
    )
    from asistencia_dominio import (  # type: ignore
        Alumno,
        EstadoAlumno,
        EstadoAsistencia,
        MetodoRegistro,
        RegistroAsistencia,
        RolUsuario,
        UsuarioOperador,
    )
    from justificaciones_dominio import (  # type: ignore
        CategoriaJustificacion,
        EstadoJustificacion,
        EstadoNoJustificableException,
        FechaInvalidaException,
        Justificacion,
        JustificacionException,
        PeriodoAcademico,
        PeriodoAcademicoCerradoException,
        PermisoJustificacionException,
        ServicioJustificaciones,
    )


@pytest.fixture
def admin_op() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_general", rol=RolUsuario.ADMIN)


@pytest.fixture
def coord_op() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="coord_secundaria", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def staff_op() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="staff_asistencia", rol=RolUsuario.ADMIN_STAFF)


@pytest.fixture
def alumnos_muestra() -> list[Alumno]:
    return [
        Alumno(
            id=101,
            codigo="SEC-5A-01",
            dni="10000001",
            nombres="Eduardo",
            apellidos="Luna",
            nivel="Secundaria",
            grado="5to",
            seccion="A",
            carnet_codigo="CRN-01",
        ),
        Alumno(
            id=102,
            codigo="SEC-5A-02",
            dni="10000002",
            nombres="Yhovana",
            apellidos="Quispe",
            nivel="Secundaria",
            grado="5to",
            seccion="A",
            carnet_codigo="CRN-02",
        ),
        Alumno(
            id=103,
            codigo="SEC-5B-01",
            dni="10000003",
            nombres="Dudú",
            apellidos="Fabiano",
            nivel="Secundaria",
            grado="5to",
            seccion="B",
            carnet_codigo="CRN-03",
        ),
        Alumno(
            id=104,
            codigo="PRI-1A-01",
            dni="10000004",
            nombres="Jacob",
            apellidos="Luna",
            nivel="Primaria",
            grado="1ro",
            seccion="A",
            carnet_codigo="CRN-04",
        ),
        Alumno(
            id=105,
            codigo="PRI-1A-02",
            dni="10000005",
            nombres="Gari",
            apellidos="Chávez",
            nivel="Primaria",
            grado="1ro",
            seccion="A",
            carnet_codigo="CRN-05",
        ),
    ]


@pytest.fixture
def periodo_activo() -> PeriodoAcademico:
    return PeriodoAcademico(
        id=1,
        nombre="Bimestre I - 2026",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 12, 20),
        cerrado=False,
    )


# --- PRUEBAS PBI-03: DASHBOARD DE AFORO ---


def test_aforo_consulta_permitida_roles_oficiales(
    admin_op: UsuarioOperador, coord_op: UsuarioOperador, staff_op: UsuarioOperador
) -> None:
    """Verifica que ADMIN, COORDINADOR y ADMIN_STAFF puedan acceder al dashboard."""
    for op in [admin_op, coord_op, staff_op]:
        ServicioAforo.validar_acceso_consulta(op)


def test_aforo_consulta_denegada_rol_invalido_o_inactivo(staff_op: UsuarioOperador) -> None:
    """Rechazar consulta de usuarios con rol no autorizado o cuenta inactiva."""
    op_inactivo = UsuarioOperador(
        id=9, username="inactivo", rol=RolUsuario.ADMIN, activo=False
    )
    with pytest.raises(PermisoAforoException, match="no tiene una cuenta activa"):
        ServicioAforo.validar_acceso_consulta(op_inactivo)

    op_portero = UsuarioOperador(
        id=10, username="portero", rol="PORTERIA", activo=True  # type: ignore
    )
    with pytest.raises(PermisoAforoException, match="no está autorizado"):
        ServicioAforo.validar_acceso_consulta(op_portero)


def test_aforo_configurar_hora_cierre_exclusivo_admin(
    admin_op: UsuarioOperador, coord_op: UsuarioOperador, staff_op: UsuarioOperador
) -> None:
    """RN-17: Configuración de hora de cierre permitida solo para ADMIN."""
    nueva_hora = time(8, 45, 0)
    hora_config = ServicioAforo.configurar_hora_cierre(admin_op, nueva_hora)
    assert hora_config == nueva_hora

    for no_admin in [coord_op, staff_op]:
        with pytest.raises(PermisoAforoException, match="Únicamente el rol ADMIN"):
            ServicioAforo.configurar_hora_cierre(no_admin, nueva_hora)

    admin_inactivo = UsuarioOperador(
        id=1, username="admin_inac", rol=RolUsuario.ADMIN, activo=False
    )
    with pytest.raises(PermisoAforoException, match="no tiene una cuenta activa"):
        ServicioAforo.configurar_hora_cierre(admin_inactivo, nueva_hora)


def test_aforo_calculo_metricas_completo(
    staff_op: UsuarioOperador, alumnos_muestra: list[Alumno]
) -> None:
    """Calcula indicadores globales y desglose por salón (Nivel-Grado-Sección)."""
    fecha = date(2026, 11, 2)
    alumno_inactivo = Alumno(
        id=999,
        codigo="INACTIVO",
        dni="99999999",
        nombres="Inac",
        apellidos="Tivo",
        nivel="Secundaria",
        grado="5to",
        seccion="A",
        carnet_codigo="CRN-INAC",
        estado=EstadoAlumno.INACTIVO,
    )
    alumnos_totales = [*alumnos_muestra, alumno_inactivo]

    asistencias = [
        RegistroAsistencia(
            id="ast-1",
            alumno_id=101,
            fecha_escolar=fecha,
            hora_efectiva=time(7, 10, 0),
            estado=EstadoAsistencia.PUNTUAL,
            minutos_tardanza=0,
            metodo=MetodoRegistro.CARNET,
            usuario_id=staff_op.id,
            rol_usuario=staff_op.rol,
        ),
        RegistroAsistencia(
            id="ast-2",
            alumno_id=102,
            fecha_escolar=fecha,
            hora_efectiva=time(7, 25, 0),
            estado=EstadoAsistencia.TARDANZA,
            minutos_tardanza=10,
            metodo=MetodoRegistro.MANUAL_DNI,
            usuario_id=staff_op.id,
            rol_usuario=staff_op.rol,
        ),
        RegistroAsistencia(
            id="ast-3",
            alumno_id=103,
            fecha_escolar=fecha,
            hora_efectiva=time(8, 0, 0),
            estado=EstadoAsistencia.PENDIENTE,
            minutos_tardanza=0,
            metodo=MetodoRegistro.MANUAL_BUSQUEDA,
            usuario_id=staff_op.id,
            rol_usuario=staff_op.rol,
        ),
        RegistroAsistencia(
            id="ast-4",
            alumno_id=104,
            fecha_escolar=fecha,
            hora_efectiva=time(8, 0, 0),
            estado=EstadoAsistencia.JUSTIFICADO,
            minutos_tardanza=0,
            metodo=MetodoRegistro.MANUAL_BUSQUEDA,
            usuario_id=staff_op.id,
            rol_usuario=staff_op.rol,
        ),
        # Alumno 105 queda sin registro (ast is None) antes de hora de cierre
    ]

    metricas = ServicioAforo.calcular_metricas(
        operador=staff_op,
        alumnos=alumnos_totales,
        asistencias_dia=asistencias,
        fecha_escolar=fecha,
        hora_consulta=time(8, 0, 0),
        hora_cierre=time(9, 0, 0),
    )

    assert metricas.total_matriculados == 5
    assert metricas.presentes == 1
    assert metricas.tardanzas == 1
    assert metricas.justificados == 1
    assert metricas.pendientes == 2  # 103 (PENDIENTE) + 105 (None)
    assert metricas.ausentes == 0
    assert metricas.aforo_actual_plantel == 2


def test_aforo_calculo_despues_de_hora_cierre_marca_ausentes(
    coord_op: UsuarioOperador, alumnos_muestra: list[Alumno]
) -> None:
    """Consulta posterior a la hora de cierre contabiliza los sin registro como ausentes."""
    fecha = date(2026, 11, 2)
    ast_pendiente = RegistroAsistencia(
        id="ast-pnd",
        alumno_id=101,
        fecha_escolar=fecha,
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.PENDIENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=coord_op.id,
        rol_usuario=coord_op.rol,
    )
    ast_ausente = RegistroAsistencia(
        id="ast-aus",
        alumno_id=102,
        fecha_escolar=fecha,
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=coord_op.id,
        rol_usuario=coord_op.rol,
    )
    metricas = ServicioAforo.calcular_metricas(
        operador=coord_op,
        alumnos=alumnos_muestra,
        asistencias_dia=[ast_pendiente, ast_ausente],
        fecha_escolar=fecha,
        hora_consulta=time(9, 30, 0),
        hora_cierre=time(9, 0, 0),
    )
    assert metricas.total_matriculados == 5
    assert metricas.presentes == 0
    assert metricas.ausentes == 5
    assert metricas.pendientes == 0


def test_aforo_sin_alumnos_matriculados(admin_op: UsuarioOperador) -> None:
    """Verifica que el cálculo con lista vacía de alumnos retorne porcentaje 0.0."""
    metricas = ServicioAforo.calcular_metricas(
        operador=admin_op,
        alumnos=[],
        asistencias_dia=[],
        fecha_escolar=date(2026, 11, 2),
        hora_consulta=time(8, 0, 0),
    )
    assert metricas.total_matriculados == 0
    assert metricas.porcentaje_asistencia == 0.0
    assert len(metricas.desglose_salones) == 0


def test_aforo_ejecutar_cierre_automatico(
    admin_op: UsuarioOperador, alumnos_muestra: list[Alumno]
) -> None:
    """Cierre oficial crea asistencias AUSENTE para alumnos que quedaron sin registro."""
    fecha = date(2026, 11, 2)
    alumno_inactivo = Alumno(
        id=999,
        codigo="INAC",
        dni="99999999",
        nombres="Inactivo",
        apellidos="Test",
        nivel="Secundaria",
        grado="1ro",
        seccion="A",
        carnet_codigo="CRN-INAC",
        estado=EstadoAlumno.INACTIVO,
    )
    lista_alumnos = [*alumnos_muestra, alumno_inactivo]

    ast_existente = RegistroAsistencia(
        id="ast-puntual",
        alumno_id=101,
        fecha_escolar=fecha,
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=admin_op.id,
        rol_usuario=admin_op.rol,
    )

    nuevas, evento = ServicioAforo.ejecutar_cierre_automatico(
        operador_o_sistema=admin_op,
        alumnos=lista_alumnos,
        asistencias_existentes=[ast_existente],
        fecha_escolar=fecha,
        hora_cierre=time(9, 0, 0),
    )

    assert len(nuevas) == 4
    assert evento.total_ausentes_marcados == 4
    assert 101 not in evento.alumnos_ids_afectados
    assert 999 not in evento.alumnos_ids_afectados
    assert all(a.estado == EstadoAsistencia.AUSENTE for a in nuevas)


# --- PRUEBAS PBI-04: GESTIÓN DE JUSTIFICACIONES ---


def test_justificacion_registro_exitoso_ausente(
    staff_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    periodo_activo: PeriodoAcademico,
) -> None:
    """Registra y aprueba justificación para un estado AUSENTE."""
    alumno = alumnos_muestra[0]
    ast_ausente = RegistroAsistencia(
        id="ast-aus-01",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )

    res = ServicioJustificaciones.registrar_y_aprobar_justificacion(
        operador=staff_op,
        alumno=alumno,
        asistencia=ast_ausente,
        fecha_solicitud=date(2026, 11, 2),
        fecha_actual=date(2026, 11, 2),
        categoria=CategoriaJustificacion.MEDICA,
        motivo="Cita médica por gastroenteritis con certificado",
        periodo=periodo_activo,
        documento_adjunto="certificado_medico_001.pdf",
    )

    assert res.justificacion.estado == EstadoJustificacion.APROBADA
    assert res.justificacion.categoria == CategoriaJustificacion.MEDICA
    assert res.asistencia_actualizada.estado == EstadoAsistencia.JUSTIFICADO
    assert res.asistencia_actualizada.estado_anterior == EstadoAsistencia.AUSENTE
    assert res.asistencia_actualizada.minutos_tardanza == 0


def test_justificacion_registro_exitoso_tardanza(
    admin_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    periodo_activo: PeriodoAcademico,
) -> None:
    """Registra justificación para un alumno en TARDANZA."""
    alumno = alumnos_muestra[1]
    ast_tardanza = RegistroAsistencia(
        id="ast-tar-01",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 30, 0),
        estado=EstadoAsistencia.TARDANZA,
        minutos_tardanza=15,
        metodo=MetodoRegistro.CARNET,
        usuario_id=admin_op.id,
        rol_usuario=admin_op.rol,
    )

    res = ServicioJustificaciones.registrar_y_aprobar_justificacion(
        operador=admin_op,
        alumno=alumno,
        asistencia=ast_tardanza,
        fecha_solicitud=date(2026, 11, 2),
        fecha_actual=date(2026, 11, 2),
        categoria=CategoriaJustificacion.PERMISO_FAMILIAR,
        motivo="Trámite legal documentado con apoderado",
        periodo=periodo_activo,
    )

    assert res.asistencia_actualizada.estado == EstadoAsistencia.JUSTIFICADO
    assert res.asistencia_actualizada.estado_anterior == EstadoAsistencia.TARDANZA


def test_justificacion_anulacion_restaura_estado_anterior(
    staff_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    periodo_activo: PeriodoAcademico,
) -> None:
    """Al anular una justificación previa, restaura la asistencia a AUSENTE o TARDANZA."""
    alumno = alumnos_muestra[0]
    ast_ausente = RegistroAsistencia(
        id="ast-aus-02",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )

    res = ServicioJustificaciones.registrar_y_aprobar_justificacion(
        operador=staff_op,
        alumno=alumno,
        asistencia=ast_ausente,
        fecha_solicitud=date(2026, 11, 2),
        fecha_actual=date(2026, 11, 2),
        categoria=CategoriaJustificacion.OTRA,
        motivo="Problema vial justificado",
        periodo=periodo_activo,
    )

    # Anulación
    restaurada = ServicioJustificaciones.anular_justificacion(
        operador=staff_op,
        justificacion=res.justificacion,
        asistencia=res.asistencia_actualizada,
    )

    assert restaurada.estado == EstadoAsistencia.AUSENTE
    assert restaurada.estado_anterior == EstadoAsistencia.JUSTIFICADO


def test_justificacion_anulacion_sin_estado_anterior_usa_ausente(
    staff_op: UsuarioOperador,
) -> None:
    """Al anular cuando estado_anterior es None, asume AUSENTE por defecto."""
    ast_sin_anterior = RegistroAsistencia(
        id="ast-sin-ant",
        alumno_id=101,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.JUSTIFICADO,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
        estado_anterior=None,
    )
    just = Justificacion(
        id="j1",
        asistencia_id="ast-sin-ant",
        alumno_id=101,
        fecha_solicitud=date(2026, 11, 2),
        categoria=CategoriaJustificacion.OTRA,
        motivo="test",
        estado=EstadoJustificacion.APROBADA,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )
    restaurada = ServicioJustificaciones.anular_justificacion(
        operador=staff_op,
        justificacion=just,
        asistencia=ast_sin_anterior,
    )
    assert restaurada.estado == EstadoAsistencia.AUSENTE


def test_justificacion_denegada_coordinador_u_operador_inactivo(
    coord_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    periodo_activo: PeriodoAcademico,
) -> None:
    """COORDINADOR no tiene permiso de gestión de justificaciones en esta versión."""
    ast = RegistroAsistencia(
        id="ast-test",
        alumno_id=101,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=coord_op.id,
        rol_usuario=coord_op.rol,
    )
    with pytest.raises(PermisoJustificacionException, match="no está autorizado"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=coord_op,
            alumno=alumnos_muestra[0],
            asistencia=ast,
            fecha_solicitud=date(2026, 11, 2),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Prueba",
            periodo=periodo_activo,
        )

    op_inactivo = UsuarioOperador(
        id=99, username="staff_inac", rol=RolUsuario.ADMIN_STAFF, activo=False
    )
    with pytest.raises(PermisoJustificacionException, match="no cuenta con una cuenta activa"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=op_inactivo,
            alumno=alumnos_muestra[0],
            asistencia=ast,
            fecha_solicitud=date(2026, 11, 2),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Prueba",
            periodo=periodo_activo,
        )


def test_justificacion_errores_de_negocio(
    staff_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    periodo_activo: PeriodoAcademico,
) -> None:
    """Verifica rechazo de fechas futuras, períodos cerrados, estado PUNTUAL y motivo vacío."""
    alumno = alumnos_muestra[0]
    ast = RegistroAsistencia(
        id="ast-err",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 5, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )

    # 1. Error alumno inactivo
    alumno_inactivo = Alumno(
        id=999,
        codigo="INAC",
        dni="99999999",
        nombres="Inac",
        apellidos="Tivo",
        nivel="Secundaria",
        grado="1ro",
        seccion="A",
        carnet_codigo="CRN-999",
        estado=EstadoAlumno.INACTIVO,
    )
    with pytest.raises(JustificacionException, match="no se encuentra ACTIVO"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=staff_op,
            alumno=alumno_inactivo,
            asistencia=ast,
            fecha_solicitud=date(2026, 11, 2),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Test",
            periodo=periodo_activo,
        )

    # 2. Fecha futura
    ast_aus = RegistroAsistencia(
        id="ast-aus-fut",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 5),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )
    with pytest.raises(FechaInvalidaException, match="fecha futura"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=staff_op,
            alumno=alumno,
            asistencia=ast_aus,
            fecha_solicitud=date(2026, 11, 10),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Test",
            periodo=periodo_activo,
        )

    # 3. Período cerrado
    periodo_cerrado = PeriodoAcademico(
        id=2,
        nombre="Bimestre Pasado",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 2, 28),
        cerrado=True,
    )
    with pytest.raises(PeriodoAcademicoCerradoException, match="se encuentra cerrado"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=staff_op,
            alumno=alumno,
            asistencia=ast_aus,
            fecha_solicitud=date(2026, 1, 15),
            fecha_actual=date(2026, 1, 15),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Test",
            periodo=periodo_cerrado,
        )

    # 4. Asistencia con fecha fuera de rango del período
    ast_fuera_de_periodo = RegistroAsistencia(
        id="ast-fuera",
        alumno_id=alumno.id,
        fecha_escolar=date(2025, 5, 10),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )
    with pytest.raises(JustificacionException, match="está fuera del período"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=staff_op,
            alumno=alumno,
            asistencia=ast_fuera_de_periodo,
            fecha_solicitud=date(2026, 11, 2),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Test",
            periodo=periodo_activo,
        )

    # 5. Estado PUNTUAL no es justificable
    ast_puntual_valida = RegistroAsistencia(
        id="ast-punt",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 5, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )
    with pytest.raises(EstadoNoJustificableException, match="No es posible justificar"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=staff_op,
            alumno=alumno,
            asistencia=ast_puntual_valida,
            fecha_solicitud=date(2026, 11, 2),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Test",
            periodo=periodo_activo,
        )

    # 6. Motivo vacío
    ast_aus_valida = RegistroAsistencia(
        id="ast-aus-mot",
        alumno_id=alumno.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )
    with pytest.raises(JustificacionException, match="motivo de la justificación es obligatorio"):
        ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=staff_op,
            alumno=alumno,
            asistencia=ast_aus_valida,
            fecha_solicitud=date(2026, 11, 2),
            fecha_actual=date(2026, 11, 2),
            categoria=CategoriaJustificacion.MEDICA,
            motivo="",
            periodo=periodo_activo,
        )

    # 7. Error anulación sobre asistencia no JUSTIFICADO
    with pytest.raises(JustificacionException, match="no se encuentra en estado JUSTIFICADO"):
        ServicioJustificaciones.anular_justificacion(
            operador=staff_op,
            justificacion=Justificacion(
                id="j1",
                asistencia_id="ast-aus-mot",
                alumno_id=alumno.id,
                fecha_solicitud=date(2026, 11, 2),
                categoria=CategoriaJustificacion.OTRA,
                motivo="test",
                estado=EstadoJustificacion.APROBADA,
                usuario_id=staff_op.id,
                rol_usuario=staff_op.rol,
            ),
            asistencia=ast_aus_valida,
        )
