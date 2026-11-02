from datetime import time


class AsistenciaUnificada:
    """Regla unificada de asistencia para Domingo Savio S.A.C."""

    # Hora límite de ingreso sin tardanza: 08:00:00
    HORA_LIMITE = time(8, 0, 0)

    @classmethod
    def registrar_asistencia(cls, hora_ingreso: time) -> dict:
        """Clasifica el ingreso como ASISTENCIA o TARDANZA y calcula los minutos de retraso."""
        if not isinstance(hora_ingreso, time):
            raise TypeError("hora_ingreso debe ser un objeto datetime.time")

        if hora_ingreso <= cls.HORA_LIMITE:
            return {"estado": "ASISTENCIA", "minutos_tardanza": 0}

        minutos_ingreso = hora_ingreso.hour * 60 + hora_ingreso.minute
        minutos_limite = cls.HORA_LIMITE.hour * 60 + cls.HORA_LIMITE.minute
        return {"estado": "TARDANZA", "minutos_tardanza": minutos_ingreso - minutos_limite}
