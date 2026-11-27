"""Punto de entrada WSGI de producción (Gunicorn / Docker / Render).

Uso con Gunicorn:
    gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 "wsgi:crear_app_produccion()"
"""

from __future__ import annotations

import os

from flask import Flask

from src.infraestructura.base_datos import (
    crear_motor,
    crear_session_factory,
    inicializar_bd,
    obtener_database_url,
)
from src.presentacion.app import crear_app


def crear_app_produccion() -> Flask:
    """Inicializa la base de datos (DER v2 + roles + admin inicial) y devuelve la app Flask."""
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY es obligatoria en producción. Configúrela en las variables de entorno."
        )

    database_url = obtener_database_url()
    motor = crear_motor(database_url)
    inicializar_bd(motor)

    return crear_app(
        {
            "SECRET_KEY": secret_key,
            "DATABASE_URL": database_url,
            "SESSION_FACTORY": crear_session_factory(motor),
        }
    )


app: Flask | None = crear_app_produccion() if os.environ.get("SECRET_KEY") else None
