import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import ClassVar

from src.dominio.asistencia import (
    Alumno,
    EstadoAlumno,
    EstadoAsistencia,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
)


class CategoriaJustificacion(StrEnum):
    MEDICA = "MEDICA"
    PERMISO_FAMILIAR = "PERMISO_FAMILIAR"
    OTRA = "OTRA"


class EstadoJustificacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


class JustificacionException(Exception):
    """Excepción base para el módulo de Justificaciones de Inasistencia."""


class PermisoJustificacionException(JustificacionException):
    """Lanzada cuando un rol no autorizado intenta gestionar justificaciones."""


class FechaInvalidaException(JustificacionException):
    """Lanzada al intentar justificar una inasistencia en una fecha futura."""


class PeriodoAcademicoCerradoException(JustificacionException):
    """Lanzada cuando se intenta justificar dentro de un período académico ya clausurado."""


class EstadoNoJustificableException(JustificacionException):
    """Lanzada cuando la asistencia no está en estado AUSENTE o TARDANZA."""


@dataclass(frozen=True)
class PeriodoAcademico:
    id: int
    nombre: str  # Ej. "Bimestre I - 2026"
    fecha_inicio: date
    fecha_fin: date
    cerrado: bool = False


@dataclass(frozen=True)
class Justificacion:
    id: str
    asistencia_id: str
    alumno_id: int
    fecha_solicitud: date
    categoria: CategoriaJustificacion
    motivo: str
    estado: EstadoJustificacion
    usuario_id: int
    rol_usuario: RolUsuario
    documento_adjunto: str | None = None
    fecha_resolucion: datetime | None = None


@dataclass(frozen=True)
class ResultadoOperacionJustificacion:
    justificacion: Justificacion
    asistencia_actualizada: RegistroAsistencia
    auditoria_id: str


class ServicioJustificaciones:
    """Implementa las reglas de negocio del PBI-04 (Gestión de Justificaciones)."""

    # Roles oficiales con permisos para registrar y resolver justificaciones (ADMIN y ADMIN_STAFF)
    ROLES_GESTION: ClassVar[set[RolUsuario]] = {RolUsuario.ADMIN, RolUsuario.ADMIN_STAFF}

    @classmethod
    def validar_operador(cls, operador: UsuarioOperador) -> None:
        """Verifica que el operador pertenezca a ADMIN o ADMIN_STAFF."""
        if not operador.activo:
            raise PermisoJustificacionException("El operador no cuenta con una cuenta activa.")
        if operador.rol not in cls.ROLES_GESTION:
            raise PermisoJustificacionException(
                f"El rol {operador.rol.value} no está autorizado para gestionar justificaciones."
            )

    @classmethod
    def registrar_y_aprobar_justificacion(
        cls,
        operador: UsuarioOperador,
        alumno: Alumno,
        asistencia: RegistroAsistencia,
        fecha_solicitud: date,
        fecha_actual: date,
        categoria: CategoriaJustificacion,
        motivo: str,
        periodo: PeriodoAcademico,
        documento_adjunto: str | None = None,
    ) -> ResultadoOperacionJustificacion:
        """Registra y aprueba una justificación, actualizando atómicamente la asistencia."""
        cls.validar_operador(operador)

        if alumno.estado != EstadoAlumno.ACTIVO:
            raise JustificacionException(f"El alumno {alumno.codigo} no se encuentra ACTIVO.")

        if fecha_solicitud > fecha_actual:
            raise FechaInvalidaException(
                "No se puede presentar una justificación para una fecha futura."
            )

        if periodo.cerrado:
            raise PeriodoAcademicoCerradoException(
                f"El período académico '{periodo.nombre}' se encuentra cerrado."
            )

        if not (periodo.fecha_inicio <= asistencia.fecha_escolar <= periodo.fecha_fin):
            raise JustificacionException(
                f"La fecha de la asistencia {asistencia.fecha_escolar} "
                f"está fuera del período {periodo.nombre}."
            )

        if asistencia.estado not in (EstadoAsistencia.AUSENTE, EstadoAsistencia.TARDANZA):
            raise EstadoNoJustificableException(
                f"No es posible justificar una asistencia con estado '{asistencia.estado.value}'."
            )

        if not motivo or not motivo.strip():
            raise JustificacionException("El motivo de la justificación es obligatorio.")

        id_just = f"just-{uuid.uuid4().hex[:10]}"
        id_aud = f"aud-just-{uuid.uuid4().hex[:10]}"

        justificacion = Justificacion(
            id=id_just,
            asistencia_id=asistencia.id,
            alumno_id=alumno.id,
            fecha_solicitud=fecha_solicitud,
            categoria=categoria,
            motivo=motivo.strip(),
            estado=EstadoJustificacion.APROBADA,
            usuario_id=operador.id,
            rol_usuario=operador.rol,
            documento_adjunto=documento_adjunto,
            fecha_resolucion=datetime.now(),
        )

        asistencia_modificada = RegistroAsistencia(
            id=asistencia.id,
            alumno_id=asistencia.alumno_id,
            fecha_escolar=asistencia.fecha_escolar,
            hora_efectiva=asistencia.hora_efectiva,
            estado=EstadoAsistencia.JUSTIFICADO,
            minutos_tardanza=0,
            metodo=asistencia.metodo,
            usuario_id=operador.id,
            rol_usuario=operador.rol,
            estado_anterior=asistencia.estado,
            motivo_correccion=f"Justificado: {motivo.strip()}",
            auditoria_id=id_aud,
        )

        return ResultadoOperacionJustificacion(
            justificacion=justificacion,
            asistencia_actualizada=asistencia_modificada,
            auditoria_id=id_aud,
        )

    @classmethod
    def anular_justificacion(
        cls,
        operador: UsuarioOperador,
        justificacion: Justificacion,
        asistencia: RegistroAsistencia,
    ) -> RegistroAsistencia:
        """Anula una justificación y restaura la asistencia a su estado anterior."""
        cls.validar_operador(operador)

        if asistencia.estado != EstadoAsistencia.JUSTIFICADO:
            raise JustificacionException(
                "La asistencia no se encuentra en estado JUSTIFICADO."
            )

        estado_original = asistencia.estado_anterior or EstadoAsistencia.AUSENTE

        return RegistroAsistencia(
            id=asistencia.id,
            alumno_id=asistencia.alumno_id,
            fecha_escolar=asistencia.fecha_escolar,
            hora_efectiva=asistencia.hora_efectiva,
            estado=estado_original,
            minutos_tardanza=asistencia.minutos_tardanza,
            metodo=asistencia.metodo,
            usuario_id=operador.id,
            rol_usuario=operador.rol,
            estado_anterior=EstadoAsistencia.JUSTIFICADO,
            motivo_correccion="Anulación de justificación previa",
            auditoria_id=f"aud-anul-{uuid.uuid4().hex[:10]}",
        )
