"""Texto del aviso de ingreso que recibe el apoderado por WhatsApp (PBI-17)."""

from datetime import date, time

from src.dominio.asistencia import Alumno, EstadoAsistencia


def construir_mensaje_ingreso(
    alumno: Alumno,
    apoderado: str | None,
    fecha_escolar: date,
    hora_ingreso: time,
    estado: EstadoAsistencia,
    minutos_tardanza: int,
) -> tuple[str, tuple[str, ...]]:
    """Devuelve el texto libre y las variables para una plantilla de WhatsApp.

    Las variables, en orden, son: alumno, fecha, hora y estado.
    """
    nombre_alumno = f"{alumno.nombres} {alumno.apellidos}"
    fecha = fecha_escolar.strftime("%d/%m/%Y")
    hora = hora_ingreso.strftime("%H:%M")
    if estado == EstadoAsistencia.TARDANZA:
        detalle_estado = f"Tardanza ({minutos_tardanza} min)"
    else:
        detalle_estado = "Puntual"
    saludo = f"Estimado(a) {apoderado}" if apoderado else "Estimado(a) apoderado(a)"
    texto = (
        f"Colegio Domingo Savio: {saludo}, le informamos que {nombre_alumno} "
        f"({alumno.grado} de {alumno.nivel}, sección {alumno.seccion}) ya ingresó "
        f"al colegio hoy {fecha} a las {hora}. Estado: {detalle_estado}."
    )
    return texto, (nombre_alumno, fecha, hora, detalle_estado)
