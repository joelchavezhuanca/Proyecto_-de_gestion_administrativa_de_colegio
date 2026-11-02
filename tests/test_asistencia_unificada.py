import time as pytime
from datetime import date, time

import pytest

try:
    from src.dominio.asistencia import (
        Alumno,
        AlumnoInactivoException,
        AlumnoNoEncontradoException,
        AsistenciaJustificadaException,
        CarnetInvalidoException,
        DniInvalidoException,
        EstadoAlumno,
        EstadoAsistencia,
        FaltaMotivoCorreccionException,
        MetodoRegistro,
        RegistroAsistencia,
        RegistroDuplicadoException,
        RolNoAutorizadoException,
        RolUsuario,
        UsuarioOperador,
        buscar_alumnos_activos,
        calcular_estado_y_tardanza,
        registrar_asistencia_unificada,
    )
except ImportError:
    from asistencia_dominio import (  # type: ignore
        Alumno,
        AlumnoInactivoException,
        AlumnoNoEncontradoException,
        AsistenciaJustificadaException,
        CarnetInvalidoException,
        DniInvalidoException,
        EstadoAlumno,
        EstadoAsistencia,
        FaltaMotivoCorreccionException,
        MetodoRegistro,
        RegistroAsistencia,
        RegistroDuplicadoException,
        RolNoAutorizadoException,
        RolUsuario,
        UsuarioOperador,
        buscar_alumnos_activos,
        calcular_estado_y_tardanza,
        registrar_asistencia_unificada,
    )


@pytest.fixture
def alumno_activo() -> Alumno:
    return Alumno(
        id=101,
        codigo="ALU-2026-001",
        dni="72945734",
        nombres="Eduardo",
        apellidos="Luna Lezano",
        nivel="Secundaria",
        grado="5to",
        seccion="A",
        carnet_codigo="CRN-EDU-7294",
        estado=EstadoAlumno.ACTIVO,
    )


@pytest.fixture
def operador_admin() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_general", rol=RolUsuario.ADMIN)


@pytest.fixture
def operador_coordinador() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="coord_secundaria", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def operador_staff() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="staff_asistencia", rol=RolUsuario.ADMIN_STAFF)


def test_escenario_01_asistencia_puntual_carnet(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 1: Registrar asistencia puntual mediante carnet (07:10:00)."""
    res = registrar_asistencia_unificada(
        operador=operador_staff,
        alumno=alumno_activo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 10, 0),
        fecha_escolar=date(2026, 11, 2),
        codigo_carnet="CRN-EDU-7294",
    )
    assert res.asistencia.estado == EstadoAsistencia.PUNTUAL
    assert res.asistencia.minutos_tardanza == 0
    assert res.asistencia.metodo == MetodoRegistro.CARNET
    assert res.asistencia.usuario_id == operador_staff.id
    assert res.auditoria.operacion == "REGISTRO_ASISTENCIA"
    assert res.evento_whatsapp is not None
    assert res.evento_whatsapp.estado == EstadoAsistencia.PUNTUAL


def test_escenario_02_asistencia_tardanza_carnet(
    operador_coordinador: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 2: Registrar tardanza mediante carnet a las 07:16:01 -> 2 minutos."""
    res = registrar_asistencia_unificada(
        operador=operador_coordinador,
        alumno=alumno_activo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 16, 1),
        fecha_escolar=date(2026, 11, 2),
        codigo_carnet="CRN-EDU-7294",
    )
    assert res.asistencia.estado == EstadoAsistencia.TARDANZA
    assert res.asistencia.minutos_tardanza == 2
    assert res.asistencia.metodo == MetodoRegistro.CARNET
    assert res.evento_whatsapp is not None
    assert res.evento_whatsapp.minutos_tardanza == 2


