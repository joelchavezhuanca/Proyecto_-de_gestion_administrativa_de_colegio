"""Modelos ORM SQLAlchemy 2.0 del esquema relacional completo (DER v2)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def hora_actual_utc() -> datetime:
    """Devuelve la fecha y hora actual en UTC con zona horaria explícita."""
    return datetime.now(UTC)


def _nuevo_id_justificacion() -> str:
    return f"just-{uuid.uuid4().hex[:10]}"


class Base(DeclarativeBase):
    """Clase base declarativa para todas las entidades ORM (SQLAlchemy 2.0)."""


# ===========================================================================
# BLOQUE 1 — Seguridad, RBAC Dinámico y Auditoría (PBI-02, PBI-15, PBI-16)
# ===========================================================================


class RolModel(Base):
    """Catálogo de roles del sistema y roles personalizados (PBI-15)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    permisos_rel: Mapped[list[RolPermisoModel]] = relationship(
        "RolPermisoModel",
        back_populates="rol",
        cascade="all, delete-orphan",
    )


class PermisoModel(Base):
    """Catálogo maestro de los 28 permisos granulares del sistema (PBI-15)."""

    __tablename__ = "permisos"

    codigo: Mapped[str] = mapped_column(String(80), primary_key=True)
    modulo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)


class RolPermisoModel(Base):
    """Tabla asociativa N:M entre roles y permisos (PBI-15)."""

    __tablename__ = "rol_permisos"

    rol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permiso_codigo: Mapped[str] = mapped_column(
        String(80), ForeignKey("permisos.codigo", ondelete="CASCADE"), primary_key=True
    )

    rol: Mapped[RolModel] = relationship("RolModel", back_populates="permisos_rel")
    permiso: Mapped[PermisoModel] = relationship("PermisoModel")


