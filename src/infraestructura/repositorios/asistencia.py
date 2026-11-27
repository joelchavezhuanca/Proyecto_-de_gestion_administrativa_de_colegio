"""Repositorios ORM SQLAlchemy 2.0 para asistencia, aforo, justificaciones y calendario."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.dominio.aforo import CalendarioEscolar, EventoCierreDiario
from src.dominio.asistencia import (
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
)
from src.dominio.justificaciones import (
    ZONA_HORARIA_LIMA,
    AdjuntoJustificacion,
    CategoriaJustificacion,
    EstadoJustificacion,
    FiltroJustificaciones,
    Justificacion,
    PeriodoAcademico,
    TipoPeriodo,
)
from src.infraestructura.modelos import (
    AsistenciaHistorialModel,
    AsistenciaModel,
    CalendarioEscolarModel,
    CierreDiarioModel,
    ConfiguracionSistemaModel,
    JustificacionAdjuntoModel,
    JustificacionModel,
    PeriodoAcademicoModel,
    hora_actual_utc,
)


def _codigo_rol_str(rol: RolUsuario | str) -> str:
    return rol.value if isinstance(rol, RolUsuario) else str(rol).strip().upper()


def _rol_a_dominio(codigo: str) -> RolUsuario | str:
    normalizado = codigo.strip().upper()
    try:
        return RolUsuario(normalizado)
    except ValueError:
        return normalizado


def _normalizar_lima(fecha_hora: datetime) -> datetime:
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


class RepositorioAsistencia:
    """Persistencia de registros diarios de asistencia e historial de correcciones (PBI-01)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: AsistenciaModel) -> RegistroAsistencia:
        estado_anterior = (
            EstadoAsistencia(modelo.estado_anterior) if modelo.estado_anterior else None
        )
        return RegistroAsistencia(
            id=modelo.id,
            alumno_id=modelo.estudiante_id,
            fecha_escolar=modelo.fecha_escolar,
            hora_efectiva=modelo.hora_efectiva,
            estado=EstadoAsistencia(modelo.estado),
            minutos_tardanza=modelo.minutos_tardanza,
            metodo=MetodoRegistro(modelo.metodo),
            usuario_id=modelo.usuario_id or 0,
            rol_usuario=_rol_a_dominio(modelo.rol_usuario),
            estado_anterior=estado_anterior,
            motivo_correccion=modelo.motivo_correccion,
            auditoria_id=modelo.auditoria_id,
            nivel=modelo.nivel_snapshot,
            grado=modelo.grado_snapshot,
            seccion=modelo.seccion_snapshot,
        )

    def guardar(self, asistencia: RegistroAsistencia) -> RegistroAsistencia:
        """Inserta o actualiza un registro diario de asistencia usando flush()."""
        usuario_fk = asistencia.usuario_id if asistencia.usuario_id > 0 else None
        rol_str = _codigo_rol_str(asistencia.rol_usuario)
        estado_anterior = (
            asistencia.estado_anterior.value if asistencia.estado_anterior else None
        )

        modelo = self._session.get(AsistenciaModel, asistencia.id)
        if modelo is None:
            modelo = AsistenciaModel(
                id=asistencia.id,
                estudiante_id=asistencia.alumno_id,
                usuario_id=usuario_fk,
                fecha_escolar=asistencia.fecha_escolar,
                hora_efectiva=asistencia.hora_efectiva,
                estado=asistencia.estado.value,
                minutos_tardanza=asistencia.minutos_tardanza,
                metodo=asistencia.metodo.value,
                rol_usuario=rol_str,
                estado_anterior=estado_anterior,
                motivo_correccion=asistencia.motivo_correccion,
                nivel_snapshot=asistencia.nivel,
                grado_snapshot=asistencia.grado,
                seccion_snapshot=asistencia.seccion,
                auditoria_id=asistencia.auditoria_id,
            )
            self._session.add(modelo)
        else:
            modelo.estudiante_id = asistencia.alumno_id
            modelo.usuario_id = usuario_fk
            modelo.fecha_escolar = asistencia.fecha_escolar
            modelo.hora_efectiva = asistencia.hora_efectiva
            modelo.estado = asistencia.estado.value
            modelo.minutos_tardanza = asistencia.minutos_tardanza
            modelo.metodo = asistencia.metodo.value
            modelo.rol_usuario = rol_str
            modelo.estado_anterior = estado_anterior
            modelo.motivo_correccion = asistencia.motivo_correccion
            modelo.nivel_snapshot = asistencia.nivel
            modelo.grado_snapshot = asistencia.grado
            modelo.seccion_snapshot = asistencia.seccion
            modelo.auditoria_id = asistencia.auditoria_id

        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, asistencia_id: str) -> RegistroAsistencia | None:
        modelo = self._session.get(AsistenciaModel, asistencia_id)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_por_alumno_y_fecha(
        self, alumno_id: int, fecha_escolar: date
    ) -> RegistroAsistencia | None:
        stmt = select(AsistenciaModel).where(
            AsistenciaModel.estudiante_id == alumno_id,
            AsistenciaModel.fecha_escolar == fecha_escolar,
        )
        modelo = self._session.scalar(stmt)
        return None if modelo is None else self._a_dominio(modelo)

    def listar_por_fecha(self, fecha_escolar: date) -> list[RegistroAsistencia]:
        stmt = (
            select(AsistenciaModel)
            .where(AsistenciaModel.fecha_escolar == fecha_escolar)
            .order_by(AsistenciaModel.hora_efectiva, AsistenciaModel.id)
        )
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def listar_por_alumno(
        self,
        alumno_id: int,
        *,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[RegistroAsistencia]:
        stmt = select(AsistenciaModel).where(AsistenciaModel.estudiante_id == alumno_id)
        if fecha_desde is not None:
            stmt = stmt.where(AsistenciaModel.fecha_escolar >= fecha_desde)
        if fecha_hasta is not None:
            stmt = stmt.where(AsistenciaModel.fecha_escolar <= fecha_hasta)
        stmt = stmt.order_by(AsistenciaModel.fecha_escolar, AsistenciaModel.id)
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def listar_por_rango(
        self, fecha_desde: date, fecha_hasta: date
    ) -> list[RegistroAsistencia]:
        stmt = (
            select(AsistenciaModel)
            .where(
                AsistenciaModel.fecha_escolar >= fecha_desde,
                AsistenciaModel.fecha_escolar <= fecha_hasta,
            )
            .order_by(AsistenciaModel.fecha_escolar, AsistenciaModel.id)
        )
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def registrar_historial(
        self,
        asistencia: RegistroAsistencia,
        *,
        fecha_hora: datetime | None = None,
    ) -> int:
        """Registra una entrada de historial para cambios/correcciones de asistencia."""
        usuario_fk = asistencia.usuario_id if asistencia.usuario_id > 0 else None
        estado_anterior = (
            asistencia.estado_anterior.value if asistencia.estado_anterior else None
        )
        marca = (
            _normalizar_lima(fecha_hora)
            if fecha_hora is not None
            else datetime.now(ZONA_HORARIA_LIMA)
        )
        entrada = AsistenciaHistorialModel(
            asistencia_id=asistencia.id,
            usuario_id=usuario_fk,
            rol_usuario=_codigo_rol_str(asistencia.rol_usuario),
            estado_anterior=estado_anterior,
            estado_nuevo=asistencia.estado.value,
            motivo=asistencia.motivo_correccion,
            metodo=asistencia.metodo.value,
            auditoria_id=asistencia.auditoria_id,
            fecha_hora=marca,
        )
        self._session.add(entrada)
        self._session.flush()
        return entrada.id

    def listar_historial(self, asistencia_id: str) -> list[dict[str, object]]:
        stmt = (
            select(AsistenciaHistorialModel)
            .where(AsistenciaHistorialModel.asistencia_id == asistencia_id)
            .order_by(AsistenciaHistorialModel.fecha_hora, AsistenciaHistorialModel.id)
        )
        return [
            {
                "id": m.id,
                "asistencia_id": m.asistencia_id,
                "usuario_id": m.usuario_id or 0,
                "rol_usuario": m.rol_usuario,
                "estado_anterior": m.estado_anterior,
                "estado_nuevo": m.estado_nuevo,
                "motivo": m.motivo,
                "metodo": m.metodo,
                "auditoria_id": m.auditoria_id,
                "fecha_hora": _normalizar_lima(m.fecha_hora),
            }
            for m in self._session.scalars(stmt).all()
        ]

    def marcar_notificacion_ausencia_enviada(self, asistencia_id: str) -> bool:
        modelo = self._session.get(AsistenciaModel, asistencia_id)
        if modelo is None:
            return False
        modelo.notificacion_ausencia_enviada = True
        self._session.flush()
        return True

    def listar_alumnos_notificados_ausencia(self, fecha_escolar: date) -> frozenset[int]:
        stmt = select(AsistenciaModel.estudiante_id).where(
            AsistenciaModel.fecha_escolar == fecha_escolar,
            AsistenciaModel.notificacion_ausencia_enviada.is_(True),
        )
        return frozenset(self._session.scalars(stmt).all())


class RepositorioAforo:
    """Persistencia de cierres diarios y parámetros globales del sistema (PBI-03)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: CierreDiarioModel) -> EventoCierreDiario:
        return EventoCierreDiario(
            id=modelo.evento_id,
            fecha_escolar=modelo.fecha_escolar,
            hora_cierre=modelo.hora_cierre,
            total_ausentes_marcados=modelo.total_ausentes_marcados,
            alumnos_ids_afectados=[],
        )

    def registrar_cierre(
        self,
        evento: EventoCierreDiario,
        *,
        actor_ejecutante: str,
        usuario_id: int | None = None,
    ) -> EventoCierreDiario:
        usuario_fk = usuario_id if usuario_id and usuario_id > 0 else None
        modelo = CierreDiarioModel(
            evento_id=evento.id,
            fecha_escolar=evento.fecha_escolar,
            hora_cierre=evento.hora_cierre,
            total_ausentes_marcados=evento.total_ausentes_marcados,
            actor_ejecutante=actor_ejecutante.strip().upper(),
            usuario_id=usuario_fk,
        )
        self._session.add(modelo)
        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_cierre_por_fecha(self, fecha_escolar: date) -> EventoCierreDiario | None:
        modelo = self._session.scalar(
            select(CierreDiarioModel).where(CierreDiarioModel.fecha_escolar == fecha_escolar)
        )
        return None if modelo is None else self._a_dominio(modelo)

    def listar_fechas_cerradas(self) -> frozenset[date]:
        return frozenset(self._session.scalars(select(CierreDiarioModel.fecha_escolar)).all())

    def guardar_configuracion(
        self,
        clave: str,
        valor: str,
        *,
        actualizado_por: int | None = None,
    ) -> None:
        clave_norm = clave.strip()
        modelo = self._session.get(ConfiguracionSistemaModel, clave_norm)
        if modelo is None:
            self._session.add(
                ConfiguracionSistemaModel(
                    clave=clave_norm,
                    valor=valor,
                    actualizado_por=actualizado_por,
                )
            )
        else:
            modelo.valor = valor
            modelo.actualizado_por = actualizado_por
            modelo.actualizado_en = hora_actual_utc()
        self._session.flush()

    def obtener_configuracion(
        self, clave: str, defecto: str | None = None
    ) -> str | None:
        modelo = self._session.get(ConfiguracionSistemaModel, clave.strip())
        return defecto if modelo is None else modelo.valor


class RepositorioJustificaciones:
    """Persistencia de justificaciones y metadatos de adjuntos privados (PBI-04)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: JustificacionModel) -> Justificacion:
        adjuntos = tuple(
            AdjuntoJustificacion(nombre=adj.nombre_archivo, tamano_bytes=adj.tamano_bytes)
            for adj in modelo.adjuntos
        )
        fecha_resolucion = (
            _normalizar_lima(modelo.fecha_resolucion)
            if modelo.fecha_resolucion is not None
            else None
        )
        fecha_solicitud = modelo.fecha_solicitud or modelo.creado_en.date()
        return Justificacion(
            id=modelo.id,
            asistencia_id=modelo.asistencia_id,
            alumno_id=modelo.estudiante_id,
            fecha_solicitud=fecha_solicitud,
            categoria=CategoriaJustificacion(modelo.categoria),
            motivo=modelo.motivo,
            estado=EstadoJustificacion(modelo.estado),
            usuario_id=modelo.usuario_id,
            rol_usuario=_rol_a_dominio(modelo.rol_usuario),
            documento_adjunto=modelo.documento_adjunto,
            fecha_resolucion=fecha_resolucion,
            adjuntos=adjuntos,
            minutos_tardanza_original=modelo.minutos_tardanza_original,
            nivel=modelo.nivel,
            grado=modelo.grado,
            seccion=modelo.seccion,
        )

    def guardar(
        self,
        justificacion: Justificacion,
        *,
        periodo_id: int | None = None,
        rutas_adjuntos: Mapping[str, str] | None = None,
    ) -> Justificacion:
        rutas = dict(rutas_adjuntos or {})
        fecha_resolucion = (
            _normalizar_lima(justificacion.fecha_resolucion)
            if justificacion.fecha_resolucion is not None
            else None
        )

        stmt = (
            select(JustificacionModel)
            .options(selectinload(JustificacionModel.adjuntos))
            .where(JustificacionModel.id == justificacion.id)
        )
        modelo = self._session.scalar(stmt)
        rutas_previas: dict[str, str] = {}
        if modelo is None:
            modelo = JustificacionModel(
                id=justificacion.id,
                asistencia_id=justificacion.asistencia_id,
                estudiante_id=justificacion.alumno_id,
                periodo_id=periodo_id,
                usuario_id=justificacion.usuario_id,
                rol_usuario=_codigo_rol_str(justificacion.rol_usuario),
                fecha_solicitud=justificacion.fecha_solicitud,
                categoria=justificacion.categoria.value,
                motivo=justificacion.motivo,
                estado=justificacion.estado.value,
                minutos_tardanza_original=justificacion.minutos_tardanza_original,
                documento_adjunto=justificacion.documento_adjunto,
                nivel=justificacion.nivel,
                grado=justificacion.grado,
                seccion=justificacion.seccion,
                fecha_resolucion=fecha_resolucion,
            )
            self._session.add(modelo)
        else:
            rutas_previas = {
                adj.nombre_archivo: adj.ruta_almacenamiento for adj in modelo.adjuntos
            }
            if periodo_id is not None:
                modelo.periodo_id = periodo_id
            modelo.rol_usuario = _codigo_rol_str(justificacion.rol_usuario)
            modelo.fecha_solicitud = justificacion.fecha_solicitud
            modelo.categoria = justificacion.categoria.value
            modelo.motivo = justificacion.motivo
            modelo.estado = justificacion.estado.value
            modelo.minutos_tardanza_original = justificacion.minutos_tardanza_original
            modelo.documento_adjunto = justificacion.documento_adjunto
            modelo.nivel = justificacion.nivel
            modelo.grado = justificacion.grado
            modelo.seccion = justificacion.seccion
            modelo.fecha_resolucion = fecha_resolucion
            modelo.adjuntos.clear()
            self._session.flush()

        for adj in justificacion.adjuntos:
            ruta = rutas.get(adj.nombre) or rutas_previas.get(adj.nombre) or adj.nombre
            modelo.adjuntos.append(
                JustificacionAdjuntoModel(
                    nombre_archivo=adj.nombre,
                    extension=adj.extension,
                    tamano_bytes=adj.tamano_bytes,
                    ruta_almacenamiento=ruta,
                )
            )

        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, justificacion_id: str) -> Justificacion | None:
        stmt = (
            select(JustificacionModel)
            .options(selectinload(JustificacionModel.adjuntos))
            .where(JustificacionModel.id == justificacion_id)
        )
        modelo = self._session.scalar(stmt)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_por_asistencia(self, asistencia_id: str) -> list[Justificacion]:
        stmt = (
            select(JustificacionModel)
            .options(selectinload(JustificacionModel.adjuntos))
            .where(JustificacionModel.asistencia_id == asistencia_id)
            .order_by(JustificacionModel.creado_en, JustificacionModel.id)
        )
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def listar(self, filtro: FiltroJustificaciones | None = None) -> list[Justificacion]:
        stmt = (
            select(JustificacionModel)
            .options(selectinload(JustificacionModel.adjuntos))
            .order_by(JustificacionModel.fecha_solicitud, JustificacionModel.id)
        )
        if filtro is not None:
            if filtro.nivel is not None:
                stmt = stmt.where(
                    func.lower(JustificacionModel.nivel) == filtro.nivel.strip().lower()
                )
            if filtro.grado is not None:
                stmt = stmt.where(
                    func.lower(JustificacionModel.grado) == filtro.grado.strip().lower()
                )
            if filtro.seccion is not None:
                stmt = stmt.where(
                    func.lower(JustificacionModel.seccion) == filtro.seccion.strip().lower()
                )
            if filtro.alumno_id is not None:
                stmt = stmt.where(JustificacionModel.estudiante_id == filtro.alumno_id)
            if filtro.categoria is not None:
                stmt = stmt.where(JustificacionModel.categoria == filtro.categoria.value)
            if filtro.estado is not None:
                stmt = stmt.where(JustificacionModel.estado == filtro.estado.value)
            if filtro.fecha_desde is not None:
                stmt = stmt.where(JustificacionModel.fecha_solicitud >= filtro.fecha_desde)
            if filtro.fecha_hasta is not None:
                stmt = stmt.where(JustificacionModel.fecha_solicitud <= filtro.fecha_hasta)
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]