def test_escenario_03_04_atribucion_sesion_operador(
    operador_admin: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenarios 3 y 4: La marcación se atribuye a la sesión del operador autenticado."""
    res = registrar_asistencia_unificada(
        operador=operador_admin,
        alumno=alumno_activo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 5, 0),
        fecha_escolar=date(2026, 11, 2),
    )
    assert res.asistencia.usuario_id == operador_admin.id
    assert res.asistencia.rol_usuario == RolUsuario.ADMIN
    assert res.auditoria.usuario_id == operador_admin.id


def test_escenario_05_impedir_operador_inactivo_o_no_autorizado(
    alumno_activo: Alumno,
) -> None:
    """Escenario 5: Impedir escaneo sin sesión activa o con cuenta inactiva."""
    operador_inactivo = UsuarioOperador(
        id=9, username="desactivado", rol=RolUsuario.ADMIN_STAFF, activo=False
    )
    with pytest.raises(RolNoAutorizadoException, match="no cuenta con una cuenta activa"):
        registrar_asistencia_unificada(
            operador=operador_inactivo,
            alumno=alumno_activo,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
        )


def test_escenario_05_rol_no_reconocido_lanza_excepcion(
    alumno_activo: Alumno,
) -> None:
    """Verifica rechazo inmediato si el operador posee un rol no oficial."""
    operador_invalido = UsuarioOperador(
        id=99, username="portero_antiguo", rol="PORTERIA", activo=True  # type: ignore
    )
    with pytest.raises(RolNoAutorizadoException, match="no está autorizado"):
        registrar_asistencia_unificada(
            operador=operador_invalido,
            alumno=alumno_activo,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
        )


def test_escenario_06_registro_manual_por_dni(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 6: Registrar manualmente por DNI de 8 dígitos."""
    res = registrar_asistencia_unificada(
        operador=operador_staff,
        alumno=alumno_activo,
        metodo=MetodoRegistro.MANUAL_DNI,
        hora_servidor=time(7, 8, 30),
        fecha_escolar=date(2026, 11, 2),
        dni_manual="72945734",
    )
    assert res.asistencia.estado == EstadoAsistencia.PUNTUAL
    assert res.asistencia.metodo == MetodoRegistro.MANUAL_DNI
    assert res.asistencia.minutos_tardanza == 0


def test_escenario_07_busqueda_asistida_solo_activos(alumno_activo: Alumno) -> None:
    """Escenario 7: Buscar alumno por nombres/apellidos/DNI/código y filtrar inactivos."""
    inactivo = Alumno(
        id=102,
        codigo="ALU-INACTIVO",
        dni="12345678",
        nombres="Juan",
        apellidos="Luna Perez",
        nivel="Primaria",
        grado="1ro",
        seccion="B",
        carnet_codigo="CRN-INAC-1",
        estado=EstadoAlumno.INACTIVO,
    )
    universo = [alumno_activo, inactivo]

    res_nombre = buscar_alumnos_activos("Luna", universo)
    assert len(res_nombre) == 1
    assert res_nombre[0].codigo == "ALU-2026-001"

    res_dni = buscar_alumnos_activos("72945734", universo)
    assert len(res_dni) == 1

    res_cod = buscar_alumnos_activos("ALU-2026", universo)
    assert len(res_cod) == 1

    res_vacio = buscar_alumnos_activos("NoExiste", universo)
    assert len(res_vacio) == 0

    assert buscar_alumnos_activos("   ", universo) == []


def test_escenario_08_rechazar_dni_invalido(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 8: Rechazar DNI con longitud distinta a 8 o caracteres no numéricos."""
    dnis_invalidos = ["1234567", "123456789", "7294A734", "", "abcdefgh"]
    for dni_bad in dnis_invalidos:
        with pytest.raises(DniInvalidoException):
            registrar_asistencia_unificada(
                operador=operador_staff,
                alumno=alumno_activo,
                metodo=MetodoRegistro.MANUAL_DNI,
                hora_servidor=time(7, 5, 0),
                fecha_escolar=date(2026, 11, 2),
                dni_manual=dni_bad,
            )


def test_escenario_08_rechazar_manual_sin_dni(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Rechazar registro MANUAL_DNI si no se proporciona el argumento dni_manual."""
    with pytest.raises(DniInvalidoException, match="Debe proporcionar el DNI"):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_activo,
            metodo=MetodoRegistro.MANUAL_DNI,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
            dni_manual=None,
        )


def test_escenario_08_rechazar_dni_que_no_coincide_con_alumno(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Rechazar cuando el DNI de 8 dígitos no corresponde al alumno."""
    with pytest.raises(AlumnoNoEncontradoException, match="no coincide con el alumno"):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_activo,
            metodo=MetodoRegistro.MANUAL_DNI,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
            dni_manual="11112222",
        )


def test_escenario_09_rechazar_alumno_inexistente(
    operador_staff: UsuarioOperador,
) -> None:
    """Escenario 9: Rechazar registro cuando el alumno no fue encontrado."""
    with pytest.raises(AlumnoNoEncontradoException):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=None,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
        )


def test_escenario_10_rechazar_alumno_inactivo(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 10: Rechazar registro de alumno que no se encuentra ACTIVO."""
    alumno_inactivo = Alumno(
        id=103,
        codigo="ALU-SUSP",
        dni="88889999",
        nombres="Carlos",
        apellidos="Rosas",
        nivel="Secundaria",
        grado="4to",
        seccion="B",
        carnet_codigo="CRN-SUSP-1",
        estado=EstadoAlumno.INACTIVO,
    )
    with pytest.raises(AlumnoInactivoException):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_inactivo,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
        )


def test_escenario_11_corregir_asistencia_ausente(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 11: Corregir AUSENTE a TARDANZA con motivo, guardando trazabilidad."""
    asistencia_ausente = RegistroAsistencia(
        id="ast-ausente-01",
        alumno_id=alumno_activo.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=operador_staff.id,
        rol_usuario=operador_staff.rol,
    )

    res = registrar_asistencia_unificada(
        operador=operador_staff,
        alumno=alumno_activo,
        metodo=MetodoRegistro.MANUAL_DNI,
        hora_servidor=time(7, 25, 0),
        fecha_escolar=date(2026, 11, 2),
        asistencia_existente=asistencia_ausente,
        motivo_correccion="Alumno llegó tarde con autorización de coordinación",
        dni_manual="72945734",
    )

    assert res.asistencia.estado == EstadoAsistencia.TARDANZA
    assert res.asistencia.minutos_tardanza == 10
    assert res.asistencia.estado_anterior == EstadoAsistencia.AUSENTE
    assert (
        res.asistencia.motivo_correccion
        == "Alumno llegó tarde con autorización de coordinación"
    )
    assert res.auditoria.operacion == "CORRECCION_AUSENTE"
    assert res.auditoria.estado_anterior == EstadoAsistencia.AUSENTE
    assert res.auditoria.estado_nuevo == EstadoAsistencia.TARDANZA


def test_escenario_11_error_corregir_ausente_sin_motivo(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 11 error: Rechazar corrección de AUSENTE si no se proporciona motivo."""
    asistencia_ausente = RegistroAsistencia(
        id="ast-ausente-02",
        alumno_id=alumno_activo.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_DNI,
        usuario_id=operador_staff.id,
        rol_usuario=operador_staff.rol,
    )

    with pytest.raises(FaltaMotivoCorreccionException):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_activo,
            metodo=MetodoRegistro.MANUAL_DNI,
            hora_servidor=time(7, 25, 0),
            fecha_escolar=date(2026, 11, 2),
            asistencia_existente=asistencia_ausente,
            motivo_correccion="",
            dni_manual="72945734",
        )


def test_escenario_12_rechazar_registro_duplicado(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 12: Rechazar duplicado si el alumno ya tiene PUNTUAL o TARDANZA."""
    asistencia_previa = RegistroAsistencia(
        id="ast-prev-01",
        alumno_id=alumno_activo.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=operador_staff.id,
        rol_usuario=operador_staff.rol,
    )

    with pytest.raises(RegistroDuplicadoException):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_activo,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 12, 0),
            fecha_escolar=date(2026, 11, 2),
            asistencia_existente=asistencia_previa,
        )


def test_escenario_13_no_modificar_justificado_automaticamente(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 13: Rechazar sobreescritura de estado JUSTIFICADO."""
    asistencia_justificada = RegistroAsistencia(
        id="ast-just-01",
        alumno_id=alumno_activo.id,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 0, 0),
        estado=EstadoAsistencia.JUSTIFICADO,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=operador_staff.id,
        rol_usuario=operador_staff.rol,
    )

    with pytest.raises(AsistenciaJustificadaException):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_activo,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 10, 0),
            fecha_escolar=date(2026, 11, 2),
            asistencia_existente=asistencia_justificada,
        )


