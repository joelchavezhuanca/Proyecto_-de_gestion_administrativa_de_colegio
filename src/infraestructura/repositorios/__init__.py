"""Repositorios ORM SQLAlchemy 2.0 de la capa de infraestructura (Partes A y B)."""

from __future__ import annotations

from src.infraestructura.repositorios.academico import (
    BoletaEmitida,
    RepositorioBoletas,
    RepositorioCalificaciones,
    RepositorioDocentes,
    RepositorioMalla,
)
from src.infraestructura.repositorios.alumnos import (
    RepositorioCarnets,
    RepositorioEstadosAcademicos,
    RepositorioMatricula,
)
from src.infraestructura.repositorios.asistencia import (
    RepositorioAforo,
    RepositorioAsistencia,
    RepositorioCalendario,
    RepositorioJustificaciones,
    RepositorioPeriodos,
)
from src.infraestructura.repositorios.auditoria import RepositorioAuditoria
from src.infraestructura.repositorios.pagos_notificaciones import (
    RepositorioNotificacionesWhatsApp,
    RepositorioPagos,
)
from src.infraestructura.repositorios.seguridad import (
    RepositorioRoles,
    RepositorioSesiones,
    RepositorioUsuarios,
)

__all__ = [
    "BoletaEmitida",
    "RepositorioAforo",
    "RepositorioAsistencia",
    "RepositorioAuditoria",
    "RepositorioBoletas",
    "RepositorioCalendario",
    "RepositorioCalificaciones",
    "RepositorioCarnets",
    "RepositorioDocentes",
    "RepositorioEstadosAcademicos",
    "RepositorioJustificaciones",
    "RepositorioMalla",
    "RepositorioMatricula",
    "RepositorioNotificacionesWhatsApp",
    "RepositorioPagos",
    "RepositorioPeriodos",
    "RepositorioRoles",
    "RepositorioSesiones",
    "RepositorioUsuarios",
]
