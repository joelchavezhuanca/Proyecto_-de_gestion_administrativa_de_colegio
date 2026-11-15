"""Configuración del motor SQLite de demostración y de las sesiones ORM."""

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infraestructura.modelos import Base


@event.listens_for(Engine, "connect")
def activar_claves_foraneas(dbapi_connection, connection_record) -> None:
    """SQLite requiere activar explícitamente las claves foráneas."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def crear_engine(url: str) -> Engine:
    """Crea el motor y garantiza que el esquema exista."""
    if url.startswith("sqlite:///"):
        ruta = Path(url.replace("sqlite:///", "", 1))
        ruta.parent.mkdir(parents=True, exist_ok=True)

    if url in ("sqlite://", "sqlite:///:memory:"):
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(url, future=True)
    Base.metadata.create_all(bind=engine)
    _agregar_columnas_faltantes(engine)
    return engine


# Columnas añadidas después de la primera versión del esquema. ``create_all`` no
# altera tablas existentes, así que se agregan aquí sin perder los datos.
_COLUMNAS_NUEVAS = {
    "estudiantes": {
        "apoderado_nombre": "VARCHAR(150)",
        "apoderado_celular": "VARCHAR(20)",
    },
}


def _agregar_columnas_faltantes(engine: Engine) -> None:
    inspector = inspect(engine)
    tablas = set(inspector.get_table_names())
    with engine.begin() as conexion:
        for tabla, columnas in _COLUMNAS_NUEVAS.items():
            if tabla not in tablas:
                continue
            existentes = {columna["name"] for columna in inspector.get_columns(tabla)}
            for nombre, tipo in columnas.items():
                if nombre not in existentes:
                    conexion.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}"))


def crear_fabrica_sesiones(engine: Engine) -> sessionmaker[Session]:
    """Fábrica de sesiones con expiración diferida para plantillas."""
    return sessionmaker(bind=engine, expire_on_commit=False)
