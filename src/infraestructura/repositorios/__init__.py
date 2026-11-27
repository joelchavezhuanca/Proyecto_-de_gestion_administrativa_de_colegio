"""Repositorios de infraestructura para persistencia ORM de alumnos, académico y pagos."""

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
from src.infraestructura.repositorios.pagos_notificaciones import (
    RepositorioNotificacionesWhatsApp,
    RepositorioPagos,
)

__all__ = [
    "BoletaEmitida",
    "RepositorioBoletas",
    "RepositorioCalificaciones",
    "RepositorioCarnets",
    "RepositorioDocentes",
    "RepositorioEstadosAcademicos",
    "RepositorioMalla",
    "RepositorioMatricula",
    "RepositorioNotificacionesWhatsApp",
    "RepositorioPagos",
]
