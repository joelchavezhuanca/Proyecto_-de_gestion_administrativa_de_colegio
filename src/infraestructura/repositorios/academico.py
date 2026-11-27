"""Repositorios de infraestructura para malla curricular, docentes y calificaciones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.dominio.calificaciones import ActividadEvaluable, Calificacion, RubroEvaluacion
from src.dominio.docentes import AsignacionDocente
from src.dominio.malla_curricular import Curso, NivelEducativo, Salon
from src.infraestructura.modelos import (
    ActividadEvaluableModel,
    AsignacionDocenteModel,
    BoletaEmitidaModel,
    CalificacionModel,
    CursoModel,
    EstudianteModel,
    RubroEvaluacionModel,
    SalonModel,
)

ZONA_LIMA = timezone(timedelta(hours=-5), name="America/Lima")


def _normalizar_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZONA_LIMA)
    return dt.astimezone(ZONA_LIMA)


@dataclass(frozen=True)
class BoletaEmitida:
    """Representación inmutable de boleta de calificaciones emitida (PBI-14)."""

    id: str
    estudiante_id: int
    periodo_id: int
    anio_lectivo: int
    es_oficial: bool
    promedio_general: Decimal
    resumen_asistencia_json: str
    emitido_por: int
    emitido_en: datetime
    codigo_verificacion: str | None = None


class RepositorioMalla:
    """Acceso a datos de salones y cursos por nivel, grado y año lectivo (PBI-09)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    # -- Salones --------------------------------------------------------
    @staticmethod
    def _salon_a_dominio(modelo: SalonModel) -> Salon:
        return Salon(
            id=modelo.id,
            anio_lectivo=modelo.anio_lectivo,
            nivel=NivelEducativo(modelo.nivel),
            grado=modelo.grado,
            seccion=modelo.seccion,
            capacidad_maxima=modelo.capacidad_maxima,
            activo=modelo.activo,
        )

    def guardar_salon(self, salon: Salon) -> Salon:
        modelo = self.sesion.get(SalonModel, salon.id)
        if modelo is None:
            modelo = SalonModel(
                id=salon.id if salon.id > 0 else None,
                anio_lectivo=salon.anio_lectivo,
                nivel=salon.nivel.value,
                grado=salon.grado,
                seccion=salon.seccion,
                capacidad_maxima=salon.capacidad_maxima,
                activo=salon.activo,
            )
            self.sesion.add(modelo)
        else:
            modelo.anio_lectivo = salon.anio_lectivo
            modelo.nivel = salon.nivel.value
            modelo.grado = salon.grado
            modelo.seccion = salon.seccion
            modelo.capacidad_maxima = salon.capacidad_maxima
            modelo.activo = salon.activo

        self.sesion.flush()
        return self._salon_a_dominio(modelo)

    def obtener_salon_por_id(self, salon_id: int) -> Salon | None:
        modelo = self.sesion.get(SalonModel, salon_id)
        return self._salon_a_dominio(modelo) if modelo else None

    def obtener_salon(
        self,
        anio_lectivo: int,
        nivel: NivelEducativo,
        grado: str,
        seccion: str,
    ) -> Salon | None:
        modelo = self.sesion.scalars(
            select(SalonModel).where(
                SalonModel.anio_lectivo == anio_lectivo,
                SalonModel.nivel == nivel.value,
                SalonModel.grado == grado.strip().lower(),
                SalonModel.seccion == seccion.strip().upper(),
            )
        ).first()
        return self._salon_a_dominio(modelo) if modelo else None

    def listar_salones(
        self,
        anio_lectivo: int | None = None,
        nivel: NivelEducativo | None = None,
        grado: str | None = None,
        solo_activos: bool = False,
    ) -> list[Salon]:
        stmt = select(SalonModel)
        if anio_lectivo is not None:
            stmt = stmt.where(SalonModel.anio_lectivo == anio_lectivo)
        if nivel is not None:
            stmt = stmt.where(SalonModel.nivel == nivel.value)
        if grado is not None:
            stmt = stmt.where(SalonModel.grado == grado.strip().lower())
        if solo_activos:
            stmt = stmt.where(SalonModel.activo.is_(True))

        modelos = self.sesion.scalars(
            stmt.order_by(
                SalonModel.anio_lectivo,
                SalonModel.nivel,
                SalonModel.grado,
                SalonModel.seccion,
            )
        ).all()
        return [self._salon_a_dominio(m) for m in modelos]

    # -- Cursos ---------------------------------------------------------
    @staticmethod
    def _curso_a_dominio(modelo: CursoModel) -> Curso:
        return Curso(
            id=modelo.id,
            anio_lectivo=modelo.anio_lectivo,
            nivel=NivelEducativo(modelo.nivel),
            grado=modelo.grado,
            codigo=modelo.codigo,
            nombre=modelo.nombre,
            area_curricular=modelo.area_curricular,
            horas_semanales=modelo.horas_semanales,
            activo=modelo.activo,
        )

    def guardar_curso(self, curso: Curso) -> Curso:
        modelo = self.sesion.get(CursoModel, curso.id)
        if modelo is None:
            modelo = CursoModel(
                id=curso.id if curso.id > 0 else None,
                anio_lectivo=curso.anio_lectivo,
                nivel=curso.nivel.value,
                grado=curso.grado,
                codigo=curso.codigo,
                nombre=curso.nombre,
                area_curricular=curso.area_curricular,
                horas_semanales=curso.horas_semanales,
                activo=curso.activo,
            )
            self.sesion.add(modelo)
        else:
            modelo.anio_lectivo = curso.anio_lectivo
            modelo.nivel = curso.nivel.value
            modelo.grado = curso.grado
            modelo.codigo = curso.codigo
            modelo.nombre = curso.nombre
            modelo.area_curricular = curso.area_curricular
            modelo.horas_semanales = curso.horas_semanales
            modelo.activo = curso.activo

        self.sesion.flush()
        return self._curso_a_dominio(modelo)

    def obtener_curso_por_id(self, curso_id: int) -> Curso | None:
        modelo = self.sesion.get(CursoModel, curso_id)
        return self._curso_a_dominio(modelo) if modelo else None

    def obtener_curso(
        self,
        anio_lectivo: int,
        nivel: NivelEducativo,
        grado: str,
        codigo: str,
    ) -> Curso | None:
        modelo = self.sesion.scalars(
            select(CursoModel).where(
                CursoModel.anio_lectivo == anio_lectivo,
                CursoModel.nivel == nivel.value,
                CursoModel.grado == grado.strip().lower(),
                CursoModel.codigo == codigo.strip(),
            )
        ).first()
        return self._curso_a_dominio(modelo) if modelo else None

    def listar_cursos(
        self,
        anio_lectivo: int | None = None,
        nivel: NivelEducativo | None = None,
        grado: str | None = None,
        solo_activos: bool = False,
    ) -> list[Curso]:
        stmt = select(CursoModel)
        if anio_lectivo is not None:
            stmt = stmt.where(CursoModel.anio_lectivo == anio_lectivo)
        if nivel is not None:
            stmt = stmt.where(CursoModel.nivel == nivel.value)
        if grado is not None:
            stmt = stmt.where(CursoModel.grado == grado.strip().lower())
        if solo_activos:
            stmt = stmt.where(CursoModel.activo.is_(True))

        modelos = self.sesion.scalars(
            stmt.order_by(
                CursoModel.anio_lectivo,
                CursoModel.nivel,
                CursoModel.grado,
                CursoModel.codigo,
            )
        ).all()
        return [self._curso_a_dominio(m) for m in modelos]


