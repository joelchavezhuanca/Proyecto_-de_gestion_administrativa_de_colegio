"""Pruebas de integración en SQLite en memoria para Repositorios Parte A (núcleo)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.dominio.aforo import EventoCierreDiario
from src.dominio.asistencia import (
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
)
from src.dominio.auditoria import (
    HASH_GENESIS,
    ZONA_HORARIA_LIMA,
    ContextoAcademicoAuditoria,
    FiltroAuditoria,
    ResultadoAuditoria,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.justificaciones import (
    AdjuntoJustificacion,
    CategoriaJustificacion,
    EstadoJustificacion,
    FiltroJustificaciones,
    Justificacion,
    PeriodoAcademico,
    TipoPeriodo,
)
from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
    ServicioGestionRoles,
    Usuario,
    hashear_password,
)
from src.infraestructura.base_datos import sembrar_seguridad_base
from src.infraestructura.modelos import AuditoriaEventoModel, EstudianteModel
from src.infraestructura.repositorios import (
    RepositorioAforo,
    RepositorioAsistencia,
    RepositorioAuditoria,
    RepositorioCalendario,
    RepositorioJustificaciones,
    RepositorioPeriodos,
    RepositorioRoles,
    RepositorioSesiones,
    RepositorioUsuarios,
)

FECHA_LIMA = datetime(2026, 11, 27, 8, 30, 0, tzinfo=ZONA_HORARIA_LIMA)
FECHA_UTC = datetime(2026, 11, 27, 13, 30, 0, tzinfo=UTC)


@pytest.fixture
def usuario_admin_guardado(db_session: Session) -> Usuario:
    sembrar_seguridad_base(db_session)
    repo = RepositorioUsuarios(db_session)
    pwd_hash, salt = hashear_password("AdminSeguro2026!")
    admin = Usuario(
        id=0,
        username="admin_repo",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Administrador Núcleo",
        rol=RolUsuario.ADMIN,
        estado=EstadoUsuario.ACTIVO,
        creado_en=FECHA_UTC,
    )
    guardado = repo.guardar(admin)
    db_session.commit()
    return guardado


@pytest.fixture
def estudiante_bd(db_session: Session) -> EstudianteModel:
    est = EstudianteModel(
        codigo="ALU-2026-500",
        dni="74561234",
        nombres="Lucía",
        apellidos="Quispe Salas",
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        carnet_codigo="DSV-2026-500",
        estado="ACTIVO",
    )
    db_session.add(est)
    db_session.commit()
    return est


# ===========================================================================
# 1. Seguridad: RepositorioRoles, RepositorioUsuarios y RepositorioSesiones
# ===========================================================================


def test_repositorio_roles_crud_y_permisos_dinamicos(db_session: Session) -> None:
    sembrar_seguridad_base(db_session)
    repo = RepositorioRoles(db_session)

    # Lista roles base sembrados
    base = repo.listar()
    assert {r.codigo for r in base} == {"ADMIN", "COORDINADOR", "ADMIN_STAFF"}
    assert repo.obtener_por_codigo("NO_EXISTE") is None
    assert repo.obtener_id_por_codigo("NO_EXISTE") is None
    assert repo.obtener_id_por_codigo("ADMIN") is not None

    # Crear rol personalizado DOCENTE
    rol_docente = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Califica sus cursos asignados",
        permisos=frozenset(
            {
                PermisoOperacion.REGISTRAR_CALIFICACIONES,
                PermisoOperacion.CONSULTAR_CALIFICACIONES,
            }
        ),
    )
    guardado = repo.guardar(rol_docente)
    assert guardado == rol_docente

    # Actualizar permisos y estado inactivo
    actualizado = replace(
        guardado,
        permisos=frozenset({PermisoOperacion.CONSULTAR_CALIFICACIONES}),
        activo=False,
    )
    repo.guardar(actualizado)
    recuperado = repo.obtener_por_codigo("docente")
    assert recuperado is not None
    assert recuperado.activo is False
    assert recuperado.permisos == frozenset({PermisoOperacion.CONSULTAR_CALIFICACIONES})
    assert "DOCENTE" not in {r.codigo for r in repo.listar(solo_activos=True)}

    # Eliminar rol personalizado
    assert repo.eliminar("DOCENTE") is True
    assert repo.eliminar("DOCENTE") is False
    assert repo.obtener_por_codigo("DOCENTE") is None


def test_repositorio_roles_crea_permisos_si_bd_vacia(db_session: Session) -> None:
    repo = RepositorioRoles(db_session)
    rol_tesoreria = Rol(
        codigo="TESORERIA",
        nombre="Tesorería",
        descripcion="Gestión de pagos",
        permisos=frozenset({PermisoOperacion.GESTIONAR_PAGOS}),
    )
    guardado = repo.guardar(rol_tesoreria)
    assert guardado.codigo == "TESORERIA"
    assert repo.obtener_por_codigo("TESORERIA") == rol_tesoreria


def test_repositorio_usuarios_crud_unicidad_y_filtros(
    db_session: Session, usuario_admin_guardado: Usuario
) -> None:
    repo_roles = RepositorioRoles(db_session)
    repo_roles.guardar(
        Rol(
            codigo="DOCENTE",
            nombre="Docente",
            descripcion="Docente aula",
            permisos=frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
        )
    )
    repo = RepositorioUsuarios(db_session)

    pwd_hash, salt = hashear_password("Docente2026!")
    docente = repo.guardar(
        Usuario(
            id=0,
            username="Docente.Uno",
            password_hash=pwd_hash,
            salt=salt,
            nombre_completo="Juan Pérez",
            rol="DOCENTE",
            estado=EstadoUsuario.ACTIVO,
            creado_en=FECHA_UTC,
        )
    )
    assert docente.id > 0
    assert docente.username == "docente.uno"
    assert docente.rol == "DOCENTE"
    assert repo.obtener_por_id(docente.id) == docente
    assert repo.obtener_por_id(99999) is None
    assert repo.obtener_por_username("DOCENTE.UNO") == docente
    assert repo.obtener_por_username("inexistente") is None

    # Actualizar datos y desactivar usuario
    modificado = repo.guardar(
        replace(
            docente,
            nombre_completo="Juan Pérez Modificado",
            estado=EstadoUsuario.INACTIVO,
        )
    )
    assert modificado.nombre_completo == "Juan Pérez Modificado"
    assert modificado.estado == EstadoUsuario.INACTIVO

    # Filtros de listado
    assert len(repo.listar()) == 2
    assert [u.username for u in repo.listar(solo_activos=True)] == ["admin_repo"]
    assert [u.username for u in repo.listar(rol="DOCENTE")] == ["docente.uno"]
    assert [u.username for u in repo.listar(rol=RolUsuario.ADMIN)] == ["admin_repo"]

    # Guardar usuario con id explícito nuevo y validar username único
    creado_con_id = repo.guardar(
        Usuario(
            id=50,
            username="coord_50",
            password_hash=pwd_hash,
            salt=salt,
            nombre_completo="Coord 50",
            rol=RolUsuario.COORDINADOR,
            estado=EstadoUsuario.ACTIVO,
            creado_en=None,
        )
    )
    assert creado_con_id.id == 50
    assert creado_con_id.rol == RolUsuario.COORDINADOR

    with pytest.raises(IntegrityError):
        repo.guardar(
            Usuario(
                id=0,
                username="admin_repo",
                password_hash="h",
                salt="s",
                nombre_completo="Duplicado",
                rol=RolUsuario.ADMIN_STAFF,
            )
        )
    db_session.rollback()


def test_repositorio_sesiones_ciclo_de_vida_y_revocaciones(
    db_session: Session, usuario_admin_guardado: Usuario
) -> None:
    repo_roles = RepositorioRoles(db_session)
    rol_doc = repo_roles.guardar(
        Rol(
            codigo="DOCENTE",
            nombre="Docente",
            descripcion="Docente",
            permisos=frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
        )
    )
    repo_usr = RepositorioUsuarios(db_session)
    pwd_hash, salt = hashear_password("DocPass2026!")
    docente = repo_usr.guardar(
        Usuario(
            id=0,
            username="doc_ses",
            password_hash=pwd_hash,
            salt=salt,
            nombre_completo="Docente Sesión",
            rol="DOCENTE",
        )
    )
    db_session.commit()

    repo_ses = RepositorioSesiones(db_session)
    s_admin = ServicioAutenticacionYPermisos.iniciar_sesion(
        "admin_repo",
        "AdminSeguro2026!",
        [usuario_admin_guardado],
        fecha_hora=FECHA_UTC,
    )
    s_doc = ServicioAutenticacionYPermisos.iniciar_sesion(
        "doc_ses",
        "DocPass2026!",
        [docente],
        fecha_hora=FECHA_UTC,
        roles=[rol_doc],
    )

    repo_ses.guardar(s_admin)
    repo_ses.guardar(s_doc)
    db_session.commit()

    recuperada = repo_ses.obtener_por_token(s_admin.token)
    assert recuperada is not None
    assert recuperada.rol == RolUsuario.ADMIN
    assert recuperada.fecha_inicio == FECHA_UTC
    assert repo_ses.obtener_por_token("tok-inexistente") is None
    assert len(repo_ses.listar_activas()) == 2
    assert len(repo_ses.listar_por_usuario(usuario_admin_guardado.id)) == 1

    # Actualizar sesión existente (cerrarla) mediante guardar
    cerrada = ServicioAutenticacionYPermisos.cerrar_sesion(s_admin)
    repo_ses.guardar(cerrada)
    assert repo_ses.obtener_por_token(s_admin.token).activa is False  # type: ignore[union-attr]
    assert repo_ses.listar_por_usuario(usuario_admin_guardado.id, solo_activas=True) == []

    # Revocar por token (inexistente, activa y ya revocada)
    assert repo_ses.revocar_por_token("tok-no-existe") is False
    assert repo_ses.revocar_por_token(s_doc.token, revocada_en=FECHA_UTC) is True
    assert repo_ses.revocar_por_token(s_doc.token) is False
    assert repo_ses.listar_activas() == []

    # Revocar por usuario y por rol (con sesiones activas y luego sin activas)
    s_doc_2 = ServicioAutenticacionYPermisos.iniciar_sesion(
        "doc_ses", "DocPass2026!", [docente], fecha_hora=FECHA_UTC, roles=[rol_doc]
    )
    s_admin_2 = ServicioAutenticacionYPermisos.iniciar_sesion(
        "admin_repo", "AdminSeguro2026!", [usuario_admin_guardado], fecha_hora=FECHA_UTC
    )
    repo_ses.guardar(s_doc_2)
    repo_ses.guardar(s_admin_2)
    assert repo_ses.revocar_por_rol("docente") == 1
    assert repo_ses.revocar_por_rol("docente") == 0
    assert repo_ses.revocar_por_usuario(usuario_admin_guardado.id) == 1
    assert repo_ses.revocar_por_usuario(usuario_admin_guardado.id) == 0
    assert repo_ses.listar_activas() == []


# ===========================================================================
# 2. Auditoría: RepositorioAuditoria append-only y cadena SHA-256
# ===========================================================================


def test_repositorio_auditoria_append_only_cadena_sha256_y_filtros(
    db_session: Session, usuario_admin_guardado: Usuario
) -> None:
    repo = RepositorioAuditoria(db_session)

    # Estrictamente append-only: sin métodos de actualización ni borrado
    for prohibido in ("update", "actualizar", "delete", "eliminar", "modificar"):
        assert not hasattr(repo, prohibido)

    assert repo.obtener_ultimo() is None
    assert repo.obtener_ultimo_hash() == HASH_GENESIS
    assert repo.siguiente_secuencia() == 1
    assert repo.contar() == 0

    ev1 = ServicioAuditoria.registrar_evento(
        usuario_id=usuario_admin_guardado.id,
        rol_ejecutante="ADMIN",
        operacion=TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
        entidad="ASISTENCIA",
        entidad_id="ast-100",
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=FECHA_LIMA,
        eventos_existentes=[],
        alumno_id=500,
        metodo_asistencia="CARNET",
        contexto_academico=ContextoAcademicoAuditoria("Secundaria", "3ro", "A"),
        estado_anterior=None,
        estado_nuevo="PUNTUAL",
        detalle={"origen": "lector_qr"},
        persistir=repo.registrar,
    )
    assert repo.obtener_ultimo_hash() == ev1.hash_integridad
    assert repo.siguiente_secuencia() == 2

    ev2 = ServicioAuditoria.registrar_evento(
        usuario_id=0,
        rol_ejecutante="SYSTEM_CRON",
        operacion=TipoOperacionAuditoria.CIERRE_ESCOLAR,
        entidad="CIERRE_DIARIO",
        entidad_id="2026-11-27",
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=FECHA_LIMA + timedelta(minutes=30),
        eventos_existentes=[ev1],
        estado_nuevo="CERRADO",
        motivo="Cierre automático 09:00",
        detalle={"ausentes": 3},
        persistir=repo.registrar,
    )
    db_session.commit()
    db_session.expire_all()

    assert repo.contar() == 2
    assert repo.obtener_por_id(ev1.id) == ev1
    assert repo.obtener_por_id("aud-inexistente") is None
    assert repo.obtener_ultimo() == ev2

    # Verificación criptográfica SHA-256 sobre los eventos deserializados desde SQLite
    todos = repo.listar()
    assert len(todos) == 2
    verificacion = ServicioAuditoria.verificar_integridad(
        todos,
        operador=usuario_admin_guardado,
        total_esperado=repo.contar(),
        roles=ServicioGestionRoles.obtener_roles_base(),
    )
    assert verificacion.integra is True

    # Filtros combinados
    filtrados = repo.listar(
        FiltroAuditoria(
            fecha_desde=FECHA_LIMA,
            fecha_hasta=FECHA_LIMA + timedelta(minutes=10),
            usuario_id=usuario_admin_guardado.id,
            rol="ADMIN",
            operacion=TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
            entidad="ASISTENCIA",
            alumno_id=500,
            resultado=ResultadoAuditoria.CONFIRMADA,
        )
    )
    assert [e.id for e in filtrados] == [ev1.id]

    # Filtro por nombre de operación en texto plano
    solo_cierre = repo.listar(FiltroAuditoria(operacion="CIERRE_ESCOLAR"))
    assert [e.id for e in solo_cierre] == [ev2.id]

    # Intento de duplicar evento/secuencia falla por unicidad en BD
    with pytest.raises(IntegrityError):
        repo.registrar(ev1)
    db_session.rollback()

    # Alteración directa en BD rompe verificación SHA-256
    fila_ev1 = db_session.get(AuditoriaEventoModel, ev1.id)
    assert fila_ev1 is not None
    fila_ev1.motivo = "Manipulación indebida"
    db_session.flush()
    verif_alterada = ServicioAuditoria.verificar_integridad(
        repo.listar(),
        operador=usuario_admin_guardado,
        total_esperado=repo.contar(),
        roles=ServicioGestionRoles.obtener_roles_base(),
    )
    assert verif_alterada.integra is False
    assert ev1.id in verif_alterada.ids_alterados
    db_session.rollback()


# ===========================================================================
# 3. Asistencia, Aforo, Justificaciones, Períodos y Calendario
# ===========================================================================


def test_repositorio_asistencia_crud_unicidad_notificacion_e_historial(
    db_session: Session,
    usuario_admin_guardado: Usuario,
    estudiante_bd: EstudianteModel,
) -> None:
    repo = RepositorioAsistencia(db_session)
    fecha = date(2026, 11, 2)

    ast = RegistroAsistencia(
        id="ast-repo-001",
        alumno_id=estudiante_bd.id,
        fecha_escolar=fecha,
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=usuario_admin_guardado.id,
        rol_usuario=RolUsuario.ADMIN,
        auditoria_id="aud-001",
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
    )
    guardada = repo.guardar(ast)
    assert guardada == ast
    assert repo.obtener_por_id("ast-repo-001") == ast
    assert repo.obtener_por_id("ast-inexistente") is None
    assert repo.obtener_por_alumno_y_fecha(estudiante_bd.id, fecha) == ast
    assert repo.obtener_por_alumno_y_fecha(estudiante_bd.id, date(2026, 11, 9)) is None

    # Actualización de la misma asistencia + historial
    corregida = replace(
        ast,
        estado=EstadoAsistencia.JUSTIFICADO,
        estado_anterior=EstadoAsistencia.PUNTUAL,
        motivo_correccion="Corrección validada",
    )
    repo.guardar(corregida)
    repo.registrar_historial(corregida, fecha_hora=FECHA_LIMA)
    repo.registrar_historial(corregida)
    historial = repo.listar_historial(ast.id)
    assert len(historial) == 2
    assert historial[0]["estado_nuevo"] == "JUSTIFICADO"
    assert historial[1]["fecha_hora"].tzinfo == ZONA_HORARIA_LIMA  # type: ignore[union-attr]

    # Registro creado por SYSTEM_CRON (usuario_id=0 -> FK nullable)
    ast_cron = RegistroAsistencia(
        id="ast-repo-cron",
        alumno_id=estudiante_bd.id,
        fecha_escolar=date(2026, 11, 3),
        hora_efectiva=time(9, 0, 0),
        estado=EstadoAsistencia.AUSENTE,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=0,
        rol_usuario="SYSTEM_CRON",
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
    )
    recuperada_cron = repo.guardar(ast_cron)
    assert recuperada_cron.usuario_id == 0
    assert recuperada_cron.rol_usuario == "SYSTEM_CRON"

    # Consultas por fecha, alumno y rango
    assert [r.id for r in repo.listar_por_fecha(fecha)] == ["ast-repo-001"]
    assert len(repo.listar_por_alumno(estudiante_bd.id)) == 2
    assert [
        r.id
        for r in repo.listar_por_alumno(
            estudiante_bd.id,
            fecha_desde=date(2026, 11, 3),
            fecha_hasta=date(2026, 11, 3),
        )
    ] == ["ast-repo-cron"]
    assert len(repo.listar_por_rango(date(2026, 11, 1), date(2026, 11, 5))) == 2

    # Flag notificacion_ausencia_enviada
    assert repo.marcar_notificacion_ausencia_enviada("no-existe") is False
    assert repo.marcar_notificacion_ausencia_enviada("ast-repo-cron") is True
    assert repo.listar_alumnos_notificados_ausencia(date(2026, 11, 3)) == frozenset(
        {estudiante_bd.id}
    )

    db_session.commit()

    # UNIQUE(estudiante_id, fecha_escolar)
    with pytest.raises(IntegrityError):
        repo.guardar(replace(ast, id="ast-repo-dup"))
    db_session.rollback()


def test_repositorio_aforo_cierres_y_configuracion(
    db_session: Session, usuario_admin_guardado: Usuario
) -> None:
    repo = RepositorioAforo(db_session)
    fecha = date(2026, 11, 4)

    assert repo.obtener_cierre_por_fecha(fecha) is None
    assert repo.listar_fechas_cerradas() == frozenset()

    cierre = EventoCierreDiario(
        id="evt-cie-repo-1",
        fecha_escolar=fecha,
        hora_cierre=time(9, 0, 0),
        total_ausentes_marcados=4,
        alumnos_ids_afectados=[],
    )
    guardado = repo.registrar_cierre(
        cierre,
        actor_ejecutante="SYSTEM_CRON",
        usuario_id=None,
    )
    assert guardado.id == "evt-cie-repo-1"
    assert repo.obtener_cierre_por_fecha(fecha) == guardado
    assert repo.listar_fechas_cerradas() == frozenset({fecha})

    # Configuración del sistema (crear y actualizar)
    assert repo.obtener_configuracion("hora_cierre_oficial", "09:00:00") == "09:00:00"
    repo.guardar_configuracion(
        "hora_cierre_oficial", "08:45:00", actualizado_por=usuario_admin_guardado.id
    )
    assert repo.obtener_configuracion("hora_cierre_oficial") == "08:45:00"
    repo.guardar_configuracion(
        "hora_cierre_oficial", "09:15:00", actualizado_por=usuario_admin_guardado.id
    )
    assert repo.obtener_configuracion("hora_cierre_oficial") == "09:15:00"
    db_session.commit()

    # Doble cierre en misma fecha viola UNIQUE
    with pytest.raises(IntegrityError):
        repo.registrar_cierre(
            replace(cierre, id="evt-cie-repo-2"),
            actor_ejecutante="ADMIN",
            usuario_id=usuario_admin_guardado.id,
        )
    db_session.rollback()


def test_repositorio_justificaciones_periodos_y_calendario(
    db_session: Session,
    usuario_admin_guardado: Usuario,
    estudiante_bd: EstudianteModel,
) -> None:
    # Períodos académicos
    repo_per = RepositorioPeriodos(db_session)
    periodo = PeriodoAcademico(
        id=0,
        nombre="Bimestre I - 2026",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 5, 15),
        cerrado=False,
        anio_lectivo=2026,
        tipo_periodo=TipoPeriodo.BIMESTRE,
        orden=1,
        fecha_limite_notas=date(2026, 5, 22),
    )
    p_guardado = repo_per.guardar(periodo)
    assert p_guardado.id > 0
    assert repo_per.obtener_por_id(p_guardado.id) == p_guardado
    assert repo_per.obtener_por_id(9999) is None
    assert repo_per.obtener_por_nombre("bimestre i - 2026") == p_guardado
    assert repo_per.obtener_por_nombre("no existe") is None

    # Actualizar período existente
    p_cerrado = repo_per.guardar(replace(p_guardado, cerrado=True))
    assert p_cerrado.cerrado is True
    assert repo_per.listar(anio_lectivo=2026) == [p_cerrado]
    assert repo_per.listar(solo_abiertos=True) == []

    # Crear y eliminar segundo período con id explícito
    p2 = repo_per.guardar(
        PeriodoAcademico(
            id=20,
            nombre="Bimestre II - 2026",
            fecha_inicio=date(2026, 5, 18),
            fecha_fin=date(2026, 7, 24),
            anio_lectivo=2026,
            orden=2,
            fecha_limite_notas=date(2026, 7, 30),
        )
    )
    assert p2.id == 20
    assert repo_per.eliminar(20) is True
    assert repo_per.eliminar(20) is False

    # Justificaciones + adjuntos + filtros
    repo_ast = RepositorioAsistencia(db_session)
    ast = repo_ast.guardar(
        RegistroAsistencia(
            id="ast-just-01",
            alumno_id=estudiante_bd.id,
            fecha_escolar=date(2026, 4, 10),
            hora_efectiva=time(7, 25, 0),
            estado=EstadoAsistencia.JUSTIFICADO,
            minutos_tardanza=0,
            metodo=MetodoRegistro.CARNET,
            usuario_id=usuario_admin_guardado.id,
            rol_usuario=RolUsuario.ADMIN,
            nivel="Secundaria",
            grado="3ro",
            seccion="A",
        )
    )
    repo_just = RepositorioJustificaciones(db_session)
    adj1 = AdjuntoJustificacion("certificado.pdf", 2048)
    just = Justificacion(
        id="just-repo-01",
        asistencia_id=ast.id,
        alumno_id=estudiante_bd.id,
        fecha_solicitud=date(2026, 4, 10),
        categoria=CategoriaJustificacion.MEDICA,
        motivo="Atención médica",
        estado=EstadoJustificacion.APROBADA,
        usuario_id=usuario_admin_guardado.id,
        rol_usuario=RolUsuario.ADMIN,
        fecha_resolucion=FECHA_LIMA,
        adjuntos=(adj1,),
        minutos_tardanza_original=10,
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
    )
    j_guardada = repo_just.guardar(
        just,
        periodo_id=p_guardado.id,
        rutas_adjuntos={"certificado.pdf": "/privado/certificado.pdf"},
    )
    assert j_guardada.adjuntos == (adj1,)
    assert repo_just.obtener_por_id("just-repo-01") == j_guardada
    assert repo_just.obtener_por_id("no-existe") is None
    assert [j.id for j in repo_just.obtener_por_asistencia(ast.id)] == ["just-repo-01"]

    # Actualizar justificación agregando segundo adjunto y reasignando periodo_id
    adj2 = AdjuntoJustificacion("receta.png", 1024)
    j_mod = repo_just.guardar(
        replace(j_guardada, motivo="Actualizado", adjuntos=(adj1, adj2)),
        periodo_id=p_guardado.id,
    )
    assert len(j_mod.adjuntos) == 2
    assert len(repo_just.listar()) == 1

    # Filtros de consulta
    filtradas = repo_just.listar(
        FiltroJustificaciones(
            nivel="secundaria",
            grado="3RO",
            seccion="a",
            alumno_id=estudiante_bd.id,
            categoria=CategoriaJustificacion.MEDICA,
            estado=EstadoJustificacion.APROBADA,
            fecha_desde=date(2026, 4, 1),
            fecha_hasta=date(2026, 4, 30),
        )
    )
    assert [j.id for j in filtradas] == ["just-repo-01"]
    assert repo_just.listar(FiltroJustificaciones(nivel="Primaria")) == []

    # Calendario escolar (feriado, suspensión excepcional y sábado recuperativo)
    repo_cal = RepositorioCalendario(db_session)
    feriado = date(2026, 7, 28)
    suspension = date(2026, 8, 12)
    sabado_lectivo = date(2026, 11, 7)
    repo_cal.guardar_fecha(feriado, es_lectivo=False, descripcion="Fiestas Patrias")
    repo_cal.guardar_fecha(
        feriado, es_lectivo=False, descripcion="Fiestas Patrias Oficial"
    )
    repo_cal.guardar_fecha(
        suspension, es_lectivo=False, es_excepcion=True, descripcion="Suspensión excepcional"
    )
    repo_cal.guardar_fecha(
        sabado_lectivo, es_lectivo=True, es_excepcion=True, descripcion="Recuperación"
    )

    calendario = repo_cal.obtener_calendario()
    assert calendario.es_dia_lectivo(feriado) is False
    assert calendario.es_dia_lectivo(suspension) is False
    assert calendario.es_dia_lectivo(sabado_lectivo) is True
    assert len(repo_cal.listar_fechas()) == 3
    assert repo_cal.eliminar_fecha(feriado) is True
    assert repo_cal.eliminar_fecha(feriado) is False


# ===========================================================================
# 4. Atomicidad transaccional (sin commit interno -> rollback revierte todo)
# ===========================================================================


def test_rollback_atomico_revierte_asistencia_y_auditoria_sin_commit_interno(
    db_session: Session,
    usuario_admin_guardado: Usuario,
    estudiante_bd: EstudianteModel,
) -> None:
    repo_ast = RepositorioAsistencia(db_session)
    repo_aud = RepositorioAuditoria(db_session)

    ast = RegistroAsistencia(
        id="ast-atom-01",
        alumno_id=estudiante_bd.id,
        fecha_escolar=date(2026, 11, 10),
        hora_efectiva=time(7, 5, 0),
        estado=EstadoAsistencia.PUNTUAL,
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=usuario_admin_guardado.id,
        rol_usuario=RolUsuario.ADMIN,
    )
    repo_ast.guardar(ast)
    ServicioAuditoria.registrar_evento(
        usuario_id=usuario_admin_guardado.id,
        rol_ejecutante="ADMIN",
        operacion=TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
        entidad="ASISTENCIA",
        entidad_id=ast.id,
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=FECHA_LIMA,
        persistir=repo_aud.registrar,
    )

    # Simulamos un fallo posterior en la misma unidad de trabajo: rollback revierte todo
    db_session.rollback()

    assert repo_ast.obtener_por_id("ast-atom-01") is None
    assert repo_aud.contar() == 0
