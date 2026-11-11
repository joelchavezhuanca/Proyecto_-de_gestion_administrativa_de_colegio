"""Repositorios de infraestructura: traducen ORM ↔ objetos de dominio.

La capa de presentación y los casos de uso nunca manipulan modelos ORM ni SQL.
"""

import json
from collections.abc import Iterable
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.dominio.aforo import EventoCierreDiario
from src.dominio.asistencia import (
    Alumno,
    EstadoAlumno,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    buscar_alumnos_activos,
)
from src.dominio.asistencia import (
    RolUsuario as RolAsistencia,
)
from src.dominio.justificaciones import (
    CategoriaJustificacion,
    EstadoJustificacion,
    Justificacion,
    PeriodoAcademico,
)
from src.dominio.usuarios import EstadoUsuario, RolUsuario, Usuario
from src.infraestructura.modelos import (
    AsistenciaModel,
    AuditoriaModel,
    CierreDiarioModel,
    ConfiguracionModel,
    EstudianteModel,
    JustificacionModel,
    PeriodoAcademicoModel,
    UsuarioModel,
)


class RepositorioColegio:
    """Acceso a datos de la demostración, siempre devolviendo objetos de dominio."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    # ------------------------------------------------------------------
    # Usuarios
    # ------------------------------------------------------------------
    @staticmethod
    def _usuario_dominio(modelo: UsuarioModel) -> Usuario:
        return Usuario(
            id=modelo.id,
            username=modelo.username,
            password_hash=modelo.password_hash,
            salt=modelo.salt or "",
            nombre_completo=modelo.nombre_completo or modelo.username,
            rol=RolUsuario(modelo.rol),
            estado=EstadoUsuario.ACTIVO if modelo.activo else EstadoUsuario.INACTIVO,
            creado_en=modelo.creado_en,
        )

    def listar_usuarios(self) -> list[Usuario]:
        modelos = self.sesion.scalars(select(UsuarioModel).order_by(UsuarioModel.username)).all()
        return [self._usuario_dominio(m) for m in modelos]

    def obtener_usuario(self, usuario_id: int) -> Usuario | None:
        modelo = self.sesion.get(UsuarioModel, usuario_id)
        return self._usuario_dominio(modelo) if modelo else None

    def obtener_usuario_por_username(self, username: str) -> Usuario | None:
        modelo = self.sesion.scalars(
            select(UsuarioModel).where(UsuarioModel.username == username.strip().lower())
        ).first()
        return self._usuario_dominio(modelo) if modelo else None

    def insertar_usuario(self, usuario: Usuario) -> Usuario:
        modelo = UsuarioModel(
            id=usuario.id,
            username=usuario.username,
            password_hash=usuario.password_hash,
            salt=usuario.salt,
            nombre_completo=usuario.nombre_completo,
            rol=usuario.rol.value,
            activo=usuario.estado == EstadoUsuario.ACTIVO,
            creado_en=usuario.creado_en or datetime.now(),
        )
        self.sesion.add(modelo)
        self.sesion.flush()
        return self._usuario_dominio(modelo)

    def actualizar_usuario(self, usuario: Usuario) -> Usuario:
        modelo = self.sesion.get(UsuarioModel, usuario.id)
        if modelo is None:
            return self.insertar_usuario(usuario)

        modelo.username = usuario.username
        modelo.password_hash = usuario.password_hash
        modelo.salt = usuario.salt
        modelo.nombre_completo = usuario.nombre_completo
        modelo.rol = usuario.rol.value
        modelo.activo = usuario.estado == EstadoUsuario.ACTIVO
        self.sesion.flush()
        return self._usuario_dominio(modelo)

    # ------------------------------------------------------------------
    # Estudiantes
    # ------------------------------------------------------------------
    @staticmethod
    def _alumno_dominio(modelo: EstudianteModel) -> Alumno:
        return Alumno(
            id=modelo.id,
            codigo=modelo.codigo,
            dni=modelo.dni,
            nombres=modelo.nombres,
            apellidos=modelo.apellidos,
            nivel=modelo.nivel,
            grado=modelo.grado,
            seccion=modelo.seccion,
            carnet_codigo=modelo.carnet_codigo,
            estado=EstadoAlumno(modelo.estado),
        )

    def listar_alumnos(self) -> list[Alumno]:
        modelos = self.sesion.scalars(select(EstudianteModel).order_by(EstudianteModel.id)).all()
        return [self._alumno_dominio(m) for m in modelos]

    def obtener_alumno(self, alumno_id: int) -> Alumno | None:
        modelo = self.sesion.get(EstudianteModel, alumno_id)
        return self._alumno_dominio(modelo) if modelo else None

    def obtener_alumno_por_dni(self, dni: str) -> Alumno | None:
        modelo = self.sesion.scalars(
            select(EstudianteModel).where(EstudianteModel.dni == dni)
        ).first()
        return self._alumno_dominio(modelo) if modelo else None

    def obtener_alumno_por_carnet(self, carnet: str) -> Alumno | None:
        modelo = self.sesion.scalars(
            select(EstudianteModel).where(EstudianteModel.carnet_codigo == carnet)
        ).first()
        return self._alumno_dominio(modelo) if modelo else None

    def buscar_alumnos(self, criterio: str) -> list[Alumno]:
        return buscar_alumnos_activos(criterio, self.listar_alumnos())

    def opciones_academicas(self) -> dict[str, list[str]]:
        alumnos = self.listar_alumnos()
        return {
            "niveles": sorted({a.nivel for a in alumnos}),
            "grados": sorted({a.grado for a in alumnos}),
            "secciones": sorted({a.seccion for a in alumnos}),
        }

    # ------------------------------------------------------------------
    # Asistencias
    # ------------------------------------------------------------------
    @staticmethod
    def _asistencia_dominio(modelo: AsistenciaModel) -> RegistroAsistencia:
        rol = RolAsistencia.ADMIN_STAFF
        if modelo.usuario is not None:
            try:
                rol = RolAsistencia(modelo.usuario.rol)
            except ValueError:
                rol = RolAsistencia.ADMIN_STAFF

        return RegistroAsistencia(
            id=modelo.id,
            alumno_id=modelo.estudiante_id,
            fecha_escolar=modelo.fecha_escolar,
            hora_efectiva=modelo.hora_efectiva,
            estado=EstadoAsistencia(modelo.estado),
            minutos_tardanza=modelo.minutos_tardanza,
            metodo=MetodoRegistro(modelo.metodo),
            usuario_id=modelo.usuario_id,
            rol_usuario=rol,
            estado_anterior=(
                EstadoAsistencia(modelo.estado_anterior) if modelo.estado_anterior else None
            ),
            motivo_correccion=modelo.motivo_correccion,
            auditoria_id=modelo.auditoria_id,
        )

    def listar_asistencias(
        self, fecha_escolar: date, estudiante_ids: Iterable[int] | None = None
    ) -> list[RegistroAsistencia]:
        consulta = (
            select(AsistenciaModel)
            .options(joinedload(AsistenciaModel.usuario))
            .where(AsistenciaModel.fecha_escolar == fecha_escolar)
            .order_by(AsistenciaModel.hora_efectiva)
        )
        modelos = self.sesion.scalars(consulta).unique().all()
        ids = set(estudiante_ids) if estudiante_ids is not None else None
        return [
            self._asistencia_dominio(m)
            for m in modelos
            if ids is None or m.estudiante_id in ids
        ]

    def obtener_asistencia(
        self, alumno_id: int, fecha_escolar: date
    ) -> RegistroAsistencia | None:
        modelo = self.sesion.scalars(
            select(AsistenciaModel)
            .options(joinedload(AsistenciaModel.usuario))
            .where(
                AsistenciaModel.estudiante_id == alumno_id,
                AsistenciaModel.fecha_escolar == fecha_escolar,
            )
        ).first()
        return self._asistencia_dominio(modelo) if modelo else None

    def obtener_asistencia_por_id(self, asistencia_id: str) -> RegistroAsistencia | None:
        modelo = self.sesion.scalars(
            select(AsistenciaModel)
            .options(joinedload(AsistenciaModel.usuario))
            .where(AsistenciaModel.id == asistencia_id)
        ).first()
        return self._asistencia_dominio(modelo) if modelo else None

    def guardar_asistencia(self, registro: RegistroAsistencia) -> None:
        modelo = self.sesion.get(AsistenciaModel, registro.id)
        if modelo is None:
            modelo = AsistenciaModel(id=registro.id)
            self.sesion.add(modelo)

        modelo.estudiante_id = registro.alumno_id
        modelo.usuario_id = registro.usuario_id
        modelo.fecha_escolar = registro.fecha_escolar
        modelo.hora_efectiva = registro.hora_efectiva
        modelo.estado = registro.estado.value
        modelo.minutos_tardanza = registro.minutos_tardanza
        modelo.metodo = registro.metodo.value
        modelo.estado_anterior = (
            registro.estado_anterior.value if registro.estado_anterior else None
        )
        modelo.motivo_correccion = registro.motivo_correccion
        modelo.auditoria_id = registro.auditoria_id
        self.sesion.flush()

    def contar_asistencias(self, fecha_escolar: date) -> int:
        return len(self.listar_asistencias(fecha_escolar))

    # ------------------------------------------------------------------
    # Justificaciones
    # ------------------------------------------------------------------
    def _justificacion_dominio(self, modelo: JustificacionModel) -> Justificacion:
        usuario = self.sesion.get(UsuarioModel, modelo.usuario_id)
        rol = RolAsistencia.ADMIN_STAFF
        if usuario is not None:
            try:
                rol = RolAsistencia(usuario.rol)
            except ValueError:
                rol = RolAsistencia.ADMIN_STAFF

        return Justificacion(
            id=modelo.codigo or f"just-{modelo.id}",
            asistencia_id=modelo.asistencia_id,
            alumno_id=modelo.estudiante_id,
            fecha_solicitud=modelo.fecha_solicitud or modelo.creado_en.date(),
            categoria=CategoriaJustificacion(modelo.categoria),
            motivo=modelo.motivo,
            estado=EstadoJustificacion(modelo.estado),
            usuario_id=modelo.usuario_id,
            rol_usuario=rol,
            documento_adjunto=modelo.documento_adjunto,
            fecha_resolucion=modelo.fecha_resolucion,
        )

    def listar_justificaciones(self, fecha: date | None = None) -> list[Justificacion]:
        consulta = select(JustificacionModel).order_by(JustificacionModel.creado_en.desc())
        if fecha is not None:
            consulta = consulta.where(JustificacionModel.fecha_solicitud == fecha)
        modelos = self.sesion.scalars(consulta).all()
        return [self._justificacion_dominio(m) for m in modelos]

    def obtener_justificacion(self, codigo: str) -> Justificacion | None:
        modelo = self.sesion.scalars(
            select(JustificacionModel).where(JustificacionModel.codigo == codigo)
        ).first()
        return self._justificacion_dominio(modelo) if modelo else None

    def existe_justificacion_activa(self, asistencia_id: str) -> bool:
        modelo = self.sesion.scalars(
            select(JustificacionModel).where(
                JustificacionModel.asistencia_id == asistencia_id,
                JustificacionModel.estado.in_(["APROBADA", "PENDIENTE"]),
            )
        ).first()
        return modelo is not None

    def insertar_justificacion(self, justificacion: Justificacion) -> None:
        modelo = JustificacionModel(
            codigo=justificacion.id,
            asistencia_id=justificacion.asistencia_id,
            estudiante_id=justificacion.alumno_id,
            usuario_id=justificacion.usuario_id,
            motivo=justificacion.motivo,
            categoria=justificacion.categoria.value,
            estado=justificacion.estado.value,
            fecha_solicitud=justificacion.fecha_solicitud,
            fecha_resolucion=justificacion.fecha_resolucion,
            documento_adjunto=justificacion.documento_adjunto,
        )
        self.sesion.add(modelo)
        self.sesion.flush()

    def marcar_justificacion_anulada(self, codigo: str) -> None:
        modelo = self.sesion.scalars(
            select(JustificacionModel).where(JustificacionModel.codigo == codigo)
        ).first()
        if modelo is not None:
            modelo.estado = EstadoJustificacion.RECHAZADA.value
            self.sesion.flush()

    # ------------------------------------------------------------------
    # Períodos académicos
    # ------------------------------------------------------------------
    @staticmethod
    def _periodo_dominio(modelo: PeriodoAcademicoModel) -> PeriodoAcademico:
        return PeriodoAcademico(
            id=modelo.id,
            nombre=modelo.nombre,
            fecha_inicio=modelo.fecha_inicio,
            fecha_fin=modelo.fecha_fin,
            cerrado=modelo.cerrado,
        )

    def periodo_por_fecha(self, fecha: date) -> PeriodoAcademico | None:
        modelo = self.sesion.scalars(
            select(PeriodoAcademicoModel)
            .where(
                PeriodoAcademicoModel.fecha_inicio <= fecha,
                PeriodoAcademicoModel.fecha_fin >= fecha,
            )
            .order_by(PeriodoAcademicoModel.fecha_inicio.desc())
        ).first()
        return self._periodo_dominio(modelo) if modelo else None

    def listar_periodos(self) -> list[PeriodoAcademico]:
        modelos = self.sesion.scalars(
            select(PeriodoAcademicoModel).order_by(PeriodoAcademicoModel.fecha_inicio.desc())
        ).all()
        return [self._periodo_dominio(m) for m in modelos]

    # ------------------------------------------------------------------
    # Configuración y cierres
    # ------------------------------------------------------------------
    def obtener_config(self, clave: str, defecto: str) -> str:
        modelo = self.sesion.get(ConfiguracionModel, clave)
        return modelo.valor if modelo else defecto

    def obtener_hora_cierre(self) -> time:
        valor = self.obtener_config("hora_cierre", "08:30")
        try:
            return time.fromisoformat(valor)
        except ValueError:
            return time(8, 30)

    def guardar_config(self, clave: str, valor: str) -> None:
        modelo = self.sesion.get(ConfiguracionModel, clave)
        if modelo is None:
            modelo = ConfiguracionModel(clave=clave, valor=valor)
            self.sesion.add(modelo)
        else:
            modelo.valor = valor
        self.sesion.flush()

    def existe_cierre(self, fecha_escolar: date) -> bool:
        return (
            self.sesion.scalars(
                select(CierreDiarioModel).where(
                    CierreDiarioModel.fecha_escolar == fecha_escolar
                )
            ).first()
            is not None
        )

    def registrar_cierre(self, evento: EventoCierreDiario, ejecutado_por: int) -> None:
        modelo = CierreDiarioModel(
            evento_id=evento.id,
            fecha_escolar=evento.fecha_escolar,
            hora_cierre=evento.hora_cierre,
            total_ausentes_marcados=evento.total_ausentes_marcados,
            alumnos_ids=json.dumps(evento.alumnos_ids_afectados),
            ejecutado_por=ejecutado_por,
        )
        self.sesion.add(modelo)
        self.sesion.flush()

    # ------------------------------------------------------------------
    # Auditoría
    # ------------------------------------------------------------------
    def registrar_auditoria(
        self,
        *,
        evento_id: str,
        fecha_hora: datetime,
        usuario_id: int,
        username: str,
        rol: str,
        operacion: str,
        entidad: str,
        entidad_id: str,
        detalle: dict[str, object] | None = None,
    ) -> None:
        modelo = AuditoriaModel(
            id=evento_id,
            fecha_hora=fecha_hora,
            usuario_id=usuario_id,
            username=username,
            rol=rol,
            operacion=operacion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=json.dumps(detalle or {}, ensure_ascii=False, default=str),
        )
        self.sesion.add(modelo)
        self.sesion.flush()