class RepositorioDocentes:
    """Acceso a datos de asignaciones docentes y aislamiento de ámbito (PBI-11)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    @staticmethod
    def _a_dominio(modelo: AsignacionDocenteModel) -> AsignacionDocente:
        return AsignacionDocente(
            id=modelo.id,
            usuario_docente_id=modelo.usuario_docente_id,
            curso_id=modelo.curso_id,
            salon_id=modelo.salon_id,
            anio_lectivo=modelo.anio_lectivo,
            activa=modelo.activa,
            asignado_por=modelo.asignado_por,
            creado_en=_normalizar_dt(modelo.creado_en),
            revocada_en=_normalizar_dt(modelo.revocada_en),
            motivo_revocacion=modelo.motivo_revocacion,
        )

    def guardar_asignacion(self, asignacion: AsignacionDocente) -> AsignacionDocente:
        modelo = self.sesion.get(AsignacionDocenteModel, asignacion.id)
        if modelo is None:
            modelo = AsignacionDocenteModel(
                id=asignacion.id,
                usuario_docente_id=asignacion.usuario_docente_id,
                curso_id=asignacion.curso_id,
                salon_id=asignacion.salon_id,
                anio_lectivo=asignacion.anio_lectivo,
                activa=asignacion.activa,
                asignado_por=asignacion.asignado_por,
                creado_en=asignacion.creado_en or datetime.now(ZONA_LIMA),
                revocada_en=asignacion.revocada_en,
                motivo_revocacion=asignacion.motivo_revocacion,
            )
            self.sesion.add(modelo)
        else:
            modelo.usuario_docente_id = asignacion.usuario_docente_id
            modelo.curso_id = asignacion.curso_id
            modelo.salon_id = asignacion.salon_id
            modelo.anio_lectivo = asignacion.anio_lectivo
            modelo.activa = asignacion.activa
            modelo.revocada_en = asignacion.revocada_en
            modelo.motivo_revocacion = asignacion.motivo_revocacion

        self.sesion.flush()
        return self._a_dominio(modelo)

    def obtener_asignacion_por_id(self, asignacion_id: str) -> AsignacionDocente | None:
        modelo = self.sesion.get(AsignacionDocenteModel, asignacion_id)
        return self._a_dominio(modelo) if modelo else None

    def obtener_asignacion_activa(
        self, curso_id: int, salon_id: int, anio_lectivo: int
    ) -> AsignacionDocente | None:
        modelo = self.sesion.scalars(
            select(AsignacionDocenteModel).where(
                AsignacionDocenteModel.curso_id == curso_id,
                AsignacionDocenteModel.salon_id == salon_id,
                AsignacionDocenteModel.anio_lectivo == anio_lectivo,
                AsignacionDocenteModel.activa.is_(True),
            )
        ).first()
        return self._a_dominio(modelo) if modelo else None

    def listar_asignaciones_docente(
        self,
        usuario_docente_id: int,
        anio_lectivo: int | None = None,
        solo_activas: bool = True,
    ) -> list[AsignacionDocente]:
        stmt = select(AsignacionDocenteModel).where(
            AsignacionDocenteModel.usuario_docente_id == usuario_docente_id
        )
        if anio_lectivo is not None:
            stmt = stmt.where(AsignacionDocenteModel.anio_lectivo == anio_lectivo)
        if solo_activas:
            stmt = stmt.where(AsignacionDocenteModel.activa.is_(True))

        modelos = self.sesion.scalars(stmt.order_by(AsignacionDocenteModel.id)).all()
        return [self._a_dominio(m) for m in modelos]

    def listar_todas(
        self,
        anio_lectivo: int | None = None,
        solo_activas: bool = True,
    ) -> list[AsignacionDocente]:
        stmt = select(AsignacionDocenteModel)
        if anio_lectivo is not None:
            stmt = stmt.where(AsignacionDocenteModel.anio_lectivo == anio_lectivo)
        if solo_activas:
            stmt = stmt.where(AsignacionDocenteModel.activa.is_(True))

        modelos = self.sesion.scalars(stmt.order_by(AsignacionDocenteModel.id)).all()
        return [self._a_dominio(m) for m in modelos]

    def revocar_asignacion(
        self, asignacion_id: str, motivo: str, revocada_en: datetime
    ) -> AsignacionDocente:
        modelo = self.sesion.get(AsignacionDocenteModel, asignacion_id)
        if modelo is None:
            raise ValueError(f"No existe la asignación con id '{asignacion_id}'.")

        modelo.activa = False
        modelo.motivo_revocacion = motivo
        modelo.revocada_en = revocada_en
        self.sesion.flush()
        return self._a_dominio(modelo)


class RepositorioCalificaciones:
    """Acceso a datos del libro de calificaciones de 3 niveles con precisión Decimal (PBI-10)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    # -- Rubros de Evaluación -------------------------------------------
    @staticmethod
    def _rubro_a_dominio(modelo: RubroEvaluacionModel) -> RubroEvaluacion:
        return RubroEvaluacion(
            id=modelo.id,
            asignacion_docente_id=modelo.asignacion_docente_id,
            periodo_id=modelo.periodo_id,
            nombre=modelo.nombre,
            peso_porcentaje=Decimal(str(modelo.peso_porcentaje)),
            activo=modelo.activo,
        )

    def guardar_rubro(self, rubro: RubroEvaluacion) -> RubroEvaluacion:
        modelo = self.sesion.get(RubroEvaluacionModel, rubro.id)
        if modelo is None:
            modelo = RubroEvaluacionModel(
                id=rubro.id,
                asignacion_docente_id=rubro.asignacion_docente_id,
                periodo_id=rubro.periodo_id,
                nombre=rubro.nombre,
                peso_porcentaje=rubro.peso_porcentaje,
                activo=rubro.activo,
            )
            self.sesion.add(modelo)
        else:
            modelo.nombre = rubro.nombre
            modelo.peso_porcentaje = rubro.peso_porcentaje
            modelo.activo = rubro.activo

        self.sesion.flush()
        return self._rubro_a_dominio(modelo)

    def obtener_rubro_por_id(self, rubro_id: str) -> RubroEvaluacion | None:
        modelo = self.sesion.get(RubroEvaluacionModel, rubro_id)
        return self._rubro_a_dominio(modelo) if modelo else None

    def listar_rubros_asignacion(
        self,
        asignacion_docente_id: str,
        periodo_id: int,
        solo_activos: bool = True,
    ) -> list[RubroEvaluacion]:
        stmt = select(RubroEvaluacionModel).where(
            RubroEvaluacionModel.asignacion_docente_id == asignacion_docente_id,
            RubroEvaluacionModel.periodo_id == periodo_id,
        )
        if solo_activos:
            stmt = stmt.where(RubroEvaluacionModel.activo.is_(True))

        modelos = self.sesion.scalars(stmt.order_by(RubroEvaluacionModel.id)).all()
        return [self._rubro_a_dominio(m) for m in modelos]

    # -- Actividades Evaluables -----------------------------------------
    @staticmethod
    def _actividad_a_dominio(modelo: ActividadEvaluableModel) -> ActividadEvaluable:
        return ActividadEvaluable(
            id=modelo.id,
            rubro_id=modelo.rubro_id,
            titulo=modelo.titulo,
            fecha=modelo.fecha,
            activo=modelo.activo,
        )

    def guardar_actividad(self, actividad: ActividadEvaluable) -> ActividadEvaluable:
        modelo = self.sesion.get(ActividadEvaluableModel, actividad.id)
        if modelo is None:
            modelo = ActividadEvaluableModel(
                id=actividad.id,
                rubro_id=actividad.rubro_id,
                titulo=actividad.titulo,
                fecha=actividad.fecha,
                activo=actividad.activo,
            )
            self.sesion.add(modelo)
        else:
            modelo.titulo = actividad.titulo
            modelo.fecha = actividad.fecha
            modelo.activo = actividad.activo

        self.sesion.flush()
        return self._actividad_a_dominio(modelo)

    def obtener_actividad_por_id(self, actividad_id: str) -> ActividadEvaluable | None:
        modelo = self.sesion.get(ActividadEvaluableModel, actividad_id)
        return self._actividad_a_dominio(modelo) if modelo else None

    def listar_actividades_rubro(
        self, rubro_id: str, solo_activos: bool = True
    ) -> list[ActividadEvaluable]:
        stmt = select(ActividadEvaluableModel).where(ActividadEvaluableModel.rubro_id == rubro_id)
        if solo_activos:
            stmt = stmt.where(ActividadEvaluableModel.activo.is_(True))

        modelos = self.sesion.scalars(stmt.order_by(ActividadEvaluableModel.fecha)).all()
        return [self._actividad_a_dominio(m) for m in modelos]

    # -- Calificaciones -------------------------------------------------
    @staticmethod
    def _calificacion_a_dominio(modelo: CalificacionModel) -> Calificacion:
        nota_ant = (
            Decimal(str(modelo.nota_anterior))
            if modelo.nota_anterior is not None
            else None
        )
        return Calificacion(
            id=modelo.id,
            actividad_id=modelo.actividad_id,
            alumno_id=modelo.estudiante_id,
            nota=Decimal(str(modelo.nota)),
            usuario_id=modelo.usuario_id,
            actualizado_en=_normalizar_dt(modelo.actualizado_en),  # type: ignore[arg-type]
            observacion=modelo.observacion,
            nota_anterior=nota_ant,
            motivo_modificacion=modelo.motivo_modificacion,
        )

    def _a_modelo_calificacion(self, cal: Calificacion) -> CalificacionModel:
        return CalificacionModel(
            id=cal.id,
            actividad_id=cal.actividad_id,
            estudiante_id=cal.alumno_id,
            nota=cal.nota,
            nota_anterior=cal.nota_anterior,
            motivo_modificacion=cal.motivo_modificacion,
            observacion=cal.observacion,
            usuario_id=cal.usuario_id,
            actualizado_en=cal.actualizado_en,
        )

    def guardar_calificacion(self, calificacion: Calificacion) -> Calificacion:
        modelo = self.sesion.get(CalificacionModel, calificacion.id)
        if modelo is None:
            # Buscar por par único (actividad_id, estudiante_id)
            modelo = self.sesion.scalars(
                select(CalificacionModel).where(
                    CalificacionModel.actividad_id == calificacion.actividad_id,
                    CalificacionModel.estudiante_id == calificacion.alumno_id,
                )
            ).first()

        if modelo is None:
            modelo = self._a_modelo_calificacion(calificacion)
            self.sesion.add(modelo)
        else:
            modelo.nota = calificacion.nota
            modelo.nota_anterior = calificacion.nota_anterior
            modelo.motivo_modificacion = calificacion.motivo_modificacion
            modelo.observacion = calificacion.observacion
            modelo.usuario_id = calificacion.usuario_id
            modelo.actualizado_en = calificacion.actualizado_en

        self.sesion.flush()
        return self._calificacion_a_dominio(modelo)

    def obtener_calificacion(self, actividad_id: str, alumno_id: int) -> Calificacion | None:
        modelo = self.sesion.scalars(
            select(CalificacionModel).where(
                CalificacionModel.actividad_id == actividad_id,
                CalificacionModel.estudiante_id == alumno_id,
            )
        ).first()
        return self._calificacion_a_dominio(modelo) if modelo else None

    def listar_calificaciones_actividad(self, actividad_id: str) -> list[Calificacion]:
        modelos = self.sesion.scalars(
            select(CalificacionModel)
            .where(CalificacionModel.actividad_id == actividad_id)
            .order_by(CalificacionModel.estudiante_id)
        ).all()
        return [self._calificacion_a_dominio(m) for m in modelos]

    def listar_calificaciones_alumno_en_rubro(
        self, rubro_id: str, alumno_id: int
    ) -> list[Calificacion]:
        stmt = (
            select(CalificacionModel)
            .join(
                ActividadEvaluableModel,
                ActividadEvaluableModel.id == CalificacionModel.actividad_id,
            )
            .where(
                ActividadEvaluableModel.rubro_id == rubro_id,
                CalificacionModel.estudiante_id == alumno_id,
            )
            .order_by(ActividadEvaluableModel.fecha)
        )
        modelos = self.sesion.scalars(stmt).all()
        return [self._calificacion_a_dominio(m) for m in modelos]

    def listar_calificaciones_alumno_en_asignacion(
        self, asignacion_docente_id: str, periodo_id: int, alumno_id: int
    ) -> list[Calificacion]:
        stmt = (
            select(CalificacionModel)
            .join(
                ActividadEvaluableModel,
                ActividadEvaluableModel.id == CalificacionModel.actividad_id,
            )
            .join(
                RubroEvaluacionModel,
                RubroEvaluacionModel.id == ActividadEvaluableModel.rubro_id,
            )
            .where(
                RubroEvaluacionModel.asignacion_docente_id == asignacion_docente_id,
                RubroEvaluacionModel.periodo_id == periodo_id,
                CalificacionModel.estudiante_id == alumno_id,
            )
            .order_by(ActividadEvaluableModel.fecha)
        )
        modelos = self.sesion.scalars(stmt).all()
        return [self._calificacion_a_dominio(m) for m in modelos]


