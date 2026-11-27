"""Fixtures compartidos de infraestructura y persistencia SQLite en memoria."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from src.infraestructura import Base, crear_motor, crear_session_factory


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Fixture hermético que provee una sesión limpia de SQLite en memoria con FKs activas."""
    engine = crear_motor("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = crear_session_factory(engine)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
