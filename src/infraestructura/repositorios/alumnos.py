"""Repositorios de infraestructura para la gestión de alumnos, matrícula y carnets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.dominio.carnets import CarnetEscolar, EstadoCarnet, MotivoAnulacionCarnet
from src.dominio.estados_academicos import EstadoAcademico, HistorialEstadoAlumno
from src.dominio.matricula import Apoderado, FichaMatricula
from src.infraestructura.modelos import (
    ApoderadoModel,
    CarnetModel,
    EstudianteApoderadoModel,
    EstudianteEstadoHistorialModel,
    EstudianteModel,
)

ZONA_LIMA = timezone(timedelta(hours=-5), name="America/Lima")


def _normalizar_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZONA_LIMA)
    return dt.astimezone(ZONA_LIMA)


class RepositorioMatricula:
    """Acceso a datos de fichas de matrícula digital y apoderados vinculados."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    def _cargar_apoderados(self, estudiante_id: int) -> tuple[Apoderado, ...]:
        query = (
            select(ApoderadoModel, EstudianteApoderadoModel.es_principal)
            .join(
                EstudianteApoderadoModel,
                EstudianteApoderadoModel.apoderado_id == ApoderadoModel.id,
            )
            .where(EstudianteApoderadoModel.estudiante_id == estudiante_id)
            .order_by(ApoderadoModel.id)
        )
        registros = self.sesion.execute(query).all()
        resultado: list[Apoderado] = []
        for ap_model, es_principal in registros:
            resultado.append(
                Apoderado(
                    id=ap_model.id,
                    nombres=ap_model.nombres,
                    apellidos=ap_model.apellidos,
                    documento=ap_model.documento,
                    parentesco=ap_model.parentesco,
                    telefono_whatsapp=ap_model.telefono_whatsapp,
                    es_principal=es_principal,
                    activo=ap_model.activo,
                )
            )
        return tuple(resultado)

    def _a_dominio(self, modelo: EstudianteModel) -> FichaMatricula:
        apoderados = self._cargar_apoderados(modelo.id)
        anio_lectivo = (
            modelo.salon.anio_lectivo
            if modelo.salon
            else (modelo.creado_en.year if modelo.creado_en else 2026)
        )
        return FichaMatricula(
            id=f"mat-{modelo.codigo}",
            alumno_id=modelo.id,
            codigo_estudiante=modelo.codigo,
            dni=modelo.dni,
            nombres=modelo.nombres,
            apellidos=modelo.apellidos,
            fecha_nacimiento=modelo.fecha_nacimiento,  # type: ignore[arg-type]
            anio_lectivo=anio_lectivo,
            salon_id=modelo.salon_id or 0,
            nivel=modelo.nivel,
            grado=modelo.grado,
            seccion=modelo.seccion,
            apoderados=apoderados,
            estado=EstadoAcademico(modelo.estado),
            creado_en=_normalizar_dt(modelo.creado_en),
        )

    def guardar(self, ficha: FichaMatricula) -> FichaMatricula:
        """Inserta o actualiza una ficha de matrícula digital con sus apoderados."""
        est = self.sesion.get(EstudianteModel, ficha.alumno_id)
        if est is None:
            est = EstudianteModel(
                id=ficha.alumno_id,
                codigo=ficha.codigo_estudiante,
                dni=ficha.dni,
                nombres=ficha.nombres,
                apellidos=ficha.apellidos,
                fecha_nacimiento=ficha.fecha_nacimiento,
                salon_id=ficha.salon_id,
                nivel=ficha.nivel,
                grado=ficha.grado,
                seccion=ficha.seccion,
                estado=ficha.estado.value,
                creado_en=ficha.creado_en or datetime.now(ZONA_LIMA),
            )
            self.sesion.add(est)
        else:
            est.codigo = ficha.codigo_estudiante
            est.dni = ficha.dni
            est.nombres = ficha.nombres
            est.apellidos = ficha.apellidos
            est.fecha_nacimiento = ficha.fecha_nacimiento
            est.salon_id = ficha.salon_id
            est.nivel = ficha.nivel
            est.grado = ficha.grado
            est.seccion = ficha.seccion
            est.estado = ficha.estado.value

        self.sesion.flush()

        # Sincronizar apoderados
        apoderados_ids_actuales: set[int] = set()
        for ap in ficha.apoderados:
            ap_model = self.sesion.get(ApoderadoModel, ap.id)
            if ap_model is None:
                ap_model = self.sesion.scalars(
                    select(ApoderadoModel).where(ApoderadoModel.documento == ap.documento)
                ).first()

            if ap_model is None:
                ap_model = ApoderadoModel(
                    id=ap.id if ap.id > 0 else None,
                    nombres=ap.nombres,
                    apellidos=ap.apellidos,
                    documento=ap.documento,
                    parentesco=ap.parentesco,
                    telefono_whatsapp=ap.telefono_whatsapp,
                    activo=ap.activo,
                )
                self.sesion.add(ap_model)
                self.sesion.flush()
            else:
                ap_model.nombres = ap.nombres
                ap_model.apellidos = ap.apellidos
                ap_model.documento = ap.documento
                ap_model.parentesco = ap.parentesco
                ap_model.telefono_whatsapp = ap.telefono_whatsapp
                ap_model.activo = ap.activo
                self.sesion.flush()

            apoderados_ids_actuales.add(ap_model.id)

            # Relación N:M
            rel = self.sesion.get(EstudianteApoderadoModel, (est.id, ap_model.id))
            if rel is None:
                rel = EstudianteApoderadoModel(
                    estudiante_id=est.id,
                    apoderado_id=ap_model.id,
                    es_principal=ap.es_principal,
                )
                self.sesion.add(rel)
            else:
                rel.es_principal = ap.es_principal

        # Eliminar vínculos de apoderados que ya no figuren
        todos_rel = self.sesion.scalars(
            select(EstudianteApoderadoModel).where(EstudianteApoderadoModel.estudiante_id == est.id)
        ).all()
        for r in todos_rel:
            if r.apoderado_id not in apoderados_ids_actuales:
                self.sesion.delete(r)

        self.sesion.flush()
        return self._a_dominio(est)

    def obtener_por_id(self, ficha_id: str) -> FichaMatricula | None:
        codigo = ficha_id.removeprefix("mat-")
        est = self.sesion.scalars(
            select(EstudianteModel).where(
                (EstudianteModel.codigo == codigo) | (EstudianteModel.codigo == ficha_id)
            )
        ).first()
        return self._a_dominio(est) if est else None

    def obtener_por_alumno_id(self, alumno_id: int) -> FichaMatricula | None:
        est = self.sesion.get(EstudianteModel, alumno_id)
        return self._a_dominio(est) if est else None

    def obtener_por_dni(self, dni: str) -> FichaMatricula | None:
        est = self.sesion.scalars(
            select(EstudianteModel).where(EstudianteModel.dni == dni.strip())
        ).first()
        return self._a_dominio(est) if est else None

    def obtener_por_codigo(self, codigo: str) -> FichaMatricula | None:
        est = self.sesion.scalars(
            select(EstudianteModel).where(EstudianteModel.codigo == codigo.strip())
        ).first()
        return self._a_dominio(est) if est else None

    def listar_por_salon(
        self, salon_id: int, anio_lectivo: int | None = None
    ) -> list[FichaMatricula]:
        stmt = select(EstudianteModel).where(EstudianteModel.salon_id == salon_id)
        if anio_lectivo is not None:
            stmt = stmt.join(EstudianteModel.salon).where(
                EstudianteModel.salon.has(anio_lectivo=anio_lectivo)
            )
        modelos = self.sesion.scalars(stmt.order_by(EstudianteModel.apellidos)).all()
        return [self._a_dominio(m) for m in modelos]

    def contar_matriculados(self, salon_id: int, anio_lectivo: int) -> int:
        stmt = (
            select(func.count(EstudianteModel.id))
            .join(EstudianteModel.salon)
            .where(
                EstudianteModel.salon_id == salon_id,
                EstudianteModel.salon.has(anio_lectivo=anio_lectivo),
                EstudianteModel.estado == EstadoAcademico.ACTIVO.value,
            )
        )
        return int(self.sesion.scalar(stmt) or 0)

    def listar_todas(self) -> list[FichaMatricula]:
        modelos = self.sesion.scalars(
            select(EstudianteModel).order_by(EstudianteModel.apellidos)
        ).all()
        return [self._a_dominio(m) for m in modelos]


