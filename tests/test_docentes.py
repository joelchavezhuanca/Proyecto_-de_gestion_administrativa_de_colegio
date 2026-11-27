"""Pruebas BDD y unitarias del PBI-11: Asignación Docente Segura."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.dominio.asistencia import UsuarioOperador
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    ErrorRegistroAuditoriaException,
    RegistroAuditoria,
    ResultadoAuditoria,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.docentes import (
    AccesoAmbitoDocenteDenegadoException,
    AmbitoDocenteDenegadoException,
    AsignacionDocente,
    AsignacionDuplicadaException,
    AsignacionEnUsoException,
    AsignacionInvalidaException,
    DocenteException,
    DocenteNoHabilitadoException,
    PermisoAsignacionDocenteException,
    PermisoDocenteException,
    ServicioAsignacionDocente,
)
from src.dominio.malla_curricular import Curso, NivelEducativo, Salon
from src.dominio.usuarios import (
    AccesoDenegadoException,
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolUsuario,
    Usuario,
)

FECHA_HORA_LIMA = datetime(2026, 3, 2, 9, 15, 0, tzinfo=ZONA_HORARIA_LIMA)


@pytest.fixture
def rol_docente() -> Rol:
    return Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Registra y consulta calificaciones de sus grupos asignados",
        permisos=frozenset(
            {
                PermisoOperacion.REGISTRAR_CALIFICACIONES,
                PermisoOperacion.CONSULTAR_CALIFICACIONES,
            }
        ),
        activo=True,
    )


@pytest.fixture
def rol_gestor_docentes() -> Rol:
    return Rol(
        codigo="COORDINADOR_ACADEMICO",
        nombre="Coordinador Académico",
        descripcion="Puede asignar y revocar carga docente",
        permisos=frozenset({PermisoOperacion.ASIGNAR_DOCENTES}),
        activo=True,
    )


@pytest.fixture
def rol_auxiliar() -> Rol:
    return Rol(
        codigo="AUXILIAR",
        nombre="Auxiliar",
        descripcion="Solo registra asistencia",
        permisos=frozenset({PermisoOperacion.REGISTRAR_ASISTENCIA}),
        activo=True,
    )


@pytest.fixture
def admin_operador() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=True)


@pytest.fixture
def docente_activo() -> Usuario:
    return Usuario(
        id=10,
        username="j.perez",
        password_hash="hash-doc",
        salt="salt-doc",
        nombre_completo="Juan Pérez",
        rol="DOCENTE",
        estado=EstadoUsuario.ACTIVO,
    )


@pytest.fixture
def otro_docente_activo() -> Usuario:
    return Usuario(
        id=11,
        username="m.lopez",
        password_hash="hash-doc2",
        salt="salt-doc2",
        nombre_completo="María López",
        rol="DOCENTE",
        estado=EstadoUsuario.ACTIVO,
    )


@pytest.fixture
def salon_3ro_a() -> Salon:
    return Salon(
        id=101,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
        capacidad_maxima=30,
    )


@pytest.fixture
def salon_3ro_b() -> Salon:
    return Salon(
        id=102,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="B",
        capacidad_maxima=30,
    )


@pytest.fixture
def curso_matematica() -> Curso:
    return Curso(
        id=201,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo="MAT-301",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=6,
    )


@pytest.fixture
def curso_comunicacion() -> Curso:
    return Curso(
        id=202,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo="COM-301",
        nombre="Comunicación",
        area_curricular="Comunicación",
        horas_semanales=5,
    )


def test_jerarquia_excepciones_e_inmutabilidad(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    assert issubclass(PermisoAsignacionDocenteException, AccesoDenegadoException)
    assert issubclass(PermisoAsignacionDocenteException, DocenteException)
    assert PermisoDocenteException is PermisoAsignacionDocenteException
    assert issubclass(AccesoAmbitoDocenteDenegadoException, AccesoDenegadoException)
    assert issubclass(AccesoAmbitoDocenteDenegadoException, DocenteException)
    assert AmbitoDocenteDenegadoException is AccesoAmbitoDocenteDenegadoException
    assert issubclass(DocenteNoHabilitadoException, DocenteException)
    assert issubclass(AsignacionInvalidaException, DocenteException)
    assert issubclass(AsignacionDuplicadaException, DocenteException)
    assert issubclass(AsignacionEnUsoException, DocenteException)

    asignacion = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        roles=[rol_docente],
        fecha_hora=FECHA_HORA_LIMA,
    )
    assert isinstance(asignacion, AsignacionDocente)
    assert isinstance(asignacion.id, str)
    assert asignacion.id.startswith("asg-")
    assert asignacion.asignado_por == admin_operador.id
    with pytest.raises(FrozenInstanceError):
        asignacion.activa = False  # type: ignore[misc]


def test_bdd_escenario_1_asignar_docente_rol_personalizado_y_auditar_pbi16(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    bitacora: list[RegistroAuditoria] = []

    asignacion = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        asignaciones_existentes=[],
        fecha_hora=FECHA_HORA_LIMA,
        roles=[rol_docente],
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )

    assert asignacion.id.startswith("asg-")
    assert asignacion.usuario_docente_id == docente_activo.id
    assert asignacion.curso_id == curso_matematica.id
    assert asignacion.salon_id == salon_3ro_a.id
    assert asignacion.anio_lectivo == 2026
    assert asignacion.activa is True
    assert asignacion.asignado_por == admin_operador.id
    assert asignacion.creado_en == FECHA_HORA_LIMA

    assert len(bitacora) == 1
    evento = bitacora[0]
    assert evento.usuario_id == admin_operador.id
    assert evento.entidad == "ASIGNACION_DOCENTE"
    assert evento.entidad_id == asignacion.id
    assert evento.resultado == ResultadoAuditoria.CONFIRMADA
    assert evento.estado_nuevo == "ACTIVA"
    assert evento.contexto_academico is not None
    assert evento.contexto_academico.nivel == "Secundaria"
    assert evento.contexto_academico.grado == "3ro"
    assert evento.contexto_academico.seccion == "A"
    assert evento.detalle["accion"] == "ASIGNAR_DOCENTE"

    admin_usuario = Usuario(
        id=1,
        username="admin",
        password_hash="h",
        salt="s",
        nombre_completo="Admin",
        rol=RolUsuario.ADMIN,
    )
    verificacion = ServicioAuditoria.verificar_integridad(bitacora, operador=admin_usuario)
    assert verificacion.integra is True


def test_asignar_docente_con_rol_dinamico_asignador_y_usuario_operador(
    rol_gestor_docentes: Rol,
    rol_docente: Rol,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
) -> None:
    operador_dinamico = Usuario(
        id=5,
        username="coord.acad",
        password_hash="h",
        salt="s",
        nombre_completo="Coord Académico",
        rol="COORDINADOR_ACADEMICO",
        estado=EstadoUsuario.ACTIVO,
    )
    docente_operador = UsuarioOperador(id=15, username="doc.op", rol="DOCENTE", activo=True)

    asignacion = ServicioAsignacionDocente.asignar_docente(
        operador_dinamico,
        docente_operador,
        curso_matematica,
        salon_3ro_a,
        [],
        datetime(2026, 3, 2, 14, 0, tzinfo=UTC),
        [rol_gestor_docentes, rol_docente],
    )

    assert asignacion.usuario_docente_id == 15
    assert asignacion.asignado_por == 5
    assert asignacion.creado_en == datetime(
        2026, 3, 2, 9, 0, tzinfo=timezone(timedelta(hours=-5))
    )


def test_bdd_escenario_2_validar_ambito_docente_permitido_y_denegado_auditado(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    curso_comunicacion: Curso,
    salon_3ro_a: Salon,
    salon_3ro_b: Salon,
    rol_docente: Rol,
) -> None:
    bitacora: list[RegistroAuditoria] = []
    creada = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        roles=[rol_docente],
        fecha_hora=FECHA_HORA_LIMA,
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )

    # Invocación posicional exacta del contrato Ola 2 / PBI-10
    permitida = ServicioAsignacionDocente.validar_ambito_docente(
        docente_activo,
        curso_matematica.id,
        salon_3ro_a.id,
        2026,
        [creada],
        [rol_docente],
        fecha_hora=FECHA_HORA_LIMA,
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )
    assert permitida == creada
    assert len(bitacora) == 1

    # Intento en salón 3ro B (no asignado) -> AccesoDenegadoException y auditoría PBI-16
    with pytest.raises(AccesoDenegadoException) as exc_info:
        ServicioAsignacionDocente.validar_ambito_docente(
            docente=docente_activo,
            curso_id=curso_matematica.id,
            salon_id=salon_3ro_b.id,
            anio_lectivo=2026,
            asignaciones=[creada],
            roles=[rol_docente],
            fecha_hora=FECHA_HORA_LIMA,
            eventos_auditoria_existentes=bitacora,
            persistir_auditoria=bitacora.append,
        )

    assert isinstance(exc_info.value, AccesoAmbitoDocenteDenegadoException)
    assert len(bitacora) == 2
    denegado = bitacora[-1]
    assert denegado.operacion == TipoOperacionAuditoria.ACCESO_DENEGADO
    assert denegado.resultado == ResultadoAuditoria.FALLIDA
    assert denegado.usuario_id == docente_activo.id
    assert denegado.entidad == "ASIGNACION_DOCENTE"
    assert denegado.entidad_id == f"{curso_matematica.id}:{salon_3ro_b.id}:2026"
    assert exc_info.value.auditoria == denegado

    # Intento en curso no asignado del mismo salón 3ro A -> también denegado
    with pytest.raises(AccesoDenegadoException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente=docente_activo,
            curso_id=curso_comunicacion.id,
            salon_id=salon_3ro_a.id,
            anio_lectivo=2026,
            asignaciones=[creada],
            roles=[rol_docente],
        )

    # Intento en otro año lectivo -> también denegado (aislamiento por año obligatorio)
    with pytest.raises(AccesoDenegadoException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente=docente_activo,
            curso_id=curso_matematica.id,
            salon_id=salon_3ro_a.id,
            anio_lectivo=2027,
            asignaciones=[creada],
            roles=[rol_docente],
        )


def test_bdd_escenario_3_rechazar_docente_inactivo_o_sin_permiso_calificar(
    admin_operador: UsuarioOperador,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
    rol_auxiliar: Rol,
) -> None:
    docente_inactivo = Usuario(
        id=20,
        username="doc.off",
        password_hash="h",
        salt="s",
        nombre_completo="Docente Inactivo",
        rol="DOCENTE",
        estado=EstadoUsuario.INACTIVO,
    )
    with pytest.raises(DocenteNoHabilitadoException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=docente_inactivo,
            curso=curso_matematica,
            salon=salon_3ro_a,
            roles=[rol_docente],
        )

    docente_op_inactivo = UsuarioOperador(id=21, username="op.off", rol="DOCENTE", activo=False)
    with pytest.raises(DocenteNoHabilitadoException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=docente_op_inactivo,
            curso=curso_matematica,
            salon=salon_3ro_a,
            roles=[rol_docente],
        )

    usuario_auxiliar = Usuario(
        id=22,
        username="aux1",
        password_hash="h",
        salt="s",
        nombre_completo="Auxiliar",
        rol="AUXILIAR",
        estado=EstadoUsuario.ACTIVO,
    )
    with pytest.raises(DocenteNoHabilitadoException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=usuario_auxiliar,
            curso=curso_matematica,
            salon=salon_3ro_a,
            roles=[rol_docente, rol_auxiliar],
        )

    coordinador_sin_calificar = Usuario(
        id=23,
        username="coord1",
        password_hash="h",
        salt="s",
        nombre_completo="Coordinador",
        rol=RolUsuario.COORDINADOR,
        estado=EstadoUsuario.ACTIVO,
    )
    with pytest.raises(DocenteNoHabilitadoException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=coordinador_sin_calificar,
            curso=curso_matematica,
            salon=salon_3ro_a,
            roles=[rol_docente],
        )

    rol_docente_inactivo = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Rol desactivado",
        permisos=frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
        activo=False,
    )
    docente_con_rol_inactivo = Usuario(
        id=24,
        username="doc.roloff",
        password_hash="h",
        salt="s",
        nombre_completo="Docente Rol Inactivo",
        rol="DOCENTE",
        estado=EstadoUsuario.ACTIVO,
    )
    with pytest.raises(DocenteNoHabilitadoException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=docente_con_rol_inactivo,
            curso=curso_matematica,
            salon=salon_3ro_a,
            roles=[rol_docente_inactivo],
        )


def test_rn01_rechazar_operador_inactivo_o_sin_permiso_asignar_docentes(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    ServicioAsignacionDocente.validar_operador_asignacion(admin_operador)

    admin_inactivo = UsuarioOperador(id=2, username="admin.off", rol=RolUsuario.ADMIN, activo=False)
    coordinador = UsuarioOperador(id=3, username="coord", rol=RolUsuario.COORDINADOR, activo=True)
    staff = UsuarioOperador(id=4, username="staff", rol=RolUsuario.ADMIN_STAFF, activo=True)

    for operador in (admin_inactivo, coordinador, staff, docente_activo):
        with pytest.raises(PermisoAsignacionDocenteException):
            ServicioAsignacionDocente.validar_operador_asignacion(operador, roles=[rol_docente])
        with pytest.raises(PermisoAsignacionDocenteException):
            ServicioAsignacionDocente.asignar_docente(
                operador=operador,
                docente=docente_activo,
                curso=curso_matematica,
                salon=salon_3ro_a,
                roles=[rol_docente],
            )

    asignacion = AsignacionDocente(
        id="asg-001",
        usuario_docente_id=docente_activo.id,
        curso_id=curso_matematica.id,
        salon_id=salon_3ro_a.id,
        anio_lectivo=2026,
    )
    with pytest.raises(PermisoAsignacionDocenteException):
        ServicioAsignacionDocente.revocar_asignacion(
            operador=coordinador,
            asignacion=asignacion,
            fecha_hora=FECHA_HORA_LIMA,
            roles=[rol_docente],
        )


def test_bdd_escenario_4_rechazar_asignacion_duplicada_y_cruce_en_curso_salon(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    otro_docente_activo: Usuario,
    curso_matematica: Curso,
    curso_comunicacion: Curso,
    salon_3ro_a: Salon,
    salon_3ro_b: Salon,
    rol_docente: Rol,
) -> None:
    primera = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        roles=[rol_docente],
    )

    # Mismo docente, curso, salón y año -> duplicado
    with pytest.raises(AsignacionDuplicadaException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=docente_activo,
            curso=curso_matematica,
            salon=salon_3ro_a,
            asignaciones_existentes=[primera],
            roles=[rol_docente],
        )

    # Otro docente en el mismo curso, salón y año activo -> conflicto/cruce
    with pytest.raises(AsignacionDuplicadaException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=otro_docente_activo,
            curso=curso_matematica,
            salon=salon_3ro_a,
            asignaciones_existentes=[primera],
            roles=[rol_docente],
        )

    # Mismo docente en otro salón (3ro B) u otro curso -> permitido
    segunda = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_b,
        asignaciones_existentes=[primera],
        roles=[rol_docente],
    )
    tercera = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_comunicacion,
        salon=salon_3ro_a,
        asignaciones_existentes=[primera, segunda],
        roles=[rol_docente],
    )
    assert len({primera.id, segunda.id, tercera.id}) == 3


def test_bdd_escenario_5_revocar_asignacion_bloquea_acceso_y_permite_reasignar(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    otro_docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    bitacora: list[RegistroAuditoria] = []
    asignacion = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        roles=[rol_docente],
        fecha_hora=FECHA_HORA_LIMA,
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )

    fecha_revocacion = FECHA_HORA_LIMA + timedelta(days=30)
    revocada = ServicioAsignacionDocente.revocar_asignacion(
        admin_operador,
        asignacion,
        fecha_revocacion,
        [rol_docente],
        motivo="Reasignación de carga horaria",
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )

    assert revocada.activa is False
    assert revocada.revocada_en == fecha_revocacion
    assert revocada.motivo_revocacion == "Reasignación de carga horaria"
    assert bitacora[-1].estado_anterior == "ACTIVA"
    assert bitacora[-1].estado_nuevo == "REVOCADA"
    assert bitacora[-1].detalle["accion"] == "REVOCAR_DOCENTE"

    # El docente original pierde acceso tras la revocación
    with pytest.raises(AccesoDenegadoException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente=docente_activo,
            curso_id=curso_matematica.id,
            salon_id=salon_3ro_a.id,
            anio_lectivo=2026,
            asignaciones=[revocada],
            roles=[rol_docente],
            fecha_hora=fecha_revocacion,
            eventos_auditoria_existentes=bitacora,
            persistir_auditoria=bitacora.append,
        )

    # El historial sigue disponible para consulta (solo_activas=False)
    historial = ServicioAsignacionDocente.listar_asignaciones_docente(
        docente_activo.id,
        [revocada],
        solo_activas=False,
    )
    assert historial == [revocada]
    assert (
        ServicioAsignacionDocente.listar_asignaciones_docente(
            docente_activo.id,
            [revocada],
            solo_activas=True,
        )
        == []
    )

    # Tras revocar, sí es posible asignar un nuevo docente al mismo curso y salón
    nueva = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=otro_docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        asignaciones_existentes=[revocada],
        roles=[rol_docente],
        fecha_hora=fecha_revocacion,
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )
    assert nueva.activa is True
    assert nueva.id != asignacion.id


def test_rn05_desactivar_usuario_o_rol_bloquea_acceso_docente(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    asignacion = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        roles=[rol_docente],
    )

    docente_desactivado = Usuario(
        id=docente_activo.id,
        username=docente_activo.username,
        password_hash=docente_activo.password_hash,
        salt=docente_activo.salt,
        nombre_completo=docente_activo.nombre_completo,
        rol=docente_activo.rol,
        estado=EstadoUsuario.INACTIVO,
    )
    with pytest.raises(AccesoDenegadoException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente=docente_desactivado,
            curso_id=curso_matematica.id,
            salon_id=salon_3ro_a.id,
            anio_lectivo=2026,
            asignaciones=[asignacion],
            roles=[rol_docente],
        )

    rol_docente_off = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Desactivado",
        permisos=frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
        activo=False,
    )
    with pytest.raises(AccesoDenegadoException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente=docente_activo,
            curso_id=curso_matematica.id,
            salon_id=salon_3ro_a.id,
            anio_lectivo=2026,
            asignaciones=[asignacion],
            roles=[rol_docente_off],
        )


def test_restriccion_eliminacion_fisica_asignacion(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    asignacion = ServicioAsignacionDocente.asignar_docente(
        operador=admin_operador,
        docente=docente_activo,
        curso=curso_matematica,
        salon=salon_3ro_a,
        roles=[rol_docente],
    )

    with pytest.raises(AsignacionEnUsoException):
        ServicioAsignacionDocente.eliminar_asignacion(
            operador=admin_operador,
            asignacion=asignacion,
            tiene_calificaciones_asociadas=True,
        )

    bitacora: list[RegistroAuditoria] = []
    evento = ServicioAsignacionDocente.eliminar_asignacion(
        operador=admin_operador,
        asignacion=asignacion,
        tiene_calificaciones_asociadas=False,
        fecha_hora=FECHA_HORA_LIMA,
        eventos_auditoria_existentes=bitacora,
        persistir_auditoria=bitacora.append,
    )
    assert len(bitacora) == 1
    assert evento.estado_nuevo == "ELIMINADA"
    assert evento.detalle["accion"] == "ELIMINAR_ASIGNACION"

    asignacion_inactiva = ServicioAsignacionDocente.revocar_asignacion(
        operador=admin_operador,
        asignacion=asignacion,
    )
    evento_inactiva = ServicioAsignacionDocente.eliminar_asignacion(
        operador=admin_operador,
        asignacion=asignacion_inactiva,
        tiene_calificaciones_asociadas=False,
    )
    assert evento_inactiva.estado_anterior == "REVOCADA"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": ""},
        {"id": "   "},
        {"id": 123},
        {"usuario_docente_id": 0},
        {"usuario_docente_id": False},
        {"curso_id": 0},
        {"salon_id": -3},
        {"anio_lectivo": 1999},
        {"anio_lectivo": True},
        {"activa": "si"},
        {"asignado_por": -1},
        {"asignado_por": True},
        {"creado_en": "2026-03-02"},
        {"revocada_en": "2026-03-03"},
        {"motivo_revocacion": "   "},
        {"motivo_revocacion": 123},
        {
            "creado_en": FECHA_HORA_LIMA,
            "revocada_en": FECHA_HORA_LIMA - timedelta(minutes=1),
        },
    ],
)
def test_validaciones_asignacion_docente_invalida(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "id": "asg-001",
        "usuario_docente_id": 10,
        "curso_id": 201,
        "salon_id": 101,
        "anio_lectivo": 2026,
        "activa": True,
    }
    base.update(kwargs)
    with pytest.raises(AsignacionInvalidaException):
        AsignacionDocente(**base)  # type: ignore[arg-type]


def test_validaciones_consistencia_curso_salon_revocacion_y_filtros(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    otro_docente_activo: Usuario,
    curso_matematica: Curso,
    curso_comunicacion: Curso,
    salon_3ro_a: Salon,
    salon_3ro_b: Salon,
    rol_docente: Rol,
) -> None:
    # Curso o salón inactivo
    curso_inactivo = Curso(
        id=203,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo="HIS-301",
        nombre="Historia",
        area_curricular="Ciencias Sociales",
        horas_semanales=3,
        activo=False,
    )
    salon_inactivo = Salon(
        id=103,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="C",
        activo=False,
    )
    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.asignar_docente(
            admin_operador, docente_activo, curso_inactivo, salon_3ro_a, roles=[rol_docente]
        )
    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.asignar_docente(
            admin_operador, docente_activo, curso_matematica, salon_inactivo, roles=[rol_docente]
        )

    # Año, nivel o grado incompatibles entre curso y salón, o año explícito inconsistente
    salon_2027 = Salon(
        id=104,
        anio_lectivo=2027,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
    )
    salon_primaria = Salon(
        id=105,
        anio_lectivo=2026,
        nivel=NivelEducativo.PRIMARIA,
        grado="3ro",
        seccion="A",
    )
    salon_4to = Salon(
        id=106,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        seccion="A",
    )
    for salon_incompatible in (salon_2027, salon_primaria, salon_4to):
        with pytest.raises(AsignacionInvalidaException):
            ServicioAsignacionDocente.asignar_docente(
                admin_operador,
                docente_activo,
                curso_matematica,
                salon_incompatible,
                roles=[rol_docente],
            )

    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.asignar_docente(
            admin_operador,
            docente_activo,
            curso_matematica,
            salon_3ro_a,
            anio_lectivo=2027,
            roles=[rol_docente],
        )

    # Revocar ya revocada o con motivo vacío
    a1 = ServicioAsignacionDocente.asignar_docente(
        admin_operador, docente_activo, curso_matematica, salon_3ro_a, roles=[rol_docente]
    )
    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.revocar_asignacion(admin_operador, a1, motivo="  ")

    revocada = ServicioAsignacionDocente.revocar_asignacion(admin_operador, a1)
    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.revocar_asignacion(admin_operador, revocada)

    # Identificadores inválidos al validar ámbito
    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente_activo, 0, salon_3ro_a.id, 2026, [a1], roles=[rol_docente]
        )
    with pytest.raises(AsignacionInvalidaException):
        ServicioAsignacionDocente.validar_ambito_docente(
            docente_activo,
            curso_matematica.id,
            salon_3ro_a.id,
            1999,
            [a1],
            roles=[rol_docente],
        )

    # Listar con múltiples filtros
    a2 = ServicioAsignacionDocente.asignar_docente(
        admin_operador,
        otro_docente_activo,
        curso_comunicacion,
        salon_3ro_b,
        asignaciones_existentes=[a1],
        roles=[rol_docente],
    )
    todas = [revocada, a2]
    assert ServicioAsignacionDocente.listar_asignaciones_docente(None, todas) == [a2]
    assert (
        ServicioAsignacionDocente.listar_asignaciones_docente(
            otro_docente_activo.id,
            todas,
            curso_id=curso_comunicacion.id,
            salon_id=salon_3ro_b.id,
            anio_lectivo=2026,
        )
        == [a2]
    )
    assert (
        ServicioAsignacionDocente.listar_asignaciones_docente(
            None,
            todas,
            solo_activas=False,
            curso_id=curso_matematica.id,
            salon_id=salon_3ro_a.id,
        )
        == [revocada]
    )


def test_normalizacion_fecha_naive_a_lima() -> None:
    asignacion = AsignacionDocente(
        id="  asg-001  ",
        usuario_docente_id=10,
        curso_id=201,
        salon_id=101,
        anio_lectivo=2026,
        creado_en=datetime(2026, 3, 2, 8, 30, 0),
    )
    assert asignacion.id == "asg-001"
    assert asignacion.creado_en == datetime(2026, 3, 2, 8, 30, 0, tzinfo=ZONA_HORARIA_LIMA)


def test_error_persistencia_auditoria_se_propaga(
    admin_operador: UsuarioOperador,
    docente_activo: Usuario,
    curso_matematica: Curso,
    salon_3ro_a: Salon,
    rol_docente: Rol,
) -> None:
    def _fallar(_registro: RegistroAuditoria) -> None:
        raise RuntimeError("Fallo de almacenamiento")

    with pytest.raises(ErrorRegistroAuditoriaException):
        ServicioAsignacionDocente.asignar_docente(
            operador=admin_operador,
            docente=docente_activo,
            curso=curso_matematica,
            salon=salon_3ro_a,
            roles=[rol_docente],
            persistir_auditoria=_fallar,
        )
