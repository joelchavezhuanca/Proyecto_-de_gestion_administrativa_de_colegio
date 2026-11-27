"""Fábrica de motor SQLAlchemy 2.0, sesiones e inicialización idempotente de BD."""

from __future__ import annotations

import os
from typing import Final

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    RolUsuario,
    ServicioGestionRoles,
    hashear_password,
    validar_politica_password,
)
from src.infraestructura.modelos import (
    Base,
    PermisoModel,
    RolModel,
    RolPermisoModel,
    UsuarioModel,
)

DATABASE_URL_DEFECTO: Final[str] = "sqlite:///domingo_savio.db"

_MODULO_POR_PERMISO: Final[dict[PermisoOperacion, str]] = {
    PermisoOperacion.REGISTRAR_ASISTENCIA: "asistencia",
    PermisoOperacion.CORREGIR_AUSENTE: "asistencia",
    PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA: "asistencia",
    PermisoOperacion.CONSULTAR_DASHBOARD_AFORO: "aforo",
    PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA: "aforo",
    PermisoOperacion.EJECUTAR_CIERRE_ASISTENCIA: "aforo",
    PermisoOperacion.ADMINISTRAR_CALENDARIO_ESCOLAR: "aforo",
    PermisoOperacion.GESTIONAR_JUSTIFICACIONES: "justificaciones",
    PermisoOperacion.ADMINISTRAR_PERIODOS: "justificaciones",
    PermisoOperacion.GESTIONAR_USUARIOS: "seguridad",
    PermisoOperacion.GESTIONAR_ROLES: "seguridad",
    PermisoOperacion.ASIGNAR_ROLES: "seguridad",
    PermisoOperacion.CONSULTAR_AUDITORIA: "auditoria",
    PermisoOperacion.VERIFICAR_INTEGRIDAD_AUDITORIA: "auditoria",
    PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL: "whatsapp",
    PermisoOperacion.CONFIGURAR_NOTIFICACIONES_WHATSAPP: "whatsapp",
    PermisoOperacion.GESTIONAR_MATRICULA: "matricula",
    PermisoOperacion.GESTIONAR_CARNETS: "carnets",
    PermisoOperacion.GESTIONAR_PAGOS: "pagos",
    PermisoOperacion.VER_ALERTA_PAGOS: "pagos",
    PermisoOperacion.GESTIONAR_ESTADOS_ACADEMICOS: "estados_academicos",
    PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR: "academico",
    PermisoOperacion.ASIGNAR_DOCENTES: "academico",
    PermisoOperacion.REGISTRAR_CALIFICACIONES: "academico",
    PermisoOperacion.CONSULTAR_CALIFICACIONES: "academico",
    PermisoOperacion.CONSULTAR_FICHA_ALUMNO: "reportes",
    PermisoOperacion.EXPORTAR_ASISTENCIAS: "reportes",
    PermisoOperacion.EMITIR_BOLETAS: "reportes",
}


def obtener_database_url(database_url: str | None = None) -> str:
    """Resuelve y normaliza la URL de conexión (SQLite o PostgreSQL con psycopg v3)."""
    url = database_url or os.environ.get("DATABASE_URL") or DATABASE_URL_DEFECTO
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _activar_pragma_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def crear_motor(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Crea un Engine SQLAlchemy 2.0 activando PRAGMA foreign_keys=ON en SQLite."""
    url = obtener_database_url(database_url)
    engine = create_engine(url, echo=echo, future=True)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _activar_pragma_foreign_keys)
    return engine


def crear_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Devuelve una fábrica de sesiones SQLAlchemy 2.0 sin expiración al confirmar."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def sembrar_seguridad_base(session: Session) -> None:
    """Siembra idempotentemente los 28 permisos y 3 roles base del sistema."""
    permisos_existentes = set(session.scalars(select(PermisoModel.codigo)).all())
    for permiso in PermisoOperacion:
        if permiso.value not in permisos_existentes:
            session.add(
                PermisoModel(
                    codigo=permiso.value,
                    modulo=_MODULO_POR_PERMISO[permiso],
                    descripcion=permiso.value.replace("_", " ").capitalize(),
                )
            )
    session.flush()

    roles_existentes = {rol.codigo: rol for rol in session.scalars(select(RolModel)).all()}
    for rol_base in ServicioGestionRoles.obtener_roles_base():
        rol_orm = roles_existentes.get(rol_base.codigo)
        if rol_orm is None:
            rol_orm = RolModel(
                codigo=rol_base.codigo,
                nombre=rol_base.nombre,
                descripcion=rol_base.descripcion,
                es_sistema=True,
                activo=True,
            )
            session.add(rol_orm)
            session.flush()
            roles_existentes[rol_base.codigo] = rol_orm

        asignados = set(
            session.scalars(
                select(RolPermisoModel.permiso_codigo).filter_by(rol_id=rol_orm.id)
            ).all()
        )
        for permiso in rol_base.permisos:
            if permiso.value not in asignados:
                session.add(RolPermisoModel(rol_id=rol_orm.id, permiso_codigo=permiso.value))
    session.flush()


def sembrar_admin_inicial(
    session: Session,
    *,
    username: str | None = None,
    password: str | None = None,
    nombre_completo: str | None = None,
) -> bool:
    """Crea de forma idempotente un usuario ADMIN inicial usando variables de entorno.

    Requiere ``ADMIN_USERNAME`` y ``ADMIN_PASSWORD`` (o argumentos explícitos).
    Si ya existe al menos un usuario ADMIN activo o faltan credenciales, no crea nada.
    """
    usr = (username if username is not None else os.environ.get("ADMIN_USERNAME") or "").strip()
    pwd = password if password is not None else (os.environ.get("ADMIN_PASSWORD") or "")
    if not usr or not pwd:
        return False

    admin_existente = session.scalar(
        select(UsuarioModel.id).where(
            UsuarioModel.rol == RolUsuario.ADMIN.value,
            UsuarioModel.activo.is_(True),
        )
    )
    if admin_existente is not None:
        return False

    validar_politica_password(pwd)
    pwd_hash, salt = hashear_password(pwd)
    rol_admin_id = session.scalar(
        select(RolModel.id).where(RolModel.codigo == RolUsuario.ADMIN.value)
    )
    nombre = (
        nombre_completo or os.environ.get("ADMIN_NOMBRE_COMPLETO") or "Administrador del Sistema"
    ).strip()

    session.add(
        UsuarioModel(
            username=usr.lower(),
            nombre_completo=nombre,
            password_hash=pwd_hash,
            salt=salt,
            rol_id=rol_admin_id,
            rol=RolUsuario.ADMIN.value,
            estado=EstadoUsuario.ACTIVO.value,
            activo=True,
        )
    )
    session.flush()
    return True


def inicializar_bd(engine: Engine) -> None:
    """Crea el esquema completo del DER v2 y siembra seguridad base de forma idempotente."""
    Base.metadata.create_all(bind=engine)
    session_factory = crear_session_factory(engine)
    with session_factory() as session:
        sembrar_seguridad_base(session)
        sembrar_admin_inicial(session)
        session.commit()
