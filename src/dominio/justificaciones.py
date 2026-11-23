"""PBI-04: gestión de justificaciones de inasistencia y períodos académicos."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from src.dominio.asistencia import (
    Alumno,
    EstadoAlumno,
    EstadoAsistencia,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
)
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

EXTENSIONES_PERMITIDAS = frozenset({"pdf", "jpg", "jpeg", "png"})
TAMANO_MAXIMO_ADJUNTO = 5_242_880
MAX_ADJUNTOS = 3


class TipoPeriodo(StrEnum):
    BIMESTRE = "BIMESTRE"
    TRIMESTRE = "TRIMESTRE"
    SEMESTRE = "SEMESTRE"


class CategoriaJustificacion(StrEnum):
    MEDICA = "MEDICA"
    PERMISO_FAMILIAR = "PERMISO_FAMILIAR"
    OTRA = "OTRA"


class EstadoJustificacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


class JustificacionException(Exception):
    """Excepción base para el módulo de justificaciones."""


class PermisoJustificacionException(JustificacionException):
    """Lanzada cuando un operador no tiene el permiso requerido."""


class FechaInvalidaException(JustificacionException):
    """Lanzada al intentar justificar una fecha futura."""


class PeriodoAcademicoCerradoException(JustificacionException):
    """Lanzada cuando se opera sobre un período académico cerrado."""


class EstadoNoJustificableException(JustificacionException):
    """Lanzada cuando la asistencia no está en estado AUSENTE o TARDANZA."""


class AdjuntoInvalidoException(JustificacionException):
    """Lanzada cuando un adjunto no cumple extensión, tamaño o cantidad."""


class PeriodoInvalidoException(JustificacionException):
    """Lanzada cuando los datos de un período académico son inválidos."""


class PeriodoSolapadoException(PeriodoInvalidoException):
    """Lanzada cuando un período se solapa con otro existente."""


class PeriodoConUsoException(JustificacionException):
    """Lanzada cuando se intenta eliminar un período con uso asociado."""


@dataclass(frozen=True)
class AdjuntoJustificacion:
    nombre: str
    tamano_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.nombre, str) or not self.nombre.strip():
            raise AdjuntoInvalidoException("El nombre del adjunto es obligatorio.")
        nombre = self.nombre.strip()
        extension = Path(nombre).suffix.lower().lstrip(".")
        if extension not in EXTENSIONES_PERMITIDAS:
            raise AdjuntoInvalidoException(
                "Extensión de adjunto no permitida. Use pdf, jpg, jpeg o png."
            )
        if not isinstance(self.tamano_bytes, int) or isinstance(self.tamano_bytes, bool):
            raise AdjuntoInvalidoException("El tamaño del adjunto debe ser un entero.")
        if self.tamano_bytes <= 0 or self.tamano_bytes > TAMANO_MAXIMO_ADJUNTO:
            raise AdjuntoInvalidoException(
                "El adjunto debe pesar más de 0 bytes y como máximo 5 MB."
            )
        object.__setattr__(self, "nombre", nombre)

    @property
    def extension(self) -> str:
        return Path(self.nombre).suffix.lower().lstrip(".")


def _validar_adjuntos(
    adjuntos: Sequence[AdjuntoJustificacion],
) -> tuple[AdjuntoJustificacion, ...]:
    if isinstance(adjuntos, (str, bytes)) or not isinstance(adjuntos, Sequence):
        raise AdjuntoInvalidoException("Los adjuntos deben ser una colección válida.")
    if len(adjuntos) > MAX_ADJUNTOS:
        raise AdjuntoInvalidoException("Solo se permiten hasta 3 adjuntos por justificación.")
    for adjunto in adjuntos:
        if not isinstance(adjunto, AdjuntoJustificacion):
            raise AdjuntoInvalidoException(
                "Cada adjunto debe ser un AdjuntoJustificacion válido."
            )
    return tuple(adjuntos)


@dataclass(frozen=True)
class PeriodoAcademico:
    id: int
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    cerrado: bool = False
    anio_lectivo: int = 0
    tipo_periodo: TipoPeriodo = TipoPeriodo.BIMESTRE
    orden: int = 1
    fecha_limite_notas: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.nombre, str) or not self.nombre.strip():
            raise PeriodoInvalidoException("El nombre del período es obligatorio.")
        if self.fecha_inicio > self.fecha_fin:
            raise PeriodoInvalidoException(
                "La fecha de inicio no puede ser posterior a la fecha fin."
            )
        if self.anio_lectivo < 0:
            raise PeriodoInvalidoException("El año lectivo no puede ser negativo.")
        if self.orden < 1:
            raise PeriodoInvalidoException("El orden del período debe ser mayor o igual a 1.")

        tipo = self.tipo_periodo
        if not isinstance(tipo, TipoPeriodo):
            try:
                tipo = TipoPeriodo(str(tipo).upper())
            except ValueError as error:
                raise PeriodoInvalidoException("Tipo de período inválido.") from error

        if self.fecha_limite_notas is not None and not (
            self.fecha_inicio <= self.fecha_limite_notas <= self.fecha_fin
        ):
            raise PeriodoInvalidoException(
                "La fecha límite de notas debe estar dentro del período."
            )

        object.__setattr__(self, "nombre", self.nombre.strip())
        object.__setattr__(self, "tipo_periodo", tipo)


@dataclass(frozen=True)
class Justificacion:
    id: str
    asistencia_id: str
    alumno_id: int
    fecha_solicitud: date
    categoria: CategoriaJustificacion
    motivo: str
    estado: EstadoJustificacion
    usuario_id: int
    rol_usuario: RolUsuario
    documento_adjunto: str | None = None
    fecha_resolucion: datetime | None = None
    adjuntos: tuple[AdjuntoJustificacion, ...] = ()
    minutos_tardanza_original: int = 0
    nivel: str = ""
    grado: str = ""
    seccion: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "adjuntos", _validar_adjuntos(self.adjuntos))
        if self.minutos_tardanza_original < 0:
            raise JustificacionException(
                "Los minutos de tardanza original no pueden ser negativos."
            )


@dataclass(frozen=True)
class FiltroJustificaciones:
    nivel: str | None = None
    grado: str | None = None
    seccion: str | None = None
    alumno_id: int | None = None
    categoria: CategoriaJustificacion | None = None
    estado: EstadoJustificacion | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None

    def __post_init__(self) -> None:
        if (
            self.fecha_desde is not None
            and self.fecha_hasta is not None
            and self.fecha_desde > self.fecha_hasta
        ):
            raise JustificacionException(
                "El rango de fechas es inválido: fecha_desde no puede superar a fecha_hasta."
            )


@dataclass(frozen=True)
class ResultadoOperacionJustificacion:
    justificacion: Justificacion
    asistencia_actualizada: RegistroAsistencia
    auditoria_id: str


def _codigo_rol(rol: RolUsuario | str) -> str:
    return getattr(rol, "value", str(rol))


class ServicioJustificaciones:
    """Implementa las reglas de negocio del PBI-04."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        permiso: PermisoOperacion = PermisoOperacion.GESTIONAR_JUSTIFICACIONES,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso en servidor; nunca por nombre de rol."""
        if not operador.activo:
            raise PermisoJustificacionException(
                "El operador no cuenta con una cuenta activa."
            )
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol, permiso, roles
        ):
            raise PermisoJustificacionException(
                f"El rol {_codigo_rol(operador.rol)} no está autorizado para la operación "
                f"'{permiso.value}'."
            )

    @staticmethod
    def registrar_y_aprobar_justificacion(
        operador: UsuarioOperador,
        alumno: Alumno | None,
        asistencia: RegistroAsistencia,
        fecha_solicitud: date,
        fecha_actual: date,
        categoria: CategoriaJustificacion,
        motivo: str,
        periodo: PeriodoAcademico,
        documento_adjunto: str | None = None,
        adjuntos: Sequence[AdjuntoJustificacion] = (),
        roles: Sequence[Rol] | None = None,
    ) -> ResultadoOperacionJustificacion:
        """Registra y aprueba una justificación, actualizando la asistencia."""
        ServicioJustificaciones.validar_operador(operador, roles=roles)

        if alumno is None:
            raise JustificacionException("El alumno especificado no existe.")
        if alumno.estado != EstadoAlumno.ACTIVO:
            raise JustificacionException(f"El alumno {alumno.codigo} no se encuentra ACTIVO.")

        if fecha_solicitud > fecha_actual:
            raise FechaInvalidaException(
                "No se puede presentar una justificación para una fecha futura."
            )

        if periodo.cerrado:
            raise PeriodoAcademicoCerradoException(
                f"El período académico '{periodo.nombre}' se encuentra cerrado."
            )

        if not (periodo.fecha_inicio <= asistencia.fecha_escolar <= periodo.fecha_fin):
            raise JustificacionException(
                f"La fecha de la asistencia {asistencia.fecha_escolar} "
                f"está fuera del período {periodo.nombre}."
            )

        if asistencia.estado not in (EstadoAsistencia.AUSENTE, EstadoAsistencia.TARDANZA):
            raise EstadoNoJustificableException(
                f"No es posible justificar una asistencia con estado "
                f"'{asistencia.estado.value}'."
            )

        motivo_limpio = motivo.strip() if isinstance(motivo, str) else ""
        if not motivo_limpio:
            raise JustificacionException("El motivo de la justificación es obligatorio.")

        adjuntos_validos = _validar_adjuntos(adjuntos)
        id_just = f"just-{uuid.uuid4().hex[:10]}"
        id_aud = f"aud-just-{uuid.uuid4().hex[:10]}"

        justificacion = Justificacion(
            id=id_just,
            asistencia_id=asistencia.id,
            alumno_id=alumno.id,
            fecha_solicitud=fecha_solicitud,
            categoria=categoria,
            motivo=motivo_limpio,
            estado=EstadoJustificacion.APROBADA,
            usuario_id=operador.id,
            rol_usuario=operador.rol,
            documento_adjunto=documento_adjunto,
            fecha_resolucion=datetime.now(),
            adjuntos=adjuntos_validos,
            minutos_tardanza_original=asistencia.minutos_tardanza,
            nivel=alumno.nivel,
            grado=alumno.grado,
            seccion=alumno.seccion,
        )

        asistencia_modificada = RegistroAsistencia(
            id=asistencia.id,
            alumno_id=asistencia.alumno_id,
            fecha_escolar=asistencia.fecha_escolar,
            hora_efectiva=asistencia.hora_efectiva,
            estado=EstadoAsistencia.JUSTIFICADO,
            minutos_tardanza=0,
            metodo=asistencia.metodo,
            usuario_id=operador.id,
            rol_usuario=operador.rol,
            estado_anterior=asistencia.estado,
            motivo_correccion=f"Justificado: {motivo_limpio}",
            auditoria_id=id_aud,
        )

        return ResultadoOperacionJustificacion(
            justificacion=justificacion,
            asistencia_actualizada=asistencia_modificada,
            auditoria_id=id_aud,
        )

    @staticmethod
    def anular_justificacion(
        operador: UsuarioOperador,
        justificacion: Justificacion,
        asistencia: RegistroAsistencia,
        periodo: PeriodoAcademico | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> RegistroAsistencia:
        """Anula una justificación y restaura estado y minutos originales."""
        ServicioJustificaciones.validar_operador(operador, roles=roles)

        if periodo is not None:
            if periodo.cerrado:
                raise PeriodoAcademicoCerradoException(
                    f"El período académico '{periodo.nombre}' se encuentra cerrado."
                )
            if not (periodo.fecha_inicio <= asistencia.fecha_escolar <= periodo.fecha_fin):
                raise JustificacionException(
                    f"La fecha de la asistencia {asistencia.fecha_escolar} "
                    f"está fuera del período {periodo.nombre}."
                )

        if asistencia.estado != EstadoAsistencia.JUSTIFICADO:
            raise JustificacionException(
                "La asistencia no se encuentra en estado JUSTIFICADO."
            )

        estado_original = asistencia.estado_anterior or EstadoAsistencia.AUSENTE
        minutos_originales = (
            justificacion.minutos_tardanza_original
            if estado_original == EstadoAsistencia.TARDANZA
            else 0
        )

        return RegistroAsistencia(
            id=asistencia.id,
            alumno_id=asistencia.alumno_id,
            fecha_escolar=asistencia.fecha_escolar,
            hora_efectiva=asistencia.hora_efectiva,
            estado=estado_original,
            minutos_tardanza=minutos_originales,
            metodo=asistencia.metodo,
            usuario_id=operador.id,
            rol_usuario=operador.rol,
            estado_anterior=EstadoAsistencia.JUSTIFICADO,
            motivo_correccion="Anulación de justificación previa",
            auditoria_id=f"aud-anul-{uuid.uuid4().hex[:10]}",
        )

    @staticmethod
    def modificar_justificacion(
        operador: UsuarioOperador,
        justificacion: Justificacion,
        asistencia: RegistroAsistencia,
        periodo: PeriodoAcademico,
        categoria: CategoriaJustificacion | None = None,
        motivo: str | None = None,
        nuevos_adjuntos: Sequence[AdjuntoJustificacion] = (),
        roles: Sequence[Rol] | None = None,
        fecha_hora: datetime | None = None,
    ) -> ResultadoOperacionJustificacion:
        """Modifica categoría/motivo y anexa adjuntos sin perder los previos."""
        ServicioJustificaciones.validar_operador(operador, roles=roles)

        if periodo.cerrado:
            raise PeriodoAcademicoCerradoException(
                f"El período académico '{periodo.nombre}' se encuentra cerrado."
            )
        if not (periodo.fecha_inicio <= asistencia.fecha_escolar <= periodo.fecha_fin):
            raise JustificacionException(
                f"La fecha de la asistencia {asistencia.fecha_escolar} "
                f"está fuera del período {periodo.nombre}."
            )
        if asistencia.estado != EstadoAsistencia.JUSTIFICADO:
            raise JustificacionException(
                "La asistencia no se encuentra en estado JUSTIFICADO."
            )
        if justificacion.estado != EstadoJustificacion.APROBADA:
            raise JustificacionException(
                "Solo se pueden modificar justificaciones aprobadas."
            )

        categoria_final = categoria or justificacion.categoria
        if not isinstance(categoria_final, CategoriaJustificacion):
            try:
                categoria_final = CategoriaJustificacion(str(categoria_final).upper())
            except ValueError as error:
                raise JustificacionException("Categoría de justificación inválida.") from error

        motivo_final = (
            motivo.strip()
            if isinstance(motivo, str)
            else justificacion.motivo
        )
        if not motivo_final:
            raise JustificacionException("El motivo de la justificación es obligatorio.")

        adjuntos_finales = _validar_adjuntos(
            (*justificacion.adjuntos, *nuevos_adjuntos)
        )
        id_aud = f"aud-just-{uuid.uuid4().hex[:10]}"

        actualizada = replace(
            justificacion,
            categoria=categoria_final,
            motivo=motivo_final,
            adjuntos=adjuntos_finales,
            fecha_resolucion=fecha_hora or datetime.now(),
        )
        asistencia_actualizada = replace(asistencia, auditoria_id=id_aud)

        return ResultadoOperacionJustificacion(
            justificacion=actualizada,
            asistencia_actualizada=asistencia_actualizada,
            auditoria_id=id_aud,
        )

    @staticmethod
    def consultar_justificaciones(
        justificaciones: Sequence[Justificacion],
        filtro: FiltroJustificaciones | None = None,
        *,
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> list[Justificacion]:
        """Consulta el historial aplicando filtros académicos y de estado."""
        ServicioJustificaciones.validar_operador(operador, roles=roles)
        criterio = filtro or FiltroJustificaciones()

        resultados = []
        for justificacion in justificaciones:
            if (
                criterio.nivel is not None
                and justificacion.nivel.lower() != criterio.nivel.strip().lower()
            ):
                continue
            if (
                criterio.grado is not None
                and justificacion.grado.lower() != criterio.grado.strip().lower()
            ):
                continue
            if (
                criterio.seccion is not None
                and justificacion.seccion.lower() != criterio.seccion.strip().lower()
            ):
                continue
            if (
                criterio.alumno_id is not None
                and justificacion.alumno_id != criterio.alumno_id
            ):
                continue
            if (
                criterio.categoria is not None
                and justificacion.categoria != criterio.categoria
            ):
                continue
            if criterio.estado is not None and justificacion.estado != criterio.estado:
                continue
            if (
                criterio.fecha_desde is not None
                and justificacion.fecha_solicitud < criterio.fecha_desde
            ):
                continue
            if (
                criterio.fecha_hasta is not None
                and justificacion.fecha_solicitud > criterio.fecha_hasta
            ):
                continue
            resultados.append(justificacion)

        return sorted(
            resultados,
            key=lambda justificacion: (justificacion.fecha_solicitud, justificacion.id),
        )


class ServicioPeriodosAcademicos:
    """Administra períodos académicos flexibles y sus fechas límite de notas."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        if not operador.activo:
            raise PermisoJustificacionException(
                "El operador no cuenta con una cuenta activa."
            )
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.ADMINISTRAR_PERIODOS,
            roles,
        ):
            raise PermisoJustificacionException(
                f"El rol {_codigo_rol(operador.rol)} no está autorizado para "
                "administrar períodos académicos."
            )

    @staticmethod
    def _validar_periodo(
        periodo: PeriodoAcademico,
        periodos_existentes: Sequence[PeriodoAcademico],
        excluir_id: int | None = None,
    ) -> None:
        if periodo.anio_lectivo <= 0:
            raise PeriodoInvalidoException("El año lectivo es obligatorio.")
        if periodo.fecha_limite_notas is None:
            raise PeriodoInvalidoException("La fecha límite de notas es obligatoria.")

        for existente in periodos_existentes:
            if excluir_id is not None and existente.id == excluir_id:
                continue
            if existente.nombre.strip().lower() == periodo.nombre.strip().lower():
                raise PeriodoInvalidoException(
                    f"El nombre del período '{periodo.nombre}' ya existe."
                )
            if (
                periodo.fecha_inicio <= existente.fecha_fin
                and periodo.fecha_fin >= existente.fecha_inicio
            ):
                raise PeriodoSolapadoException(
                    f"El período '{periodo.nombre}' se solapa con '{existente.nombre}'."
                )

    @staticmethod
    def crear_periodo(
        operador: UsuarioOperador,
        periodo: PeriodoAcademico,
        periodos_existentes: Sequence[PeriodoAcademico],
        roles: Sequence[Rol] | None = None,
    ) -> PeriodoAcademico:
        ServicioPeriodosAcademicos.validar_operador(operador, roles)
        ServicioPeriodosAcademicos._validar_periodo(periodo, periodos_existentes)
        return periodo

    @staticmethod
    def modificar_periodo(
        operador: UsuarioOperador,
        periodo: PeriodoAcademico,
        periodos_existentes: Sequence[PeriodoAcademico],
        nombre: str | None = None,
        fecha_inicio: date | None = None,
        fecha_fin: date | None = None,
        fecha_limite_notas: date | None = None,
        cerrado: bool | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> PeriodoAcademico:
        ServicioPeriodosAcademicos.validar_operador(operador, roles)

        cambios: dict[str, object] = {}
        if nombre is not None:
            cambios["nombre"] = nombre
        if fecha_inicio is not None:
            cambios["fecha_inicio"] = fecha_inicio
        if fecha_fin is not None:
            cambios["fecha_fin"] = fecha_fin
        if fecha_limite_notas is not None:
            cambios["fecha_limite_notas"] = fecha_limite_notas
        if cerrado is not None:
            cambios["cerrado"] = cerrado

        actualizado = replace(periodo, **cambios)
        ServicioPeriodosAcademicos._validar_periodo(
            actualizado,
            periodos_existentes,
            excluir_id=periodo.id,
        )
        return actualizado

    @staticmethod
    def cambiar_estado_periodo(
        operador: UsuarioOperador,
        periodo: PeriodoAcademico,
        cerrado: bool,
        roles: Sequence[Rol] | None = None,
    ) -> PeriodoAcademico:
        ServicioPeriodosAcademicos.validar_operador(operador, roles)
        return replace(periodo, cerrado=cerrado)

    @staticmethod
    def eliminar_periodo(
        operador: UsuarioOperador,
        periodo: PeriodoAcademico,
        periodos_existentes: Sequence[PeriodoAcademico],
        justificaciones: Sequence[Justificacion],
        tiene_calificaciones: bool = False,
        roles: Sequence[Rol] | None = None,
    ) -> list[PeriodoAcademico]:
        ServicioPeriodosAcademicos.validar_operador(operador, roles)

        if tiene_calificaciones:
            raise PeriodoConUsoException(
                "El período tiene calificaciones asociadas y no puede eliminarse."
            )
        if any(
            periodo.fecha_inicio <= justificacion.fecha_solicitud <= periodo.fecha_fin
            for justificacion in justificaciones
        ):
            raise PeriodoConUsoException(
                "El período tiene justificaciones asociadas y no puede eliminarse."
            )

        return [
            existente
            for existente in periodos_existentes
            if existente.id != periodo.id
        ]
