"""PBI-14: emisión de boletas de calificaciones (individual y masiva por salón).

- Período abierto  → boleta ``BORRADOR / PRELIMINAR`` (sin código ni auditoría).
- Período cerrado  → boleta ``OFICIAL`` con ``codigo_verificacion`` único y auditoría (PBI-16).
- No se bloquea la emisión por deuda (RN-05): este módulo no consulta pagos.
- Toda la aritmética usa ``Decimal`` con ``ROUND_HALF_UP`` a 2 decimales.
"""

from __future__ import annotations

import secrets
import unicodedata
import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from src.dominio.asistencia import EstadoAsistencia, RegistroAsistencia, UsuarioOperador
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    ContextoAcademicoAuditoria,
    RegistroAuditoria,
    ResultadoAuditoria,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.calificaciones import EscalaLiteral, PromedioPeriodo, ServicioCalificaciones
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.justificaciones import PeriodoAcademico
from src.dominio.malla_curricular import Curso, Salon
from src.dominio.matricula import FichaMatricula
from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolUsuario,
    ServicioAutenticacionYPermisos,
    Usuario,
)

NOMBRE_INSTITUCION: Final[str] = "Colegio Domingo Savio S.A.C."
ETIQUETA_OFICIAL: Final[str] = "OFICIAL"
ETIQUETA_PRELIMINAR: Final[str] = "BORRADOR / PRELIMINAR"
ENTIDAD_AUDITORIA: Final[str] = "BOLETA_CALIFICACIONES"
PRECISION: Final[Decimal] = Decimal("0.01")

OperadorBoleta = Usuario | UsuarioOperador
PersistirAuditoria = Callable[[RegistroAuditoria], None]


class BoletaException(Exception):
    """Excepción base del módulo de boletas de calificaciones."""


class PermisoBoletaException(BoletaException):
    """Lanzada cuando el operador no está activo o carece del permiso EMITIR_BOLETAS."""


class BoletaIncompletaException(BoletaException):
    """Lanzada al emitir una boleta oficial sin notas en todos los cursos obligatorios."""


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineaCursoBoleta:
    """Fila de la tabla de cursos; ``nota`` es ``None`` solo en boletas preliminares."""

    curso_id: int
    codigo_curso: str
    nombre_curso: str
    nota: Decimal | None
    escala_literal: EscalaLiteral | None


@dataclass(frozen=True)
class ResumenAsistenciaPeriodo:
    puntual: int
    tardanza: int
    ausente: int
    justificado: int

    @property
    def total(self) -> int:
        return self.puntual + self.tardanza + self.ausente + self.justificado


@dataclass(frozen=True)
class BoletaCalificaciones:
    id: str
    institucion: str
    alumno_id: int
    codigo_estudiante: str
    nombre_completo_alumno: str
    dni: str
    anio_lectivo: int
    salon_id: int
    nivel: str
    grado: str
    seccion: str
    periodo_id: int
    periodo_nombre: str
    lineas: tuple[LineaCursoBoleta, ...]
    promedio_general: Decimal | None
    escala_literal_general: EscalaLiteral | None
    resumen_asistencia: ResumenAsistenciaPeriodo
    es_oficial: bool
    etiqueta: str
    codigo_verificacion: str | None
    emitido_por: int
    fecha_emision: datetime
    auditoria: RegistroAuditoria | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISION, rounding=ROUND_HALF_UP)


def _normalizar_fecha_hora(fecha_hora: object) -> datetime:
    if not isinstance(fecha_hora, datetime):
        raise BoletaException("La fecha de emisión debe ser una instancia datetime válida.")
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _codigo_rol(rol: RolUsuario | str) -> str:
    return rol.value if isinstance(rol, RolUsuario) else str(rol).strip().upper()


def _actor_activo(actor: OperadorBoleta) -> bool:
    if isinstance(actor, UsuarioOperador):
        return actor.activo
    return actor.estado == EstadoUsuario.ACTIVO