class RepositorioPeriodos:
    """Persistencia de períodos académicos flexibles con cierre y fecha límite de notas."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: PeriodoAcademicoModel) -> PeriodoAcademico:
        return PeriodoAcademico(
            id=modelo.id,
            nombre=modelo.nombre,
            fecha_inicio=modelo.fecha_inicio,
            fecha_fin=modelo.fecha_fin,
            cerrado=modelo.cerrado,
            anio_lectivo=modelo.anio_lectivo,
            tipo_periodo=TipoPeriodo(modelo.tipo_periodo),
            orden=modelo.orden,
            fecha_limite_notas=modelo.fecha_limite_notas,
        )

    def guardar(self, periodo: PeriodoAcademico) -> PeriodoAcademico:
        modelo = self._session.get(PeriodoAcademicoModel, periodo.id) if periodo.id > 0 else None
        if modelo is None:
            modelo = PeriodoAcademicoModel(
                anio_lectivo=periodo.anio_lectivo,
                tipo_periodo=periodo.tipo_periodo.value,
                orden=periodo.orden,
                nombre=periodo.nombre,
                fecha_inicio=periodo.fecha_inicio,
                fecha_fin=periodo.fecha_fin,
                fecha_limite_notas=periodo.fecha_limite_notas,
                cerrado=periodo.cerrado,
            )
            if periodo.id > 0:
                modelo.id = periodo.id
            self._session.add(modelo)
        else:
            modelo.anio_lectivo = periodo.anio_lectivo
            modelo.tipo_periodo = periodo.tipo_periodo.value
            modelo.orden = periodo.orden
            modelo.nombre = periodo.nombre
            modelo.fecha_inicio = periodo.fecha_inicio
            modelo.fecha_fin = periodo.fecha_fin
            modelo.fecha_limite_notas = periodo.fecha_limite_notas
            modelo.cerrado = periodo.cerrado

        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, periodo_id: int) -> PeriodoAcademico | None:
        modelo = self._session.get(PeriodoAcademicoModel, periodo_id)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_por_nombre(self, nombre: str) -> PeriodoAcademico | None:
        stmt = select(PeriodoAcademicoModel).where(
            func.lower(PeriodoAcademicoModel.nombre) == nombre.strip().lower()
        )
        modelo = self._session.scalar(stmt)
        return None if modelo is None else self._a_dominio(modelo)

    def listar(
        self,
        *,
        anio_lectivo: int | None = None,
        solo_abiertos: bool = False,
    ) -> list[PeriodoAcademico]:
        stmt = select(PeriodoAcademicoModel).order_by(
            PeriodoAcademicoModel.anio_lectivo,
            PeriodoAcademicoModel.orden,
            PeriodoAcademicoModel.id,
        )
        if anio_lectivo is not None:
            stmt = stmt.where(PeriodoAcademicoModel.anio_lectivo == anio_lectivo)
        if solo_abiertos:
            stmt = stmt.where(PeriodoAcademicoModel.cerrado.is_(False))
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def eliminar(self, periodo_id: int) -> bool:
        modelo = self._session.get(PeriodoAcademicoModel, periodo_id)
        if modelo is None:
            return False
        self._session.delete(modelo)
        self._session.flush()
        return True


class RepositorioCalendario:
    """Persistencia del calendario escolar institucional (días no lectivos y excepciones)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def guardar_fecha(
        self,
        fecha: date,
        *,
        es_lectivo: bool,
        es_excepcion: bool = False,
        descripcion: str = "",
    ) -> None:
        modelo = self._session.get(CalendarioEscolarModel, fecha)
        if modelo is None:
            self._session.add(
                CalendarioEscolarModel(
                    fecha=fecha,
                    es_lectivo=es_lectivo,
                    es_excepcion=es_excepcion,
                    descripcion=descripcion.strip(),
                )
            )
        else:
            modelo.es_lectivo = es_lectivo
            modelo.es_excepcion = es_excepcion
            modelo.descripcion = descripcion.strip()
        self._session.flush()

    def eliminar_fecha(self, fecha: date) -> bool:
        modelo = self._session.get(CalendarioEscolarModel, fecha)
        if modelo is None:
            return False
        self._session.delete(modelo)
        self._session.flush()
        return True

    def obtener_calendario(
        self, *, fines_de_semana_no_lectivos: bool = True
    ) -> CalendarioEscolar:
        filas = self._session.scalars(select(CalendarioEscolarModel)).all()
        no_lectivos = frozenset(
            f.fecha for f in filas if not f.es_lectivo and not f.es_excepcion
        )
        excepciones = frozenset(f.fecha for f in filas if f.es_lectivo and f.es_excepcion)
        return CalendarioEscolar(
            dias_no_lectivos=no_lectivos,
            excepciones_lectivas=excepciones,
            fines_de_semana_no_lectivos=fines_de_semana_no_lectivos,
        )

    def listar_fechas(self) -> list[dict[str, object]]:
        filas = self._session.scalars(
            select(CalendarioEscolarModel).order_by(CalendarioEscolarModel.fecha)
        ).all()
        return [
            {
                "fecha": f.fecha,
                "es_lectivo": f.es_lectivo,
                "es_excepcion": f.es_excepcion,
                "descripcion": f.descripcion,
            }
            for f in filas
        ]
