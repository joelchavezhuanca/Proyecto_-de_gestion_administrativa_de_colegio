"""PBI-12: Ficha Informativa del Alumno.

Ensambla en un único DTO inmutable la información de matrícula, estado
académico, carnet, asistencia, rendimiento y —solo si el operador posee el
permiso correspondiente— el resumen financiero del alumno.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from src.dominio.asistencia import (
    AlumnoNoEncontradoException,
    EstadoAsistencia,
    RegistroAsistencia,
    UsuarioOperador,
)
from src.dominio.calificaciones import PromedioPeriodo
from src.dominio.carnets import CarnetEscolar
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.matricula import Apoderado, FichaMatricula
from src.dominio.pagos import EstadoObligacion, ObligacionPago
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

ZONA_HORARIA_LIMA: Final[timezone] = timezone(timedelta(hours=-5))
_CERO: Final[Decimal] = Decimal("0.00")
_CIEN: Final[Decimal] = Decimal("100")
_DOS_DECIMALES: Final[Decimal] = Decimal("0.01")


class FichaAlumnoException(Exception):
    """Excepción base del dominio de la ficha informativa del alumno."""


class PermisoFichaAlumnoException(FichaAlumnoException):
    """Lanzada cuando el operador no está activo o carece del permiso requerido."""


def _validar_entero_no_negativo(valor: object, campo: str) -> int:
    """Valida que un conteo sea un entero no negativo (excluyendo booleanos)."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise FichaAlumnoException(f"El campo '{campo}' debe ser un entero no negativo.")
    return valor


def _validar_decimal_no_negativo(valor: object, campo: str) -> Decimal:
    """Valida que un monto sea un Decimal finito no negativo."""
    if not isinstance(valor, Decimal) or not valor.is_finite() or valor < _CERO:
        raise FichaAlumnoException(
            f"El campo '{campo}' debe ser un Decimal finito no negativo."
        )
    return valor


@dataclass(frozen=True)
class ResumenAsistenciaAlumno:
    """Consolidado inmutable de asistencia del alumno.

    El porcentaje considera como asistencia efectiva los registros ``PUNTUAL``,
    ``TARDANZA`` y ``JUSTIFICADO``; los registros ``PENDIENTE`` no forman parte
    del denominador.
    """

    puntuales: int
    tardanzas: int
    ausentes: int
    justificados: int
    porcentaje_asistencia: Decimal

    def __post_init__(self) -> None:
        for campo in ("puntuales", "tardanzas", "ausentes", "justificados"):
            _validar_entero_no_negativo(getattr(self, campo), campo)
        porcentaje = _validar_decimal_no_negativo(
            self.porcentaje_asistencia, "porcentaje_asistencia"
        )
        if porcentaje > _CIEN:
            raise FichaAlumnoException(
                "El porcentaje de asistencia no puede superar 100."
            )
        object.__setattr__(
            self,
            "porcentaje_asistencia",
            porcentaje.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP),
        )


@dataclass(frozen=True)
class ResumenPagosAlumno:
    """Consolidado inmutable de obligaciones económicas del alumno."""

    total_obligaciones: int
    monto_total: Decimal
    monto_pagado: Decimal
    monto_pendiente: Decimal
    obligaciones_vencidas: int
    monto_vencido: Decimal

    def __post_init__(self) -> None:
        _validar_entero_no_negativo(self.total_obligaciones, "total_obligaciones")
        _validar_entero_no_negativo(
            self.obligaciones_vencidas, "obligaciones_vencidas"
        )
        for campo in (
            "monto_total",
            "monto_pagado",
            "monto_pendiente",
            "monto_vencido",
        ):
            _validar_decimal_no_negativo(getattr(self, campo), campo)