@pytest.mark.parametrize(
    ("hora_ingreso", "estado_esperado", "minutos_esperados"),
    [
        (time(7, 0, 0), EstadoAsistencia.PUNTUAL, 0),
        (time(7, 14, 59), EstadoAsistencia.PUNTUAL, 0),
        (time(7, 15, 0), EstadoAsistencia.PUNTUAL, 0),
        (time(7, 15, 1), EstadoAsistencia.TARDANZA, 1),
        (time(7, 15, 59), EstadoAsistencia.TARDANZA, 1),
        (time(7, 16, 0), EstadoAsistencia.TARDANZA, 1),
        (time(7, 16, 1), EstadoAsistencia.TARDANZA, 2),
        (time(7, 20, 0), EstadoAsistencia.TARDANZA, 5),
        (time(7, 30, 0), EstadoAsistencia.TARDANZA, 15),
    ],
)
def test_escenario_14_tabla_validacion_calculo_oficial(
    hora_ingreso: time, estado_esperado: EstadoAsistencia, minutos_esperados: int
) -> None:
    """Escenario 14: Validación rigurosa de la tabla oficial sección 2.5."""
    estado, minutos = calcular_estado_y_tardanza(hora_ingreso)
    assert estado == estado_esperado
    assert minutos == minutos_esperados


