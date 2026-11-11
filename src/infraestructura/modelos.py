from datetime import UTC, date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def hora_actual_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Clase base declarativa para todas las entidades ORM (SQLAlchemy 2.0)."""


class UsuarioModel(Base):
    """Entidad ORM para usuarios del sistema y control de acceso (PBI-02 y PBI-15)."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Columnas añadidas para alinear el ORM con el dominio de autenticación (PBI-15).
    salt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nombre_completo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)  # ADMIN, COORDINADOR, ADMIN_STAFF
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    asistencias_registradas: Mapped[list["AsistenciaModel"]] = relationship(
        "AsistenciaModel", back_populates="usuario"
    )


class EstudianteModel(Base):
    """Entidad ORM para estudiantes matriculados en la institución educativa."""

    __tablename__ = "estudiantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    dni: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    nombres: Mapped[str] = mapped_column(String(100), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(100), nullable=False)
    nivel: Mapped[str] = mapped_column(String(20), nullable=False)  # Primaria / Secundaria
    grado: Mapped[str] = mapped_column(String(20), nullable=False)  # 1ro a 5to
    seccion: Mapped[str] = mapped_column(String(5), nullable=False)  # A, B, C
    carnet_codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), default="ACTIVO", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    # Relación 1:N con AsistenciaModel y regla de cascada exigida por la rúbrica (DB2/DB3)
    asistencias: Mapped[list["AsistenciaModel"]] = relationship(
        "AsistenciaModel",
        back_populates="estudiante",
        cascade="all, delete-orphan",
    )


class AsistenciaModel(Base):
    """Entidad ORM para el registro unificado diario de asistencia escolar (PBI-01)."""

    __tablename__ = "asistencias"
    __table_args__ = (
        UniqueConstraint("estudiante_id", "fecha_escolar", name="uq_asistencia_estudiante_fecha"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    fecha_escolar: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hora_efectiva: Mapped[time] = mapped_column(Time, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # PUNTUAL, TARDANZA, AUSENTE, JUSTIFICADO, PENDIENTE
    minutos_tardanza: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metodo: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # CARNET, MANUAL_DNI, MANUAL_BUSQUEDA
    estado_anterior: Mapped[str | None] = mapped_column(String(20), nullable=True)
    motivo_correccion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auditoria_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    estudiante: Mapped["EstudianteModel"] = relationship(
        "EstudianteModel", back_populates="asistencias"
    )
    usuario: Mapped["UsuarioModel"] = relationship(
        "UsuarioModel", back_populates="asistencias_registradas"
    )
    justificaciones: Mapped[list["JustificacionModel"]] = relationship(
        "JustificacionModel",
        back_populates="asistencia",
        cascade="all, delete-orphan",
    )


class JustificacionModel(Base):
    """Entidad ORM para solicitudes y resoluciones de inasistencias o tardanzas (PBI-04)."""

    __tablename__ = "justificaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Código de dominio (``just-xxxxxxxxxx``) para no acoplar la UI al id entero.
    codigo: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    asistencia_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("asistencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    categoria: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # MEDICA, PERMISO_FAMILIAR, OTRA
    estado: Mapped[str] = mapped_column(
        String(20), default="APROBADA", nullable=False
    )  # PENDIENTE, APROBADA, RECHAZADA
    fecha_solicitud: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    documento_adjunto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    asistencia: Mapped["AsistenciaModel"] = relationship(
        "AsistenciaModel", back_populates="justificaciones"
    )


class PeriodoAcademicoModel(Base):
    """Períodos académicos usados por las reglas de justificaciones (PBI-04)."""

    __tablename__ = "periodos_academicos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    cerrado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ConfiguracionModel(Base):
    """Parámetros operativos de la demostración (por ejemplo, hora de cierre)."""

    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[str] = mapped_column(String(255), nullable=False)


class CierreDiarioModel(Base):
    """Registro del cierre escolar ejecutado para una fecha (PBI-03)."""

    __tablename__ = "cierres_diarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evento_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    fecha_escolar: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    hora_cierre: Mapped[time] = mapped_column(Time, nullable=False)
    total_ausentes_marcados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alumnos_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    ejecutado_por: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class AuditoriaModel(Base):
    """Bitácora append-only de operaciones críticas (base mínima para PBI-16)."""

    __tablename__ = "auditoria_eventos"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    operacion: Mapped[str] = mapped_column(String(60), nullable=False)
    entidad: Mapped[str] = mapped_column(String(40), nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(60), nullable=False)
    detalle: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

