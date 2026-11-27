"""Reloj y zona horaria institucional única para la aplicación web.

El servidor es la fuente oficial de fecha y hora (RN-06 / sección 1.4).
El Perú no aplica horario de verano, por lo que se utiliza un huso horario
fijo de America/Lima (UTC-5).
"""

from datetime import datetime, time, timedelta, timezone

ZONA_HORARIA_LIMA = timezone(timedelta(hours=-5), name="America/Lima")
DESPLAZAMIENTO_PERU = timedelta(hours=-5)


def hora_institucional() -> datetime:
    """Devuelve la fecha y hora institucional actual en America/Lima (UTC-5)."""
    return datetime.now(ZONA_HORARIA_LIMA).replace(microsecond=0)


def hora_actual() -> time:
    """Hora institucional actual, sin microsegundos."""
    return hora_institucional().time()


def ahora_lima() -> datetime:
    """Devuelve la fecha y hora actual consciente de la zona horaria America/Lima."""
    return datetime.now(ZONA_HORARIA_LIMA)