def test_escenario_15_trazabilidad_auditoria_completa(
    operador_coordinador: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 15: Cada operación genera auditoría atómica e inmutable."""
    res = registrar_asistencia_unificada(
        operador=operador_coordinador,
        alumno=alumno_activo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 14, 0),
        fecha_escolar=date(2026, 11, 2),
    )
    aud = res.auditoria
    assert aud.usuario_id == operador_coordinador.id
    assert aud.rol == RolUsuario.COORDINADOR
    assert aud.alumno_id == alumno_activo.id
    assert aud.estado_nuevo == EstadoAsistencia.PUNTUAL
    assert aud.metodo == MetodoRegistro.CARNET
    assert aud.id is not None


def test_escenario_16_rendimiento_menor_200ms(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Escenario 16: El procesamiento del registro termina en < 200 ms."""
    inicio = pytime.perf_counter()
    registrar_asistencia_unificada(
        operador=operador_staff,
        alumno=alumno_activo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 10, 0),
        fecha_escolar=date(2026, 11, 2),
    )
    fin = pytime.perf_counter()
    duracion_ms = (fin - inicio) * 1000
    assert duracion_ms < 200, f"El tiempo fue {duracion_ms:.2f} ms (debe ser < 200 ms)"


def test_carnet_invalido_lanza_excepcion(
    operador_staff: UsuarioOperador, alumno_activo: Alumno
) -> None:
    """Verifica que un código de carnet incorrecto sea rechazado."""
    with pytest.raises(CarnetInvalidoException):
        registrar_asistencia_unificada(
            operador=operador_staff,
            alumno=alumno_activo,
            metodo=MetodoRegistro.CARNET,
            hora_servidor=time(7, 5, 0),
            fecha_escolar=date(2026, 11, 2),
            codigo_carnet="CRN-EQUIVOCADO-999",
        )
