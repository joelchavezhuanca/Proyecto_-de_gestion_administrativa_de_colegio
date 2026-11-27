"""PBI-10: libro de calificaciones de 3 niveles y cálculo de promedios.

Jerarquía: Período (``PeriodoAcademico``) → Rubros (``RubroEvaluacion``, pesos = 100 %)
→ Actividades (``ActividadEvaluable``) → Calificaciones (``Calificacion``).

Toda la aritmética usa ``Decimal`` con ``ROUND_HALF_UP`` a 2 decimales; nunca ``float``.
No existe el estado ``EXONERADO``: toda actividad activa del rubro entra en el cálculo.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final

from src.dominio.asistencia import UsuarioOperador
from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.docentes import (
    ActorDocente,
    AsignacionDocente,
    ServicioAsignacionDocente,
)
from src.dominio.justificaciones import PeriodoAcademico
from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolUsuario,
    ServicioAutenticacionYPermisos,
)

NOTA_MINIMA: Final[Decimal] = Decimal("0")
NOTA_MAXIMA: Final[Decimal] = Decimal("20")
PESO_TOTAL: Final[Decimal] = Decimal("100")
PRECISION: Final[Decimal] = Decimal("0.01")

UMBRAL_AD: Final[Decimal] = Decimal("18")
UMBRAL_A: Final[Decimal] = Decimal("14")
UMBRAL_B: Final[Decimal] = Decimal("11")


class EscalaLiteral(StrEnum):
    AD = "AD"
    A = "A"
    B = "B"
    C = "C"


class CalificacionException(Exception):
    """Excepción base del módulo de calificaciones."""


class PermisoCalificacionException(CalificacionException):
    """Lanzada cuando el actor no está activo, carece de permiso o de asignación válida."""


class NotaFueraDeRangoException(CalificacionException):
    """Lanzada cuando una nota no es un Decimal válido dentro de [0, 20]."""


class PesosRubrosInvalidosException(CalificacionException):
    """Lanzada cuando los pesos de los rubros son inválidos o no suman 100 %."""


class PeriodoCalificacionCerradoException(CalificacionException):
    """Lanzada al operar sobre un período académico cerrado."""


class FechaLimiteNotasVencidaException(CalificacionException):
    """Lanzada al operar después de la fecha límite de notas del período."""


class ActividadInvalidaException(CalificacionException):
    """Lanzada ante actividades inválidas, inactivas, fuera de contexto o sin nota."""


# ---------------------------------------------------------------------------
# Helpers de validación
# ---------------------------------------------------------------------------


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISION, rounding=ROUND_HALF_UP)


def _texto(valor: object, campo: str, excepcion: type[CalificacionException]) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise excepcion(f"El campo '{campo}' es obligatorio y no puede estar vacío.")
    return valor.strip()


def _entero_positivo(valor: object, campo: str) -> int:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise CalificacionException(f"El campo '{campo}' debe ser un entero positivo.")
    return valor


def _booleano(valor: object, campo: str, excepcion: type[CalificacionException]) -> bool:
    if not isinstance(valor, bool):
        raise excepcion(f"El campo '{campo}' debe ser booleano.")
    return valor


def _a_decimal(valor: object, excepcion: type[CalificacionException], campo: str) -> Decimal:
    """Acepta ``Decimal`` finito o ``int``; rechaza ``float``, ``bool`` y textos."""
    if isinstance(valor, bool) or not isinstance(valor, Decimal | int):
        raise excepcion(f"El campo '{campo}' debe ser Decimal (nunca float).")
    decimal = Decimal(valor)
    if not decimal.is_finite():
        raise excepcion(f"El campo '{campo}' debe ser un número finito.")
    return decimal


def _validar_nota(valor: object, campo: str = "nota") -> Decimal:
    nota = _a_decimal(valor, NotaFueraDeRangoException, campo)
    if not NOTA_MINIMA <= nota <= NOTA_MAXIMA:
        raise NotaFueraDeRangoException(
            f"La {campo} debe estar en el rango [{NOTA_MINIMA}, {NOTA_MAXIMA}]."
        )
    return _redondear(nota)


def _normalizar_fecha_hora(fecha_hora: object) -> datetime:
    if not isinstance(fecha_hora, datetime):
        raise CalificacionException("La fecha y hora debe ser una instancia datetime válida.")
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _fecha_lima(fecha: date | datetime) -> date:
    """Convierte la marca temporal a la fecha calendario institucional (America/Lima)."""
    if isinstance(fecha, datetime):
        return _normalizar_fecha_hora(fecha).date()
    return fecha


def _generar_id(prefijo: str) -> str:
    return f"{prefijo}-{uuid.uuid4().hex[:12]}"


def _actor_activo(actor: ActorDocente) -> bool:
    if isinstance(actor, UsuarioOperador):
        return actor.activo
    return actor.estado == EstadoUsuario.ACTIVO


def _es_admin(actor: ActorDocente) -> bool:
    rol = actor.rol
    codigo = rol.value if isinstance(rol, RolUsuario) else str(rol).strip().upper()
    return codigo == RolUsuario.ADMIN.value


# ---------------------------------------------------------------------------
# Entidades inmutables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RubroEvaluacion:
    id: str
    asignacion_docente_id: str
    periodo_id: int
    nombre: str
    peso_porcentaje: Decimal
    activo: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _texto(self.id, "id", CalificacionException))
        object.__setattr__(
            self,
            "asignacion_docente_id",
            _texto(self.asignacion_docente_id, "asignacion_docente_id", CalificacionException),
        )
        _entero_positivo(self.periodo_id, "periodo_id")
        object.__setattr__(self, "nombre", _texto(self.nombre, "nombre", CalificacionException))
        peso = _a_decimal(self.peso_porcentaje, PesosRubrosInvalidosException, "peso_porcentaje")
        if not NOTA_MINIMA < peso <= PESO_TOTAL:
            raise PesosRubrosInvalidosException(
                f"El peso del rubro '{self.nombre}' debe ser mayor que 0 y como máximo 100."
            )
        object.__setattr__(self, "peso_porcentaje", peso)
        _booleano(self.activo, "activo", CalificacionException)


@dataclass(frozen=True)
class ActividadEvaluable:
    id: str
    rubro_id: str
    titulo: str
    fecha: date
    activo: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _texto(self.id, "id", ActividadInvalidaException))
        object.__setattr__(
            self, "rubro_id", _texto(self.rubro_id, "rubro_id", ActividadInvalidaException)
        )
        object.__setattr__(
            self, "titulo", _texto(self.titulo, "titulo", ActividadInvalidaException)
        )
        if not isinstance(self.fecha, date):
            raise ActividadInvalidaException("La fecha de la actividad debe ser una fecha válida.")
        _booleano(self.activo, "activo", ActividadInvalidaException)


@dataclass(frozen=True)
class Calificacion:
    id: str
    actividad_id: str
    alumno_id: int
    nota: Decimal
    usuario_id: int
    actualizado_en: datetime
    observacion: str | None = None
    nota_anterior: Decimal | None = None
    motivo_modificacion: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _texto(self.id, "id", CalificacionException))
        object.__setattr__(
            self,
            "actividad_id",
            _texto(self.actividad_id, "actividad_id", CalificacionException),
        )
        _entero_positivo(self.alumno_id, "alumno_id")
        _entero_positivo(self.usuario_id, "usuario_id")
        object.__setattr__(self, "nota", _validar_nota(self.nota))
        object.__setattr__(self, "actualizado_en", _normalizar_fecha_hora(self.actualizado_en))

        if self.nota_anterior is not None:
            object.__setattr__(
                self, "nota_anterior", _validar_nota(self.nota_anterior, "nota_anterior")
            )
        if self.motivo_modificacion is not None:
            object.__setattr__(
                self,
                "motivo_modificacion",
                _texto(self.motivo_modificacion, "motivo_modificacion", CalificacionException),
            )
        if self.observacion is not None:
            if not isinstance(self.observacion, str):
                raise CalificacionException("La observación debe ser texto.")
            object.__setattr__(self, "observacion", self.observacion.strip() or None)


@dataclass(frozen=True)
class PromedioRubro:
    rubro_id: str
    nombre_rubro: str
    peso_porcentaje: Decimal
    promedio: Decimal


@dataclass(frozen=True)
class PromedioPeriodo:
    alumno_id: int
    curso_id: int
    periodo_id: int
    desglose_rubros: tuple[PromedioRubro, ...]
    nota_final: Decimal
    escala_literal: EscalaLiteral


@dataclass(frozen=True)
class PromedioAnualCurso:
    alumno_id: int
    curso_id: int
    anio_lectivo: int
    promedios_periodo: tuple[PromedioPeriodo, ...]
    promedio_anual: Decimal
    escala_literal: EscalaLiteral


# ---------------------------------------------------------------------------
# Servicio de dominio
# ---------------------------------------------------------------------------


class ServicioCalificaciones:
    """Implementa las reglas de negocio del PBI-10 (Libro de Calificaciones)."""

    @staticmethod
    def convertir_a_literal(nota: Decimal) -> EscalaLiteral:
        """Convierte una nota vigesimal a la escala literal (AD, A, B, C)."""
        valor = _validar_nota(nota)
        if valor >= UMBRAL_AD:
            return EscalaLiteral.AD
        if valor >= UMBRAL_A:
            return EscalaLiteral.A
        if valor >= UMBRAL_B:
            return EscalaLiteral.B
        return EscalaLiteral.C

    # -- Validaciones transversales -----------------------------------------

    @staticmethod
    def _autorizar(
        actor: ActorDocente,
        asignacion: AsignacionDocente,
        periodo: PeriodoAcademico,
        fecha_actual: date | datetime,
        asignaciones: Sequence[AsignacionDocente],
        roles: Sequence[Rol] | None,
    ) -> None:
        """RN-01 (permiso + ámbito PBI-11) y RN-03 (período abierto y fecha límite)."""
        if not _actor_activo(actor):
            raise PermisoCalificacionException("El usuario no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            actor.rol, PermisoOperacion.REGISTRAR_CALIFICACIONES, roles=roles
        ):
            raise PermisoCalificacionException(
                "El usuario no tiene permiso para registrar calificaciones."
            )
        if not asignacion.activa:
            raise PermisoCalificacionException("La asignación docente se encuentra revocada.")

        if not _es_admin(actor):
            vigente = ServicioAsignacionDocente.validar_ambito_docente(
                actor,
                asignacion.curso_id,
                asignacion.salon_id,
                asignacion.anio_lectivo,
                asignaciones,
                roles=roles,
                fecha_hora=fecha_actual if isinstance(fecha_actual, datetime) else None,
            )
            if vigente.id != asignacion.id:
                raise PermisoCalificacionException(
                    "La asignación indicada no pertenece al docente."
                )

        if periodo.anio_lectivo and periodo.anio_lectivo != asignacion.anio_lectivo:
            raise CalificacionException(
                "El año lectivo del período no coincide con el de la asignación docente."
            )
        if periodo.cerrado:
            raise PeriodoCalificacionCerradoException(
                f"El período '{periodo.nombre}' está cerrado para calificaciones."
            )
        hoy = _fecha_lima(fecha_actual)
        if periodo.fecha_limite_notas is not None and hoy > periodo.fecha_limite_notas:
            raise FechaLimiteNotasVencidaException(
                f"La fecha límite de notas ({periodo.fecha_limite_notas.isoformat()}) "
                f"del período '{periodo.nombre}' ha vencido."
            )

    # -- Nivel 2: rubros ----------------------------------------------------

    @staticmethod
    def configurar_rubros(
        docente: ActorDocente,
        asignacion: AsignacionDocente,
        periodo: PeriodoAcademico,
        rubros_propuestos: Sequence[tuple[str, Decimal]],
        fecha_actual: date | datetime,
        asignaciones: Sequence[AsignacionDocente],
        roles: Sequence[Rol] | None = None,
    ) -> tuple[RubroEvaluacion, ...]:
        """Configura los rubros (nombre, peso) del docente; los pesos deben sumar 100 %."""
        ServicioCalificaciones._autorizar(
            docente, asignacion, periodo, fecha_actual, asignaciones, roles
        )
        if not rubros_propuestos:
            raise PesosRubrosInvalidosException("Debe definir al menos un rubro de evaluación.")

        rubros = tuple(
            RubroEvaluacion(
                id=_generar_id("rub"),
                asignacion_docente_id=asignacion.id,
                periodo_id=periodo.id,
                nombre=nombre,
                peso_porcentaje=peso,
            )
            for nombre, peso in rubros_propuestos
        )

        nombres = {rubro.nombre.casefold() for rubro in rubros}
        if len(nombres) != len(rubros):
            raise CalificacionException("Los nombres de los rubros deben ser únicos.")

        total = sum((rubro.peso_porcentaje for rubro in rubros), Decimal("0"))
        if total != PESO_TOTAL:
            raise PesosRubrosInvalidosException(
                f"La suma de pesos de los rubros debe ser exactamente 100 % (actual: {total} %)."
            )
        return rubros

    # -- Nivel 3: actividades -----------------------------------------------

    @staticmethod
    def crear_actividad(
        docente: ActorDocente,
        asignacion: AsignacionDocente,
        periodo: PeriodoAcademico,
        rubro: RubroEvaluacion,
        titulo: str,
        fecha_actividad: date,
        fecha_actual: date | datetime,
        asignaciones: Sequence[AsignacionDocente],
        roles: Sequence[Rol] | None = None,
    ) -> ActividadEvaluable:
        """Crea una actividad evaluable dentro de un rubro activo del docente."""
        ServicioCalificaciones._autorizar(
            docente, asignacion, periodo, fecha_actual, asignaciones, roles
        )
        if rubro.asignacion_docente_id != asignacion.id or rubro.periodo_id != periodo.id:
            raise ActividadInvalidaException(
                "El rubro no pertenece a la asignación docente o al período indicado."
            )
        if not rubro.activo:
            raise ActividadInvalidaException("No se pueden crear actividades en un rubro inactivo.")
        if not isinstance(fecha_actividad, date):
            raise ActividadInvalidaException("La fecha de la actividad debe ser una fecha válida.")

        fecha = _fecha_lima(fecha_actividad)
        limite_superior = max(periodo.fecha_fin, periodo.fecha_limite_notas or periodo.fecha_fin)
        if not periodo.fecha_inicio <= fecha <= limite_superior:
            raise ActividadInvalidaException(
                "La fecha de la actividad debe estar dentro del período académico."
            )

        return ActividadEvaluable(
            id=_generar_id("act"),
            rubro_id=rubro.id,
            titulo=titulo,
            fecha=fecha,
        )

    # -- Nivel 4: calificaciones --------------------------------------------

    @staticmethod
    def registrar_calificacion(
        docente: ActorDocente,
        asignacion: AsignacionDocente,
        periodo: PeriodoAcademico,
        actividad: ActividadEvaluable,
        alumno_id: int,
        nota: Decimal,
        fecha_hora: datetime,
        asignaciones: Sequence[AsignacionDocente],
        calificacion_existente: Calificacion | None = None,
        motivo_modificacion: str | None = None,
        observacion: str | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> Calificacion:
        """Registra o modifica (RN-06) la nota de un alumno en una actividad."""
        momento = _normalizar_fecha_hora(fecha_hora)
        ServicioCalificaciones._autorizar(
            docente, asignacion, periodo, momento, asignaciones, roles
        )
        if not actividad.activo:
            raise ActividadInvalidaException("No se puede calificar una actividad inactiva.")
        alumno = _entero_positivo(alumno_id, "alumno_id")
        nota_validada = _validar_nota(nota)

        if calificacion_existente is None:
            return Calificacion(
                id=_generar_id("cal"),
                actividad_id=actividad.id,
                alumno_id=alumno,
                nota=nota_validada,
                usuario_id=docente.id,
                actualizado_en=momento,
                observacion=observacion,
            )

        if (
            calificacion_existente.actividad_id != actividad.id
            or calificacion_existente.alumno_id != alumno
        ):
            raise CalificacionException(
                "La calificación existente no corresponde a la actividad y alumno indicados."
            )
        if not isinstance(motivo_modificacion, str) or not motivo_modificacion.strip():
            raise CalificacionException(
                "Debe indicar el motivo de modificación al cambiar una nota existente."
            )
        return Calificacion(
            id=calificacion_existente.id,
            actividad_id=actividad.id,
            alumno_id=alumno,
            nota=nota_validada,
            usuario_id=docente.id,
            actualizado_en=momento,
            observacion=observacion,
            nota_anterior=calificacion_existente.nota,
            motivo_modificacion=motivo_modificacion,
        )

    # -- Cálculo de promedios (RN-05) ---------------------------------------

    @staticmethod
    def calcular_promedio_periodo(
        alumno_id: int,
        curso_id: int,
        periodo_id: int,
        rubros: Sequence[RubroEvaluacion],
        actividades: Sequence[ActividadEvaluable],
        calificaciones: Sequence[Calificacion],
        tratar_faltante_como_cero: bool = True,
    ) -> PromedioPeriodo:
        """Nota_Periodo = Σ Promedio_Rubro × (Peso_Rubro / 100), redondeada HALF_UP."""
        rubros_activos = [r for r in rubros if r.activo and r.periodo_id == periodo_id]
        total = sum((r.peso_porcentaje for r in rubros_activos), Decimal("0"))
        if not rubros_activos or total != PESO_TOTAL:
            raise PesosRubrosInvalidosException(
                f"Los rubros activos del período deben sumar 100 % (actual: {total} %)."
            )

        notas_alumno = {c.actividad_id: c.nota for c in calificaciones if c.alumno_id == alumno_id}

        desglose: list[PromedioRubro] = []
        nota_final = Decimal("0")
        for rubro in rubros_activos:
            del_rubro = [a for a in actividades if a.activo and a.rubro_id == rubro.id]
            if not del_rubro:
                raise ActividadInvalidaException(
                    f"El rubro '{rubro.nombre}' no tiene actividades evaluables."
                )
            suma = Decimal("0")
            for actividad in del_rubro:
                nota = notas_alumno.get(actividad.id)
                if nota is None:
                    if not tratar_faltante_como_cero:
                        raise ActividadInvalidaException(
                            f"Falta la nota del alumno {alumno_id} en la actividad "
                            f"'{actividad.titulo}'."
                        )
                    nota = Decimal("0")
                suma += nota
            promedio = _redondear(suma / Decimal(len(del_rubro)))
            desglose.append(
                PromedioRubro(
                    rubro_id=rubro.id,
                    nombre_rubro=rubro.nombre,
                    peso_porcentaje=rubro.peso_porcentaje,
                    promedio=promedio,
                )
            )
            nota_final += promedio * rubro.peso_porcentaje / PESO_TOTAL

        nota_final = _redondear(nota_final)
        return PromedioPeriodo(
            alumno_id=alumno_id,
            curso_id=curso_id,
            periodo_id=periodo_id,
            desglose_rubros=tuple(desglose),
            nota_final=nota_final,
            escala_literal=ServicioCalificaciones.convertir_a_literal(nota_final),
        )

    @staticmethod
    def calcular_promedio_anual(
        alumno_id: int,
        curso_id: int,
        anio_lectivo: int,
        promedios_periodo: Sequence[PromedioPeriodo],
    ) -> PromedioAnualCurso:
        """Promedio_Anual_Curso = promedio de las notas finales de los períodos oficiales."""
        if not promedios_periodo:
            raise CalificacionException("Se requiere al menos un promedio de período.")
        for promedio in promedios_periodo:
            if promedio.alumno_id != alumno_id or promedio.curso_id != curso_id:
                raise CalificacionException(
                    "Todos los promedios de período deben corresponder al mismo alumno y curso."
                )
        periodos = [p.periodo_id for p in promedios_periodo]
        if len(set(periodos)) != len(periodos):
            raise CalificacionException("Hay promedios de período duplicados.")

        suma = sum((p.nota_final for p in promedios_periodo), Decimal("0"))
        promedio_anual = _redondear(suma / Decimal(len(promedios_periodo)))
        return PromedioAnualCurso(
            alumno_id=alumno_id,
            curso_id=curso_id,
            anio_lectivo=anio_lectivo,
            promedios_periodo=tuple(promedios_periodo),
            promedio_anual=promedio_anual,
            escala_literal=ServicioCalificaciones.convertir_a_literal(promedio_anual),
        )