@dataclass(frozen=True)
class FichaInformativaAlumno:
    """Vista consolidada e inmutable del alumno (RN-02)."""

    ficha_matricula: FichaMatricula
    estado_actual: EstadoAcademico
    carnet_activo: CarnetEscolar | None
    resumen_asistencia: ResumenAsistenciaAlumno
    promedios_cursos: tuple[PromedioPeriodo, ...]
    resumen_pagos: ResumenPagosAlumno | None
    fecha_referencia: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.ficha_matricula, FichaMatricula):
            raise FichaAlumnoException("La ficha de matrícula proporcionada no es válida.")
        if not isinstance(self.estado_actual, EstadoAcademico):
            raise FichaAlumnoException("El estado académico proporcionado no es válido.")
        if self.carnet_activo is not None and not isinstance(
            self.carnet_activo, CarnetEscolar
        ):
            raise FichaAlumnoException("El carnet proporcionado no es válido.")
        if not isinstance(self.resumen_asistencia, ResumenAsistenciaAlumno):
            raise FichaAlumnoException("El resumen de asistencia no es válido.")
        if self.resumen_pagos is not None and not isinstance(
            self.resumen_pagos, ResumenPagosAlumno
        ):
            raise FichaAlumnoException("El resumen de pagos no es válido.")
        promedios = tuple(self.promedios_cursos)
        if any(not isinstance(promedio, PromedioPeriodo) for promedio in promedios):
            raise FichaAlumnoException("Los promedios por curso no son válidos.")
        if not isinstance(self.fecha_referencia, datetime):
            raise FichaAlumnoException("La fecha de referencia no es válida.")
        object.__setattr__(self, "promedios_cursos", promedios)

    @property
    def apoderados(self) -> tuple[Apoderado, ...]:
        """Apoderados registrados en la ficha de matrícula del alumno."""
        return self.ficha_matricula.apoderados


def _normalizar_estado(estado: EstadoAcademico | str) -> EstadoAcademico:
    """Normaliza el estado académico recibido, rechazando valores desconocidos."""
    if isinstance(estado, EstadoAcademico):
        return estado
    try:
        return EstadoAcademico(estado)
    except (TypeError, ValueError) as exc:
        raise FichaAlumnoException(
            f"El estado académico '{estado}' no es válido."
        ) from exc


def _normalizar_fecha_hora(fecha_hora: datetime | None) -> datetime:
    """Normaliza la fecha de referencia al huso institucional America/Lima (UTC-5)."""
    if fecha_hora is None:
        return datetime.now(ZONA_HORARIA_LIMA)
    if not isinstance(fecha_hora, datetime):
        raise FichaAlumnoException(
            "La fecha de referencia debe ser una fecha y hora válida."
        )
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora


def _puede_ver_pagos(operador: UsuarioOperador, roles: Sequence[Rol] | None) -> bool:
    """Evalúa si el operador puede ver el bloque financiero (RN-03)."""
    return ServicioAutenticacionYPermisos.tiene_permiso(
        operador.rol, PermisoOperacion.VER_ALERTA_PAGOS, roles=roles
    ) or ServicioAutenticacionYPermisos.tiene_permiso(
        operador.rol, PermisoOperacion.GESTIONAR_PAGOS, roles=roles
    )


def _calcular_porcentaje_asistencia(
    puntuales: int,
    tardanzas: int,
    ausentes: int,
    justificados: int,
) -> Decimal:
    """Calcula el porcentaje de asistencia efectiva con redondeo HALF_UP."""
    total = puntuales + tardanzas + ausentes + justificados
    if total == 0:
        return _CERO
    efectivos = puntuales + tardanzas + justificados
    return (Decimal(efectivos) / Decimal(total) * _CIEN).quantize(
        _DOS_DECIMALES, rounding=ROUND_HALF_UP
    )


def _resumir_asistencia(
    asistencias: Sequence[RegistroAsistencia],
) -> ResumenAsistenciaAlumno:
    """Calcula los conteos y el porcentaje de asistencia del alumno."""
    puntuales = sum(
        1 for registro in asistencias if registro.estado == EstadoAsistencia.PUNTUAL
    )
    tardanzas = sum(
        1 for registro in asistencias if registro.estado == EstadoAsistencia.TARDANZA
    )
    ausentes = sum(
        1 for registro in asistencias if registro.estado == EstadoAsistencia.AUSENTE
    )
    justificados = sum(
        1 for registro in asistencias if registro.estado == EstadoAsistencia.JUSTIFICADO
    )
    return ResumenAsistenciaAlumno(
        puntuales=puntuales,
        tardanzas=tardanzas,
        ausentes=ausentes,
        justificados=justificados,
        porcentaje_asistencia=_calcular_porcentaje_asistencia(
            puntuales=puntuales,
            tardanzas=tardanzas,
            ausentes=ausentes,
            justificados=justificados,
        ),
    )


