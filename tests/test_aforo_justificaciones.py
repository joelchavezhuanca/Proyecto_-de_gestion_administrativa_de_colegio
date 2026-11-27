from datetime import date, time

import pytest

try:
    from src.dominio.aforo import (
        ACTOR_SYSTEM_CRON,
        AforoException,
        CalendarioEscolar,
        CierreYaEjecutadoException,
        DetalleAsistenciaAlumno,
        DiaNoLectivoException,
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
    from src.dominio.usuarios import PermisoOperacion, Rol
except ImportError:
    from aforo_dominio import (  # type: ignore
        ACTOR_SYSTEM_CRON,
        AforoException,
        CalendarioEscolar,
        CierreYaEjecutadoException,
        DetalleAsistenciaAlumno,
        DiaNoLectivoException,
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
    from usuarios_dominio import PermisoOperacion, Rol  # type: ignore


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
    alumnos_por_id = {al.id: al for al in alumnos_muestra}
    for ausencia in nuevas:
        al = alumnos_por_id[ausencia.alumno_id]
        assert ausencia.nivel == al.nivel
        assert ausencia.grado == al.grado
        assert ausencia.seccion == al.seccion


# --- PRUEBAS PBI-03 CIERRE DE BRECHAS: CALENDARIO, RBAC DINÁMICO, FILTROS, DETALLE E HISTORIAL ---


def test_calendario_escolar_evalua_dias_lectivos_feriados_fines_de_semana_y_excepciones() -> None:
    """Valida reglas de CalendarioEscolar: excepciones > feriados > fines de semana > lectivos."""
    feriado = date(2026, 7, 28)  # Martes (Fiestas Patrias)
    sabado = date(2026, 11, 7)  # Sábado
    domingo_habilitado = date(2026, 11, 8)  # Domingo con excepción lectiva
    lunes_normal = date(2026, 11, 2)  # Lunes

    calendario = CalendarioEscolar(
        dias_no_lectivos=frozenset({feriado, domingo_habilitado}),
        excepciones_lectivas=frozenset({domingo_habilitado}),
        fines_de_semana_no_lectivos=True,
    )

    assert calendario.es_dia_lectivo(lunes_normal) is True
    assert calendario.es_dia_lectivo(feriado) is False
    assert calendario.es_dia_lectivo(sabado) is False
    assert calendario.es_dia_lectivo(domingo_habilitado) is True

    calendario_con_finde = CalendarioEscolar(fines_de_semana_no_lectivos=False)
    assert calendario_con_finde.es_dia_lectivo(sabado) is True


def test_aforo_roles_personalizados_consulta_y_configuracion(
    alumnos_muestra: list[Alumno],
) -> None:
    """Roles personalizados con permisos dinámicos acceden al dashboard y configuración."""
    rol_visor = Rol(
        codigo="SUPERVISOR_AFORO",
        nombre="Supervisor de Aforo",
        descripcion="Consulta el dashboard de aforo",
        permisos=frozenset({PermisoOperacion.CONSULTAR_DASHBOARD_AFORO}),
    )
    rol_config = Rol(
        codigo="GESTOR_HORARIOS",
        nombre="Gestor de Horarios",
        descripcion="Configura la hora oficial de cierre",
        permisos=frozenset({PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA}),
    )
    op_visor = UsuarioOperador(
        id=20, username="sup_aforo", rol="SUPERVISOR_AFORO"  # type: ignore[arg-type]
    )
    op_config = UsuarioOperador(
        id=21, username="gestor_cierre", rol="GESTOR_HORARIOS"  # type: ignore[arg-type]
    )

    metricas = ServicioAforo.calcular_metricas(
        operador=op_visor,
        alumnos=alumnos_muestra,
        asistencias_dia=[],
        fecha_escolar=date(2026, 11, 2),
        hora_consulta=time(8, 0, 0),
        roles=[rol_visor, rol_config],
    )
    assert metricas.total_matriculados == 5

    assert ServicioAforo.configurar_hora_cierre(
        op_config, time(8, 50, 0), roles=[rol_visor, rol_config]
    ) == time(8, 50, 0)

    with pytest.raises(PermisoAforoException, match="no está autorizado"):
        ServicioAforo.validar_acceso_consulta(op_config, roles=[rol_visor, rol_config])

    with pytest.raises(PermisoAforoException):
        ServicioAforo.configurar_hora_cierre(
            op_visor, time(8, 50, 0), roles=[rol_visor, rol_config]
        )


def test_aforo_cierre_automatico_acepta_system_cron_y_rol_personalizado(
    alumnos_muestra: list[Alumno],
) -> None:
    """SYSTEM_CRON y roles personalizados con EJECUTAR_CIERRE_ASISTENCIA ejecutan el cierre."""
    fecha = date(2026, 11, 2)  # Lunes
    ast_pendiente = RegistroAsistencia(
        id="ast-pend-101",
        alumno_id=101,
        fecha_escolar=fecha,
        hora_efectiva=time(7, 0, 0),
        estado=EstadoAsistencia.PENDIENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=1,
        rol_usuario=RolUsuario.ADMIN,
    )

    nuevas_cron, evento_cron = ServicioAforo.ejecutar_cierre_automatico(
        operador_o_sistema=ACTOR_SYSTEM_CRON,
        alumnos=alumnos_muestra,
        asistencias_existentes=[ast_pendiente],
        fecha_escolar=fecha,
        hora_cierre=time(9, 0, 0),
        calendario=CalendarioEscolar(),
    )
    assert len(nuevas_cron) == 5
    assert evento_cron.total_ausentes_marcados == 5
    assert all(a.usuario_id == 0 and a.rol_usuario == ACTOR_SYSTEM_CRON for a in nuevas_cron)
    assert any(a.id == "ast-pend-101" and a.estado == EstadoAsistencia.AUSENTE for a in nuevas_cron)

    rol_cierre = Rol(
        codigo="OPERADOR_CIERRE",
        nombre="Operador de Cierre",
        descripcion="Ejecuta el cierre diario",
        permisos=frozenset({PermisoOperacion.EJECUTAR_CIERRE_ASISTENCIA}),
    )
    op_cierre = UsuarioOperador(
        id=30, username="op_cierre", rol="OPERADOR_CIERRE"  # type: ignore[arg-type]
    )
    nuevas_custom, evento_custom = ServicioAforo.ejecutar_cierre_automatico(
        operador_o_sistema=op_cierre,
        alumnos=alumnos_muestra,
        asistencias_existentes=[],
        fecha_escolar=fecha,
        hora_cierre=time(9, 0, 0),
        roles=[rol_cierre],
    )
    assert len(nuevas_custom) == 5
    assert evento_custom.total_ausentes_marcados == 5


def test_aforo_cierre_automatico_rechaza_actores_sin_permiso_doble_cierre_y_no_lectivo(
    admin_op: UsuarioOperador,
    coord_op: UsuarioOperador,
    staff_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
) -> None:
    """Valida permisos, CierreYaEjecutadoException y DiaNoLectivoException en el cierre."""
    lunes = date(2026, 11, 2)
    sabado = date(2026, 11, 7)
    feriado = date(2026, 7, 28)

    for no_autorizado in [coord_op, staff_op]:
        with pytest.raises(PermisoAforoException, match="no está autorizado"):
            ServicioAforo.ejecutar_cierre_automatico(
                operador_o_sistema=no_autorizado,
                alumnos=alumnos_muestra,
                asistencias_existentes=[],
                fecha_escolar=lunes,
                hora_cierre=time(9, 0, 0),
            )

    op_inactivo = UsuarioOperador(
        id=1, username="admin_off", rol=RolUsuario.ADMIN, activo=False
    )
    with pytest.raises(PermisoAforoException, match="no tiene una cuenta activa"):
        ServicioAforo.ejecutar_cierre_automatico(
            operador_o_sistema=op_inactivo,
            alumnos=alumnos_muestra,
            asistencias_existentes=[],
            fecha_escolar=lunes,
            hora_cierre=time(9, 0, 0),
        )

    with pytest.raises(PermisoAforoException, match="no está autorizado"):
        ServicioAforo.ejecutar_cierre_automatico(
            operador_o_sistema="OTRO_PROCESO",
            alumnos=alumnos_muestra,
            asistencias_existentes=[],
            fecha_escolar=lunes,
            hora_cierre=time(9, 0, 0),
        )

    with pytest.raises(CierreYaEjecutadoException):
        ServicioAforo.ejecutar_cierre_automatico(
            operador_o_sistema=admin_op,
            alumnos=alumnos_muestra,
            asistencias_existentes=[],
            fecha_escolar=lunes,
            hora_cierre=time(9, 0, 0),
            fechas_ya_cerradas={lunes},
        )

    calendario = CalendarioEscolar(
        dias_no_lectivos=frozenset({feriado}),
        excepciones_lectivas=frozenset({sabado}),
    )
    with pytest.raises(DiaNoLectivoException):
        ServicioAforo.ejecutar_cierre_automatico(
            operador_o_sistema=ACTOR_SYSTEM_CRON,
            alumnos=alumnos_muestra,
            asistencias_existentes=[],
            fecha_escolar=feriado,
            hora_cierre=time(9, 0, 0),
            calendario=calendario,
        )

    # Sábado habilitado excepcionalmente sí permite cierre
    nuevas_excepcion, evento_excepcion = ServicioAforo.ejecutar_cierre_automatico(
        operador_o_sistema=ACTOR_SYSTEM_CRON,
        alumnos=alumnos_muestra,
        asistencias_existentes=[],
        fecha_escolar=sabado,
        hora_cierre=time(9, 0, 0),
        calendario=calendario,
    )
    assert len(nuevas_excepcion) == 5
    assert evento_excepcion.fecha_escolar == sabado


def test_aforo_calcular_metricas_filtra_por_nivel_grado_y_seccion_sin_mezclar_paralelas(
    staff_op: UsuarioOperador, alumnos_muestra: list[Alumno]
) -> None:
    """Filtros insensibles a mayúsculas/espacios separan correctamente 5to A de 5to B."""
    fecha = date(2026, 11, 2)
    asistencias = [
        RegistroAsistencia(
            id="ast-f1",
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
            id="ast-f2",
            alumno_id=103,  # Secundaria 5to B (no debe mezclarse con 5to A)
            fecha_escolar=fecha,
            hora_efectiva=time(7, 12, 0),
            estado=EstadoAsistencia.PUNTUAL,
            minutos_tardanza=0,
            metodo=MetodoRegistro.CARNET,
            usuario_id=staff_op.id,
            rol_usuario=staff_op.rol,
        ),
    ]

    metricas_5a = ServicioAforo.calcular_metricas(
        operador=staff_op,
        alumnos=alumnos_muestra,
        asistencias_dia=asistencias,
        fecha_escolar=fecha,
        hora_consulta=time(8, 0, 0),
        nivel="  secundaria ",
        grado="5TO",
        seccion=" a ",
    )
    assert metricas_5a.total_matriculados == 2
    assert metricas_5a.presentes == 1
    assert metricas_5a.pendientes == 1
    assert len(metricas_5a.desglose_salones) == 1
    assert metricas_5a.desglose_salones[0].seccion == "A"

    metricas_primaria = ServicioAforo.calcular_metricas(
        operador=staff_op,
        alumnos=alumnos_muestra,
        asistencias_dia=asistencias,
        fecha_escolar=fecha,
        hora_consulta=time(8, 0, 0),
        nivel="primaria",
    )
    assert metricas_primaria.total_matriculados == 2
    assert metricas_primaria.presentes == 0
    assert metricas_primaria.pendientes == 2

    metricas_vacio = ServicioAforo.calcular_metricas(
        operador=staff_op,
        alumnos=alumnos_muestra,
        asistencias_dia=asistencias,
        fecha_escolar=fecha,
        hora_consulta=time(8, 0, 0),
        nivel="Secundaria",
        grado="5to",
        seccion="Z",
    )
    assert metricas_vacio.total_matriculados == 0
    assert metricas_vacio.porcentaje_asistencia == 0.0
    assert metricas_vacio.desglose_salones == []


def test_aforo_obtener_detalle_salon_antes_y_despues_de_cierre(
    coord_op: UsuarioOperador, alumnos_muestra: list[Alumno]
) -> None:
    """RN-04: Detalle individual de salón muestra estado, hora efectiva, tardanza y método."""
    fecha = date(2026, 11, 2)
    alumno_inactivo = Alumno(
        id=998,
        codigo="SEC-5A-INAC",
        dni="99999998",
        nombres="Alumno",
        apellidos="Retirado",
        nivel="Secundaria",
        grado="5to",
        seccion="A",
        carnet_codigo="CRN-998",
        estado=EstadoAlumno.INACTIVO,
    )
    asistencias = [
        RegistroAsistencia(
            id="ast-d1",
            alumno_id=101,
            fecha_escolar=fecha,
            hora_efectiva=time(7, 20, 0),
            estado=EstadoAsistencia.TARDANZA,
            minutos_tardanza=5,
            metodo=MetodoRegistro.CARNET,
            usuario_id=coord_op.id,
            rol_usuario=coord_op.rol,
        ),
        RegistroAsistencia(
            id="ast-d2",
            alumno_id=103,  # 5to B, no pertenece a 5to A
            fecha_escolar=fecha,
            hora_efectiva=time(7, 10, 0),
            estado=EstadoAsistencia.PUNTUAL,
            minutos_tardanza=0,
            metodo=MetodoRegistro.MANUAL_DNI,
            usuario_id=coord_op.id,
            rol_usuario=coord_op.rol,
        ),
    ]

    detalle_antes = ServicioAforo.obtener_detalle_salon(
        operador=coord_op,
        alumnos=[*alumnos_muestra, alumno_inactivo],
        asistencias_dia=asistencias,
        nivel="secundaria",
        grado="5to",
        seccion="a",
        hora_consulta=time(8, 15, 0),
        hora_cierre=time(9, 0, 0),
    )
    assert len(detalle_antes) == 2
    assert all(isinstance(item, DetalleAsistenciaAlumno) for item in detalle_antes)
    por_id = {item.alumno_id: item for item in detalle_antes}
    assert por_id[101].estado == EstadoAsistencia.TARDANZA
    assert por_id[101].hora_efectiva == time(7, 20, 0)
    assert por_id[101].minutos_tardanza == 5
    assert por_id[101].metodo == MetodoRegistro.CARNET
    assert por_id[101].nombre_completo == "Eduardo Luna"
    assert por_id[102].estado == EstadoAsistencia.PENDIENTE
    assert por_id[102].hora_efectiva is None
    assert por_id[102].metodo is None

    # Después del cierre: alumno sin registro y registro PENDIENTE se muestran como AUSENTE
    ast_pendiente_102 = RegistroAsistencia(
        id="ast-pend-102",
        alumno_id=102,
        fecha_escolar=fecha,
        hora_efectiva=time(7, 0, 0),
        estado=EstadoAsistencia.PENDIENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=coord_op.id,
        rol_usuario=coord_op.rol,
    )
    detalle_despues = ServicioAforo.obtener_detalle_salon(
        operador=coord_op,
        alumnos=alumnos_muestra,
        asistencias_dia=[asistencias[0], ast_pendiente_102],
        nivel="Secundaria",
        grado="5to",
        seccion="A",
        hora_consulta=time(9, 10, 0),
        hora_cierre=time(9, 0, 0),
    )
    por_id_despues = {item.alumno_id: item for item in detalle_despues}
    assert por_id_despues[102].estado == EstadoAsistencia.AUSENTE

    detalle_5b_despues = ServicioAforo.obtener_detalle_salon(
        operador=coord_op,
        alumnos=alumnos_muestra,
        asistencias_dia=[],
        nivel="Secundaria",
        grado="5to",
        seccion="B",
        hora_consulta=time(9, 10, 0),
        hora_cierre=time(9, 0, 0),
    )
    assert len(detalle_5b_despues) == 1
    assert detalle_5b_despues[0].estado == EstadoAsistencia.AUSENTE
    assert detalle_5b_despues[0].hora_efectiva is None


def test_aforo_consultar_historial_modificaciones_filtros_y_permisos(
    staff_op: UsuarioOperador,
) -> None:
    """RN-05: Devuelve solo registros modificados filtrados por fecha y alumno."""
    ast_sin_cambios = RegistroAsistencia(
        id="ast-h1",
        alumno_id=101,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
    )
    ast_corregida = RegistroAsistencia(
        id="ast-h2",
        alumno_id=101,
        fecha_escolar=date(2026, 11, 3),
        hora_efectiva=time(7, 25, 0),
        estado=EstadoAsistencia.TARDANZA,
        minutos_tardanza=10,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
        estado_anterior=EstadoAsistencia.AUSENTE,
        motivo_correccion="Ingreso tardío autorizado",
    )
    ast_justificada = RegistroAsistencia(
        id="ast-h3",
        alumno_id=102,
        fecha_escolar=date(2026, 11, 5),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.JUSTIFICADO,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=staff_op.id,
        rol_usuario=staff_op.rol,
        estado_anterior=EstadoAsistencia.AUSENTE,
        motivo_correccion="Justificado: Certificado médico",
    )
    registros = [ast_sin_cambios, ast_justificada, ast_corregida]

    todos = ServicioAforo.consultar_historial_modificaciones(staff_op, registros)
    assert [r.id for r in todos] == ["ast-h2", "ast-h3"]

    por_rango = ServicioAforo.consultar_historial_modificaciones(
        staff_op,
        registros,
        fecha_desde=date(2026, 11, 4),
        fecha_hasta=date(2026, 11, 6),
    )
    assert [r.id for r in por_rango] == ["ast-h3"]

    por_alumno = ServicioAforo.consultar_historial_modificaciones(
        staff_op,
        registros,
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2026, 11, 3),
        alumno_id=101,
    )
    assert [r.id for r in por_alumno] == ["ast-h2"]

    solo_por_alumno = ServicioAforo.consultar_historial_modificaciones(
        staff_op,
        registros,
        alumno_id=101,
    )
    assert [r.id for r in solo_por_alumno] == ["ast-h2"]

    # Rol personalizado con permiso CONSULTAR_HISTORIAL_ASISTENCIA
    rol_hist = Rol(
        codigo="AUDITOR_ASISTENCIA",
        nombre="Auditor de Asistencia",
        descripcion="Consulta historial de modificaciones",
        permisos=frozenset({PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA}),
    )
    rol_sin_hist = Rol(
        codigo="SOLO_DASHBOARD",
        nombre="Solo Dashboard",
        descripcion="Sin acceso al historial",
        permisos=frozenset({PermisoOperacion.CONSULTAR_DASHBOARD_AFORO}),
    )
    op_hist = UsuarioOperador(
        id=40, username="aud_ast", rol="AUDITOR_ASISTENCIA"  # type: ignore[arg-type]
    )
    op_sin_hist = UsuarioOperador(
        id=41, username="solo_dash", rol="SOLO_DASHBOARD"  # type: ignore[arg-type]
    )
    op_inactivo = UsuarioOperador(
        id=42, username="inac", rol=RolUsuario.ADMIN, activo=False
    )

    assert len(
        ServicioAforo.consultar_historial_modificaciones(
            op_hist, registros, roles=[rol_hist, rol_sin_hist]
        )
    ) == 2

    with pytest.raises(PermisoAforoException, match="no está autorizado"):
        ServicioAforo.consultar_historial_modificaciones(
            op_sin_hist, registros, roles=[rol_hist, rol_sin_hist]
        )

    with pytest.raises(PermisoAforoException, match="no tiene una cuenta activa"):
        ServicioAforo.consultar_historial_modificaciones(op_inactivo, registros)

    with pytest.raises(AforoException, match="rango"):
        ServicioAforo.consultar_historial_modificaciones(
            staff_op,
            registros,
            fecha_desde=date(2026, 11, 10),
            fecha_hasta=date(2026, 11, 5),
        )


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


def test_justificacion_permitida_coordinador_y_denegada_operador_inactivo(
    coord_op: UsuarioOperador,
    alumnos_muestra: list[Alumno],
    periodo_activo: PeriodoAcademico,
) -> None:
    """COORDINADOR puede gestionar justificaciones; un operador inactivo no."""
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
    resultado = ServicioJustificaciones.registrar_y_aprobar_justificacion(
        operador=coord_op,
        alumno=alumnos_muestra[0],
        asistencia=ast,
        fecha_solicitud=date(2026, 11, 2),
        fecha_actual=date(2026, 11, 2),
        categoria=CategoriaJustificacion.MEDICA,
        motivo="Prueba de coordinador",
        periodo=periodo_activo,
    )
    assert resultado.asistencia_actualizada.estado == EstadoAsistencia.JUSTIFICADO

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
