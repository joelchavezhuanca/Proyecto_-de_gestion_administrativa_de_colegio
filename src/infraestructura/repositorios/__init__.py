"""Repositorios ORM SQLAlchemy 2.0 de la capa de infraestructura (Parte A - núcleo)."""

from __future__ import annotations

from src.infraestructura.repositorios.asistencia import (
    RepositorioAforo,
    RepositorioAsistencia,
    RepositorioCalendario,
    RepositorioJustificaciones,
    RepositorioPeriodos,
)
from src.infraestructura.repositorios.auditoria import RepositorioAuditoria
from src.infraestructura.repositorios.seguridad import (
    RepositorioRoles,
    RepositorioSesiones,
    RepositorioUsuarios,
)

__all__ = [
    "RepositorioAforo",
    "RepositorioAsistencia",
    "RepositorioAuditoria",
    "RepositorioCalendario",
    "RepositorioJustificaciones",
    "RepositorioPeriodos",
    "RepositorioRoles",
    "RepositorioSesiones",
    "RepositorioUsuarios",
]
