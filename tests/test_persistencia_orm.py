"""Pruebas de persistencia ORM SQLAlchemy 2.0 para los 5 bloques del DER v2."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.dominio.usuarios import MATRIZ_PERMISOS, PermisoOperacion
from src.infraestructura import (
    Base,
    crear_motor,
    crear_session_factory,
    inicializar_bd,
    obtener_database_url,
    sembrar_seguridad_base,
)
from src.infraestructura.modelos import (
    ActividadEvaluableModel,
    AlertaPagoSilenciosaModel,
    ApoderadoModel,
    AsignacionDocenteModel,
    AsistenciaHistorialModel,
    AsistenciaModel,
    AuditoriaEventoModel,
    BoletaEmitidaModel,
    CalendarioEscolarModel,
    CalificacionModel,
    CarnetModel,
    CierreDiarioModel,
    ConfiguracionSistemaModel,
    CursoModel,
    EstudianteApoderadoModel,
    EstudianteEstadoHistorialModel,
    EstudianteModel,
    JustificacionAdjuntoModel,
    JustificacionModel,
    NotificacionWhatsappModel,
    ObligacionPagoModel,
    PeriodoAcademicoModel,
    PermisoModel,
    RolModel,
    RolPermisoModel,
    RubroEvaluacionModel,
    SalonModel,
    SesionUsuarioModel,
    UsuarioModel,
)


@pytest.fixture
def usuario_operador(db_session: Session) -> UsuarioModel:
    user = UsuarioModel(
        username="jluna_qa",
        password_hash="argon2id$hashedpasswordstring",
        rol="ADMIN_STAFF",
        activo=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def estudiante_ejemplo(db_session: Session) -> EstudianteModel:
    est = EstudianteModel(
        codigo="ALU-2026-001",
        dni="72945734",
        nombres="Eduardo",
        apellidos="Luna Lezano",
        nivel="Secundaria",
        grado="5to",
        seccion="A",
        carnet_codigo="CRN-EDU-7294",
        estado="ACTIVO",
    )
    db_session.add(est)
    db_session.commit()
    return est


# ---------------------------------------------------------------------------
# Pruebas base heredadas (retrocompatibilidad obligatoria DB1/DB2/DB3)
# ---------------------------------------------------------------------------


def test_guardar_estudiante_con_asistencias_1_a_n(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    """Ciclo 1: Guardar y consultar relación 1:N entre Estudiante y Asistencias (DB2)."""
    ast1 = AsistenciaModel(
        id="ast-001",
        estudiante=estudiante_ejemplo,
        usuario=usuario_operador,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 10, 0),
        estado="PUNTUAL",
        minutos_tardanza=0,
        metodo="CARNET",
    )
    ast2 = AsistenciaModel(
        id="ast-002",
        estudiante=estudiante_ejemplo,
        usuario=usuario_operador,
        fecha_escolar=date(2026, 11, 3),
        hora_efectiva=time(7, 20, 0),
        estado="TARDANZA",
        minutos_tardanza=5,
        metodo="MANUAL_DNI",
    )
    db_session.add_all([ast1, ast2])
    db_session.commit()

    stmt = select(EstudianteModel).filter_by(codigo="ALU-2026-001")
    est_db = db_session.scalars(stmt).first()

    assert est_db is not None
    assert len(est_db.asistencias) == 2
    assert est_db.asistencias[0].estado == "PUNTUAL"
    assert est_db.asistencias[1].minutos_tardanza == 5
    assert est_db.asistencias[0].usuario is not None
    assert est_db.asistencias[0].usuario.username == "jluna_qa"


def test_guardar_asistencia_con_justificacion_1_a_n(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    """Ciclo 2: Guardar y consultar Asistencia con Justificación médica asociada."""
    ast = AsistenciaModel(
        id="ast-aus-01",
        estudiante=estudiante_ejemplo,
        usuario=usuario_operador,
        fecha_escolar=date(2026, 11, 4),
        hora_efectiva=time(8, 0, 0),
        estado="AUSENTE",
        minutos_tardanza=0,
        metodo="MANUAL_BUSQUEDA",
    )
    db_session.add(ast)
    db_session.flush()

    just = JustificacionModel(
        asistencia=ast,
        estudiante_id=estudiante_ejemplo.id,
        usuario_id=usuario_operador.id,
        motivo="Cita médica de emergencia odontológica con certificado",
        categoria="MEDICA",
        estado="APROBADA",
    )
    db_session.add(just)
    db_session.commit()

    ast_db = db_session.scalars(select(AsistenciaModel).filter_by(id="ast-aus-01")).first()
    assert ast_db is not None
    assert len(ast_db.justificaciones) == 1
    assert ast_db.justificaciones[0].categoria == "MEDICA"
    assert ast_db.justificaciones[0].asistencia.id == "ast-aus-01"


def test_eliminar_estudiante_elimina_asistencias_en_cascada(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    """Ciclo 3: Comprobar eliminación en cascada (cascade='all, delete-orphan') (DB3 Rúbrica)."""
    ast = AsistenciaModel(
        id="ast-cascada-01",
        estudiante=estudiante_ejemplo,
        usuario=usuario_operador,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(7, 5, 0),
        estado="PUNTUAL",
        minutos_tardanza=0,
        metodo="CARNET",
    )
    db_session.add(ast)
    db_session.commit()

    assert (
        db_session.scalars(select(AsistenciaModel).filter_by(id="ast-cascada-01")).first()
        is not None
    )

    db_session.delete(estudiante_ejemplo)
    db_session.commit()

    asistencia_huerfana = db_session.scalars(
        select(AsistenciaModel).filter_by(id="ast-cascada-01")
    ).first()
    assert asistencia_huerfana is None


def test_eliminar_asistencia_elimina_justificaciones_en_cascada(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    """Comprobar que al borrar una asistencia se eliminan sus justificaciones huérfanas."""
    ast = AsistenciaModel(
        id="ast-cascada-02",
        estudiante=estudiante_ejemplo,
        usuario=usuario_operador,
        fecha_escolar=date(2026, 11, 2),
        hora_efectiva=time(8, 0, 0),
        estado="AUSENTE",
        minutos_tardanza=0,
        metodo="MANUAL_DNI",
    )
    db_session.add(ast)
    db_session.flush()

    just = JustificacionModel(
        asistencia=ast,
        estudiante_id=estudiante_ejemplo.id,
        usuario_id=usuario_operador.id,
        motivo="Permiso familiar por viaje",
        categoria="PERMISO_FAMILIAR",
        estado="APROBADA",
    )
    db_session.add(just)
    db_session.commit()

    db_session.delete(ast)
    db_session.commit()

    assert (
        db_session.scalars(select(AsistenciaModel).filter_by(id="ast-cascada-02")).first()
        is None
    )
    assert (
        db_session.scalars(
            select(JustificacionModel).filter_by(motivo="Permiso familiar por viaje")
        ).first()
        is None
    )


# ---------------------------------------------------------------------------
# Fábrica de base de datos, PRAGMA foreign_keys y sembrado idempotente
# ---------------------------------------------------------------------------


def test_base_datos_obtener_url_y_inicializar_bd_idempotente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert obtener_database_url() == "sqlite:///domingo_savio.db"
    assert obtener_database_url("sqlite:///:memory:") == "sqlite:///:memory:"

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/savio")
    assert obtener_database_url() == "postgresql+psycopg://user:pass@localhost:5432/savio"

    engine = crear_motor("sqlite:///:memory:")
    try:
        inicializar_bd(engine)
        # Segunda ejecución es estrictamente idempotente
        inicializar_bd(engine)

        tablas = set(inspect(engine).get_table_names())
        esperadas = {
            "roles",
            "permisos",
            "rol_permisos",
            "usuarios",
            "sesiones_usuario",
            "auditoria_eventos",
            "salones",
            "cursos",
            "asignaciones_docentes",
            "estudiantes",
            "estudiante_estados_historial",
            "apoderados",
            "estudiante_apoderado",
            "carnets",
            "asistencias",
            "asistencia_historial",
            "periodos_academicos",
            "justificaciones",
            "justificacion_adjuntos",
            "calendario_escolar",
            "configuracion_sistema",
            "cierres_diarios",
            "notificaciones_whatsapp",
            "obligaciones_pago",
            "alertas_pago_silenciosas",
            "rubros_evaluacion",
            "actividades_evaluables",
            "calificaciones",
            "boletas_emitidas",
        }
        assert esperadas.issubset(tablas)

        session_factory = crear_session_factory(engine)
        with session_factory() as session:
            fk_activo = session.execute(text("PRAGMA foreign_keys")).scalar_one()
            assert fk_activo == 1

            total_permisos = session.scalar(select(func.count(PermisoModel.codigo)))
            assert total_permisos == len(PermisoOperacion)

            roles = {r.codigo: r for r in session.scalars(select(RolModel)).all()}
            assert set(roles) == {"ADMIN", "COORDINADOR", "ADMIN_STAFF"}
            assert all(r.es_sistema and r.activo for r in roles.values())

            for rol_enum, permisos_esperados in MATRIZ_PERMISOS.items():
                codigos_bd = {
                    rp.permiso_codigo
                    for rp in session.scalars(
                        select(RolPermisoModel).filter_by(rol_id=roles[rol_enum.value].id)
                    ).all()
                }
                assert codigos_bd == {p.value for p in permisos_esperados}

            # Re-sembrar directamente en sesión también es idempotente
            sembrar_seguridad_base(session)
            session.commit()
            assert session.scalar(select(func.count(RolModel.id))) == 3
    finally:
        engine.dispose()


def test_crear_motor_acepta_url_no_sqlite_sin_listener_pragma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registrado: list[str] = []

    class _FakeEngine:
        pass

    def _fake_create_engine(url: str, *, echo: bool = False, future: bool = True) -> _FakeEngine:
        registrado.append(f"{url}|{echo}|{future}")
        return _FakeEngine()

    monkeypatch.setattr("src.infraestructura.base_datos.create_engine", _fake_create_engine)
    motor = crear_motor("postgresql://user:pass@localhost/savio", echo=True)
    assert isinstance(motor, _FakeEngine)
    assert registrado == ["postgresql://user:pass@localhost/savio|True|True"]


# ---------------------------------------------------------------------------
# Bloque 1: Seguridad, RBAC Dinámico y Auditoría append-only
# ---------------------------------------------------------------------------


def test_bloque1_rbac_sesiones_y_auditoria_sin_cascada(db_session: Session) -> None:
    sembrar_seguridad_base(db_session)
    db_session.flush()

    rol_admin = db_session.scalars(select(RolModel).filter_by(codigo="ADMIN")).one()
    usuario = UsuarioModel(
        username="admin_v2",
        nombre_completo="Gari Joel Chávez",
        password_hash="hash_pbkdf2",
        salt="salt_hex_1234",
        rol_id=rol_admin.id,
        rol="ADMIN",
        estado="ACTIVO",
        activo=True,
    )
    db_session.add(usuario)
    db_session.flush()

    ahora = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
    sesion = SesionUsuarioModel(
        token="tok-sesion-v2-001",
        usuario_id=usuario.id,
        rol_codigo_snapshot="ADMIN",
        fecha_inicio=ahora,
        fecha_expiracion=ahora + timedelta(hours=8),
        activa=True,
    )
    evento = AuditoriaEventoModel(
        id="aud-001",
        secuencia=1,
        fecha_hora=ahora,
        usuario_id=usuario.id,
        rol_ejecutante="ADMIN",
        operacion="INICIAR_SESION",
        entidad="USUARIO",
        entidad_id=str(usuario.id),
        resultado="CONFIRMADA",
        detalle_json='{"origen":"web"}',
        hash_anterior="GENESIS",
        hash_integridad="a" * 64,
    )
    evento_cron = AuditoriaEventoModel(
        id="aud-002",
        secuencia=2,
        fecha_hora=ahora,
        usuario_id=0,
        rol_ejecutante="SYSTEM_CRON",
        operacion="CIERRE_ESCOLAR",
        entidad="ASISTENCIA",
        entidad_id="2026-11-26",
        resultado="CONFIRMADA",
        detalle_json="{}",
        hash_anterior="a" * 64,
        hash_integridad="b" * 64,
    )
    db_session.add_all([sesion, evento, evento_cron])
    db_session.commit()

    # Eliminar la sesión y el usuario NO elimina en cascada los registros de auditoría
    db_session.delete(sesion)
    db_session.delete(usuario)
    db_session.commit()

    auditorias = db_session.scalars(
        select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia)
    ).all()
    assert [a.id for a in auditorias] == ["aud-001", "aud-002"]


# ---------------------------------------------------------------------------
# Bloque 2: Salones, Cursos, Asignación Docente, Alumnos, Apoderados y Carnets
# ---------------------------------------------------------------------------


def test_bloque2_estructura_academica_matricula_carnets_y_unicos(
    db_session: Session, usuario_operador: UsuarioModel
) -> None:
    salon = SalonModel(
        anio_lectivo=2026,
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        capacidad_maxima=30,
        activo=True,
    )
    curso = CursoModel(
        anio_lectivo=2026,
        nivel="Secundaria",
        grado="3ro",
        codigo="MAT-301",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=6,
    )
    db_session.add_all([salon, curso])
    db_session.flush()

    asignacion = AsignacionDocenteModel(
        id="asg-001",
        usuario_docente_id=usuario_operador.id,
        curso_id=curso.id,
        salon_id=salon.id,
        anio_lectivo=2026,
        activa=True,
        asignado_por=usuario_operador.id,
    )
    estudiante = EstudianteModel(
        codigo="EST-2026-100",
        dni="71112222",
        nombres="Lucía",
        apellidos="Salas",
        fecha_nacimiento=date(2012, 5, 14),
        salon_id=salon.id,
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        estado="ACTIVO",
    )
    apoderado = ApoderadoModel(
        nombres="María",
        apellidos="Salas",
        documento="40112233",
        parentesco="Madre",
        telefono_whatsapp="+51987654321",
        activo=True,
    )
    db_session.add_all([asignacion, estudiante, apoderado])
    db_session.flush()

    vinculo = EstudianteApoderadoModel(
        estudiante_id=estudiante.id,
        apoderado_id=apoderado.id,
        es_principal=True,
    )
    historial_estado = EstudianteEstadoHistorialModel(
        id="est-hist-001",
        estudiante_id=estudiante.id,
        estado_anterior="ACTIVO",
        estado_nuevo="SUSPENDIDO",
        motivo="Medida disciplinaria",
        fecha_inicio=date(2026, 6, 1),
        fecha_fin=date(2026, 6, 5),
        usuario_id=usuario_operador.id,
        rol_usuario="ADMIN",
    )
    carnet = CarnetModel(
        id="car-001",
        estudiante_id=estudiante.id,
        codigo_qr="DSV-2026-ABCDEF123456",
        estado="ACTIVO",
        emitido_por=usuario_operador.id,
    )
    db_session.add_all([vinculo, historial_estado, carnet])
    db_session.commit()

    carnet_db = db_session.scalars(
        select(CarnetModel).filter_by(codigo_qr="DSV-2026-ABCDEF123456")
    ).one()
    asig_db = db_session.scalars(select(AsignacionDocenteModel).filter_by(id="asg-001")).one()
    assert carnet_db.id == "car-001"
    assert asig_db.curso_id == curso.id

    # UNIQUE(anio_lectivo, nivel, grado, seccion) en salones
    db_session.add(
        SalonModel(anio_lectivo=2026, nivel="Secundaria", grado="3ro", seccion="A")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # UNIQUE(anio_lectivo, nivel, grado, codigo) en cursos
    db_session.add(
        CursoModel(
            anio_lectivo=2026,
            nivel="Secundaria",
            grado="3ro",
            codigo="MAT-301",
            nombre="Matemática Duplicada",
            area_curricular="Matemática",
            horas_semanales=4,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # UNIQUE(codigo_qr) en carnets
    db_session.add(
        CarnetModel(
            id="car-dup",
            estudiante_id=estudiante.id,
            codigo_qr="DSV-2026-ABCDEF123456",
            estado="ACTIVO",
            emitido_por=usuario_operador.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Bloque 3: Asistencias UNIQUE, Historial, Períodos, Adjuntos, Calendario y Cierres
# ---------------------------------------------------------------------------


def test_bloque3_asistencias_unicas_periodos_adjuntos_calendario_y_cierres(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    periodo = PeriodoAcademicoModel(
        anio_lectivo=2026,
        tipo_periodo="BIMESTRE",
        orden=1,
        nombre="Bimestre I - 2026",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 5, 15),
        fecha_limite_notas=date(2026, 5, 22),
        cerrado=False,
    )
    calendario = CalendarioEscolarModel(
        fecha=date(2026, 7, 28),
        es_lectivo=False,
        es_excepcion=False,
        descripcion="Fiestas Patrias",
    )
    config = ConfiguracionSistemaModel(
        clave="hora_cierre_oficial",
        valor="09:00:00",
        actualizado_por=usuario_operador.id,
    )
    cierre = CierreDiarioModel(
        evento_id="evt-cie-001",
        fecha_escolar=date(2026, 4, 10),
        hora_cierre=time(9, 0, 0),
        total_ausentes_marcados=2,
        actor_ejecutante="SYSTEM_CRON",
        usuario_id=None,
    )
    asistencia = AsistenciaModel(
        id="ast-b3-001",
        estudiante_id=estudiante_ejemplo.id,
        usuario_id=usuario_operador.id,
        fecha_escolar=date(2026, 4, 10),
        hora_efectiva=time(7, 20, 0),
        estado="TARDANZA",
        minutos_tardanza=5,
        metodo="CARNET",
        nivel_snapshot="Secundaria",
        grado_snapshot="5to",
        seccion_snapshot="A",
        notificacion_ausencia_enviada=False,
    )
    db_session.add_all([periodo, calendario, config, cierre, asistencia])
    db_session.flush()

    hist = AsistenciaHistorialModel(
        asistencia_id=asistencia.id,
        usuario_id=usuario_operador.id,
        rol_usuario="ADMIN_STAFF",
        estado_anterior="TARDANZA",
        estado_nuevo="JUSTIFICADO",
        motivo="Cita médica",
        metodo="CARNET",
        auditoria_id="aud-h-1",
    )
    just = JustificacionModel(
        id="just-b3-001",
        asistencia_id=asistencia.id,
        estudiante_id=estudiante_ejemplo.id,
        periodo_id=periodo.id,
        usuario_id=usuario_operador.id,
        rol_usuario="ADMIN_STAFF",
        fecha_solicitud=date(2026, 4, 10),
        categoria="MEDICA",
        motivo="Certificado médico",
        estado="APROBADA",
        minutos_tardanza_original=5,
        nivel="Secundaria",
        grado="5to",
        seccion="A",
    )
    db_session.add_all([hist, just])
    db_session.flush()

    adjunto = JustificacionAdjuntoModel(
        justificacion_id=just.id,
        nombre_archivo="certificado.pdf",
        extension="pdf",
        tamano_bytes=2048,
        ruta_almacenamiento="/privado/just-b3-001/certificado.pdf",
    )
    db_session.add(adjunto)
    db_session.commit()

    just_db = db_session.scalars(select(JustificacionModel).filter_by(id="just-b3-001")).one()
    assert len(just_db.adjuntos) == 1
    assert just_db.adjuntos[0].extension == "pdf"

    # UNIQUE(estudiante_id, fecha_escolar) en asistencias
    db_session.add(
        AsistenciaModel(
            id="ast-b3-dup",
            estudiante_id=estudiante_ejemplo.id,
            usuario_id=usuario_operador.id,
            fecha_escolar=date(2026, 4, 10),
            hora_efectiva=time(7, 30, 0),
            estado="TARDANZA",
            minutos_tardanza=15,
            metodo="MANUAL_DNI",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # UNIQUE(fecha_escolar) en cierres_diarios
    db_session.add(
        CierreDiarioModel(
            evento_id="evt-cie-002",
            fecha_escolar=date(2026, 4, 10),
            hora_cierre=time(9, 5, 0),
            total_ausentes_marcados=0,
            actor_ejecutante="SYSTEM_CRON",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Bloque 4: Notificaciones WhatsApp, Obligaciones de Pago y Alertas Silenciosas
# ---------------------------------------------------------------------------


def test_bloque4_whatsapp_pagos_decimal_y_alertas_unicas(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    asistencia = AsistenciaModel(
        id="ast-b4-001",
        estudiante_id=estudiante_ejemplo.id,
        usuario_id=usuario_operador.id,
        fecha_escolar=date(2026, 5, 5),
        hora_efectiva=time(7, 10, 0),
        estado="PUNTUAL",
        minutos_tardanza=0,
        metodo="CARNET",
    )
    db_session.add(asistencia)
    db_session.flush()

    noti = NotificacionWhatsappModel(
        id="ntf-001",
        clave_idempotencia="ast-b4-001:PUNTUAL:2026-05-05",
        evento_origen_id="evt-001",
        asistencia_id=asistencia.id,
        estudiante_id=estudiante_ejemplo.id,
        fecha_escolar=date(2026, 5, 5),
        apoderado_nombre="María Lezano",
        telefono_destino="+51987654321",
        tipo="PUNTUAL",
        plantilla="ingreso_puntual",
        contenido="Ingreso puntual registrado",
        estado="PENDIENTE",
        intentos=0,
    )
    obligacion = ObligacionPagoModel(
        id="obl-001",
        estudiante_id=estudiante_ejemplo.id,
        concepto="Pensión Abril 2026",
        monto=Decimal("350.75"),
        fecha_vencimiento=date(2026, 4, 30),
        estado="VENCIDO",
    )
    alerta = AlertaPagoSilenciosaModel(
        id="alr-001",
        estudiante_id=estudiante_ejemplo.id,
        asistencia_id=asistencia.id,
        fecha_escolar=date(2026, 5, 5),
        cantidad_obligaciones_vencidas=1,
        monto_vencido_total=Decimal("350.75"),
        revisada=False,
    )
    db_session.add_all([noti, obligacion, alerta])
    db_session.commit()

    obl_db = db_session.scalars(select(ObligacionPagoModel).filter_by(id="obl-001")).one()
    assert obl_db.monto == Decimal("350.75")

    # UNIQUE(clave_idempotencia) en notificaciones_whatsapp
    db_session.add(
        NotificacionWhatsappModel(
            id="ntf-dup",
            clave_idempotencia="ast-b4-001:PUNTUAL:2026-05-05",
            asistencia_id=asistencia.id,
            estudiante_id=estudiante_ejemplo.id,
            fecha_escolar=date(2026, 5, 5),
            tipo="PUNTUAL",
            plantilla="ingreso_puntual",
            contenido="Duplicada",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # UNIQUE(estudiante_id, fecha_escolar) en alertas_pago_silenciosas
    db_session.add(
        AlertaPagoSilenciosaModel(
            id="alr-dup",
            estudiante_id=estudiante_ejemplo.id,
            asistencia_id=asistencia.id,
            fecha_escolar=date(2026, 5, 5),
            monto_vencido_total=Decimal("350.75"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Bloque 5: Calificaciones de 3 Niveles (Rubros -> Actividades -> Notas) y Boletas
# ---------------------------------------------------------------------------


def test_bloque5_libro_calificaciones_3_niveles_boletas_y_fk_estricta(
    db_session: Session, usuario_operador: UsuarioModel, estudiante_ejemplo: EstudianteModel
) -> None:
    salon = SalonModel(anio_lectivo=2026, nivel="Secundaria", grado="5to", seccion="A")
    curso = CursoModel(
        anio_lectivo=2026,
        nivel="Secundaria",
        grado="5to",
        codigo="MAT-501",
        nombre="Matemática V",
        area_curricular="Matemática",
        horas_semanales=6,
    )
    periodo = PeriodoAcademicoModel(
        anio_lectivo=2026,
        tipo_periodo="BIMESTRE",
        orden=1,
        nombre="Bimestre I - 5to",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 5, 15),
        fecha_limite_notas=date(2026, 5, 20),
    )
    db_session.add_all([salon, curso, periodo])
    db_session.flush()

    asignacion = AsignacionDocenteModel(
        id="asg-b5-001",
        usuario_docente_id=usuario_operador.id,
        curso_id=curso.id,
        salon_id=salon.id,
        anio_lectivo=2026,
    )
    db_session.add(asignacion)
    db_session.flush()

    rubro = RubroEvaluacionModel(
        id="rub-001",
        asignacion_docente_id=asignacion.id,
        periodo_id=periodo.id,
        nombre="Exámenes",
        peso_porcentaje=Decimal("50.00"),
    )
    db_session.add(rubro)
    db_session.flush()

    actividad = ActividadEvaluableModel(
        id="act-001",
        rubro_id=rubro.id,
        titulo="Examen Parcial 1",
        fecha=date(2026, 4, 20),
    )
    db_session.add(actividad)
    db_session.flush()

    calificacion = CalificacionModel(
        id="cal-001",
        actividad_id=actividad.id,
        estudiante_id=estudiante_ejemplo.id,
        nota=Decimal("18.50"),
        observacion="Excelente desempeño",
        usuario_id=usuario_operador.id,
    )
    boleta = BoletaEmitidaModel(
        id="bol-001",
        codigo_verificacion="BOL-2026-ABCDEF",
        estudiante_id=estudiante_ejemplo.id,
        periodo_id=periodo.id,
        anio_lectivo=2026,
        es_oficial=True,
        promedio_general=Decimal("18.50"),
        resumen_asistencia_json='{"puntuales":40,"tardanzas":1,"ausentes":0,"justificados":0}',
        emitido_por=usuario_operador.id,
    )
    db_session.add_all([calificacion, boleta])
    db_session.commit()

    cal_db = db_session.scalars(select(CalificacionModel).filter_by(id="cal-001")).one()
    assert cal_db.nota == Decimal("18.50")

    # UNIQUE(actividad_id, estudiante_id) en calificaciones
    db_session.add(
        CalificacionModel(
            id="cal-dup",
            actividad_id=actividad.id,
            estudiante_id=estudiante_ejemplo.id,
            nota=Decimal("19.00"),
            usuario_id=usuario_operador.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Integridad referencial estricta: FK inexistente debe fallar por PRAGMA foreign_keys=ON
    db_session.add(
        RubroEvaluacionModel(
            id="rub-fk-rota",
            asignacion_docente_id="asg-inexistente",
            periodo_id=periodo.id,
            nombre="Inválido",
            peso_porcentaje=Decimal("50.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # UNIQUE(codigo_verificacion) en boletas_emitidas
    db_session.add(
        BoletaEmitidaModel(
            id="bol-dup",
            codigo_verificacion="BOL-2026-ABCDEF",
            estudiante_id=estudiante_ejemplo.id,
            periodo_id=periodo.id,
            anio_lectivo=2026,
            es_oficial=True,
            promedio_general=Decimal("18.50"),
            emitido_por=usuario_operador.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert Base.metadata.tables["calificaciones"] is not None


def test_sembrar_admin_inicial_idempotente_y_por_entorno(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.dominio.usuarios import UsuarioException, verificar_password
    from src.infraestructura.base_datos import sembrar_admin_inicial, sembrar_seguridad_base

    sembrar_seguridad_base(db_session)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    # Sin variables de entorno no crea ningún usuario
    assert sembrar_admin_inicial(db_session) is False

    # Política mínima de contraseña (8 caracteres)
    with pytest.raises(UsuarioException):
        sembrar_admin_inicial(db_session, username="admin", password="123")

    # Con variables de entorno válidas crea el ADMIN inicial con hash PBKDF2
    monkeypatch.setenv("ADMIN_USERNAME", "AdminPrincipal")
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminSeguro2026!")
    assert sembrar_admin_inicial(db_session) is True

    creado = db_session.scalars(
        select(UsuarioModel).where(UsuarioModel.username == "adminprincipal")
    ).one()
    assert creado.rol == "ADMIN"
    assert creado.activo is True
    assert verificar_password("AdminSeguro2026!", creado.password_hash, creado.salt) is True

    # Segunda ejecución es idempotente y no duplica
    assert sembrar_admin_inicial(db_session) is False

