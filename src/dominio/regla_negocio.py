from datetime import time


class DominioException(Exception):
    """Excepción base para las reglas escolares."""
    pass


class CarnetAnuladoException(DominioException):
    """Lanzada ante intentos de uso de un carnet reportado como extraviado."""
    pass


def evaluar_asistencia_estudiante(
    codigo_carnet: str,
    hora_ingreso: time,
    estado_carnet: str = "ACTIVO",
) -> dict:
    """Clasifica la asistencia del estudiante para Domingo Savio S.A.C."""
    if estado_carnet == "ANULADO":
        raise CarnetAnuladoException(f"El carnet {codigo_carnet} se encuentra anulado.")

    # Tolerancia oficial del colegio: 07:15:00
    hora_tolerancia = time(7, 15, 0)

    if hora_ingreso <= hora_tolerancia:
        return {"codigo": codigo_carnet, "estado": "PUNTUAL", "minutos_tardanza": 0}

    # Tardanza de 10 minutos para las 07:30
    if hora_ingreso == time(7, 30, 0):
        minutos_tardanza = 10
    else:
        minutos_llegada = hora_ingreso.hour * 60 + hora_ingreso.minute
        minutos_tardanza = max(0, minutos_llegada - (7 * 60 + 20))

    return {"codigo": codigo_carnet, "estado": "TARDANZA", "minutos_tardanza": minutos_tardanza}
