"""Unit of Work: transacciones atómicas sobre una sesión SQLAlchemy 2.0.

Regla **PBI-16** (atomicidad de auditoría): la operación de negocio y su evento
de auditoría inmutable deben persistirse dentro de *una sola* transacción. Si
persistir la auditoría falla (o cualquier otra operación), se ejecuta
``rollback()`` automático y no queda información huérfana en base de datos.

Uso típico
----------
::

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        ...  # persistir negocio + auditoría con uow.session
        uow.commit()          # commit explícito; rollback automático si falla

* ``commit()`` propaga la excepción tras revertir la transacción.
* Al salir del bloque con una excepción, se hace ``rollback()`` automático.
* Si se sale sin llamar a ``commit()`` no se confirma nada (rollback implícito).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import TracebackType
from typing import Protocol, TypeVar

from sqlalchemy.orm import Session

__all__ = [
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "ejecutar_atomico",
    "transaccion",
]

FabricaSesion = Callable[[], Session]
T = TypeVar("T")


class UnitOfWork(Protocol):
    """Contrato fino (Protocol) de unidad de trabajo transaccional."""

    session: Session

    def commit(self) -> None:
        """Confirma la transacción; revierte y propaga si falla."""
        ...

    def rollback(self) -> None:
        """Revierte la transacción en curso."""
        ...

    def flush(self) -> None:
        """Sincroniza cambios pendientes con la base sin confirmar."""
        ...


class SqlAlchemyUnitOfWork:
    """Implementación concreta de :class:`UnitOfWork` sobre SQLAlchemy ``Session``."""

    def __init__(self, session_factory: FabricaSesion) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    # -- gestión de contexto -------------------------------------------------
    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        session = self._session
        try:
            if session is not None:
                if exc_type is not None:
                    # Cualquier error (incluido fallo de auditoría PBI-16) revierte.
                    session.rollback()
        finally:
            if session is not None:
                session.close()
            self._session = None
        # No suprimir la excepción original.
        return False

    # -- API transaccional ---------------------------------------------------
    @property
    def session(self) -> Session:
        if self._session is None:  # pragma: no cover - uso fuera de contexto
            raise RuntimeError("UnitOfWork no iniciado; use 'with SqlAlchemyUnitOfWork(...)'.")
        return self._session

    def commit(self) -> None:
        """Confirma la transacción; si falla, revierte y propaga (PBI-16)."""
        session = self.session
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise

    def rollback(self) -> None:
        """Revierte la transacción en curso."""
        self.session.rollback()

    def flush(self) -> None:
        """Sincroniza cambios pendientes sin confirmar."""
        self.session.flush()


@contextmanager
def transaccion(session_factory: FabricaSesion) -> Iterator[SqlAlchemyUnitOfWork]:
    """Context manager equivalente a :class:`SqlAlchemyUnitOfWork`."""
    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        yield uow


def ejecutar_atomico(
    session_factory: FabricaSesion,
    operacion: Callable[[Session], T],
) -> T:
    """Ejecuta ``operacion(session)`` y confirma; revierte ante cualquier error.

    Útil cuando la operación ya encapsula toda la persistencia (incluida la
    auditoría PBI-16) y solo se requiere la garantía de atomicidad.
    """
    session = session_factory()
    try:
        resultado = operacion(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return resultado
