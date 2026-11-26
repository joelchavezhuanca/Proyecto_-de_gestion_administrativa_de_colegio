"""PBI-08: Control de Estados Académicos de Acceso."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

from src.dominio.asistencia import UsuarioOperador
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

ZONA_HORARIA_LIMA = timezone(timedelta(hours=-5))


class EstadoAcademico(StrEnum):
    ACTIVO = "ACTIVO"
    SUSPENDIDO = "SUSPENDIDO"
    RETIRADO = "RETIRADO"
    TRASLADADO = "TRASLADADO"
    EGRESADO = "EGRESADO"


ESTADOS_QUE_ANULAN_CARNET: frozenset[EstadoAcademico] = frozenset(
    {
        EstadoAcademico.RETIRADO,
        EstadoAcademico.TRASLADADO,
        EstadoAcademico.EGRESADO,
    }
)

TRANSICIONES_VALIDAS: dict[EstadoAcademico, frozenset[EstadoAcademico]] = {
    EstadoAcademico.ACTIVO: frozenset(
        {
            EstadoAcademico.SUSPENDIDO,
            EstadoAcademico.RETIRADO,
            EstadoAcademico.TRASLADADO,
            EstadoAcademico.EGRESADO,
        }
    ),
    EstadoAcademico.SUSPENDIDO: frozenset(
        {
            EstadoAcademico.ACTIVO,
            EstadoAcademico.RETIRADO,
            EstadoAcademico.TRASLADADO,
        }
    ),
    EstadoAcademico.RETIRADO: frozenset({EstadoAcademico.ACTIVO}),
    EstadoAcademico.TRASLADADO: frozenset({EstadoAcademico.ACTIVO}),
    EstadoAcademico.EGRESADO: frozenset(),
}


class EstadoAcademicoException(Exception):
    """Excepción base del dominio de estados académicos."""


class PermisoEstadoAcademicoException(EstadoAcademicoException):
    """Lanzada cuando el operador no está activo o carece de permiso."""


class TransicionEstadoInvalidaException(EstadoAcademicoException):
    """Lanzada ante una transición de estado académico no permitida."""


class MotivoObligatorioException(EstadoAcademicoException):
    """Lanzada cuando no se especifica un motivo válido para el cambio."""


class RangoSuspensionInvalidoException(EstadoAcademicoException):
    """Lanzada cuando las fechas de suspensión faltan o son inconsistentes."""


@dataclass(frozen=True)
class HistorialEstadoAlumno:
    id: str
    alumno_id: int
    estado_anterior: EstadoAcademico
    estado_nuevo: EstadoAcademico
    motivo: str
    usuario_id: int
    rol_usuario: str
    fecha_hora: datetime
    fecha_inicio_suspension: date | None = None
    fecha_fin_suspension: date | None = None


@dataclass(frozen=True)
class ResultadoCambioEstado:
    alumno_id: int
    estado_actual: EstadoAcademico
    historial: HistorialEstadoAlumno
    debe_anular_carnet: bool


def _codigo_rol(rol: object) -> str:
    valor = getattr(rol, "value", rol)
    return str(valor).strip().upper()


def _normalizar_fecha_hora(fecha_hora: datetime) -> datetime:
    """Normaliza una marca temporal al huso institucional America/Lima (UTC-5)."""
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


class ServicioEstadosAcademicos:
    """Implementa las reglas de negocio del PBI-08 (Estados Académicos de Acceso)."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso GESTIONAR_ESTADOS_ACADEMICOS en servidor."""
        if not operador.activo:
            raise PermisoEstadoAcademicoException(
                "El operador no cuenta con una cuenta activa."
            )
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.GESTIONAR_ESTADOS_ACADEMICOS,
            roles,
        ):
            raise PermisoEstadoAcademicoException(
                f"El rol {_codigo_rol(operador.rol)} no está autorizado para "
                "gestionar estados académicos."
            )

    @staticmethod
    def cambiar_estado(
        operador: UsuarioOperador,
        alumno_id: int,
        estado_actual: EstadoAcademico,
        nuevo_estado: EstadoAcademico,
        motivo: str,
        fecha_hora: datetime,
        fecha_inicio_suspension: date | None = None,
        fecha_fin_suspension: date | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> ResultadoCambioEstado:
        """Valida y ejecuta la transición de estado académico de un alumno."""
        ServicioEstadosAcademicos.validar_operador(operador, roles=roles)

        motivo_limpio = motivo.strip() if isinstance(motivo, str) else ""
        if not motivo_limpio:
            raise MotivoObligatorioException(
                "El motivo del cambio de estado académico es obligatorio."
            )

        permitidos = TRANSICIONES_VALIDAS.get(estado_actual, frozenset())
        if nuevo_estado not in permitidos:
            raise TransicionEstadoInvalidaException(
                f"Transición inválida de '{estado_actual.value}' a '{nuevo_estado.value}'."
            )

        inicio_suspension: date | None = None
        fin_suspension: date | None = None
        if nuevo_estado == EstadoAcademico.SUSPENDIDO:
            if fecha_inicio_suspension is None or fecha_fin_suspension is None:
                raise RangoSuspensionInvalidoException(
                    "La suspensión requiere fecha de inicio y fecha de fin."
                )
            if fecha_inicio_suspension > fecha_fin_suspension:
                raise RangoSuspensionInvalidoException(
                    "La fecha de inicio de suspensión no puede superar a la fecha de fin."
                )
            inicio_suspension = fecha_inicio_suspension
            fin_suspension = fecha_fin_suspension

        historial = HistorialEstadoAlumno(
            id=f"est-{uuid.uuid4().hex[:12]}",
            alumno_id=alumno_id,
            estado_anterior=estado_actual,
            estado_nuevo=nuevo_estado,
            motivo=motivo_limpio,
            usuario_id=operador.id,
            rol_usuario=_codigo_rol(operador.rol),
            fecha_hora=_normalizar_fecha_hora(fecha_hora),
            fecha_inicio_suspension=inicio_suspension,
            fecha_fin_suspension=fin_suspension,
        )

        return ResultadoCambioEstado(
            alumno_id=alumno_id,
            estado_actual=nuevo_estado,
            historial=historial,
            debe_anular_carnet=nuevo_estado in ESTADOS_QUE_ANULAN_CARNET,
        )

    @staticmethod
    def estado_efectivo(
        estado_actual: EstadoAcademico,
        fecha_evaluacion: date,
        fecha_inicio_suspension: date | None = None,
        fecha_fin_suspension: date | None = None,
    ) -> EstadoAcademico:
        """Evalúa el estado vigente en una fecha considerando vencimiento de suspensión."""
        if (
            estado_actual == EstadoAcademico.SUSPENDIDO
            and fecha_fin_suspension is not None
            and fecha_evaluacion > fecha_fin_suspension
        ):
            return EstadoAcademico.ACTIVO
        return estado_actual

    @staticmethod
    def puede_registrar_asistencia(
        estado_actual: EstadoAcademico,
        fecha_evaluacion: date,
        fecha_inicio_suspension: date | None = None,
        fecha_fin_suspension: date | None = None,
    ) -> bool:
        """Indica si el alumno está habilitado para registrar asistencia en la fecha."""
        return (
            ServicioEstadosAcademicos.estado_efectivo(
                estado_actual=estado_actual,
                fecha_evaluacion=fecha_evaluacion,
                fecha_inicio_suspension=fecha_inicio_suspension,
                fecha_fin_suspension=fecha_fin_suspension,
            )
            == EstadoAcademico.ACTIVO
        )