def _clave_orden(texto: str) -> str:
    """Clave alfabética sin tildes ni mayúsculas (Á == A) para ordenar apellidos."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()


def _generar_codigo_verificacion(anio_lectivo: int, usados: set[str]) -> str:
    while True:
        codigo = f"BOL-{anio_lectivo}-{secrets.token_hex(6).upper()}"
        if codigo not in usados:
            usados.add(codigo)
            return codigo


def _resumir_asistencia(
    alumno_id: int,
    periodo: PeriodoAcademico,
    asistencias: Sequence[RegistroAsistencia],
) -> ResumenAsistenciaPeriodo:
    conteo = dict.fromkeys(
        (
            EstadoAsistencia.PUNTUAL,
            EstadoAsistencia.TARDANZA,
            EstadoAsistencia.AUSENTE,
            EstadoAsistencia.JUSTIFICADO,
        ),
        0,
    )
    for registro in asistencias:
        if (
            registro.alumno_id == alumno_id
            and periodo.fecha_inicio <= registro.fecha_escolar <= periodo.fecha_fin
            and registro.estado in conteo
        ):
            conteo[registro.estado] += 1
    return ResumenAsistenciaPeriodo(
        puntual=conteo[EstadoAsistencia.PUNTUAL],
        tardanza=conteo[EstadoAsistencia.TARDANZA],
        ausente=conteo[EstadoAsistencia.AUSENTE],
        justificado=conteo[EstadoAsistencia.JUSTIFICADO],
    )


def _indexar_promedios(
    ficha: FichaMatricula,
    periodo: PeriodoAcademico,
    promedios: Sequence[PromedioPeriodo],
) -> dict[int, Decimal]:
    """Devuelve ``curso_id -> nota_final`` del alumno en el período."""
    notas: dict[int, Decimal] = {}
    for promedio in promedios:
        if promedio.alumno_id != ficha.alumno_id:
            continue
        if promedio.periodo_id != periodo.id:
            raise BoletaException(
                f"El promedio del curso {promedio.curso_id} no corresponde al período "
                f"'{periodo.nombre}'."
            )
        if promedio.curso_id in notas:
            raise BoletaException(
                f"Promedio duplicado para el curso {promedio.curso_id} del alumno "
                f"{ficha.alumno_id}."
            )
        notas[promedio.curso_id] = promedio.nota_final
    return notas


# ---------------------------------------------------------------------------
# Servicio de dominio
# ---------------------------------------------------------------------------


class ServicioBoletas:
    """Implementa las reglas de negocio del PBI-14 (Emisión de Boletas)."""

    @staticmethod
    def validar_operador(operador: OperadorBoleta, roles: Sequence[Rol] | None = None) -> None:
        """RN-01: cuenta activa y permiso EMITIR_BOLETAS evaluado en servidor."""
        if not _actor_activo(operador):
            raise PermisoBoletaException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol, PermisoOperacion.EMITIR_BOLETAS, roles=roles
        ):
            raise PermisoBoletaException(
                f"El rol {_codigo_rol(operador.rol)} no tiene permiso para emitir boletas."
            )

    @staticmethod
    def _construir_boleta(
        operador: OperadorBoleta,
        ficha: FichaMatricula,
        periodo: PeriodoAcademico,
        cursos_obligatorios: Sequence[Curso],
        promedios_periodo: Sequence[PromedioPeriodo],
        asistencias_periodo: Sequence[RegistroAsistencia],
        momento: datetime,
        codigos_usados: set[str],
    ) -> BoletaCalificaciones:
        """Arma la boleta sin efectos secundarios (la auditoría se registra aparte)."""
        if periodo.anio_lectivo and periodo.anio_lectivo != ficha.anio_lectivo:
            raise BoletaException(
                "El año lectivo del período no coincide con el de la matrícula."
            )
        cursos = [curso for curso in cursos_obligatorios if curso.activo]
        if not cursos:
            raise BoletaException("Se requiere al menos un curso obligatorio activo.")
        for curso in cursos:
            if curso.anio_lectivo != ficha.anio_lectivo:
                raise BoletaException(
                    f"El curso {curso.codigo} no pertenece al año lectivo {ficha.anio_lectivo}."
                )

        notas = _indexar_promedios(ficha, periodo, promedios_periodo)
        es_oficial = periodo.cerrado
        if es_oficial:
            faltantes = [curso.codigo for curso in cursos if curso.id not in notas]
            if faltantes:
                raise BoletaIncompletaException(
                    f"El alumno {ficha.alumno_id} no tiene calificaciones en los cursos "
                    f"obligatorios: {', '.join(faltantes)}."
                )

        lineas: list[LineaCursoBoleta] = []
        for curso in cursos:
            nota = notas.get(curso.id)
            lineas.append(
                LineaCursoBoleta(
                    curso_id=curso.id,
                    codigo_curso=curso.codigo,
                    nombre_curso=curso.nombre,
                    nota=_redondear(nota) if nota is not None else None,
                    escala_literal=(
                        ServicioCalificaciones.convertir_a_literal(nota)
                        if nota is not None
                        else None
                    ),
                )
            )

        calificadas = [linea.nota for linea in lineas if linea.nota is not None]
        promedio_general: Decimal | None = None
        escala_general: EscalaLiteral | None = None
        if calificadas:
            promedio_general = _redondear(
                sum(calificadas, Decimal("0")) / Decimal(len(calificadas))
            )
            escala_general = ServicioCalificaciones.convertir_a_literal(promedio_general)

        return BoletaCalificaciones(
            id=f"bol-{uuid.uuid4().hex[:12]}",
            institucion=NOMBRE_INSTITUCION,
            alumno_id=ficha.alumno_id,
            codigo_estudiante=ficha.codigo_estudiante,
            nombre_completo_alumno=f"{ficha.apellidos}, {ficha.nombres}",
            dni=ficha.dni,
            anio_lectivo=ficha.anio_lectivo,
            salon_id=ficha.salon_id,
            nivel=ficha.nivel,
            grado=ficha.grado,
            seccion=ficha.seccion,
            periodo_id=periodo.id,
            periodo_nombre=periodo.nombre,
            lineas=tuple(lineas),
            promedio_general=promedio_general,
            escala_literal_general=escala_general,
            resumen_asistencia=_resumir_asistencia(
                ficha.alumno_id, periodo, asistencias_periodo
            ),
            es_oficial=es_oficial,
            etiqueta=ETIQUETA_OFICIAL if es_oficial else ETIQUETA_PRELIMINAR,
            codigo_verificacion=(
                _generar_codigo_verificacion(ficha.anio_lectivo, codigos_usados)
                if es_oficial
                else None
            ),
            emitido_por=operador.id,
            fecha_emision=momento,
        )

    @staticmethod
    def _auditar_emisiones(
        operador: OperadorBoleta,
        boletas: Sequence[BoletaCalificaciones],
        eventos_auditoria_existentes: Sequence[RegistroAuditoria],
        persistir_auditoria: PersistirAuditoria | None,
    ) -> list[BoletaCalificaciones]:
        """RN-06: registra en cadena un evento por cada boleta oficial."""
        eventos = list(eventos_auditoria_existentes)
        resultado: list[BoletaCalificaciones] = []
        for boleta in boletas:
            if not boleta.es_oficial:
                resultado.append(boleta)
                continue
            registro = ServicioAuditoria.registrar_evento(
                usuario_id=operador.id,
                rol_ejecutante=_codigo_rol(operador.rol),
                operacion=TipoOperacionAuditoria.EMITIR_BOLETA,
                entidad=ENTIDAD_AUDITORIA,
                entidad_id=str(boleta.codigo_verificacion),
                resultado=ResultadoAuditoria.CONFIRMADA,
                fecha_hora=boleta.fecha_emision,
                eventos_existentes=eventos,
                alumno_id=boleta.alumno_id,
                contexto_academico=ContextoAcademicoAuditoria(
                    nivel=boleta.nivel, grado=boleta.grado, seccion=boleta.seccion
                ),
                estado_nuevo=ETIQUETA_OFICIAL,
                detalle={
                    "accion": "EMITIR_BOLETA_OFICIAL",
                    "boleta_id": boleta.id,
                    "codigo_verificacion": boleta.codigo_verificacion,
                    "periodo_id": boleta.periodo_id,
                    "anio_lectivo": boleta.anio_lectivo,
                    "salon_id": boleta.salon_id,
                },
                persistir=persistir_auditoria,
            )
            eventos.append(registro)
            resultado.append(replace(boleta, auditoria=registro))
        return resultado

    @staticmethod
    def emitir_boleta_individual(
        operador: OperadorBoleta,
        ficha_matricula: FichaMatricula,
        periodo: PeriodoAcademico,
        cursos_obligatorios: Sequence[Curso],
        promedios_periodo: Sequence[PromedioPeriodo],
        asistencias_periodo: Sequence[RegistroAsistencia],
        fecha_emision: datetime,
        roles: Sequence[Rol] | None = None,
        *,
        codigos_existentes: Collection[str] = (),
        eventos_auditoria_existentes: Sequence[RegistroAuditoria] = (),
        persistir_auditoria: PersistirAuditoria | None = None,
    ) -> BoletaCalificaciones:
        """Emite la boleta de un alumno: oficial si el período está cerrado."""
        ServicioBoletas.validar_operador(operador, roles=roles)
        momento = _normalizar_fecha_hora(fecha_emision)
        boleta = ServicioBoletas._construir_boleta(
            operador,
            ficha_matricula,
            periodo,
            cursos_obligatorios,
            promedios_periodo,
            asistencias_periodo,
            momento,
            set(codigos_existentes),
        )
        return ServicioBoletas._auditar_emisiones(
            operador, (boleta,), eventos_auditoria_existentes, persistir_auditoria
        )[0]

    @staticmethod
    def emitir_boletas_salon(
        operador: OperadorBoleta,
        salon: Salon,
        fichas_matricula: Sequence[FichaMatricula],
        periodo: PeriodoAcademico,
        cursos_obligatorios: Sequence[Curso],
        promedios_periodo: Sequence[PromedioPeriodo],
        asistencias_periodo: Sequence[RegistroAsistencia],
        fecha_emision: datetime,
        roles: Sequence[Rol] | None = None,
        *,
        codigos_existentes: Collection[str] = (),
        eventos_auditoria_existentes: Sequence[RegistroAuditoria] = (),
        persistir_auditoria: PersistirAuditoria | None = None,
    ) -> list[BoletaCalificaciones]:
        """RN-04: emite una boleta por alumno ACTIVO del salón (operación atómica).

        Si una boleta oficial está incompleta no se emite ni audita ninguna del lote.
        """
        ServicioBoletas.validar_operador(operador, roles=roles)
        momento = _normalizar_fecha_hora(fecha_emision)
        matriculados = sorted(
            (
                ficha
                for ficha in fichas_matricula
                if ficha.salon_id == salon.id
                and ficha.anio_lectivo == salon.anio_lectivo
                and ficha.estado == EstadoAcademico.ACTIVO
            ),
            key=lambda ficha: (_clave_orden(ficha.apellidos), _clave_orden(ficha.nombres)),
        )
        usados = set(codigos_existentes)
        boletas = [
            ServicioBoletas._construir_boleta(
                operador,
                ficha,
                periodo,
                cursos_obligatorios,
                promedios_periodo,
                asistencias_periodo,
                momento,
                usados,
            )
            for ficha in matriculados
        ]
        return ServicioBoletas._auditar_emisiones(
            operador, boletas, eventos_auditoria_existentes, persistir_auditoria
        )
