"""Capa de infraestructura: modelos ORM (DER v2) y gestión de base de datos."""

from src.infraestructura.base_datos import (
    DATABASE_URL_DEFECTO,
    crear_motor,
    crear_session_factory,
    inicializar_bd,
    obtener_database_url,
    sembrar_admin_inicial,
    sembrar_seguridad_base,
)
from src.infraestructura.modelos import Base

__all__ = [
    "Base",
    "DATABASE_URL_DEFECTO",
    "crear_motor",
    "crear_session_factory",
    "inicializar_bd",
    "obtener_database_url",
    "sembrar_admin_inicial",
    "sembrar_seguridad_base",
]
