"""Reloj institucional único para la aplicación web.

El servidor es la fuente oficial de fecha y hora (RN-06 / sección 1.4 de la
especificación). El Perú no aplica horario de verano, por lo que se utiliza un
desplazamiento fijo de UTC-5.
"""

from datetime import UTC, datetime, time, timedelta

DESPLAZAMIENTO_PERU = timedelta(hours=-5)


def hora_institucional() -> datetime:
    """Devuelve la fecha y hora institucional (America/Lima, UTC-5) sin tzinfo."""
    return (datetime.now(UTC) + DESPLAZAMIENTO_PERU).replace(tzinfo=None, microsecond=0)


def hora_actual() -> time:
    """Hora institucional actual, sin microsegundos."""
    return hora_institucional().time().replace(microsecond=0)