class UsuarioModel(Base):
    """Entidad ORM para usuarios del sistema y control de acceso (PBI-02 y PBI-15)."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre_completo: Mapped[str] = mapped_column(String(150), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    rol_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("roles.id"), nullable=True, index=True
    )
    rol: Mapped[str] = mapped_column(String(50), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="ACTIVO", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=hora_actual_utc,
        onupdate=hora_actual_utc,
        nullable=False,
    )

    rol_ref: Mapped[RolModel | None] = relationship("RolModel")
    sesiones: Mapped[list[SesionUsuarioModel]] = relationship(
        "SesionUsuarioModel",
        back_populates="usuario",
        cascade="all, delete-orphan",
    )
    asistencias_registradas: Mapped[list[AsistenciaModel]] = relationship(
        "AsistenciaModel", back_populates="usuario"
    )


class SesionUsuarioModel(Base):
    """Sesiones de servidor con soporte de expiración y revocación inmediata (PBI-15)."""

    __tablename__ = "sesiones_usuario"

    token: Mapped[str] = mapped_column(String(120), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    rol_codigo_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usuario: Mapped[UsuarioModel] = relationship("UsuarioModel", back_populates="sesiones")


class AuditoriaEventoModel(Base):
    """Bitácora inmutable append-only encadenada por SHA-256 (PBI-16, sin CASCADE)."""

    __tablename__ = "auditoria_eventos"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    secuencia: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rol_ejecutante: Mapped[str] = mapped_column(String(50), nullable=False)
    operacion: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entidad: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entidad_id: Mapped[str] = mapped_column(String(80), nullable=False)
    metodo_asistencia: Mapped[str | None] = mapped_column(String(30), nullable=True)
    alumno_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contexto_academico: Mapped[str | None] = mapped_column(String(150), nullable=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(40), nullable=True)
    estado_nuevo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    detalle_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    hash_anterior: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_integridad: Mapped[str] = mapped_column(String(64), nullable=False)


# ===========================================================================
# BLOQUE 2 — Estructura Académica, Alumnos y Carnets (PBI-05, 06, 08, 09, 11)
# ===========================================================================


class SalonModel(Base):
    """Salón/sección escolar por año lectivo, nivel y grado (PBI-09)."""

    __tablename__ = "salones"
    __table_args__ = (
        UniqueConstraint("anio_lectivo", "nivel", "grado", "seccion", name="uq_salon_ubicacion"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anio_lectivo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    nivel: Mapped[str] = mapped_column(String(30), nullable=False)
    grado: Mapped[str] = mapped_column(String(20), nullable=False)
    seccion: Mapped[str] = mapped_column(String(10), nullable=False)
    capacidad_maxima: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CursoModel(Base):
    """Curso asignable por año lectivo, nivel y grado (PBI-09)."""

    __tablename__ = "cursos"
    __table_args__ = (
        UniqueConstraint("anio_lectivo", "nivel", "grado", "codigo", name="uq_curso_codigo_grado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anio_lectivo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    nivel: Mapped[str] = mapped_column(String(30), nullable=False)
    grado: Mapped[str] = mapped_column(String(20), nullable=False)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    area_curricular: Mapped[str] = mapped_column(String(100), nullable=False)
    horas_semanales: Mapped[int] = mapped_column(Integer, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AsignacionDocenteModel(Base):
    """Asignación docente segura a curso y salón por año lectivo (PBI-11)."""

    __tablename__ = "asignaciones_docentes"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    usuario_docente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    curso_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cursos.id"), nullable=False, index=True
    )
    salon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salones.id"), nullable=False, index=True
    )
    anio_lectivo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    asignado_por: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_revocacion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    docente: Mapped[UsuarioModel] = relationship("UsuarioModel")
    curso: Mapped[CursoModel] = relationship("CursoModel")
    salon: Mapped[SalonModel] = relationship("SalonModel")


class EstudianteModel(Base):
    """Entidad ORM para estudiantes matriculados en la institución educativa."""

    __tablename__ = "estudiantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    dni: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    nombres: Mapped[str] = mapped_column(String(100), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    salon_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("salones.id"), nullable=True, index=True
    )
    nivel: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    grado: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    seccion: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    carnet_codigo: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    estado: Mapped[str] = mapped_column(String(20), default="ACTIVO", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    salon: Mapped[SalonModel | None] = relationship("SalonModel")
    asistencias: Mapped[list[AsistenciaModel]] = relationship(
        "AsistenciaModel",
        back_populates="estudiante",
        cascade="all, delete-orphan",
    )
    carnets: Mapped[list[CarnetModel]] = relationship(
        "CarnetModel",
        back_populates="estudiante",
        cascade="all, delete-orphan",
    )


class EstudianteEstadoHistorialModel(Base):
    """Historial de transiciones de estado académico del estudiante (PBI-08)."""

    __tablename__ = "estudiante_estados_historial"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estado_anterior: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    rol_usuario: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class ApoderadoModel(Base):
    """Apoderado con contacto WhatsApp normalizado (PBI-05 y PBI-17)."""

    __tablename__ = "apoderados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombres: Mapped[str] = mapped_column(String(100), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(100), nullable=False)
    documento: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parentesco: Mapped[str] = mapped_column(String(40), nullable=False)
    telefono_whatsapp: Mapped[str] = mapped_column(String(20), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EstudianteApoderadoModel(Base):
    """Relación N:M entre estudiantes y apoderados indicando titularidad principal."""

    __tablename__ = "estudiante_apoderado"

    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), primary_key=True
    )
    apoderado_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("apoderados.id", ondelete="CASCADE"), primary_key=True
    )
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CarnetModel(Base):
    """Carnet escolar con código QR opaco y trazabilidad de anulación (PBI-06)."""

    __tablename__ = "carnets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    codigo_qr: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), default="ACTIVO", nullable=False)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detalle_anulacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emitido_por: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    emitido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    estudiante: Mapped[EstudianteModel] = relationship("EstudianteModel", back_populates="carnets")


# ===========================================================================
# BLOQUE 3 — Asistencia, Aforo y Justificaciones (PBI-01, PBI-03, PBI-04)
# ===========================================================================


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
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=True, index=True
    )
    fecha_escolar: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hora_efectiva: Mapped[time] = mapped_column(Time, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    minutos_tardanza: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metodo: Mapped[str] = mapped_column(String(25), nullable=False)
    rol_usuario: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(20), nullable=True)
    motivo_correccion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nivel_snapshot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    grado_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    seccion_snapshot: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notificacion_ausencia_enviada: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    auditoria_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    estudiante: Mapped[EstudianteModel] = relationship(
        "EstudianteModel", back_populates="asistencias"
    )
    usuario: Mapped[UsuarioModel | None] = relationship(
        "UsuarioModel", back_populates="asistencias_registradas"
    )
    justificaciones: Mapped[list[JustificacionModel]] = relationship(
        "JustificacionModel",
        back_populates="asistencia",
        cascade="all, delete-orphan",
    )


class AsistenciaHistorialModel(Base):
    """Historial de correcciones y cambios de estado de asistencia (PBI-01 / PBI-03)."""

    __tablename__ = "asistencia_historial"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asistencia_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("asistencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=True, index=True
    )
    rol_usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metodo: Mapped[str] = mapped_column(String(25), nullable=False)
    auditoria_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class PeriodoAcademicoModel(Base):
    """Períodos académicos flexibles (bimestre/trimestre/semestre) con límite de notas."""

    __tablename__ = "periodos_academicos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anio_lectivo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tipo_periodo: Mapped[str] = mapped_column(String(20), default="BIMESTRE", nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_limite_notas: Mapped[date | None] = mapped_column(Date, nullable=True)
    cerrado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class JustificacionModel(Base):
    """Entidad ORM para solicitudes y resoluciones de inasistencias o tardanzas (PBI-04)."""

    __tablename__ = "justificaciones"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=_nuevo_id_justificacion)
    asistencia_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("asistencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id"), nullable=False, index=True
    )
    periodo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("periodos_academicos.id"), nullable=True, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    rol_usuario: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    fecha_solicitud: Mapped[date | None] = mapped_column(Date, nullable=True)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="APROBADA", nullable=False)
    minutos_tardanza_original: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documento_adjunto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nivel: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    grado: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    seccion: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    asistencia: Mapped[AsistenciaModel] = relationship(
        "AsistenciaModel", back_populates="justificaciones"
    )
    adjuntos: Mapped[list[JustificacionAdjuntoModel]] = relationship(
        "JustificacionAdjuntoModel",
        back_populates="justificacion",
        cascade="all, delete-orphan",
    )


class JustificacionAdjuntoModel(Base):
    """Metadatos de archivos adjuntos privados asociados a una justificación (PBI-04)."""

    __tablename__ = "justificacion_adjuntos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    justificacion_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("justificaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(10), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    ruta_almacenamiento: Mapped[str] = mapped_column(String(500), nullable=False)
    subido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    justificacion: Mapped[JustificacionModel] = relationship(
        "JustificacionModel", back_populates="adjuntos"
    )


class CalendarioEscolarModel(Base):
    """Calendario escolar institucional para días no lectivos y excepciones (PBI-03/17)."""

    __tablename__ = "calendario_escolar"

    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    es_lectivo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    es_excepcion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class ConfiguracionSistemaModel(Base):
    """Parámetros globales configurables (hora cierre, hora WhatsApp, etc.)."""

    __tablename__ = "configuracion_sistema"

    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    valor: Mapped[str] = mapped_column(String(255), nullable=False)
    actualizado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=True
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class CierreDiarioModel(Base):
    """Registro único por fecha escolar de ejecución del cierre diario (PBI-03)."""

    __tablename__ = "cierres_diarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evento_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    fecha_escolar: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    hora_cierre: Mapped[time] = mapped_column(Time, nullable=False)
    total_ausentes_marcados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actor_ejecutante: Mapped[str] = mapped_column(String(50), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


# ===========================================================================
# BLOQUE 4 — Notificaciones y Pagos (PBI-07, PBI-17)
# ===========================================================================


class NotificacionWhatsappModel(Base):
    """Cola y trazabilidad de notificaciones WhatsApp con idempotencia (PBI-17)."""

    __tablename__ = "notificaciones_whatsapp"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    clave_idempotencia: Mapped[str] = mapped_column(
        String(150), unique=True, nullable=False, index=True
    )
    evento_origen_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    asistencia_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("asistencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha_escolar: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    apoderado_nombre: Mapped[str | None] = mapped_column(String(150), nullable=True)
    telefono_destino: Mapped[str | None] = mapped_column(String(25), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    plantilla: Mapped[str] = mapped_column(String(60), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referencia_proveedor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detalle_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class ObligacionPagoModel(Base):
    """Obligaciones económicas de pensiones/matrícula con precisión Decimal (PBI-07)."""

    __tablename__ = "obligaciones_pago"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concepto: Mapped[str] = mapped_column(String(150), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", nullable=False)
    pagado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_exoneracion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


class AlertaPagoSilenciosaModel(Base):
    """Alerta interna no bloqueante única por estudiante y fecha escolar (PBI-07)."""

    __tablename__ = "alertas_pago_silenciosas"
    __table_args__ = (
        UniqueConstraint("estudiante_id", "fecha_escolar", name="uq_alerta_pago_estudiante_fecha"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asistencia_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("asistencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha_escolar: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cantidad_obligaciones_vencidas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    monto_vencido_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    revisada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )


# ===========================================================================
# BLOQUE 5 — Calificaciones de 3 Niveles y Boletas (PBI-10, PBI-14)
# ===========================================================================


class RubroEvaluacionModel(Base):
    """Nivel 2 del libro de calificaciones: rubros ponderados sumando 100% (PBI-10)."""

    __tablename__ = "rubros_evaluacion"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asignacion_docente_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("asignaciones_docentes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    periodo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("periodos_academicos.id"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    peso_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    actividades: Mapped[list[ActividadEvaluableModel]] = relationship(
        "ActividadEvaluableModel",
        back_populates="rubro",
        cascade="all, delete-orphan",
    )


class ActividadEvaluableModel(Base):
    """Nivel 3 del libro de calificaciones: tareas, prácticas y exámenes (PBI-10)."""

    __tablename__ = "actividades_evaluables"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    rubro_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("rubros_evaluacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    rubro: Mapped[RubroEvaluacionModel] = relationship(
        "RubroEvaluacionModel", back_populates="actividades"
    )
    calificaciones: Mapped[list[CalificacionModel]] = relationship(
        "CalificacionModel",
        back_populates="actividad",
        cascade="all, delete-orphan",
    )


class CalificacionModel(Base):
    """Nota vigesimal exacta Decimal [0, 20] única por actividad y estudiante (PBI-10)."""

    __tablename__ = "calificaciones"
    __table_args__ = (
        UniqueConstraint(
            "actividad_id", "estudiante_id", name="uq_calificacion_actividad_estudiante"
        ),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    actividad_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("actividades_evaluables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nota: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    nota_anterior: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    motivo_modificacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )

    actividad: Mapped[ActividadEvaluableModel] = relationship(
        "ActividadEvaluableModel", back_populates="calificaciones"
    )


class BoletaEmitidaModel(Base):
    """Boletas de calificaciones preliminares u oficiales con código verificador (PBI-14)."""

    __tablename__ = "boletas_emitidas"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    codigo_verificacion: Mapped[str | None] = mapped_column(
        String(60), unique=True, nullable=True, index=True
    )
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    periodo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("periodos_academicos.id"), nullable=False, index=True
    )
    anio_lectivo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    es_oficial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promedio_general: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    resumen_asistencia_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    emitido_por: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    emitido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=hora_actual_utc, nullable=False
    )
