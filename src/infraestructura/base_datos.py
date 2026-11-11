"""Configuración del motor SQLite de demostración y de las sesiones ORM."""

from pathlib import Path

from sqlalchemy import create_engine, event
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
    return engine


def crear_fabrica_sesiones(engine: Engine) -> sessionmaker[Session]:
    """Fábrica de sesiones con expiración diferida para plantillas."""
    return sessionmaker(bind=engine, expire_on_commit=False)