class RepositorioBoletas:
    """Acceso a datos de boletas de calificaciones emitidas (PBI-14)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    @staticmethod
    def _a_dominio(modelo: BoletaEmitidaModel) -> BoletaEmitida:
        return BoletaEmitida(
            id=modelo.id,
            estudiante_id=modelo.estudiante_id,
            periodo_id=modelo.periodo_id,
            anio_lectivo=modelo.anio_lectivo,
            es_oficial=modelo.es_oficial,
            promedio_general=Decimal(str(modelo.promedio_general)),
            resumen_asistencia_json=modelo.resumen_asistencia_json,
            emitido_por=modelo.emitido_por,
            emitido_en=_normalizar_dt(modelo.emitido_en),  # type: ignore[arg-type]
            codigo_verificacion=modelo.codigo_verificacion,
        )

    def guardar(self, boleta: BoletaEmitida) -> BoletaEmitida:
        modelo = self.sesion.get(BoletaEmitidaModel, boleta.id)
        if modelo is None:
            modelo = BoletaEmitidaModel(
                id=boleta.id,
                codigo_verificacion=boleta.codigo_verificacion,
                estudiante_id=boleta.estudiante_id,
                periodo_id=boleta.periodo_id,
                anio_lectivo=boleta.anio_lectivo,
                es_oficial=boleta.es_oficial,
                promedio_general=boleta.promedio_general,
                resumen_asistencia_json=boleta.resumen_asistencia_json,
                emitido_por=boleta.emitido_por,
                emitido_en=boleta.emitido_en,
            )
            self.sesion.add(modelo)
        else:
            modelo.codigo_verificacion = boleta.codigo_verificacion
            modelo.es_oficial = boleta.es_oficial
            modelo.promedio_general = boleta.promedio_general
            modelo.resumen_asistencia_json = boleta.resumen_asistencia_json

        self.sesion.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, boleta_id: str) -> BoletaEmitida | None:
        modelo = self.sesion.get(BoletaEmitidaModel, boleta_id)
        return self._a_dominio(modelo) if modelo else None

    def obtener_por_codigo_verificacion(self, codigo_verificacion: str) -> BoletaEmitida | None:
        modelo = self.sesion.scalars(
            select(BoletaEmitidaModel).where(
                BoletaEmitidaModel.codigo_verificacion == codigo_verificacion.strip()
            )
        ).first()
        return self._a_dominio(modelo) if modelo else None

    def obtener_por_estudiante_y_periodo(
        self, estudiante_id: int, periodo_id: int
    ) -> BoletaEmitida | None:
        modelo = self.sesion.scalars(
            select(BoletaEmitidaModel).where(
                BoletaEmitidaModel.estudiante_id == estudiante_id,
                BoletaEmitidaModel.periodo_id == periodo_id,
            )
        ).first()
        return self._a_dominio(modelo) if modelo else None

    def listar_por_estudiante(
        self, estudiante_id: int, anio_lectivo: int | None = None
    ) -> list[BoletaEmitida]:
        stmt = select(BoletaEmitidaModel).where(BoletaEmitidaModel.estudiante_id == estudiante_id)
        if anio_lectivo is not None:
            stmt = stmt.where(BoletaEmitidaModel.anio_lectivo == anio_lectivo)
        modelos = self.sesion.scalars(stmt.order_by(BoletaEmitidaModel.periodo_id)).all()
        return [self._a_dominio(m) for m in modelos]

    def listar_por_salon_y_periodo(
        self, salon_id: int, periodo_id: int
    ) -> list[BoletaEmitida]:
        stmt = (
            select(BoletaEmitidaModel)
            .join(
                EstudianteModel,
                EstudianteModel.id == BoletaEmitidaModel.estudiante_id,
            )
            .where(
                EstudianteModel.salon_id == salon_id,
                BoletaEmitidaModel.periodo_id == periodo_id,
            )
            .order_by(EstudianteModel.apellidos)
        )
        modelos = self.sesion.scalars(stmt).all()
        return [self._a_dominio(m) for m in modelos]