class RepositorioCarnets:
    """Acceso a datos y ciclo de vida de carnets escolares QR."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    @staticmethod
    def _a_dominio(modelo: CarnetModel) -> CarnetEscolar:
        motivo = MotivoAnulacionCarnet(modelo.motivo_anulacion) if modelo.motivo_anulacion else None
        return CarnetEscolar(
            id=modelo.id,
            alumno_id=modelo.estudiante_id,
            codigo_qr=modelo.codigo_qr,
            estado=EstadoCarnet(modelo.estado),
            emitido_por=modelo.emitido_por,
            emitido_en=_normalizar_dt(modelo.emitido_en),  # type: ignore[arg-type]
            anulado_en=_normalizar_dt(modelo.anulado_en),
            motivo_anulacion=motivo,
            detalle_anulacion=modelo.detalle_anulacion,
        )

    def guardar(self, carnet: CarnetEscolar) -> CarnetEscolar:
        modelo = self.sesion.get(CarnetModel, carnet.id)
        if modelo is None:
            modelo = CarnetModel(
                id=carnet.id,
                estudiante_id=carnet.alumno_id,
                codigo_qr=carnet.codigo_qr,
                estado=carnet.estado.value,
                motivo_anulacion=carnet.motivo_anulacion.value if carnet.motivo_anulacion else None,
                detalle_anulacion=carnet.detalle_anulacion,
                emitido_por=carnet.emitido_por,
                emitido_en=carnet.emitido_en,
                anulado_en=carnet.anulado_en,
            )
            self.sesion.add(modelo)
        else:
            modelo.codigo_qr = carnet.codigo_qr
            modelo.estado = carnet.estado.value
            modelo.motivo_anulacion = (
                carnet.motivo_anulacion.value if carnet.motivo_anulacion else None
            )
            modelo.detalle_anulacion = carnet.detalle_anulacion
            modelo.anulado_en = carnet.anulado_en

        if carnet.estado == EstadoCarnet.ACTIVO:
            estudiante = self.sesion.get(EstudianteModel, carnet.alumno_id)
            if estudiante is not None:
                estudiante.carnet_codigo = carnet.codigo_qr

        self.sesion.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, carnet_id: str) -> CarnetEscolar | None:
        modelo = self.sesion.get(CarnetModel, carnet_id)
        return self._a_dominio(modelo) if modelo else None

    def obtener_por_codigo_qr(self, codigo_qr: str) -> CarnetEscolar | None:
        modelo = self.sesion.scalars(
            select(CarnetModel).where(CarnetModel.codigo_qr == codigo_qr.strip())
        ).first()
        return self._a_dominio(modelo) if modelo else None

    def obtener_activo_por_alumno(self, alumno_id: int) -> CarnetEscolar | None:
        modelo = self.sesion.scalars(
            select(CarnetModel).where(
                CarnetModel.estudiante_id == alumno_id,
                CarnetModel.estado == EstadoCarnet.ACTIVO.value,
            )
        ).first()
        return self._a_dominio(modelo) if modelo else None

    def listar_por_alumno(self, alumno_id: int) -> list[CarnetEscolar]:
        modelos = self.sesion.scalars(
            select(CarnetModel)
            .where(CarnetModel.estudiante_id == alumno_id)
            .order_by(CarnetModel.emitido_en.desc())
        ).all()
        return [self._a_dominio(m) for m in modelos]

    def anular(
        self,
        carnet_id: str,
        motivo: MotivoAnulacionCarnet,
        detalle: str | None,
        anulado_en: datetime,
    ) -> CarnetEscolar:
        modelo = self.sesion.get(CarnetModel, carnet_id)
        if modelo is None:
            raise ValueError(f"No existe el carnet con id '{carnet_id}'.")

        modelo.estado = EstadoCarnet.ANULADO.value
        modelo.motivo_anulacion = motivo.value
        modelo.detalle_anulacion = detalle
        modelo.anulado_en = anulado_en

        estudiante = self.sesion.get(EstudianteModel, modelo.estudiante_id)
        if estudiante is not None and estudiante.carnet_codigo == modelo.codigo_qr:
            estudiante.carnet_codigo = None

        self.sesion.flush()
        return self._a_dominio(modelo)


class RepositorioEstadosAcademicos:
    """Acceso y trazabilidad de los estados académicos del estudiante."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    @staticmethod
    def _a_dominio(modelo: EstudianteEstadoHistorialModel) -> HistorialEstadoAlumno:
        return HistorialEstadoAlumno(
            id=modelo.id,
            alumno_id=modelo.estudiante_id,
            estado_anterior=EstadoAcademico(modelo.estado_anterior),
            estado_nuevo=EstadoAcademico(modelo.estado_nuevo),
            motivo=modelo.motivo,
            usuario_id=modelo.usuario_id,
            rol_usuario=modelo.rol_usuario,
            fecha_hora=_normalizar_dt(modelo.creado_en),  # type: ignore[arg-type]
            fecha_inicio_suspension=modelo.fecha_inicio,
            fecha_fin_suspension=modelo.fecha_fin,
        )

    def guardar_historial(self, historial: HistorialEstadoAlumno) -> HistorialEstadoAlumno:
        modelo = EstudianteEstadoHistorialModel(
            id=historial.id,
            estudiante_id=historial.alumno_id,
            estado_anterior=historial.estado_anterior.value,
            estado_nuevo=historial.estado_nuevo.value,
            motivo=historial.motivo,
            fecha_inicio=historial.fecha_inicio_suspension,
            fecha_fin=historial.fecha_fin_suspension,
            usuario_id=historial.usuario_id,
            rol_usuario=historial.rol_usuario,
            creado_en=historial.fecha_hora,
        )
        self.sesion.add(modelo)
        self.sesion.flush()
        return self._a_dominio(modelo)

    def actualizar_estado_alumno(self, alumno_id: int, nuevo_estado: EstadoAcademico) -> None:
        estudiante = self.sesion.get(EstudianteModel, alumno_id)
        if estudiante is not None:
            estudiante.estado = nuevo_estado.value
            self.sesion.flush()

    def obtener_estado_alumno(self, alumno_id: int) -> EstadoAcademico | None:
        estudiante = self.sesion.get(EstudianteModel, alumno_id)
        if estudiante is None:
            return None
        return EstadoAcademico(estudiante.estado)

    def listar_historial_alumno(self, alumno_id: int) -> list[HistorialEstadoAlumno]:
        modelos = self.sesion.scalars(
            select(EstudianteEstadoHistorialModel)
            .where(EstudianteEstadoHistorialModel.estudiante_id == alumno_id)
            .order_by(EstudianteEstadoHistorialModel.creado_en.asc())
        ).all()
        return [self._a_dominio(m) for m in modelos]
