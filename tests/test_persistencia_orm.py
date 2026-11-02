from datetime import date, time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from src.infraestructura.modelos import (
        AsistenciaModel,
        EstudianteModel,
        JustificacionModel,
        UsuarioModel,
    )
except ImportError:
    from modelos_orm import (  # type: ignore
        AsistenciaModel,
        EstudianteModel,
        JustificacionModel,
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

    # Verificar que existe la asistencia
    assert (
        db_session.scalars(select(AsistenciaModel).filter_by(id="ast-cascada-01")).first()
        is not None
    )

    # Eliminar al padre (Estudiante)
    db_session.delete(estudiante_ejemplo)
    db_session.commit()

    # Comprobar que el hijo (Asistencia) fue eliminado automáticamente en cascada
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

