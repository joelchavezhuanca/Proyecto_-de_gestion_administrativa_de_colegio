"""PBI-13: Exportación de Listas de Asistencia (dominio puro)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Final

from src.dominio.asistencia import (
    Alumno,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    UsuarioOperador,
)
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

ZONA_HORARIA_LIMA: Final[timezone] = timezone(timedelta(hours=-5))
MAX_DIAS_RANGO_EXPORTACION: Final[int] = 366
_PREFIJOS_FORMULA_PELIGROSA: Final[tuple[str, ...]] = ("=", "+", "-", "@")

ENCABEZADOS_EXPORTACION: Final[tuple[str, ...]] = (
    "codigo_alumno",
    "dni",
    "apellidos_nombres",
    "nivel",
    "grado",
    "seccion",
    "fecha_escolar",
    "hora_efectiva",
    "estado",
    "minutos_tardanza",
    "metodo",
    "usuario_responsable",
)


class FormatoExportacion(StrEnum):
    """Formatos oficiales soportados para la exportación de listas de asistencia."""

    CSV = "CSV"
    XLSX = "XLSX"
    PDF = "PDF"


class ExportacionException(Exception):
    """Excepción base del dominio de exportación de asistencias."""


class PermisoExportacionException(ExportacionException):
    """Lanzada cuando el operador no está activo o carece de EXPORTAR_ASISTENCIAS."""


class FiltroExportacionInvalidoException(ExportacionException):
    """Lanzada cuando los filtros o rango de fechas de exportación son inválidos."""


def _codigo_rol(rol: object) -> str:
    valor = getattr(rol, "value", rol)
    return str(valor).strip().upper()


def _es_fecha_pura(valor: object) -> bool:
    return isinstance(valor, date) and not isinstance(valor, datetime)


def _normalizar_texto_opcional(valor: object, campo: str) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise FiltroExportacionInvalidoException(
            f"El filtro '{campo}' debe ser una cadena de texto."
        )
    limpio = valor.strip()
    return limpio or None


def _normalizar_fecha_hora(fecha_hora: datetime) -> datetime:
    if not isinstance(fecha_hora, datetime):
        raise ExportacionException("La fecha de generación debe ser una instancia datetime válida.")
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _coincide_texto(valor: str, filtro: str | None) -> bool:
    return filtro is None or valor.strip().casefold() == filtro.casefold()


def sanitizar_celda_tabular(valor: str) -> str:
    """RN-05: neutraliza Formula Injection anteponiendo apóstrofe si inicia con =, +, - o @."""
    if valor.lstrip().startswith(_PREFIJOS_FORMULA_PELIGROSA):
        return f"'{valor}"
    return valor


@dataclass(frozen=True)
class FiltroExportacionAsistencia:
    """Criterios validados de filtrado para la exportación de asistencias."""

    fecha_desde: date
    fecha_hasta: date
    formato: FormatoExportacion = FormatoExportacion.CSV
    nivel: str | None = None
    grado: str | None = None
    seccion: str | None = None
    estado: EstadoAsistencia | None = None
    alumno_id: int | None = None

    def __post_init__(self) -> None:
        if not _es_fecha_pura(self.fecha_desde) or not _es_fecha_pura(self.fecha_hasta):
            raise FiltroExportacionInvalidoException(
                "Las fechas del filtro deben ser instancias válidas de date."
            )
        if self.fecha_desde > self.fecha_hasta:
            raise FiltroExportacionInvalidoException(
                "La fecha_desde no puede ser posterior a fecha_hasta."
            )
        if (self.fecha_hasta - self.fecha_desde).days > MAX_DIAS_RANGO_EXPORTACION:
            raise FiltroExportacionInvalidoException(
                f"El rango de exportación no puede superar los {MAX_DIAS_RANGO_EXPORTACION} días."
            )
        if not isinstance(self.formato, FormatoExportacion):
            raise FiltroExportacionInvalidoException("El formato de exportación no es válido.")
        if self.estado is not None and not isinstance(self.estado, EstadoAsistencia):
            raise FiltroExportacionInvalidoException("El estado de asistencia del filtro no es válido.")
        if self.alumno_id is not None and (
            isinstance(self.alumno_id, bool)
            or not isinstance(self.alumno_id, int)
            or self.alumno_id <= 0
        ):
            raise FiltroExportacionInvalidoException(
                "El filtro 'alumno_id' debe ser un entero positivo."
            )

        nivel = _normalizar_texto_opcional(self.nivel, "nivel")
        grado = _normalizar_texto_opcional(self.grado, "grado")
        seccion = _normalizar_texto_opcional(self.seccion, "seccion")
        object.__setattr__(self, "nivel", nivel)
        object.__setattr__(self, "grado", grado)
        object.__setattr__(self, "seccion", seccion)


@dataclass(frozen=True)
class FilaExportacionAsistencia:
    """Representa una fila normalizada de las 12 columnas mínimas del reporte."""

    codigo_alumno: str
    dni: str
    apellidos_nombres: str
    nivel: str
    grado: str
    seccion: str
    fecha_escolar: date
    hora_efectiva: time
    estado: EstadoAsistencia
    minutos_tardanza: int
    metodo: MetodoRegistro
    usuario_responsable: str

    def a_tupla(self) -> tuple[str, ...]:
        """Devuelve la fila como tupla de 12 cadenas en el orden de ENCABEZADOS_EXPORTACION."""
        return (
            self.codigo_alumno,
            self.dni,
            self.apellidos_nombres,
            self.nivel,
            self.grado,
            self.seccion,
            self.fecha_escolar.isoformat(),
            self.hora_efectiva.strftime("%H:%M:%S"),
            self.estado.value,
            str(self.minutos_tardanza),
            self.metodo.value,
            self.usuario_responsable,
        )


@dataclass(frozen=True)
class DocumentoExportacionAsistencia:
    """Documento inmutable con metadatos y filas listas para renderizar (CSV/XLSX/PDF)."""

    formato: FormatoExportacion
    generado_por_id: int
    generado_por_username: str
    fecha_generacion: datetime
    filtro: FiltroExportacionAsistencia
    filas: tuple[FilaExportacionAsistencia, ...]
    total_filas: int


def _indexar_alumnos(alumnos: Mapping[int, Alumno] | Iterable[Alumno]) -> Mapping[int, Alumno]:
    if isinstance(alumnos, Mapping):
        return alumnos
    return {alumno.id: alumno for alumno in alumnos}


def _resolver_usuario_responsable(
    asistencia: RegistroAsistencia,
    usuarios_por_id: Mapping[int, str],
) -> str:
    if asistencia.usuario_id in usuarios_por_id:
        return usuarios_por_id[asistencia.usuario_id]
    if asistencia.usuario_id == 0:
        return _codigo_rol(asistencia.rol_usuario)
    return f"usuario:{asistencia.usuario_id}"


class ServicioExportacionAsistencia:
    """Implementa las reglas de negocio del PBI-13 (Exportación de Listas de Asistencia)."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso EXPORTAR_ASISTENCIAS en servidor (RN-01)."""
        if not operador.activo:
            raise PermisoExportacionException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.EXPORTAR_ASISTENCIAS,
            roles=roles,
        ):
            raise PermisoExportacionException(
                f"El rol {_codigo_rol(operador.rol)} no está autorizado para exportar asistencias."
            )

    @staticmethod
    def preparar_exportacion(
        operador: UsuarioOperador,
        filtro: FiltroExportacionAsistencia,
        alumnos: Mapping[int, Alumno] | Iterable[Alumno],
        asistencias: Iterable[RegistroAsistencia],
        usuarios_por_id: Mapping[int, str],
        fecha_generacion: datetime,
        roles: Sequence[Rol] | None = None,
    ) -> DocumentoExportacionAsistencia:
        """Filtra, ordena y sanitiza los registros de asistencia para exportación."""
        ServicioExportacionAsistencia.validar_operador(operador, roles=roles)
        if not isinstance(filtro, FiltroExportacionAsistencia):
            raise FiltroExportacionInvalidoException(
                "Debe proporcionar una instancia válida de FiltroExportacionAsistencia."
            )
        fecha_gen_norm = _normalizar_fecha_hora(fecha_generacion)
        alumnos_mapa = _indexar_alumnos(alumnos)
        es_tabular = filtro.formato in (FormatoExportacion.CSV, FormatoExportacion.XLSX)

        registros_ordenables: list[
            tuple[tuple[date, str, str, str, str], FilaExportacionAsistencia]
        ] = []

        for asistencia in asistencias:
            if not (filtro.fecha_desde <= asistencia.fecha_escolar <= filtro.fecha_hasta):
                continue
            if filtro.estado is not None and asistencia.estado != filtro.estado:
                continue
            if filtro.alumno_id is not None and asistencia.alumno_id != filtro.alumno_id:
                continue

            alumno = alumnos_mapa.get(asistencia.alumno_id)
            if alumno is None:
                continue

            nivel = asistencia.nivel or alumno.nivel
            grado = asistencia.grado or alumno.grado
            seccion = asistencia.seccion or alumno.seccion
            if not (
                _coincide_texto(nivel, filtro.nivel)
                and _coincide_texto(grado, filtro.grado)
                and _coincide_texto(seccion, filtro.seccion)
            ):
                continue

            apellidos_nombres = f"{alumno.apellidos}, {alumno.nombres}".strip(", ")
            usuario_responsable = _resolver_usuario_responsable(asistencia, usuarios_por_id)
            clave_orden = (
                asistencia.fecha_escolar,
                nivel.casefold(),
                grado.casefold(),
                seccion.casefold(),
                apellidos_nombres.casefold(),
            )

            sanitizar = sanitizar_celda_tabular if es_tabular else (lambda texto: texto)
            fila = FilaExportacionAsistencia(
                codigo_alumno=sanitizar(alumno.codigo),
                dni=sanitizar(alumno.dni),
                apellidos_nombres=sanitizar(apellidos_nombres),
                nivel=sanitizar(nivel),
                grado=sanitizar(grado),
                seccion=sanitizar(seccion),
                fecha_escolar=asistencia.fecha_escolar,
                hora_efectiva=asistencia.hora_efectiva,
                estado=asistencia.estado,
                minutos_tardanza=asistencia.minutos_tardanza,
                metodo=asistencia.metodo,
                usuario_responsable=sanitizar(usuario_responsable),
            )
            registros_ordenables.append((clave_orden, fila))

        registros_ordenables.sort(key=lambda item: item[0])
        filas = tuple(fila for _, fila in registros_ordenables)

        return DocumentoExportacionAsistencia(
            formato=filtro.formato,
            generado_por_id=operador.id,
            generado_por_username=operador.username,
            fecha_generacion=fecha_gen_norm,
            filtro=filtro,
            filas=filas,
            total_filas=len(filas),
        )
