import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

try:
    from src.infraestructura.modelos import Base
except ImportError:
    from modelos_orm import Base  # type: ignore


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Activa la verificación estricta de claves foráneas en SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Fixture hermético que provee una sesión limpia de SQLite en memoria."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    yield session

    session.close()
    engine.dispose()