def _resumir_pagos(
    obligaciones: Sequence[ObligacionPago],
    fecha_referencia: datetime,
) -> ResumenPagosAlumno:
    """Calcula el resumen financiero del alumno a la fecha de referencia (RN-03)."""
    fecha_limite = fecha_referencia.date()
    pendientes = [
        obligacion
        for obligacion in obligaciones
        if obligacion.estado in (EstadoObligacion.PENDIENTE, EstadoObligacion.VENCIDO)
    ]
    vencidas = [
        obligacion
        for obligacion in pendientes
        if obligacion.estado == EstadoObligacion.VENCIDO
        or obligacion.fecha_vencimiento < fecha_limite
    ]
    return ResumenPagosAlumno(
        total_obligaciones=len(obligaciones),
        monto_total=sum((obligacion.monto for obligacion in obligaciones), _CERO),
        monto_pagado=sum(
            (
                obligacion.monto
                for obligacion in obligaciones
                if obligacion.estado == EstadoObligacion.PAGADO
            ),
            _CERO,
        ),
        monto_pendiente=sum((obligacion.monto for obligacion in pendientes), _CERO),
        obligaciones_vencidas=len(vencidas),
        monto_vencido=sum((obligacion.monto for obligacion in vencidas), _CERO),
    )


class ServicioFichaAlumno:
    """Implementa las reglas de negocio del PBI-12 (Ficha Informativa del Alumno)."""

    @staticmethod
    def _validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None,
    ) -> None:
        """Valida que el operador esté activo y tenga permiso de consulta (RN-01)."""
        if not isinstance(operador, UsuarioOperador):
            raise PermisoFichaAlumnoException("El operador proporcionado no es válido.")
        if not operador.activo:
            raise PermisoFichaAlumnoException(
                "El operador no cuenta con una cuenta activa."
            )
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
            roles=roles,
        ):
            raise PermisoFichaAlumnoException(
                "El operador no tiene permiso para consultar la ficha del alumno."
            )

    @staticmethod
    def construir_ficha(
        operador: UsuarioOperador,
        ficha_matricula: FichaMatricula | None,
        estado_actual: EstadoAcademico | str,
        carnet_activo: CarnetEscolar | None,
        asistencias_alumno: Sequence[RegistroAsistencia],
        promedios_cursos: Sequence[PromedioPeriodo],
        obligaciones_pago: Sequence[ObligacionPago] = (),
        fecha_referencia: datetime | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> FichaInformativaAlumno:
        """Construye la ficha informativa consolidada del alumno (RN-02 a RN-05)."""
        ServicioFichaAlumno._validar_operador(operador, roles)
        if ficha_matricula is None:
            raise AlumnoNoEncontradoException(
                "No se encontró la ficha de matrícula del alumno solicitado."
            )

        estado = _normalizar_estado(estado_actual)
        momento = _normalizar_fecha_hora(fecha_referencia)
        alumno_id = ficha_matricula.alumno_id

        asistencias = tuple(
            registro
            for registro in asistencias_alumno
            if registro.alumno_id == alumno_id
        )
        promedios = tuple(
            promedio for promedio in promedios_cursos if promedio.alumno_id == alumno_id
        )
        obligaciones = tuple(
            obligacion
            for obligacion in obligaciones_pago
            if obligacion.alumno_id == alumno_id
        )

        return FichaInformativaAlumno(
            ficha_matricula=ficha_matricula,
            estado_actual=estado,
            carnet_activo=carnet_activo,
            resumen_asistencia=_resumir_asistencia(asistencias),
            promedios_cursos=promedios,
            resumen_pagos=(
                _resumir_pagos(obligaciones, momento)
                if _puede_ver_pagos(operador, roles)
                else None
            ),
            fecha_referencia=momento,
        )
