"""Capa de Aplicación: casos de uso que orquestan dominio + infraestructura.

La capa de aplicación no contiene reglas de negocio nuevas: delega en los
servicios de dominio puros de :mod:`src.dominio` y coordina la persistencia
SQLAlchemy mediante el patrón **Unit of Work** (:mod:`src.aplicacion.uow`).

Garantías transversales
-----------------------
* **Atomicidad (PBI-16):** la operación de negocio y el evento de auditoría se
  persisten en la *misma* transacción; si falla la auditoría se ejecuta
  ``rollback()`` y no quedan registros huérfanos.
* **Aislamiento de efectos externos (PBI-17/PBI-07):** WhatsApp y la evaluación
  de pagos se despachan *después* del ``commit`` del registro de asistencia, de
  forma asíncrona y totalmente contenida; su fallo nunca revierte asistencia.
"""

from __future__ import annotations

from src.aplicacion.uow import SqlAlchemyUnitOfWork, UnitOfWork, ejecutar_atomico

__all__ = [
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "ejecutar_atomico",
]
