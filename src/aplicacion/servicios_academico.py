"""Capa de aplicación de los casos de uso académicos (PBI-05 a PBI-14).

Cada operación abre su propia :class:`SqlAlchemyUnitOfWork`, reutiliza los
servicios de dominio puros y persiste los cambios junto con el evento de
auditoría PBI-16 dentro de la misma transacción. Si la auditoría falla, la
unidad de trabajo revierte todo y no queda información huérfana.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.aplicacion.servicios_asistencia import (
    _naive,
    asistencia_model_a_dominio,
    periodo_model_a_dominio,
)
from src.aplicacion.servicios_seguridad import (
    FabricaSesion,
    RelojServidor,
    _auditoria_a_model,
    _eventos_existentes,
    hora_actual_lima,
    registrar_auditoria_pbi16,
    rol_codigo,
    rol_model_a_dominio,
    usuario_model_a_dominio,
    usuario_model_a_operador,
)
from src.aplicacion.uow import SqlAlchemyUnitOfWork
from src.dominio.asistencia import Alumno, EstadoAsistencia, RegistroAsistencia
from src.dominio.auditoria import TipoOperacionAuditoria
from src.dominio.calificaciones import (
    ActividadEvaluable,
    Calificacion,
    PromedioAnualCurso,
    PromedioPeriodo,
    RubroEvaluacion,
    ServicioCalificaciones,
)
from src.dominio.carnets import (
    CarnetEscolar,
    EstadoCarnet,
    MotivoAnulacionCarnet,
    ResultadoEmisionCarnet,
    ServicioCarnets,
)
from src.dominio.docentes import AsignacionDocente, ServicioAsignacionDocente
from src.dominio.estados_academicos import (
    EstadoAcademico,
    ResultadoCambioEstado,
    ServicioEstadosAcademicos,
)
from src.dominio.exportacion_asistencia import (
    ENCABEZADOS_EXPORTACION,
    DocumentoExportacionAsistencia,
    FiltroExportacionAsistencia,
    FormatoExportacion,
    ServicioExportacionAsistencia,
)
from src.dominio.justificaciones import PeriodoAcademico
from src.dominio.malla_curricular import (
    Curso,
    EntidadEnUsoException,
    NivelEducativo,
    Salon,
    ServicioMallaCurricular,
)
from src.dominio.matricula import Apoderado, FichaMatricula, ServicioMatricula
from src.dominio.pagos import (
    AlertaSilenciosaPago,
    EstadoObligacion,
    ObligacionPago,
    ServicioPagos,
)
from src.dominio.usuarios import (
    AccesoDenegadoException,
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
    Usuario,
    UsuarioNoEncontradoException,
)
from src.infraestructura.exportadores import (
    exportar_csv_bytes,
    exportar_texto_boleta_o_pdf,
    exportar_xlsx_bytes,
)
from src.infraestructura.modelos import (
    ActividadEvaluableModel,
    AlertaPagoSilenciosaModel,
    ApoderadoModel,
    AsignacionDocenteModel,
    AsistenciaModel,
    BoletaEmitidaModel,
    CalificacionModel,
    CarnetModel,
    CursoModel,
    EstudianteApoderadoModel,
    EstudianteEstadoHistorialModel,
    EstudianteModel,
    ObligacionPagoModel,
    PeriodoAcademicoModel,
    RolModel,
    RubroEvaluacionModel,
    SalonModel,
    UsuarioModel,
)

__all__ = [
    "ApoderadoFicha",
    "BoletaCalificaciones",
    "FichaInformativaAlumno",
    "LineaCursoBoleta",
    "ResultadoEmisionBoleta",
    "ResultadoExportacionAsistencia",
    "ResumenAsistenciaAlumno",
    "ResumenCursoFicha",
    "ResumenPagosAlumno",
    "ServicioAcademico",
]

_ANIO_MINIMO = 2000
_DIAS_POR_DEFECTO = 366


# ---------------------------------------------------------------------------
# DTOs de la capa de aplicación
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApoderadoFicha:
    """Datos de apoderado expuestos en la ficha informativa."""

    nombres: str
    apellidos: str
    parentesco: str
    telefono: str
    es_principal: bool


@dataclass(frozen=True)
class ResumenAsistenciaAlumno:
    """Conteo consolidado de asistencias del alumno."""

    puntual: int
    tardanza: int
    ausente: int
    justificado: int
    porcentaje_asistencia: Decimal


@dataclass(frozen=True)
class ResumenPagosAlumno:
    """Bloque financiero de la ficha (solo visible con permiso)."""

    pendientes: int
    vencidas: int
    monto_pendiente: Decimal
    alertas_activas: int


@dataclass(frozen=True)
class ResumenCursoFicha:
    """Promedio de un curso mostrado en la ficha del alumno."""

    curso_id: int
    curso_nombre: str
    nota: Decimal
    literal: str


@dataclass(frozen=True)
class FichaInformativaAlumno:
    """DTO consolidado del PBI-12."""

    alumno_id: int
    codigo: str
    dni: str
    nombres: str
    apellidos: str
    nivel: str
    grado: str
    seccion: str
    salon_id: int | None
    estado_academico: EstadoAcademico
    carnet_codigo: str | None
    apoderados: tuple[ApoderadoFicha, ...]
    resumen_asistencia: ResumenAsistenciaAlumno
    resumen_promedios: tuple[ResumenCursoFicha, ...]
    resumen_pagos: ResumenPagosAlumno | None


@dataclass(frozen=True)
class ResultadoExportacionAsistencia:
    """Documento preparado y su representación binaria lista para descargar."""

    documento: DocumentoExportacionAsistencia
    contenido: bytes


@dataclass(frozen=True)
class LineaCursoBoleta:
    """Línea de curso de una boleta de calificaciones."""

    curso_id: int
    curso_nombre: str
    nota: Decimal
    literal: str


@dataclass(frozen=True)
class BoletaCalificaciones:
    """Boleta emitida (preliminar u oficial) del PBI-14."""

    id: str
    alumno_id: int
    periodo_id: int
    anio_lectivo: int
    es_oficial: bool
    codigo_verificacion: str | None
    promedio_general: Decimal
    lineas: tuple[LineaCursoBoleta, ...]
    resumen_asistencia: ResumenAsistenciaAlumno
    etiqueta: str


@dataclass(frozen=True)
class ResultadoEmisionBoleta:
    """Resultado de emitir una boleta individual o masiva."""

    boletas: tuple[BoletaCalificaciones, ...]


# ---------------------------------------------------------------------------
# Conversores modelo ORM -> dominio
# ---------------------------------------------------------------------------


def _nivel_educativo(valor: str) -> NivelEducativo:
    try:
        return NivelEducativo(valor)
    except ValueError as error:
        raise ValueError(f"Nivel educativo desconocido: {valor!r}") from error


def salon_model_a_dominio(modelo: SalonModel) -> Salon:
    return Salon(
        id=modelo.id,
        anio_lectivo=modelo.anio_lectivo,
        nivel=_nivel_educativo(modelo.nivel),
        grado=modelo.grado,
        seccion=modelo.seccion,
        capacidad_maxima=modelo.capacidad_maxima,
        activo=bool(modelo.activo),
    )


def curso_model_a_dominio(modelo: CursoModel) -> Curso:
    return Curso(
        id=modelo.id,
        anio_lectivo=modelo.anio_lectivo,
        nivel=_nivel_educativo(modelo.nivel),
        grado=modelo.grado,
        codigo=modelo.codigo,
        nombre=modelo.nombre,
        area_curricular=modelo.area_curricular,
        horas_semanales=modelo.horas_semanales,
        activo=bool(modelo.activo),
    )


def carnet_model_a_dominio(modelo: CarnetModel) -> CarnetEscolar:
    motivo = None
    if modelo.motivo_anulacion:
        try:
            motivo = MotivoAnulacionCarnet(modelo.motivo_anulacion)
        except ValueError:
            motivo = None
    return CarnetEscolar(
        id=modelo.id,
        alumno_id=modelo.estudiante_id,
        codigo_qr=modelo.codigo_qr,
        estado=EstadoCarnet(modelo.estado),
        emitido_por=modelo.emitido_por,
        emitido_en=modelo.emitido_en,
        anulado_en=modelo.anulado_en,
        motivo_anulacion=motivo,
        detalle_anulacion=modelo.detalle_anulacion,
    )


def asignacion_model_a_dominio(modelo: AsignacionDocenteModel) -> AsignacionDocente:
    return AsignacionDocente(
        id=modelo.id,
        usuario_docente_id=modelo.usuario_docente_id,
        curso_id=modelo.curso_id,
        salon_id=modelo.salon_id,
        anio_lectivo=modelo.anio_lectivo,
        activa=bool(modelo.activa),
        asignado_por=modelo.asignado_por,
        creado_en=modelo.creado_en,
        revocada_en=modelo.revocada_en,
        motivo_revocacion=modelo.motivo_revocacion,
    )


def rubro_model_a_dominio(modelo: RubroEvaluacionModel) -> RubroEvaluacion:
    return RubroEvaluacion(
        id=modelo.id,
        asignacion_docente_id=modelo.asignacion_docente_id,
        periodo_id=modelo.periodo_id,
        nombre=modelo.nombre,
        peso_porcentaje=Decimal(modelo.peso_porcentaje),
        activo=bool(modelo.activo),
    )


def actividad_model_a_dominio(modelo: ActividadEvaluableModel) -> ActividadEvaluable:
    return ActividadEvaluable(
        id=modelo.id,
        rubro_id=modelo.rubro_id,
        titulo=modelo.titulo,
        fecha=modelo.fecha,
        activo=bool(modelo.activo),
    )


def calificacion_model_a_dominio(modelo: CalificacionModel) -> Calificacion:
    return Calificacion(
        id=modelo.id,
        actividad_id=modelo.actividad_id,
        alumno_id=modelo.estudiante_id,
        nota=Decimal(modelo.nota),
        usuario_id=modelo.usuario_id,
        actualizado_en=modelo.actualizado_en,
        observacion=modelo.observacion,
        nota_anterior=(Decimal(modelo.nota_anterior) if modelo.nota_anterior is not None else None),
        motivo_modificacion=modelo.motivo_modificacion,
    )


def obligacion_model_a_dominio(modelo: ObligacionPagoModel) -> ObligacionPago:
    return ObligacionPago(
        id=modelo.id,
        alumno_id=modelo.estudiante_id,
        concepto=modelo.concepto,
        monto=Decimal(modelo.monto),
        fecha_vencimiento=modelo.fecha_vencimiento,
        estado=EstadoObligacion(modelo.estado),
        pagado_en=modelo.pagado_en,
        motivo_exoneracion=modelo.motivo_exoneracion,
    )


def _apoderados_de_modelo(session: Session, alumno_id: int) -> tuple[Apoderado, ...]:
    vinculos = session.scalars(
        select(EstudianteApoderadoModel).filter_by(estudiante_id=alumno_id)
    ).all()
    apoderados: list[Apoderado] = []
    for vinculo in vinculos:
        modelo = session.get(ApoderadoModel, vinculo.apoderado_id)
        if modelo is None:
            continue
        apoderados.append(
            Apoderado(
                id=modelo.id,
                nombres=modelo.nombres,
                apellidos=modelo.apellidos,
                documento=modelo.documento,
                parentesco=modelo.parentesco,
                telefono_whatsapp=modelo.telefono_whatsapp,
                es_principal=bool(vinculo.es_principal),
                activo=bool(modelo.activo),
            )
        )
    return tuple(apoderados)


def _ficha_desde_modelo(session: Session, modelo: EstudianteModel) -> FichaMatricula | None:
    """Reconstruye una ficha mínima para validar duplicados y vacantes."""
    if modelo.salon_id is None or modelo.fecha_nacimiento is None:
        return None
    salon = session.get(SalonModel, modelo.salon_id)
    if salon is None:
        return None
    apoderados = _apoderados_de_modelo(session, modelo.id)
    if not apoderados:
        apoderados = (
            Apoderado(
                id=0,
                nombres="Registro",
                apellidos="Existente",
                documento="00000000",
                parentesco="TUTOR",
                telefono_whatsapp="999999999",
                es_principal=True,
            ),
        )
    try:
        estado = EstadoAcademico(modelo.estado)
    except ValueError:
        estado = EstadoAcademico.ACTIVO
    try:
        return FichaMatricula(
            id=f"mat-{modelo.id}",
            alumno_id=modelo.id,
            codigo_estudiante=modelo.codigo,
            dni=modelo.dni,
            nombres=modelo.nombres,
            apellidos=modelo.apellidos,
            fecha_nacimiento=modelo.fecha_nacimiento,
            anio_lectivo=salon.anio_lectivo,
            salon_id=salon.id,
            nivel=modelo.nivel or salon.nivel,
            grado=modelo.grado or salon.grado,
            seccion=modelo.seccion or salon.seccion,
            apoderados=apoderados,
            estado=estado,
            creado_en=modelo.creado_en,
        )
    except Exception:
        return None


def _persistir_apoderados(
    session: Session, alumno_id: int, apoderados: Sequence[Apoderado]
) -> None:
    existentes = session.scalars(
        select(EstudianteApoderadoModel).filter_by(estudiante_id=alumno_id)
    ).all()
    for vinculo in existentes:
        session.delete(vinculo)
    session.flush()
    for apoderado in apoderados:
        modelo = session.scalars(
            select(ApoderadoModel).filter_by(documento=apoderado.documento)
        ).first()
        if modelo is None:
            modelo = ApoderadoModel(
                nombres=apoderado.nombres,
                apellidos=apoderado.apellidos,
                documento=apoderado.documento,
                parentesco=apoderado.parentesco,
                telefono_whatsapp=apoderado.telefono_whatsapp,
                activo=apoderado.activo,
            )
            session.add(modelo)
            session.flush()
        else:
            modelo.nombres = apoderado.nombres
            modelo.apellidos = apoderado.apellidos
            modelo.parentesco = apoderado.parentesco
            modelo.telefono_whatsapp = apoderado.telefono_whatsapp
            modelo.activo = apoderado.activo
        session.add(
            EstudianteApoderadoModel(
                estudiante_id=alumno_id,
                apoderado_id=modelo.id,
                es_principal=apoderado.es_principal,
            )
        )
    session.flush()


def _periodo_actual(
    session: Session, anio_lectivo: int, referencia: date
) -> PeriodoAcademico | None:
    modelo = session.scalars(
        select(PeriodoAcademicoModel)
        .filter(
            PeriodoAcademicoModel.anio_lectivo == anio_lectivo,
            PeriodoAcademicoModel.fecha_inicio <= referencia,
            PeriodoAcademicoModel.fecha_fin >= referencia,
        )
        .order_by(PeriodoAcademicoModel.orden.desc())
    ).first()
    if modelo is None:
        modelo = session.scalars(
            select(PeriodoAcademicoModel)
            .filter(PeriodoAcademicoModel.anio_lectivo == anio_lectivo)
            .order_by(PeriodoAcademicoModel.fecha_inicio.desc())
        ).first()
    return periodo_model_a_dominio(modelo) if modelo is not None else None


def _resumen_asistencia(
    asistencias: Sequence[RegistroAsistencia],
) -> ResumenAsistenciaAlumno:
    conteo = {estado: 0 for estado in EstadoAsistencia}
    for asistencia in asistencias:
        conteo[asistencia.estado] += 1
    total = sum(conteo.values())
    efectivas = conteo[EstadoAsistencia.PUNTUAL] + conteo[EstadoAsistencia.TARDANZA]
    justificadas = conteo[EstadoAsistencia.JUSTIFICADO]
    porcentaje = (
        (Decimal(efectivas + justificadas) / Decimal(total) * Decimal(100)).quantize(
            Decimal("0.01")
        )
        if total
        else Decimal("0.00")
    )
    return ResumenAsistenciaAlumno(
        puntual=conteo[EstadoAsistencia.PUNTUAL],
        tardanza=conteo[EstadoAsistencia.TARDANZA],
        ausente=conteo[EstadoAsistencia.AUSENTE],
        justificado=justificadas,
        porcentaje_asistencia=porcentaje,
    )


def _resumen_asistencia_json(resumen: ResumenAsistenciaAlumno) -> str:
    return json.dumps(
        {
            "PUNTUAL": resumen.puntual,
            "TARDANZA": resumen.tardanza,
            "AUSENTE": resumen.ausente,
            "JUSTIFICADO": resumen.justificado,
            "porcentaje_asistencia": str(resumen.porcentaje_asistencia),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


# ---------------------------------------------------------------------------
# Servicio de aplicación académico
# ---------------------------------------------------------------------------


class ServicioAcademico:
    """Casos de uso transaccionales de matrícula, carnets, malla y notas."""

    def __init__(
        self,
        session_factory: FabricaSesion,
        *,
        reloj: RelojServidor = hora_actual_lima,
    ) -> None:
        self._session_factory = session_factory
        self._reloj = reloj

    # -- helpers -------------------------------------------------------------
    def _ahora(self) -> datetime:
        return self._reloj()

    def _roles(self, session: Session) -> list[Rol]:
        return [rol_model_a_dominio(m, session) for m in session.scalars(select(RolModel)).all()]

    def _operador(self, session: Session, operador_id: int):
        modelo = session.get(UsuarioModel, operador_id)
        if modelo is None:
            raise UsuarioNoEncontradoException(f"El usuario operador {operador_id} no existe.")
        return usuario_model_a_operador(modelo)

    def _actor(self, session: Session, usuario_id: int) -> Usuario:
        modelo = session.get(UsuarioModel, usuario_id)
        if modelo is None:
            raise UsuarioNoEncontradoException(f"El usuario {usuario_id} no existe.")
        return usuario_model_a_dominio(modelo)

    def _autorizar(
        self,
        operador,
        permiso: PermisoOperacion,
        roles: Sequence[Rol],
    ) -> None:
        if not operador.activo:
            raise AccesoDenegadoException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(operador.rol, permiso, roles=roles):
            raise AccesoDenegadoException(
                f"El rol {rol_codigo(operador.rol)} no posee el permiso '{permiso.value}'."
            )

    def _auditar(
        self,
        session: Session,
        operador,
        operacion: TipoOperacionAuditoria,
        entidad: str,
        entidad_id: str | int,
        *,
        detalle: dict[str, object] | None = None,
        alumno_id: int | None = None,
        estado_anterior: str | None = None,
        estado_nuevo: str | None = None,
        motivo: str | None = None,
    ) -> None:
        registrar_auditoria_pbi16(
            session,
            usuario_id=operador.id,
            rol_ejecutante=rol_codigo(operador.rol),
            operacion=operacion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            fecha_hora=self._ahora(),
            detalle=detalle,
            alumno_id=alumno_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            motivo=motivo,
        )

    def _estudiante(self, session: Session, alumno_id: int) -> EstudianteModel:
        modelo = session.get(EstudianteModel, alumno_id)
        if modelo is None:
            raise ValueError(f"El alumno {alumno_id} no existe.")
        return modelo

    def _salon(self, session: Session, salon_id: int) -> SalonModel:
        modelo = session.get(SalonModel, salon_id)
        if modelo is None:
            raise ValueError(f"El salón {salon_id} no existe.")
        return modelo

    def _curso(self, session: Session, curso_id: int) -> CursoModel:
        modelo = session.get(CursoModel, curso_id)
        if modelo is None:
            raise ValueError(f"El curso {curso_id} no existe.")
        return modelo

    # ------------------------------------------------------------------
    # PBI-05: matrícula digital
    # ------------------------------------------------------------------
    def matricular(
        self,
        operador_id: int,
        *,
        codigo_estudiante: str,
        dni: str,
        nombres: str,
        apellidos: str,
        fecha_nacimiento: date,
        salon_id: int,
        apoderados: Sequence[Apoderado],
        alumno_id: int | None = None,
    ) -> FichaMatricula:
        """Registra o actualiza la ficha de matrícula de un alumno (PBI-05)."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            salon = self._salon(session, salon_id)
            salon_dom = salon_model_a_dominio(salon)

            existentes = [
                ficha
                for modelo in session.scalars(select(EstudianteModel)).all()
                if (ficha := _ficha_desde_modelo(session, modelo)) is not None
                and ficha.alumno_id != alumno_id
            ]

            if alumno_id is None:
                modelo = EstudianteModel(
                    codigo=codigo_estudiante,
                    dni=dni,
                    nombres=nombres,
                    apellidos=apellidos,
                    fecha_nacimiento=fecha_nacimiento,
                    salon_id=salon.id,
                    nivel=salon.nivel,
                    grado=salon.grado,
                    seccion=salon.seccion,
                    estado=EstadoAcademico.ACTIVO.value,
                )
                session.add(modelo)
                session.flush()
                alumno_id = modelo.id
            else:
                modelo = self._estudiante(session, alumno_id)

            ficha = ServicioMatricula.matricular_estudiante(
                operador=operador,
                alumno_id=alumno_id,
                codigo_estudiante=codigo_estudiante,
                dni=dni,
                nombres=nombres,
                apellidos=apellidos,
                fecha_nacimiento=fecha_nacimiento,
                salon=salon_dom,
                apoderados=apoderados,
                matriculas_existentes=existentes,
                fecha_actual=self._ahora().date(),
                roles=roles,
                creado_en=self._ahora(),
            )

            modelo.codigo = ficha.codigo_estudiante
            modelo.dni = ficha.dni
            modelo.nombres = ficha.nombres
            modelo.apellidos = ficha.apellidos
            modelo.fecha_nacimiento = ficha.fecha_nacimiento
            modelo.salon_id = ficha.salon_id
            modelo.nivel = ficha.nivel
            modelo.grado = ficha.grado
            modelo.seccion = ficha.seccion
            modelo.estado = ficha.estado.value
            _persistir_apoderados(session, ficha.alumno_id, ficha.apoderados)

            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "matricula",
                ficha.id,
                detalle={
                    "accion": "MATRICULAR",
                    "alumno_id": ficha.alumno_id,
                    "anio_lectivo": ficha.anio_lectivo,
                },
                alumno_id=ficha.alumno_id,
            )
            uow.commit()
        return ficha

    def obtener_matricula(self, alumno_id: int) -> FichaMatricula | None:
        """Devuelve la ficha de matrícula vigente del alumno, si existe."""
        session = self._session_factory()
        try:
            modelo = session.get(EstudianteModel, alumno_id)
            if modelo is None:
                return None
            return _ficha_desde_modelo(session, modelo)
        finally:
            session.close()

    def cambiar_salon(
        self, operador_id: int, alumno_id: int, nuevo_salon_id: int
    ) -> FichaMatricula:
        """Traslada internamente a un alumno ACTIVO dentro del mismo año lectivo."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._estudiante(session, alumno_id)
            ficha = _ficha_desde_modelo(session, modelo)
            if ficha is None:
                raise ValueError("El alumno no tiene una matrícula completa para cambiar de salón.")
            nuevo_salon = self._salon(session, nuevo_salon_id)
            existentes = [
                otra
                for otro in session.scalars(select(EstudianteModel)).all()
                if (otra := _ficha_desde_modelo(session, otro)) is not None
            ]
            actualizada = ServicioMatricula.cambiar_salon(
                operador=operador,
                ficha=ficha,
                nuevo_salon=salon_model_a_dominio(nuevo_salon),
                matriculas_existentes=existentes,
                roles=roles,
            )
            modelo.salon_id = actualizada.salon_id
            modelo.nivel = actualizada.nivel
            modelo.grado = actualizada.grado
            modelo.seccion = actualizada.seccion
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "matricula",
                actualizada.id,
                detalle={
                    "accion": "CAMBIAR_SALON",
                    "salon_anterior": ficha.salon_id,
                    "salon_nuevo": actualizada.salon_id,
                },
                alumno_id=alumno_id,
            )
            uow.commit()
        return actualizada

    # ------------------------------------------------------------------
    # PBI-06: carnets
    # ------------------------------------------------------------------
    def emitir_carnet(
        self,
        operador_id: int,
        alumno_id: int,
        anio_lectivo: int,
        *,
        motivo_reposicion: MotivoAnulacionCarnet | str | None = None,
        detalle_anulacion: str | None = None,
    ) -> ResultadoEmisionCarnet:
        """Emite un carnet QR y anula el activo anterior si corresponde."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            alumno = self._estudiante(session, alumno_id)
            carnets = [
                carnet_model_a_dominio(m)
                for m in session.scalars(
                    select(CarnetModel).filter_by(estudiante_id=alumno_id)
                ).all()
            ]
            resultado = ServicioCarnets.emitir_carnet(
                operador=operador,
                alumno_id=alumno_id,
                estado_alumno=alumno.estado,
                anio_lectivo=anio_lectivo,
                carnets_existentes=carnets,
                fecha_hora=self._ahora(),
                motivo_reposicion=motivo_reposicion,
                detalle_anulacion=detalle_anulacion,
                roles=roles,
            )
            if resultado.carnet_anulado is not None:
                anterior = session.get(CarnetModel, resultado.carnet_anulado.id)
                if anterior is not None:
                    anterior.estado = resultado.carnet_anulado.estado.value
                    anterior.anulado_en = _naive(resultado.carnet_anulado.anulado_en)
                    anterior.motivo_anulacion = (
                        resultado.carnet_anulado.motivo_anulacion.value
                        if resultado.carnet_anulado.motivo_anulacion
                        else None
                    )
                    anterior.detalle_anulacion = resultado.carnet_anulado.detalle_anulacion
            nuevo = resultado.carnet_nuevo
            session.add(
                CarnetModel(
                    id=nuevo.id,
                    estudiante_id=nuevo.alumno_id,
                    codigo_qr=nuevo.codigo_qr,
                    estado=nuevo.estado.value,
                    emitido_por=nuevo.emitido_por,
                    emitido_en=_naive(nuevo.emitido_en),
                )
            )
            alumno.carnet_codigo = nuevo.codigo_qr
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "carnet",
                nuevo.id,
                detalle={
                    "accion": "EMITIR_CARNET",
                    "codigo_qr": nuevo.codigo_qr,
                    "anio_lectivo": anio_lectivo,
                },
                alumno_id=alumno_id,
            )
            uow.commit()
        return resultado

    def anular_carnet(
        self,
        operador_id: int,
        carnet_id: str,
        motivo: MotivoAnulacionCarnet | str,
        *,
        detalle: str | None = None,
    ) -> CarnetEscolar:
        """Anula un carnet activo conservando su trazabilidad."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(CarnetModel, carnet_id)
            if modelo is None:
                raise ValueError(f"El carnet {carnet_id} no existe.")
            anulado = ServicioCarnets.anular_carnet(
                operador=operador,
                carnet=carnet_model_a_dominio(modelo),
                motivo=motivo,
                fecha_hora=self._ahora(),
                detalle=detalle,
                roles=roles,
            )
            modelo.estado = anulado.estado.value
            modelo.anulado_en = _naive(anulado.anulado_en)
            modelo.motivo_anulacion = (
                anulado.motivo_anulacion.value if anulado.motivo_anulacion else None
            )
            modelo.detalle_anulacion = anulado.detalle_anulacion
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "carnet",
                anulado.id,
                detalle={"accion": "ANULAR_CARNET"},
                alumno_id=anulado.alumno_id,
            )
            uow.commit()
        return anulado

    def validar_carnet(self, codigo_qr: str) -> CarnetEscolar:
        """Valida que un código QR habilite el ingreso (RN-06)."""
        session = self._session_factory()
        try:
            modelos = [
                carnet_model_a_dominio(m) for m in session.scalars(select(CarnetModel)).all()
            ]
            return ServicioCarnets.validar_carnet_para_ingreso(codigo_qr, modelos)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # PBI-08: estados académicos
    # ------------------------------------------------------------------
    def cambiar_estado_academico(
        self,
        operador_id: int,
        alumno_id: int,
        nuevo_estado: EstadoAcademico,
        motivo: str,
        *,
        fecha_inicio_suspension: date | None = None,
        fecha_fin_suspension: date | None = None,
    ) -> ResultadoCambioEstado:
        """Aplica una transición de estado académico y audita el cambio."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            alumno = self._estudiante(session, alumno_id)
            try:
                estado_actual = EstadoAcademico(alumno.estado)
            except ValueError:
                estado_actual = EstadoAcademico.ACTIVO
            resultado = ServicioEstadosAcademicos.cambiar_estado(
                operador=operador,
                alumno_id=alumno_id,
                estado_actual=estado_actual,
                nuevo_estado=nuevo_estado,
                motivo=motivo,
                fecha_hora=self._ahora(),
                fecha_inicio_suspension=fecha_inicio_suspension,
                fecha_fin_suspension=fecha_fin_suspension,
                roles=roles,
            )
            alumno.estado = resultado.estado_actual.value
            historial = resultado.historial
            session.add(
                EstudianteEstadoHistorialModel(
                    id=historial.id,
                    estudiante_id=historial.alumno_id,
                    estado_anterior=historial.estado_anterior.value,
                    estado_nuevo=historial.estado_nuevo.value,
                    motivo=historial.motivo,
                    fecha_inicio=historial.fecha_inicio_suspension,
                    fecha_fin=historial.fecha_fin_suspension,
                    usuario_id=historial.usuario_id,
                    rol_usuario=historial.rol_usuario,
                    creado_en=_naive(historial.fecha_hora),
                )
            )
            if resultado.debe_anular_carnet:
                for carnet in session.scalars(
                    select(CarnetModel).filter_by(
                        estudiante_id=alumno_id, estado=EstadoCarnet.ACTIVO.value
                    )
                ).all():
                    carnet.estado = EstadoCarnet.ANULADO.value
                    carnet.anulado_en = _naive(self._ahora())
                    carnet.motivo_anulacion = MotivoAnulacionCarnet.BAJA_ESTUDIANTE.value
                    carnet.detalle_anulacion = "Anulado por cambio de estado académico."
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "estado_academico",
                historial.id,
                detalle={"accion": "CAMBIAR_ESTADO", "motivo": historial.motivo},
                alumno_id=alumno_id,
                estado_anterior=historial.estado_anterior.value,
                estado_nuevo=historial.estado_nuevo.value,
                motivo=historial.motivo,
            )
            uow.commit()
        return resultado

    def estado_efectivo(self, alumno_id: int) -> EstadoAcademico:
        """Devuelve el estado académico vigente del alumno."""
        session = self._session_factory()
        try:
            alumno = self._estudiante(session, alumno_id)
            try:
                return EstadoAcademico(alumno.estado)
            except ValueError:
                return EstadoAcademico.ACTIVO
        finally:
            session.close()

    # ------------------------------------------------------------------
    # PBI-07: pagos y alertas
    # ------------------------------------------------------------------
    def registrar_obligacion(
        self,
        operador_id: int,
        alumno_id: int,
        concepto: str,
        monto: Decimal,
        fecha_vencimiento: date,
    ) -> ObligacionPago:
        """Registra una obligación económica pendiente."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            self._estudiante(session, alumno_id)
            obligacion = ServicioPagos.registrar_obligacion(
                operador=operador,
                alumno_id=alumno_id,
                concepto=concepto,
                monto=monto,
                fecha_vencimiento=fecha_vencimiento,
                roles=roles,
            )
            session.add(
                ObligacionPagoModel(
                    id=obligacion.id,
                    estudiante_id=obligacion.alumno_id,
                    concepto=obligacion.concepto,
                    monto=obligacion.monto,
                    fecha_vencimiento=obligacion.fecha_vencimiento,
                    estado=obligacion.estado.value,
                )
            )
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "obligacion_pago",
                obligacion.id,
                detalle={"accion": "REGISTRAR_OBLIGACION", "monto": str(obligacion.monto)},
                alumno_id=alumno_id,
            )
            uow.commit()
        return obligacion

    def registrar_pago(
        self, operador_id: int, obligacion_id: str, *, fecha_hora: datetime | None = None
    ) -> ObligacionPago:
        """Marca una obligación como pagada."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(ObligacionPagoModel, obligacion_id)
            if modelo is None:
                raise ValueError(f"La obligación {obligacion_id} no existe.")
            pagada = ServicioPagos.registrar_pago(
                operador=operador,
                obligacion=obligacion_model_a_dominio(modelo),
                fecha_hora=fecha_hora or self._ahora(),
                roles=roles,
            )
            modelo.estado = pagada.estado.value
            modelo.pagado_en = _naive(pagada.pagado_en) if pagada.pagado_en else None
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "obligacion_pago",
                modelo.id,
                detalle={"accion": "REGISTRAR_PAGO"},
                alumno_id=modelo.estudiante_id,
            )
            uow.commit()
        return pagada

    def exonerar_obligacion(
        self, operador_id: int, obligacion_id: str, motivo: str
    ) -> ObligacionPago:
        """Exonera una obligación con motivo obligatorio."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(ObligacionPagoModel, obligacion_id)
            if modelo is None:
                raise ValueError(f"La obligación {obligacion_id} no existe.")
            exonerada = ServicioPagos.exonerar_obligacion(
                operador=operador,
                obligacion=obligacion_model_a_dominio(modelo),
                motivo=motivo,
                roles=roles,
            )
            modelo.estado = exonerada.estado.value
            modelo.motivo_exoneracion = exonerada.motivo_exoneracion
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "obligacion_pago",
                modelo.id,
                detalle={"accion": "EXONERAR_OBLIGACION", "motivo": motivo},
                alumno_id=modelo.estudiante_id,
            )
            uow.commit()
        return exonerada

    def listar_obligaciones(self, alumno_id: int) -> list[ObligacionPago]:
        """Lista las obligaciones de un alumno."""
        session = self._session_factory()
        try:
            return [
                obligacion_model_a_dominio(m)
                for m in session.scalars(
                    select(ObligacionPagoModel).filter_by(estudiante_id=alumno_id)
                ).all()
            ]
        finally:
            session.close()

    def listar_alertas_pago(self, *, solo_activas: bool = True) -> list[AlertaSilenciosaPago]:
        """Lista las alertas silenciosas de pago registradas."""
        session = self._session_factory()
        try:
            consulta = select(AlertaPagoSilenciosaModel)
            if solo_activas:
                consulta = consulta.filter_by(revisada=False)
            return [
                AlertaSilenciosaPago(
                    id=m.id,
                    alumno_id=m.estudiante_id,
                    asistencia_id=m.asistencia_id,
                    fecha_escolar=m.fecha_escolar,
                    cantidad_obligaciones_vencidas=m.cantidad_obligaciones_vencidas,
                    monto_vencido_total=Decimal(m.monto_vencido_total),
                    revisada=bool(m.revisada),
                    creado_en=m.creado_en,
                )
                for m in session.scalars(consulta).all()
            ]
        finally:
            session.close()

    def marcar_alerta_revisada(self, operador_id: int, alerta_id: str) -> None:
        """Marca una alerta de pago como revisada."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            self._autorizar(operador, PermisoOperacion.VER_ALERTA_PAGOS, roles)
            modelo = session.get(AlertaPagoSilenciosaModel, alerta_id)
            if modelo is None:
                raise ValueError(f"La alerta {alerta_id} no existe.")
            modelo.revisada = True
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "alerta_pago",
                alerta_id,
                detalle={"accion": "MARCAR_ALERTA_REVISADA"},
                alumno_id=modelo.estudiante_id,
            )
            uow.commit()

    # ------------------------------------------------------------------
    # PBI-09: malla curricular
    # ------------------------------------------------------------------
    def crear_salon(
        self,
        operador_id: int,
        *,
        anio_lectivo: int,
        nivel: NivelEducativo | str,
        grado: str,
        seccion: str,
        capacidad_maxima: int = 30,
    ) -> Salon:
        """Registra un salón validando unicidad y datos académicos."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            nivel_enum = nivel if isinstance(nivel, NivelEducativo) else NivelEducativo(nivel)
            propuesto = Salon(
                id=0,
                anio_lectivo=anio_lectivo,
                nivel=nivel_enum,
                grado=grado,
                seccion=seccion,
                capacidad_maxima=capacidad_maxima,
            )
            existentes = [
                salon_model_a_dominio(m) for m in session.scalars(select(SalonModel)).all()
            ]
            validado = ServicioMallaCurricular.crear_salon(
                operador=operador,
                salon=propuesto,
                salones_existentes=existentes,
                roles=roles,
            )
            modelo = SalonModel(
                anio_lectivo=validado.anio_lectivo,
                nivel=validado.nivel.value,
                grado=validado.grado,
                seccion=validado.seccion,
                capacidad_maxima=validado.capacidad_maxima,
                activo=validado.activo,
            )
            session.add(modelo)
            session.flush()
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "salon",
                modelo.id,
                detalle={"accion": "CREAR_SALON"},
            )
            uow.commit()
        return replace(validado, id=modelo.id)

    def actualizar_capacidad_salon(
        self, operador_id: int, salon_id: int, nueva_capacidad: int
    ) -> Salon:
        """Actualiza la capacidad máxima de un salón."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._salon(session, salon_id)
            matriculados = session.query(EstudianteModel).filter_by(salon_id=salon_id).count()
            actualizado = ServicioMallaCurricular.actualizar_capacidad_salon(
                operador=operador,
                salon=salon_model_a_dominio(modelo),
                nueva_capacidad=nueva_capacidad,
                matriculados_actuales=matriculados,
                roles=roles,
            )
            modelo.capacidad_maxima = actualizado.capacidad_maxima
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "salon",
                salon_id,
                detalle={"accion": "ACTUALIZAR_CAPACIDAD"},
            )
            uow.commit()
        return actualizado

    def desactivar_salon(self, operador_id: int, salon_id: int) -> Salon:
        """Realiza la baja lógica de un salón."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._salon(session, salon_id)
            desactivado = ServicioMallaCurricular.desactivar_salon(
                operador=operador,
                salon=salon_model_a_dominio(modelo),
                roles=roles,
            )
            modelo.activo = False
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "salon",
                salon_id,
                detalle={"accion": "DESACTIVAR_SALON"},
            )
            uow.commit()
        return desactivado

    def eliminar_salon(self, operador_id: int, salon_id: int) -> None:
        """Elimina un salón sin alumnos ni asignaciones asociadas."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._salon(session, salon_id)
            tiene_alumnos = session.query(EstudianteModel).filter_by(salon_id=salon_id).count() > 0
            tiene_asignaciones = (
                session.query(AsignacionDocenteModel).filter_by(salon_id=salon_id).count() > 0
            )
            ServicioMallaCurricular.eliminar_salon(
                operador=operador,
                salon=salon_model_a_dominio(modelo),
                tiene_alumnos_asociados=tiene_alumnos,
                roles=roles,
            )
            if tiene_asignaciones:
                raise EntidadEnUsoException(
                    "No se puede eliminar el salón porque tiene asignaciones docentes."
                )
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "salon",
                salon_id,
                detalle={"accion": "ELIMINAR_SALON"},
            )
            session.delete(modelo)
            uow.commit()

    def crear_curso(
        self,
        operador_id: int,
        *,
        anio_lectivo: int,
        nivel: NivelEducativo | str,
        grado: str,
        codigo: str,
        nombre: str,
        area_curricular: str,
        horas_semanales: int,
    ) -> Curso:
        """Registra un curso de la malla curricular."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            nivel_enum = nivel if isinstance(nivel, NivelEducativo) else NivelEducativo(nivel)
            propuesto = Curso(
                id=0,
                anio_lectivo=anio_lectivo,
                nivel=nivel_enum,
                grado=grado,
                codigo=codigo,
                nombre=nombre,
                area_curricular=area_curricular,
                horas_semanales=horas_semanales,
            )
            existentes = [
                curso_model_a_dominio(m) for m in session.scalars(select(CursoModel)).all()
            ]
            validado = ServicioMallaCurricular.crear_curso(
                operador=operador,
                curso=propuesto,
                cursos_existentes=existentes,
                roles=roles,
            )
            modelo = CursoModel(
                anio_lectivo=validado.anio_lectivo,
                nivel=validado.nivel.value,
                grado=validado.grado,
                codigo=validado.codigo,
                nombre=validado.nombre,
                area_curricular=validado.area_curricular,
                horas_semanales=validado.horas_semanales,
                activo=validado.activo,
            )
            session.add(modelo)
            session.flush()
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "curso",
                modelo.id,
                detalle={"accion": "CREAR_CURSO"},
            )
            uow.commit()
        return replace(validado, id=modelo.id)

    def desactivar_curso(self, operador_id: int, curso_id: int) -> Curso:
        """Realiza la baja lógica de un curso."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._curso(session, curso_id)
            desactivado = ServicioMallaCurricular.desactivar_curso(
                operador=operador,
                curso=curso_model_a_dominio(modelo),
                roles=roles,
            )
            modelo.activo = False
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "curso",
                curso_id,
                detalle={"accion": "DESACTIVAR_CURSO"},
            )
            uow.commit()
        return desactivado

    def eliminar_curso(self, operador_id: int, curso_id: int) -> None:
        """Elimina un curso sin asignaciones ni calificaciones registradas."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._curso(session, curso_id)
            tiene_asignaciones = (
                session.query(AsignacionDocenteModel).filter_by(curso_id=curso_id).count() > 0
            )
            if tiene_asignaciones:
                raise EntidadEnUsoException(
                    "No se puede eliminar el curso porque tiene asignaciones docentes."
                )
            ServicioMallaCurricular.eliminar_curso(
                operador=operador,
                curso=curso_model_a_dominio(modelo),
                roles=roles,
            )
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.OTRA,
                "curso",
                curso_id,
                detalle={"accion": "ELIMINAR_CURSO"},
            )
            session.delete(modelo)
            uow.commit()

    def listar_salones(
        self,
        *,
        anio_lectivo: int | None = None,
        nivel: NivelEducativo | None = None,
        grado: str | None = None,
        solo_activos: bool = True,
    ) -> list[Salon]:
        """Lista salones aplicando filtros de la malla."""
        session = self._session_factory()
        try:
            salones = [salon_model_a_dominio(m) for m in session.scalars(select(SalonModel)).all()]
            return ServicioMallaCurricular.listar_salones(
                salones,
                anio_lectivo=anio_lectivo,
                nivel=nivel,
                grado=grado,
                solo_activos=solo_activos,
            )
        finally:
            session.close()

    def listar_cursos(
        self,
        *,
        anio_lectivo: int | None = None,
        nivel: NivelEducativo | None = None,
        grado: str | None = None,
        solo_activos: bool = True,
    ) -> list[Curso]:
        """Lista cursos aplicando filtros de la malla."""
        session = self._session_factory()
        try:
            cursos = [curso_model_a_dominio(m) for m in session.scalars(select(CursoModel)).all()]
            return ServicioMallaCurricular.listar_cursos(
                cursos,
                anio_lectivo=anio_lectivo,
                nivel=nivel,
                grado=grado,
                solo_activos=solo_activos,
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # PBI-11: asignación docente
    # ------------------------------------------------------------------
    def _persistir_auditoria_dominio(self, session: Session):
        def _persistir(registro) -> None:
            session.add(_auditoria_a_model(registro))
            session.flush()

        return _persistir

    def asignar_docente(
        self, operador_id: int, docente_id: int, curso_id: int, salon_id: int
    ) -> AsignacionDocente:
        """Asigna un docente habilitado a un curso y salón."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._actor(session, operador_id)
            roles = self._roles(session)
            docente = self._actor(session, docente_id)
            curso = self._curso(session, curso_id)
            salon = self._salon(session, salon_id)
            existentes = [
                asignacion_model_a_dominio(m)
                for m in session.scalars(select(AsignacionDocenteModel)).all()
            ]
            asignacion = ServicioAsignacionDocente.asignar_docente(
                operador=operador,
                docente=docente,
                curso=curso_model_a_dominio(curso),
                salon=salon_model_a_dominio(salon),
                asignaciones_existentes=existentes,
                fecha_hora=self._ahora(),
                roles=roles,
                eventos_auditoria_existentes=_eventos_existentes(session),
                persistir_auditoria=self._persistir_auditoria_dominio(session),
            )
            session.add(
                AsignacionDocenteModel(
                    id=asignacion.id,
                    usuario_docente_id=asignacion.usuario_docente_id,
                    curso_id=asignacion.curso_id,
                    salon_id=asignacion.salon_id,
                    anio_lectivo=asignacion.anio_lectivo,
                    activa=asignacion.activa,
                    asignado_por=asignacion.asignado_por,
                    creado_en=_naive(asignacion.creado_en),
                )
            )
            uow.commit()
        return asignacion

    def revocar_asignacion(
        self, operador_id: int, asignacion_id: str, motivo: str | None = None
    ) -> AsignacionDocente:
        """Revoca lógicamente una asignación docente."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._actor(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(AsignacionDocenteModel, asignacion_id)
            if modelo is None:
                raise ValueError(f"La asignación {asignacion_id} no existe.")
            revocada = ServicioAsignacionDocente.revocar_asignacion(
                operador=operador,
                asignacion=asignacion_model_a_dominio(modelo),
                fecha_hora=self._ahora(),
                roles=roles,
                motivo=motivo,
                eventos_auditoria_existentes=_eventos_existentes(session),
                persistir_auditoria=self._persistir_auditoria_dominio(session),
            )
            modelo.activa = False
            modelo.revocada_en = _naive(revocada.revocada_en)
            modelo.motivo_revocacion = revocada.motivo_revocacion
            uow.commit()
        return revocada

    def eliminar_asignacion(self, operador_id: int, asignacion_id: str) -> None:
        """Elimina una asignación sin calificaciones asociadas."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._actor(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(AsignacionDocenteModel, asignacion_id)
            if modelo is None:
                raise ValueError(f"La asignación {asignacion_id} no existe.")
            tiene_calificaciones = (
                session.query(CalificacionModel)
                .join(
                    ActividadEvaluableModel,
                    CalificacionModel.actividad_id == ActividadEvaluableModel.id,
                )
                .join(
                    RubroEvaluacionModel,
                    ActividadEvaluableModel.rubro_id == RubroEvaluacionModel.id,
                )
                .filter(RubroEvaluacionModel.asignacion_docente_id == asignacion_id)
                .count()
                > 0
            )
            ServicioAsignacionDocente.eliminar_asignacion(
                operador=operador,
                asignacion=asignacion_model_a_dominio(modelo),
                tiene_calificaciones_asociadas=tiene_calificaciones,
                fecha_hora=self._ahora(),
                roles=roles,
                eventos_auditoria_existentes=_eventos_existentes(session),
                persistir_auditoria=self._persistir_auditoria_dominio(session),
            )
            session.delete(modelo)
            uow.commit()

    def listar_asignaciones_docente(
        self, docente_id: int, *, solo_activas: bool = True
    ) -> list[AsignacionDocente]:
        """Lista las asignaciones de un docente."""
        session = self._session_factory()
        try:
            consulta = select(AsignacionDocenteModel).filter_by(usuario_docente_id=docente_id)
            if solo_activas:
                consulta = consulta.filter_by(activa=True)
            return [asignacion_model_a_dominio(m) for m in session.scalars(consulta).all()]
        finally:
            session.close()

    def validar_ambito_docente(
        self, docente_id: int, curso_id: int, salon_id: int, anio_lectivo: int
    ) -> AsignacionDocente:
        """Verifica que el docente tenga una asignación activa en el grupo."""
        session = self._session_factory()
        try:
            docente = self._actor(session, docente_id)
            roles = self._roles(session)
            asignaciones = [
                asignacion_model_a_dominio(m)
                for m in session.scalars(
                    select(AsignacionDocenteModel).filter_by(usuario_docente_id=docente_id)
                ).all()
            ]
            return ServicioAsignacionDocente.validar_ambito_docente(
                docente=docente,
                curso_id=curso_id,
                salon_id=salon_id,
                anio_lectivo=anio_lectivo,
                asignaciones=asignaciones,
                roles=roles,
                fecha_hora=self._ahora(),
                eventos_auditoria_existentes=_eventos_existentes(session),
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # PBI-10: calificaciones y promedios (3 niveles)
    # ------------------------------------------------------------------
    def configurar_rubros(
        self,
        operador_id: int,
        asignacion_id: str,
        periodo_id: int,
        rubros: Sequence[tuple[str, Decimal]],
    ) -> tuple[RubroEvaluacion, ...]:
        """Configura los rubros ponderados de una asignación y período."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            docente = self._actor(session, operador_id)
            roles = self._roles(session)
            asignacion = self._asignacion(session, asignacion_id)
            periodo = self._periodo(session, periodo_id)
            asignaciones = [
                asignacion_model_a_dominio(m)
                for m in session.scalars(
                    select(AsignacionDocenteModel).filter_by(usuario_docente_id=operador_id)
                ).all()
            ]
            creados = ServicioCalificaciones.configurar_rubros(
                docente=docente,
                asignacion=asignacion,
                periodo=periodo,
                rubros_propuestos=rubros,
                fecha_actual=self._ahora(),
                asignaciones=asignaciones,
                roles=roles,
            )
            for rubro in creados:
                session.add(
                    RubroEvaluacionModel(
                        id=rubro.id,
                        asignacion_docente_id=rubro.asignacion_docente_id,
                        periodo_id=rubro.periodo_id,
                        nombre=rubro.nombre,
                        peso_porcentaje=rubro.peso_porcentaje,
                        activo=rubro.activo,
                    )
                )
            self._auditar(
                session,
                self._operador(session, operador_id),
                TipoOperacionAuditoria.OTRA,
                "rubro_evaluacion",
                asignacion_id,
                detalle={
                    "accion": "CONFIGURAR_RUBROS",
                    "periodo_id": periodo_id,
                    "rubros": [r.nombre for r in creados],
                },
            )
            uow.commit()
        return creados

    def crear_actividad(
        self,
        operador_id: int,
        rubro_id: str,
        titulo: str,
        fecha_actividad: date,
    ) -> ActividadEvaluable:
        """Crea una actividad evaluable dentro de un rubro."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            docente = self._actor(session, operador_id)
            roles = self._roles(session)
            rubro_modelo = session.get(RubroEvaluacionModel, rubro_id)
            if rubro_modelo is None:
                raise ValueError(f"El rubro {rubro_id} no existe.")
            rubro = rubro_model_a_dominio(rubro_modelo)
            asignacion = self._asignacion(session, rubro.asignacion_docente_id)
            periodo = self._periodo(session, rubro.periodo_id)
            asignaciones = [
                asignacion_model_a_dominio(m)
                for m in session.scalars(
                    select(AsignacionDocenteModel).filter_by(usuario_docente_id=operador_id)
                ).all()
            ]
            actividad = ServicioCalificaciones.crear_actividad(
                docente=docente,
                asignacion=asignacion,
                periodo=periodo,
                rubro=rubro,
                titulo=titulo,
                fecha_actividad=fecha_actividad,
                fecha_actual=self._ahora(),
                asignaciones=asignaciones,
                roles=roles,
            )
            session.add(
                ActividadEvaluableModel(
                    id=actividad.id,
                    rubro_id=actividad.rubro_id,
                    titulo=actividad.titulo,
                    fecha=actividad.fecha,
                    activo=actividad.activo,
                )
            )
            self._auditar(
                session,
                self._operador(session, operador_id),
                TipoOperacionAuditoria.OTRA,
                "actividad_evaluable",
                actividad.id,
                detalle={"accion": "CREAR_ACTIVIDAD", "rubro_id": rubro_id},
            )
            uow.commit()
        return actividad

    def registrar_calificacion(
        self,
        operador_id: int,
        actividad_id: str,
        alumno_id: int,
        nota: Decimal,
        *,
        motivo_modificacion: str | None = None,
        observacion: str | None = None,
    ) -> Calificacion:
        """Registra o modifica la nota de un alumno en una actividad."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            docente = self._actor(session, operador_id)
            roles = self._roles(session)
            actividad_modelo = session.get(ActividadEvaluableModel, actividad_id)
            if actividad_modelo is None:
                raise ValueError(f"La actividad {actividad_id} no existe.")
            actividad = actividad_model_a_dominio(actividad_modelo)
            rubro_modelo = session.get(RubroEvaluacionModel, actividad.rubro_id)
            if rubro_modelo is None:
                raise ValueError(f"El rubro {actividad.rubro_id} no existe.")
            rubro = rubro_model_a_dominio(rubro_modelo)
            asignacion = self._asignacion(session, rubro.asignacion_docente_id)
            periodo = self._periodo(session, rubro.periodo_id)
            existente_modelo = session.scalars(
                select(CalificacionModel).filter_by(
                    actividad_id=actividad_id, estudiante_id=alumno_id
                )
            ).first()
            existente = (
                calificacion_model_a_dominio(existente_modelo)
                if existente_modelo is not None
                else None
            )
            asignaciones = [
                asignacion_model_a_dominio(m)
                for m in session.scalars(
                    select(AsignacionDocenteModel).filter_by(usuario_docente_id=operador_id)
                ).all()
            ]
            calificacion = ServicioCalificaciones.registrar_calificacion(
                docente=docente,
                asignacion=asignacion,
                periodo=periodo,
                actividad=actividad,
                alumno_id=alumno_id,
                nota=nota,
                fecha_hora=self._ahora(),
                asignaciones=asignaciones,
                calificacion_existente=existente,
                motivo_modificacion=motivo_modificacion,
                observacion=observacion,
                roles=roles,
            )
            if existente_modelo is None:
                existente_modelo = CalificacionModel(
                    id=calificacion.id,
                    actividad_id=calificacion.actividad_id,
                    estudiante_id=calificacion.alumno_id,
                    nota=calificacion.nota,
                    usuario_id=calificacion.usuario_id,
                    actualizado_en=_naive(calificacion.actualizado_en),
                )
                session.add(existente_modelo)
            existente_modelo.nota = calificacion.nota
            existente_modelo.nota_anterior = calificacion.nota_anterior
            existente_modelo.motivo_modificacion = calificacion.motivo_modificacion
            existente_modelo.observacion = calificacion.observacion
            existente_modelo.usuario_id = calificacion.usuario_id
            existente_modelo.actualizado_en = _naive(calificacion.actualizado_en)
            self._auditar(
                session,
                self._operador(session, operador_id),
                TipoOperacionAuditoria.OTRA,
                "calificacion",
                calificacion.id,
                detalle={
                    "accion": "REGISTRAR_CALIFICACION",
                    "actividad_id": actividad_id,
                    "nota": str(calificacion.nota),
                },
                alumno_id=alumno_id,
            )
            uow.commit()
        return calificacion

    def calcular_promedio_periodo(
        self, alumno_id: int, curso_id: int, periodo_id: int
    ) -> PromedioPeriodo:
        """Calcula el promedio ponderado de un curso en un período."""
        session = self._session_factory()
        try:
            return self._promedio_periodo(session, alumno_id, curso_id, periodo_id)
        finally:
            session.close()

    def calcular_promedio_anual(
        self, alumno_id: int, curso_id: int, anio_lectivo: int
    ) -> PromedioAnualCurso:
        """Calcula el promedio anual de un curso a partir de sus períodos."""
        session = self._session_factory()
        try:
            periodos = session.scalars(
                select(PeriodoAcademicoModel)
                .filter_by(anio_lectivo=anio_lectivo)
                .order_by(PeriodoAcademicoModel.orden)
            ).all()
            promedios = [
                self._promedio_periodo(session, alumno_id, curso_id, periodo.id)
                for periodo in periodos
            ]
            return ServicioCalificaciones.calcular_promedio_anual(
                alumno_id=alumno_id,
                curso_id=curso_id,
                anio_lectivo=anio_lectivo,
                promedios_periodo=promedios,
            )
        finally:
            session.close()

    # -- helpers de calificaciones ------------------------------------------
    def _asignacion(self, session: Session, asignacion_id: str) -> AsignacionDocente:
        modelo = session.get(AsignacionDocenteModel, asignacion_id)
        if modelo is None:
            raise ValueError(f"La asignación docente {asignacion_id} no existe.")
        return asignacion_model_a_dominio(modelo)

    def _periodo(self, session: Session, periodo_id: int) -> PeriodoAcademico:
        modelo = session.get(PeriodoAcademicoModel, periodo_id)
        if modelo is None:
            raise ValueError(f"El período académico {periodo_id} no existe.")
        return periodo_model_a_dominio(modelo)

    def _asignacion_de_curso(
        self, session: Session, curso_id: int, salon_id: int | None
    ) -> AsignacionDocente | None:
        consulta = select(AsignacionDocenteModel).filter_by(curso_id=curso_id, activa=True)
        if salon_id is not None:
            consulta = consulta.filter_by(salon_id=salon_id)
        modelo = session.scalars(consulta).first()
        return asignacion_model_a_dominio(modelo) if modelo is not None else None

    def _promedio_periodo(
        self, session: Session, alumno_id: int, curso_id: int, periodo_id: int
    ) -> PromedioPeriodo:
        alumno = self._estudiante(session, alumno_id)
        asignacion = self._asignacion_de_curso(session, curso_id, alumno.salon_id)
        if asignacion is None:
            raise ValueError(f"El curso {curso_id} no tiene una asignación docente activa.")
        rubros = [
            rubro_model_a_dominio(m)
            for m in session.scalars(
                select(RubroEvaluacionModel).filter_by(
                    asignacion_docente_id=asignacion.id, periodo_id=periodo_id
                )
            ).all()
        ]
        rubro_ids = [rubro.id for rubro in rubros]
        actividades = (
            [
                actividad_model_a_dominio(m)
                for m in session.scalars(
                    select(ActividadEvaluableModel).filter(
                        ActividadEvaluableModel.rubro_id.in_(rubro_ids)
                    )
                ).all()
            ]
            if rubro_ids
            else []
        )
        actividad_ids = [actividad.id for actividad in actividades]
        calificaciones = (
            [
                calificacion_model_a_dominio(m)
                for m in session.scalars(
                    select(CalificacionModel).filter(
                        CalificacionModel.actividad_id.in_(actividad_ids),
                        CalificacionModel.estudiante_id == alumno_id,
                    )
                ).all()
            ]
            if actividad_ids
            else []
        )
        return ServicioCalificaciones.calcular_promedio_periodo(
            alumno_id=alumno_id,
            curso_id=curso_id,
            periodo_id=periodo_id,
            rubros=rubros,
            actividades=actividades,
            calificaciones=calificaciones,
        )

    # ------------------------------------------------------------------
    # PBI-12: ficha informativa del alumno
    # ------------------------------------------------------------------
    def construir_ficha_alumno(self, operador_id: int, alumno_id: int) -> FichaInformativaAlumno:
        """Ensambla la ficha consolidada del alumno con segregación financiera."""
        session = self._session_factory()
        try:
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            self._autorizar(operador, PermisoOperacion.CONSULTAR_FICHA_ALUMNO, roles)
            alumno = self._estudiante(session, alumno_id)

            apoderados = tuple(
                ApoderadoFicha(
                    nombres=a.nombres,
                    apellidos=a.apellidos,
                    parentesco=a.parentesco,
                    telefono=a.telefono_whatsapp,
                    es_principal=a.es_principal,
                )
                for a in _apoderados_de_modelo(session, alumno_id)
            )

            asistencias = [
                asistencia_model_a_dominio(m)
                for m in session.scalars(
                    select(AsistenciaModel).filter_by(estudiante_id=alumno_id)
                ).all()
            ]
            resumen_asistencia = _resumen_asistencia(asistencias)

            anio_lectivo = self._ahora().year
            salon = session.get(SalonModel, alumno.salon_id) if alumno.salon_id else None
            if salon is not None:
                anio_lectivo = salon.anio_lectivo
            periodo = _periodo_actual(session, anio_lectivo, self._ahora().date())
            resumen_promedios = self._promedios_ficha(session, alumno_id, alumno, periodo)

            resumen_pagos: ResumenPagosAlumno | None = None
            if ServicioAutenticacionYPermisos.tiene_permiso(
                operador.rol, PermisoOperacion.VER_ALERTA_PAGOS, roles=roles
            ) or ServicioAutenticacionYPermisos.tiene_permiso(
                operador.rol, PermisoOperacion.GESTIONAR_PAGOS, roles=roles
            ):
                resumen_pagos = self._resumen_pagos(session, alumno_id)

            carnet = session.scalars(
                select(CarnetModel).filter_by(
                    estudiante_id=alumno_id, estado=EstadoCarnet.ACTIVO.value
                )
            ).first()

            try:
                estado = EstadoAcademico(alumno.estado)
            except ValueError:
                estado = EstadoAcademico.ACTIVO

            return FichaInformativaAlumno(
                alumno_id=alumno.id,
                codigo=alumno.codigo,
                dni=alumno.dni,
                nombres=alumno.nombres,
                apellidos=alumno.apellidos,
                nivel=alumno.nivel,
                grado=alumno.grado,
                seccion=alumno.seccion,
                salon_id=alumno.salon_id,
                estado_academico=estado,
                carnet_codigo=carnet.codigo_qr if carnet is not None else None,
                apoderados=apoderados,
                resumen_asistencia=resumen_asistencia,
                resumen_promedios=resumen_promedios,
                resumen_pagos=resumen_pagos,
            )
        finally:
            session.close()

    def _promedios_ficha(
        self,
        session: Session,
        alumno_id: int,
        alumno: EstudianteModel,
        periodo: PeriodoAcademico | None,
    ) -> tuple[ResumenCursoFicha, ...]:
        if periodo is None or alumno.salon_id is None:
            return ()
        asignaciones = session.scalars(
            select(AsignacionDocenteModel).filter_by(
                salon_id=alumno.salon_id, anio_lectivo=periodo.anio_lectivo, activa=True
            )
        ).all()
        resumenes: list[ResumenCursoFicha] = []
        vistos: set[int] = set()
        for modelo in asignaciones:
            if modelo.curso_id in vistos:
                continue
            vistos.add(modelo.curso_id)
            curso = session.get(CursoModel, modelo.curso_id)
            if curso is None:
                continue
            try:
                promedio = self._promedio_periodo(session, alumno_id, modelo.curso_id, periodo.id)
            except Exception:
                continue
            resumenes.append(
                ResumenCursoFicha(
                    curso_id=curso.id,
                    curso_nombre=curso.nombre,
                    nota=promedio.nota_final,
                    literal=promedio.escala_literal.value,
                )
            )
        return tuple(resumenes)

    def _resumen_pagos(self, session: Session, alumno_id: int) -> ResumenPagosAlumno:
        obligaciones = session.scalars(
            select(ObligacionPagoModel).filter_by(estudiante_id=alumno_id)
        ).all()
        hoy = self._ahora().date()
        pendientes = 0
        vencidas = 0
        monto = Decimal("0")
        for modelo in obligaciones:
            if modelo.estado == EstadoObligacion.PAGADO.value:
                continue
            if modelo.estado == EstadoObligacion.EXONERADO.value:
                continue
            pendientes += 1
            if modelo.fecha_vencimiento < hoy:
                vencidas += 1
            monto += Decimal(modelo.monto)
        alertas = (
            session.query(AlertaPagoSilenciosaModel)
            .filter_by(estudiante_id=alumno_id, revisada=False)
            .count()
        )
        return ResumenPagosAlumno(
            pendientes=pendientes,
            vencidas=vencidas,
            monto_pendiente=monto,
            alertas_activas=alertas,
        )

    # ------------------------------------------------------------------
    # PBI-13: exportación de asistencias
    # ------------------------------------------------------------------
    def exportar_asistencias(
        self, operador_id: int, filtro: FiltroExportacionAsistencia
    ) -> ResultadoExportacionAsistencia:
        """Filtra, sanitiza y renderiza las asistencias en el formato pedido."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            alumnos = {
                m.id: Alumno(
                    id=m.id,
                    codigo=m.codigo,
                    dni=m.dni,
                    nombres=m.nombres,
                    apellidos=m.apellidos,
                    nivel=m.nivel,
                    grado=m.grado,
                    seccion=m.seccion,
                    carnet_codigo=m.carnet_codigo or "",
                )
                for m in session.scalars(select(EstudianteModel)).all()
            }
            asistencias = [
                asistencia_model_a_dominio(m)
                for m in session.scalars(
                    select(AsistenciaModel).filter(
                        AsistenciaModel.fecha_escolar >= filtro.fecha_desde,
                        AsistenciaModel.fecha_escolar <= filtro.fecha_hasta,
                    )
                ).all()
            ]
            usuarios = {m.id: m.username for m in session.scalars(select(UsuarioModel)).all()}
            documento = ServicioExportacionAsistencia.preparar_exportacion(
                operador=operador,
                filtro=filtro,
                alumnos=alumnos,
                asistencias=asistencias,
                usuarios_por_id=usuarios,
                fecha_generacion=self._ahora(),
                roles=roles,
            )
            filas = [fila.a_tupla() for fila in documento.filas]
            if filtro.formato == FormatoExportacion.CSV:
                contenido = exportar_csv_bytes(ENCABEZADOS_EXPORTACION, filas)
            elif filtro.formato == FormatoExportacion.XLSX:
                contenido = exportar_xlsx_bytes(ENCABEZADOS_EXPORTACION, filas)
            else:
                contenido = exportar_texto_boleta_o_pdf(
                    "Lista de Asistencia",
                    ENCABEZADOS_EXPORTACION,
                    filas,
                    metadatos={
                        "generado_por": operador.username,
                        "total_filas": str(documento.total_filas),
                    },
                )
            self._auditar(
                session,
                operador,
                TipoOperacionAuditoria.EXPORTAR_ASISTENCIA,
                "asistencia_exportacion",
                f"exp-{uuid.uuid4().hex[:12]}",
                detalle={
                    "formato": filtro.formato.value,
                    "total_filas": documento.total_filas,
                    "fecha_desde": filtro.fecha_desde.isoformat(),
                    "fecha_hasta": filtro.fecha_hasta.isoformat(),
                },
            )
            uow.commit()
        return ResultadoExportacionAsistencia(documento=documento, contenido=contenido)

    # ------------------------------------------------------------------
    # PBI-14: boletas de calificaciones
    # ------------------------------------------------------------------
    def emitir_boleta_individual(
        self, operador_id: int, alumno_id: int, periodo_id: int
    ) -> BoletaCalificaciones:
        """Emite la boleta de un alumno para un período (preliminar u oficial)."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            self._autorizar(operador, PermisoOperacion.EMITIR_BOLETAS, roles)
            boleta = self._emitir_boleta(session, operador, alumno_id, periodo_id)
            uow.commit()
        return boleta

    def emitir_boletas_salon(
        self,
        operador_id: int,
        *,
        anio_lectivo: int,
        nivel: str,
        grado: str,
        seccion: str,
        periodo_id: int,
    ) -> ResultadoEmisionBoleta:
        """Emite una boleta por cada alumno del salón indicado."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            self._autorizar(operador, PermisoOperacion.EMITIR_BOLETAS, roles)
            salon = session.scalars(
                select(SalonModel).filter_by(
                    anio_lectivo=anio_lectivo,
                    nivel=nivel,
                    grado=grado,
                    seccion=seccion,
                )
            ).first()
            if salon is None:
                raise ValueError("El salón indicado no existe.")
            alumnos = session.scalars(select(EstudianteModel).filter_by(salon_id=salon.id)).all()
            boletas = tuple(
                self._emitir_boleta(session, operador, alumno.id, periodo_id) for alumno in alumnos
            )
            uow.commit()
        return ResultadoEmisionBoleta(boletas=boletas)

    def exportar_boleta_texto(self, boleta: BoletaCalificaciones) -> bytes:
        """Renderiza una boleta como texto estructurado listo para imprimir."""
        filas = [[linea.curso_nombre, str(linea.nota), linea.literal] for linea in boleta.lineas]
        return exportar_texto_boleta_o_pdf(
            f"Boleta de Calificaciones - {boleta.etiqueta}",
            ["Curso", "Nota", "Literal"],
            filas,
            metadatos={
                "alumno_id": str(boleta.alumno_id),
                "periodo_id": str(boleta.periodo_id),
                "promedio_general": str(boleta.promedio_general),
                "codigo_verificacion": boleta.codigo_verificacion or "NO OFICIAL",
            },
        )

    def _emitir_boleta(
        self, session: Session, operador, alumno_id: int, periodo_id: int
    ) -> BoletaCalificaciones:
        alumno = self._estudiante(session, alumno_id)
        periodo = self._periodo(session, periodo_id)
        salon = session.get(SalonModel, alumno.salon_id) if alumno.salon_id else None
        if salon is None:
            raise ValueError("El alumno no tiene un salón asignado.")

        asignaciones = session.scalars(
            select(AsignacionDocenteModel).filter_by(
                salon_id=salon.id, anio_lectivo=salon.anio_lectivo, activa=True
            )
        ).all()
        lineas: list[LineaCursoBoleta] = []
        vistos: set[int] = set()
        for modelo in asignaciones:
            if modelo.curso_id in vistos:
                continue
            vistos.add(modelo.curso_id)
            curso = session.get(CursoModel, modelo.curso_id)
            if curso is None:
                continue
            try:
                promedio = self._promedio_periodo(session, alumno_id, modelo.curso_id, periodo.id)
            except Exception:
                if periodo.cerrado:
                    raise
                continue
            lineas.append(
                LineaCursoBoleta(
                    curso_id=curso.id,
                    curso_nombre=curso.nombre,
                    nota=promedio.nota_final,
                    literal=promedio.escala_literal.value,
                )
            )

        if periodo.cerrado and not lineas:
            from src.dominio.calificaciones import CalificacionException

            raise CalificacionException(
                "No se puede emitir una boleta oficial sin calificaciones registradas."
            )

        promedio_general = (
            (sum((linea.nota for linea in lineas), Decimal("0")) / Decimal(len(lineas))).quantize(
                Decimal("0.01")
            )
            if lineas
            else Decimal("0.00")
        )
        asistencias = [
            asistencia_model_a_dominio(m)
            for m in session.scalars(
                select(AsistenciaModel).filter(
                    AsistenciaModel.estudiante_id == alumno_id,
                    AsistenciaModel.fecha_escolar >= periodo.fecha_inicio,
                    AsistenciaModel.fecha_escolar <= periodo.fecha_fin,
                )
            ).all()
        ]
        resumen = _resumen_asistencia(asistencias)
        es_oficial = bool(periodo.cerrado)
        codigo = f"BOL-{uuid.uuid4().hex[:12].upper()}" if es_oficial else None
        boleta_id = f"bol-{uuid.uuid4().hex[:12]}"

        session.add(
            BoletaEmitidaModel(
                id=boleta_id,
                codigo_verificacion=codigo,
                estudiante_id=alumno_id,
                periodo_id=periodo.id,
                anio_lectivo=periodo.anio_lectivo or salon.anio_lectivo,
                es_oficial=es_oficial,
                promedio_general=promedio_general,
                resumen_asistencia_json=_resumen_asistencia_json(resumen),
                emitido_por=operador.id,
                emitido_en=_naive(self._ahora()),
            )
        )
        self._auditar(
            session,
            operador,
            TipoOperacionAuditoria.EMITIR_BOLETA,
            "boleta",
            boleta_id,
            detalle={
                "es_oficial": es_oficial,
                "codigo_verificacion": codigo,
                "periodo_id": periodo.id,
            },
            alumno_id=alumno_id,
        )
        return BoletaCalificaciones(
            id=boleta_id,
            alumno_id=alumno_id,
            periodo_id=periodo.id,
            anio_lectivo=periodo.anio_lectivo or salon.anio_lectivo,
            es_oficial=es_oficial,
            codigo_verificacion=codigo,
            promedio_general=promedio_general,
            lineas=tuple(lineas),
            resumen_asistencia=resumen,
            etiqueta="OFICIAL" if es_oficial else "BORRADOR / PRELIMINAR",
        )
