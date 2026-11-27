"""Punto de entrada local del Sistema de Gestión Administrativa del Colegio.

Inicializa el esquema de base de datos (``inicializar_bd``) y arranca el
servidor Flask leyendo ``SECRET_KEY`` y ``DATABASE_URL`` del entorno.

Uso:
    $env:SECRET_KEY = "clave-segura"
    python run.py
"""

from __future__ import annotations

import os

from src.infraestructura.base_datos import (
    DATABASE_URL_DEFECTO,
    crear_motor,
    crear_session_factory,
    inicializar_bd,
)
from src.presentacion.app import crear_app


def main() -> None:
    """Inicializa la base de datos y ejecuta el servidor de desarrollo local."""
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise SystemExit(
            "SECRET_KEY es obligatoria. Defínala en el entorno antes de iniciar la app."
        )

    database_url = os.environ.get("DATABASE_URL") or DATABASE_URL_DEFECTO
    motor = crear_motor(database_url)
    inicializar_bd(motor)

    app = crear_app(
        {
            "SECRET_KEY": secret_key,
            "DATABASE_URL": database_url,
            "SESSION_FACTORY": crear_session_factory(motor),
        }
    )
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )


if __name__ == "__main__":
    main()
