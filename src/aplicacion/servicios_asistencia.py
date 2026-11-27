"""Servicios de aplicación de Asistencia (PBI-01, 03, 04, 07, 16, 17).

Casos de uso transaccionales sobre SQLAlchemy ``Session`` que reutilizan la
lógica pura de dominio y aplican las reglas críticas de la capa de aplicación:

Reglas críticas verificadas
---------------------------
1. **Auditoría atómica (PBI-16):** registro de asistencia + evento de auditoría
   inmutable en *una sola* transacción. Si falla la auditoría, ``rollback()``
   total y **no queda asistencia huérfana** en base de datos.
2. **Aislamiento de efectos externos (PBI-17 / PBI-07):** el **registro unificado
   confirma primero**; WhatsApp y la evaluación de pagos se despachan *después*
   del ``commit``, de forma **asíncrona y contenida**. Si WhatsApp falla o pagos
   falla, la asistencia **sigue confirmada** y la notificación queda ``FALLIDO``.
3. **Registro unificado < 200 ms:** la ruta transaccional sólo persiste
   asistencia + auditoría + ``commit``; los efectos externos no bloquean.

PBI-01 RN-06: la hora oficial proviene del servidor (America/Lima), nunca del
cliente; el reloj es inyectable para pruebas deterministas.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.aplicacion.servicios_seguridad import (
    FabricaSesion,
    RelojServidor,
    _auditoria_a_model,
    _eventos_existentes,
    hora_actual_lima,
    registrar_auditoria_pbi16,
    rol_codigo,
    rol_model_a_dominio,
    usuario_model_a_operador,
)
from src.aplicacion.uow import SqlAlchemyUnitOfWork
from src.dominio.aforo import (
    ACTOR_SYSTEM_CRON,
    CalendarioEscolar,
    EventoCierreDiario,
    MetricasAforo,
    ServicioAforo,
)
from src.dominio.asistencia import (
    Alumno,
    CarnetInvalidoException,
    EstadoAlumno,
    EstadoAsistencia,
    EventoAsistenciaConfirmada,
    MetodoRegistro,
    RegistroAsistencia,
    ResultadoRegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
    buscar_alumnos_activos,
    registrar_asistencia_unificada,
    validar_formato_dni,
)
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    RegistroAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.carnets import ServicioCarnets
from src.dominio.estados_academicos import EstadoAcademico, ServicioEstadosAcademicos
from src.dominio.justificaciones import (
    AdjuntoJustificacion,
    CategoriaJustificacion,
    EstadoJustificacion,
    FiltroJustificaciones,
    Justificacion,
    PeriodoAcademico,
    ResultadoOperacionJustificacion,
    ServicioJustificaciones,
    ServicioPeriodosAcademicos,
    TipoPeriodo,
)
from src.dominio.notificaciones import (
    ContactoApoderado,
    EstadoNotificacion,
    NotificacionWhatsApp,
    PuertoNotificadorWhatsApp,
    ServicioNotificacionesWhatsApp,
    TipoNotificacion,
)
from src.dominio.pagos import (
    AlertaSilenciosaPago,
    EstadoObligacion,
    ObligacionPago,
    ServicioPagos,
)
from src.dominio.usuarios import Rol
from src.infraestructura.modelos import (
    AlertaPagoSilenciosaModel,
    ApoderadoModel,
    AsistenciaHistorialModel,
    AsistenciaModel,
    CalendarioEscolarModel,
    CierreDiarioModel,
    ConfiguracionSistemaModel,
    EstudianteApoderadoModel,
    EstudianteModel,
    JustificacionAdjuntoModel,
    JustificacionModel,
    NotificacionWhatsappModel,
    ObligacionPagoModel,
    PeriodoAcademicoModel,
    RolModel,
    UsuarioModel,
)
from src.infraestructura.whatsapp import NotificadorSimulado

__all__ = [
    "PuertoPagos",
    "PagosSqlAlchemy",
    "ResultadoRegistroAsistenciaAplicacion",
    "ServicioAsistencia",
    "alumno_model_a_dominio",
    "asistencia_model_a_dominio",
    "hora_actual_lima",
    "periodo_model_a_dominio",
]

# Umbral de rendimiento del registro unificado (PBI-01 RN-07).
LIMITE_REGISTRO_MS = 200
CLAVE_HORA_CIERRE = "hora_cierre_oficial"
CLAVE_HORA_NOTIFICACION_AUSENCIAS = "hora_notificacion_ausencias"


# ---------------------------------------------------------------------------
# Puertos (Protocols finos — nota de coordinación con repositorios núcleo/académico)
# ---------------------------------------------------------------------------


class PuertoPagos(Protocol):
    """Puerto de salida hacia PBI-07 (pagos/alerta silenciosa)."""

    def evaluar_alerta_silenciosa(
        self,
        evento: EventoAsistenciaConfirmada,
        *,
        session_factory: FabricaSesion,
    ) -> AlertaSilenciosaPago | None: ...


# ---------------------------------------------------------------------------
# Conversiones ORM -> dominio
# ---------------------------------------------------------------------------


def _rol_usuario(rol: str) -> RolUsuario | str:
    try:
        return RolUsuario(rol)
    except ValueError:
        return rol


def estado_academico(valor: str) -> EstadoAcademico:
    try:
        return EstadoAcademico(valor)
    except ValueError:
        return EstadoAcademico.RETIRADO


def alumno_model_a_dominio(modelo: EstudianteModel) -> Alumno:
    """Convierte ``EstudianteModel`` a ``Alumno`` evaluando habilitación (PBI-08)."""
    ea = estado_academico(modelo.estado)
    habilitado = ServicioEstadosAcademicos.puede_registrar_asistencia(ea, date.today())
    estado = EstadoAlumno.ACTIVO if habilitado else EstadoAlumno.INACTIVO
    return Alumno(
        id=modelo.id,
        codigo=modelo.codigo or "",
        dni=modelo.dni or "",
        nombres=modelo.nombres or "",
        apellidos=modelo.apellidos or "",
        nivel=modelo.nivel or "",
        grado=modelo.grado or "",
        seccion=modelo.seccion or "",
        carnet_codigo=modelo.carnet_codigo or "",
        estado=estado,
    )


def asistencia_model_a_dominio(modelo: AsistenciaModel) -> RegistroAsistencia:
    return RegistroAsistencia(
        id=modelo.id,
        alumno_id=modelo.estudiante_id,
        fecha_escolar=modelo.fecha_escolar,
        hora_efectiva=modelo.hora_efectiva,
        estado=EstadoAsistencia(modelo.estado),
        minutos_tardanza=modelo.minutos_tardanza,
        metodo=MetodoRegistro(modelo.metodo),
        usuario_id=modelo.usuario_id or 0,
        rol_usuario=_rol_usuario(modelo.rol_usuario or ""),
        estado_anterior=(
            EstadoAsistencia(modelo.estado_anterior) if modelo.estado_anterior else None
        ),
        motivo_correccion=modelo.motivo_correccion,
        auditoria_id=modelo.auditoria_id,
        nivel=modelo.nivel_snapshot,
        grado=modelo.grado_snapshot,
        seccion=modelo.seccion_snapshot,
    )


def periodo_model_a_dominio(modelo: PeriodoAcademicoModel) -> PeriodoAcademico:
    try:
        tipo = TipoPeriodo(modelo.tipo_periodo)
    except ValueError:
        tipo = TipoPeriodo.BIMESTRE
    return PeriodoAcademico(
        id=modelo.id,
        nombre=modelo.nombre,
        fecha_inicio=modelo.fecha_inicio,
        fecha_fin=modelo.fecha_fin,
        cerrado=bool(modelo.cerrado),
        anio_lectivo=modelo.anio_lectivo,
        tipo_periodo=tipo,
        orden=modelo.orden,
        fecha_limite_notas=modelo.fecha_limite_notas,
    )


def _obligacion_model_a_dominio(modelo: ObligacionPagoModel) -> ObligacionPago:
    return ObligacionPago(
        id=modelo.id,
        alumno_id=modelo.estudiante_id,
        concepto=modelo.concepto,
        monto=modelo.monto,
        fecha_vencimiento=modelo.fecha_vencimiento,
        estado=EstadoObligacion(modelo.estado),
        pagado_en=modelo.pagado_en,
        motivo_exoneracion=modelo.motivo_exoneracion,
    )


def _notificacion_model_a_dominio(modelo: NotificacionWhatsappModel) -> NotificacionWhatsApp:
    return NotificacionWhatsApp(
        id=modelo.id,
        clave_idempotencia=modelo.clave_idempotencia,
        evento_origen_id=modelo.evento_origen_id,
        asistencia_id=modelo.asistencia_id,
        alumno_id=modelo.estudiante_id,
        fecha_escolar=modelo.fecha_escolar,
        apoderado_nombre=modelo.apoderado_nombre,
        telefono_destino=modelo.telefono_destino,
        tipo=TipoNotificacion(modelo.tipo),
        plantilla=modelo.plantilla,
        contenido=modelo.contenido,
        estado=EstadoNotificacion(modelo.estado),
        intentos=modelo.intentos,
        referencia_proveedor=modelo.referencia_proveedor,
        detalle_error=modelo.detalle_error,
        creado_en=modelo.creado_en,
        actualizado_en=modelo.actualizado_en,
    )


def _notificacion_dominio_a_model(n: NotificacionWhatsApp) -> NotificacionWhatsappModel:
    return NotificacionWhatsappModel(
        id=n.id,
        clave_idempotencia=n.clave_idempotencia,
        evento_origen_id=n.evento_origen_id,
        asistencia_id=n.asistencia_id,
        estudiante_id=n.alumno_id,
        fecha_escolar=n.fecha_escolar,
        apoderado_nombre=n.apoderado_nombre,
        telefono_destino=n.telefono_destino,
        tipo=n.tipo.value,
        plantilla=n.plantilla,
        contenido=n.contenido,
        estado=n.estado.value,
        intentos=n.intentos,
        referencia_proveedor=n.referencia_proveedor,
        detalle_error=n.detalle_error,
        creado_en=_naive(n.creado_en),
        actualizado_en=_naive(n.actualizado_en),
    )


def _naive(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        return momento
    return momento.astimezone(ZONA_HORARIA_LIMA).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Pagos SQLAlchemy (PBI-07)
# ---------------------------------------------------------------------------


class PagosSqlAlchemy:
    """Implementación por defecto de :class:`PuertoPagos` sobre SQLAlchemy."""

    def evaluar_alerta_silenciosa(
        self,
        evento: EventoAsistenciaConfirmada,
        *,
        session_factory: FabricaSesion,
    ) -> AlertaSilenciosaPago | None:
        session = session_factory()
        try:
            obligaciones = [
                _obligacion_model_a_dominio(m)
                for m in session.scalars(
                    select(ObligacionPagoModel).filter_by(estudiante_id=evento.alumno_id)
                ).all()
            ]
            alertas = [
                AlertaSilenciosaPago(
                    id=m.id,
                    alumno_id=m.estudiante_id,
                    asistencia_id=m.asistencia_id,
                    fecha_escolar=m.fecha_escolar,
                    cantidad_obligaciones_vencidas=m.cantidad_obligaciones_vencidas,
                    monto_vencido_total=m.monto_vencido_total,
                    revisada=bool(m.revisada),
                    creado_en=m.creado_en,
                )
                for m in session.scalars(
                    select(AlertaPagoSilenciosaModel).filter_by(estudiante_id=evento.alumno_id)
                ).all()
            ]
            alerta = ServicioPagos.evaluar_alerta_silenciosa(
                evento, obligaciones=obligaciones, alertas_existentes=alertas, ahora=None
            )
            if alerta is None:
                return None
            session.add(
                AlertaPagoSilenciosaModel(
                    id=alerta.id,
                    estudiante_id=alerta.alumno_id,
                    asistencia_id=alerta.asistencia_id,
                    fecha_escolar=alerta.fecha_escolar,
                    cantidad_obligaciones_vencidas=alerta.cantidad_obligaciones_vencidas,
                    monto_vencido_total=alerta.monto_vencido_total,
                    revisada=False,
                )
            )
            session.commit()
            return alerta
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class ResultadoRegistroAsistenciaAplicacion:
    """Resultado del registro unificado + despachos asíncronos post-commit."""

    asistencia: RegistroAsistencia
    auditoria_id: str
    registro_auditoria_pbi16: RegistroAuditoria | None
    evento_whatsapp: EventoAsistenciaConfirmada | None
    notificacion_whatsapp_id: str | None = None
    despachos: list[Future[object]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Servicio de asistencia
# ---------------------------------------------------------------------------


class ServicioAsistencia:
    """Casos de uso transaccionales de asistencia con persistencia SQLAlchemy."""

    def __init__(
        self,
        session_factory: FabricaSesion,
        *,
        reloj: RelojServidor = hora_actual_lima,
        notificador: PuertoNotificadorWhatsApp | None = None,
        pagos: PuertoPagos | None = None,
        max_workers: int = 2,
    ) -> None:
        self._session_factory = session_factory
        self._reloj = reloj
        self._notificador = notificador or NotificadorSimulado()
        self._pagos = pagos or PagosSqlAlchemy()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ahora(self) -> datetime:
        return self._reloj()

    def _roles(self, session: Session) -> list[Rol]:
        return [rol_model_a_dominio(m, session) for m in session.scalars(select(RolModel)).all()]

    def _operador(self, session: Session, operador_id: int) -> UsuarioOperador:
        modelo = session.get(UsuarioModel, operador_id)
        if modelo is None:
            raise ValueError(f"El operador {operador_id} no existe.")
        return usuario_model_a_operador(modelo)

    def _alumnos(self, session: Session) -> list[Alumno]:
        return [alumno_model_a_dominio(m) for m in session.scalars(select(EstudianteModel)).all()]

    def _asistencias_dia(self, session: Session, fecha: date) -> list[RegistroAsistencia]:
        return [
            asistencia_model_a_dominio(m)
            for m in session.scalars(select(AsistenciaModel).filter_by(fecha_escolar=fecha)).all()
        ]

    def _hora_cierre(self, session: Session) -> time:
        config = session.get(ConfiguracionSistemaModel, CLAVE_HORA_CIERRE)
        if config is not None:
            try:
                return time.fromisoformat(config.valor)
            except ValueError:
                pass
        return time(9, 0, 0)

    def _calendario(self, session: Session) -> CalendarioEscolar:
        no_lectivos: set[date] = set()
        excepciones: set[date] = set()
        for m in session.scalars(select(CalendarioEscolarModel)).all():
            if m.es_excepcion and m.es_lectivo:
                excepciones.add(m.fecha)
            elif not m.es_lectivo:
                no_lectivos.add(m.fecha)
        return CalendarioEscolar(
            dias_no_lectivos=frozenset(no_lectivos),
            excepciones_lectivas=frozenset(excepciones),
            fines_de_semana_no_lectivos=True,
        )

    # ------------------------------------------------------------------
    # Registro unificado < 200 ms + auditoría atómica + despacho asíncrono
    # ------------------------------------------------------------------

    def registrar_asistencia(
        self,
        operador_id: int,
        *,
        metodo: MetodoRegistro,
        alumno_id: int | None = None,
        codigo_carnet: str | None = None,
        dni_manual: str | None = None,
        criterio_busqueda: str | None = None,
        motivo_correccion: str | None = None,
        persistir_auditoria: Callable[[RegistroAuditoria], None] | None = None,
        notificador: PuertoNotificadorWhatsApp | None = None,
        pagos: PuertoPagos | None = None,
        contacto_override: ContactoApoderado | None = None,
    ) -> ResultadoRegistroAsistenciaAplicacion:
        """Registra asistencia de forma unificada, atómica y < 200 ms.

        La transacción (asistencia + historial + auditoría PBI-16 + ``commit``)
        es atómica. Si falla la auditoría, ``rollback()`` total. Tras confirmar,
        despacha asíncronamente WhatsApp + alerta silenciosa de pagos aislada.
        """
        momento = self._ahora()
        fecha_escolar = momento.date()
        hora_servidor = momento.time().replace(microsecond=0, tzinfo=None)

        evento_whatsapp: EventoAsistenciaConfirmada | None = None
        resultado: ResultadoRegistroAsistencia
        asistencia: RegistroAsistencia

        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)

            alumno = self._resolver_alumno(
                session,
                metodo=metodo,
                alumno_id=alumno_id,
                codigo_carnet=codigo_carnet,
                dni_manual=dni_manual,
                criterio_busqueda=criterio_busqueda,
            )

            asistencia_existente = self._asistencia_existente(session, alumno.id, fecha_escolar)
            eventos_auditoria = _eventos_existentes(session)

            def _persistir(registro: RegistroAuditoria) -> None:
                session.add(_auditoria_a_model(registro))
                session.flush()
                if persistir_auditoria is not None:
                    persistir_auditoria(registro)

            resultado = registrar_asistencia_unificada(
                operador=operador,
                alumno=alumno,
                metodo=metodo,
                hora_servidor=hora_servidor,
                fecha_escolar=fecha_escolar,
                asistencia_existente=asistencia_existente,
                motivo_correccion=motivo_correccion,
                codigo_carnet=None,  # carnet ya validado por la capa de aplicación (PBI-06)
                dni_manual=dni_manual if metodo == MetodoRegistro.MANUAL_DNI else None,
                timestamp_servidor=momento,
                roles=roles,
                persistir_auditoria=_persistir,
                eventos_auditoria_existentes=eventos_auditoria,
            )

            asistencia = resultado.asistencia
            evento_whatsapp = resultado.evento_whatsapp

            # -- persistir asistencia + historial en la MISMA transacción ----
            self._guardar_asistencia(session, asistencia, asistencia_existente)
            self._guardar_historial(session, asistencia, resultado)

            uow.commit()

        # ---------- despacho POST-COMMIT asíncrono + contenido ----------
        notificacion_id: str | None = None
        despachos: list[Future[object]] = []
        if evento_whatsapp is not None:
            notificador_final = notificador or self._notificador
            pagos_final = pagos or self._pagos
            future = self._executor.submit(
                self._tarea_post_commit,
                evento_whatsapp,
                alumno,
                contacto_override,
                notificador_final,
                pagos_final,
            )
            despachos.append(future)

        return ResultadoRegistroAsistenciaAplicacion(
            asistencia=asistencia,
            auditoria_id=asistencia.auditoria_id or "",
            registro_auditoria_pbi16=resultado.registro_auditoria_pbi16,
            evento_whatsapp=evento_whatsapp,
            notificacion_whatsapp_id=notificacion_id,
            despachos=despachos,
        )

    # ------------------------------------------------------------------
    # Despacho post-commit asíncrono (PBI-17 + PBI-07) totalmente contenido
    # ------------------------------------------------------------------

    def _tarea_post_commit(
        self,
        evento: EventoAsistenciaConfirmada,
        alumno: Alumno,
        contacto_override: ContactoApoderado | None,
        notificador: PuertoNotificadorWhatsApp,
        pagos: PuertoPagos,
    ) -> NotificacionWhatsApp | None:
        """Ejecuta pagos + WhatsApp con sesiones propias; nunca propaga errores."""
        ahora = _ahora_seguro(self._reloj)

        # 1) PBI-07 alerta silenciosa de pagos (aislada; nunca afecta asistencia).
        pagos_ok = self._procesar_pagos_aislado(evento, pagos, ahora)

        # 2) PBI-17 notificación WhatsApp (aislada).
        try:
            contacto = contacto_override or self._contacto_apoderado(evento.alumno_id)
            return self._crear_y_enviar_notificacion(
                evento, alumno, contacto, notificador, ahora, forzar_fallido=not pagos_ok
            )
        except Exception:
            # último recurso: intenta persistir FALLIDO; jamás propaga.
            try:
                return self._persistir_fallido_minimo(evento, ahora)
            except Exception:
                return None

    def _procesar_pagos_aislado(
        self, evento: EventoAsistenciaConfirmada, pagos: PuertoPagos, ahora: datetime
    ) -> bool:
        """Devuelve True si la evaluación de pagos no falló (PBI-07 no bloquea)."""
        try:
            pagos.evaluar_alerta_silenciosa(evento, session_factory=self._session_factory)
            return True
        except Exception:
            return False

    def _contacto_apoderado(self, alumno_id: int) -> ContactoApoderado | None:
        session = self._session_factory()
        try:
            vinculo = session.scalars(
                select(EstudianteApoderadoModel).filter_by(
                    estudiante_id=alumno_id, es_principal=True
                )
            ).first()
            if vinculo is None:
                vinculo = session.scalars(
                    select(EstudianteApoderadoModel).filter_by(estudiante_id=alumno_id)
                ).first()
            if vinculo is None:
                return None
            apoderado = session.get(ApoderadoModel, vinculo.apoderado_id)
            if apoderado is None or not apoderado.activo:
                return None
            nombre = f"{apoderado.nombres} {apoderado.apellidos}".strip()
            return ContactoApoderado(
                alumno_id=alumno_id,
                nombre_apoderado=nombre,
                telefono=apoderado.telefono_whatsapp,
            )
        except Exception:
            return None
        finally:
            session.close()

    def _crear_y_enviar_notificacion(
        self,
        evento: EventoAsistenciaConfirmada,
        alumno: Alumno,
        contacto: ContactoApoderado | None,
        notificador: PuertoNotificadorWhatsApp,
        ahora: datetime,
        *,
        forzar_fallido: bool,
    ) -> NotificacionWhatsApp | None:
        session = self._session_factory()
        try:
            claves = set(
                session.scalars(select(NotificacionWhatsappModel.clave_idempotencia)).all()
            )
            notificacion = ServicioNotificacionesWhatsApp.encolar_notificacion_ingreso(
                evento, alumno, contacto, ahora, claves_existentes=claves
            )
            if forzar_fallido:
                notificacion = replace(
                    notificacion,
                    estado=EstadoNotificacion.FALLIDO,
                    detalle_error="Fallo en la evaluación de pagos (PBI-07).",
                )

            modelo = _notificacion_dominio_a_model(notificacion)
            session.add(modelo)
            session.flush()

            if not forzar_fallido:
                # envío contenido; el dominio ya aísla fallos del proveedor
                try:
                    procesada = ServicioNotificacionesWhatsApp.procesar_envio(
                        notificacion, notificador, ahora
                    )
                except Exception as error:  # noqa: BLE001
                    procesada = replace(
                        notificacion,
                        estado=EstadoNotificacion.FALLIDO,
                        intentos=notificacion.intentos + 1,
                        detalle_error=f"Error del proveedor: {error}",
                        actualizado_en=ahora,
                    )
                modelo.estado = procesada.estado.value
                modelo.intentos = procesada.intentos
                modelo.referencia_proveedor = procesada.referencia_proveedor
                modelo.detalle_error = procesada.detalle_error
                modelo.actualizado_en = _naive(procesada.actualizado_en)
                notificacion = procesada

            session.commit()
            return notificacion
        except Exception:
            session.rollback()
            # último recurso: persistir registro FALLIDO en sesión nueva
            raise
        finally:
            session.close()

    def _persistir_fallido_minimo(
        self, evento: EventoAsistenciaConfirmada, ahora: datetime
    ) -> NotificacionWhatsApp | None:
        session = self._session_factory()
        try:
            tipo = TipoNotificacion(evento.estado.value)
            notificacion = NotificacionWhatsApp(
                id=f"ntf-{uuid.uuid4().hex[:12]}",
                clave_idempotencia=(
                    f"{evento.asistencia_id}:{tipo.value}:{evento.fecha_escolar.isoformat()}"
                    f":FALLIDO:{uuid.uuid4().hex[:8]}"
                ),
                evento_origen_id=evento.id,
                asistencia_id=evento.asistencia_id,
                alumno_id=evento.alumno_id,
                fecha_escolar=evento.fecha_escolar,
                apoderado_nombre=None,
                telefono_destino=None,
                tipo=tipo,
                plantilla=(
                    "ingreso_puntual" if tipo == TipoNotificacion.PUNTUAL else "ingreso_tardanza"
                ),
                contenido="",
                estado=EstadoNotificacion.FALLIDO,
                intentos=0,
                referencia_proveedor=None,
                detalle_error="Fallo interno del despacho.",
                creado_en=ahora,
                actualizado_en=ahora,
            )
            session.add(_notificacion_dominio_a_model(notificacion))
            session.commit()
            return notificacion
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Esperar despachos (pruebas / graceful shutdown)
    # ------------------------------------------------------------------

    @staticmethod
    def esperar_despachos(resultado: ResultadoRegistroAsistenciaAplicacion, timeout: float = 10.0):
        """Bloquea hasta que los despachos asíncronos terminen (útil en pruebas)."""
        for future in resultado.despachos:
            future.result(timeout=timeout)

    def cerrar(self, esperar: bool = True) -> None:
        self._executor.shutdown(wait=esperar)

    # ------------------------------------------------------------------
    # Resolución de alumno + validaciones (PBI-01/PBI-06/PBI-08)
    # ------------------------------------------------------------------

    def _resolver_alumno(
        self,
        session: Session,
        *,
        metodo: MetodoRegistro,
        alumno_id: int | None,
        codigo_carnet: str | None,
        dni_manual: str | None,
        criterio_busqueda: str | None,
    ) -> Alumno:
        modelo: EstudianteModel | None = None

        if metodo == MetodoRegistro.CARNET:
            if not codigo_carnet:
                raise CarnetInvalidoException("Debe proporcionar el código de carnet.")
            modelo = self._resolver_por_carnet(session, codigo_carnet)
        elif metodo == MetodoRegistro.MANUAL_DNI:
            if not dni_manual:
                raise CarnetInvalidoException("Debe proporcionar el DNI para registro manual.")
            validar_formato_dni(dni_manual)
            modelo = session.scalars(select(EstudianteModel).filter_by(dni=dni_manual)).first()
            if modelo is not None and modelo.dni != dni_manual:
                modelo = None
        elif criterio_busqueda is not None and metodo == MetodoRegistro.MANUAL_BUSQUEDA:
            todos = [
                alumno_model_a_dominio(m) for m in session.scalars(select(EstudianteModel)).all()
            ]
            resultados = buscar_alumnos_activos(criterio_busqueda, todos)
            if not resultados:
                modelo = None
            else:
                elegido = resultados[0]
                modelo = session.get(EstudianteModel, elegido.id)
        elif alumno_id is not None:
            modelo = session.get(EstudianteModel, alumno_id)
        else:
            # MANUAL_BUSQUEDA / por alumno_id
            if alumno_id is not None:
                modelo = session.get(EstudianteModel, alumno_id)

        if modelo is None:
            from src.dominio.asistencia import AlumnoNoEncontradoException

            raise AlumnoNoEncontradoException("El alumno especificado no fue encontrado.")

        # PBI-08: habilitación académica explícita
        ea = estado_academico(modelo.estado)
        hoy = self._ahora().date()
        if not ServicioEstadosAcademicos.puede_registrar_asistencia(ea, hoy):
            from src.dominio.asistencia import AlumnoInactivoException

            raise AlumnoInactivoException(f"El alumno {modelo.codigo} no se encuentra ACTIVO.")

        return alumno_model_a_dominio(modelo)

    def _resolver_por_carnet(self, session: Session, codigo_carnet: str) -> EstudianteModel | None:
        # PBI-06: validar carnet activo si existe registro CarnetModel
        from src.dominio.carnets import CarnetEscolar, EstadoCarnet

        carnets_modelo = session.scalars(select(src_carnet_model())).all()
        carnets_dominio = [
            CarnetEscolar(
                id=c.id,
                alumno_id=c.estudiante_id,
                codigo_qr=c.codigo_qr,
                estado=EstadoCarnet(c.estado),
                emitido_por=c.emitido_por,
                emitido_en=c.emitido_en,
                anulado_en=c.anulado_en,
            )
            for c in carnets_modelo
        ]
        carnet_qr = next((c for c in carnets_modelo if c.codigo_qr == codigo_carnet), None)
        if carnet_qr is not None:
            # lanza CarnetInactivoOAnuladoException / CarnetNoEncontradoException
            ServicioCarnets.validar_carnet_para_ingreso(codigo_carnet, carnets_dominio)
            return session.get(EstudianteModel, carnet_qr.estudiante_id)

        # Carnet "simple" por EstudianteModel.carnet_codigo
        modelo = session.scalars(
            select(EstudianteModel).filter_by(carnet_codigo=codigo_carnet)
        ).first()
        if modelo is None:
            from src.dominio.carnets import CarnetNoEncontradoException

            raise CarnetNoEncontradoException(
                f"No existe un carnet con el código QR '{codigo_carnet}'."
            )
        return modelo

    def _asistencia_existente(
        self, session: Session, alumno_id: int, fecha: date
    ) -> RegistroAsistencia | None:
        modelo = session.scalars(
            select(AsistenciaModel).filter_by(estudiante_id=alumno_id, fecha_escolar=fecha)
        ).first()
        return asistencia_model_a_dominio(modelo) if modelo is not None else None

    # ------------------------------------------------------------------
    # Persistencia asistencia + historial
    # ------------------------------------------------------------------

    def _guardar_asistencia(
        self,
        session: Session,
        asistencia: RegistroAsistencia,
        existente: RegistroAsistencia | None,
    ) -> None:
        modelo = session.get(AsistenciaModel, asistencia.id)
        rol = rol_codigo(asistencia.rol_usuario)
        if modelo is None:
            modelo = AsistenciaModel(
                id=asistencia.id,
                estudiante_id=asistencia.alumno_id,
                usuario_id=asistencia.usuario_id or None,
                fecha_escolar=asistencia.fecha_escolar,
                hora_efectiva=asistencia.hora_efectiva,
                estado=asistencia.estado.value,
                minutos_tardanza=asistencia.minutos_tardanza,
                metodo=asistencia.metodo.value,
                rol_usuario=rol,
                estado_anterior=(
                    asistencia.estado_anterior.value if asistencia.estado_anterior else None
                ),
                motivo_correccion=asistencia.motivo_correccion,
                nivel_snapshot=asistencia.nivel,
                grado_snapshot=asistencia.grado,
                seccion_snapshot=asistencia.seccion,
                auditoria_id=asistencia.auditoria_id,
            )
            session.add(modelo)
        else:
            modelo.estado = asistencia.estado.value
            modelo.hora_efectiva = asistencia.hora_efectiva
            modelo.minutos_tardanza = asistencia.minutos_tardanza
            modelo.metodo = asistencia.metodo.value
            modelo.usuario_id = asistencia.usuario_id or None
            modelo.rol_usuario = rol
            modelo.estado_anterior = (
                asistencia.estado_anterior.value if asistencia.estado_anterior else None
            )
            modelo.motivo_correccion = asistencia.motivo_correccion
            modelo.nivel_snapshot = asistencia.nivel
            modelo.grado_snapshot = asistencia.grado
            modelo.seccion_snapshot = asistencia.seccion
            modelo.auditoria_id = asistencia.auditoria_id

        # Garantiza que la fila padre exista antes de insertar el historial que
        # la referencia (sin relación ORM explícita SQLAlchemy no ordena por FK).
        session.flush()

    def _guardar_historial(
        self,
        session: Session,
        asistencia: RegistroAsistencia,
        resultado: ResultadoRegistroAsistencia,
    ) -> None:
        session.add(
            AsistenciaHistorialModel(
                asistencia_id=asistencia.id,
                usuario_id=asistencia.usuario_id or None,
                rol_usuario=rol_codigo(asistencia.rol_usuario),
                estado_anterior=(
                    asistencia.estado_anterior.value if asistencia.estado_anterior else None
                ),
                estado_nuevo=asistencia.estado.value,
                motivo=asistencia.motivo_correccion,
                metodo=asistencia.metodo.value,
                auditoria_id=asistencia.auditoria_id,
                fecha_hora=_naive(self._ahora()),
            )
        )

    # ==================================================================
    # PBI-03 Aforo
    # ==================================================================

    def consultar_metricas_aforo(
        self,
        operador_id: int,
        *,
        fecha_escolar: date | None = None,
        hora_consulta: time | None = None,
        nivel: str | None = None,
        grado: str | None = None,
        seccion: str | None = None,
    ) -> MetricasAforo:
        momento = self._ahora()
        fecha = fecha_escolar or momento.date()
        hora = hora_consulta or momento.time().replace(microsecond=0, tzinfo=None)
        session = self._session_factory()
        try:
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            alumnos = self._alumnos(session)
            asistencias = self._asistencias_dia(session, fecha)
            hora_cierre = self._hora_cierre(session)
            return ServicioAforo.calcular_metricas(
                operador=operador,
                alumnos=alumnos,
                asistencias_dia=asistencias,
                fecha_escolar=fecha,
                hora_consulta=hora,
                hora_cierre=hora_cierre,
                nivel=nivel,
                grado=grado,
                seccion=seccion,
                roles=roles,
            )
        finally:
            session.close()

    def obtener_detalle_salon(
        self,
        operador_id: int,
        *,
        nivel: str,
        grado: str,
        seccion: str,
        fecha_escolar: date | None = None,
        hora_consulta: time | None = None,
    ):
        momento = self._ahora()
        fecha = fecha_escolar or momento.date()
        hora = hora_consulta or momento.time().replace(microsecond=0, tzinfo=None)
        session = self._session_factory()
        try:
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            alumnos = self._alumnos(session)
            asistencias = self._asistencias_dia(session, fecha)
            return ServicioAforo.obtener_detalle_salon(
                operador=operador,
                alumnos=alumnos,
                asistencias_dia=asistencias,
                nivel=nivel,
                grado=grado,
                seccion=seccion,
                hora_consulta=hora,
                hora_cierre=self._hora_cierre(session),
                roles=roles,
            )
        finally:
            session.close()

    def configurar_hora_cierre(self, operador_id: int, nueva_hora: time) -> time:
        """Configura la hora oficial de cierre (PBI-03); persiste en configuración."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            hora = ServicioAforo.configurar_hora_cierre(operador, nueva_hora, roles=roles)
            config = session.get(ConfiguracionSistemaModel, CLAVE_HORA_CIERRE)
            valor = hora.isoformat()
            if config is None:
                session.add(
                    ConfiguracionSistemaModel(
                        clave=CLAVE_HORA_CIERRE, valor=valor, actualizado_por=operador_id
                    )
                )
            else:
                config.valor = valor
                config.actualizado_por = operador_id
            uow.commit()
            return hora

    def consultar_historial_modificaciones(
        self,
        operador_id: int,
        *,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        alumno_id: int | None = None,
    ) -> list[RegistroAsistencia]:
        session = self._session_factory()
        try:
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            asistencias = [
                asistencia_model_a_dominio(m)
                for m in session.scalars(select(AsistenciaModel)).all()
            ]
            return ServicioAforo.consultar_historial_modificaciones(
                operador=operador,
                asistencias=asistencias,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                alumno_id=alumno_id,
                roles=roles,
            )
        finally:
            session.close()

    def ejecutar_cierre_diario(
        self,
        operador_o_sistema: int | str = ACTOR_SYSTEM_CRON,
        *,
        fecha_escolar: date | None = None,
        hora_cierre: time | None = None,
    ) -> EventoCierreDiario:
        """Cierre automático de jornada (PBI-03): marca AUSENTE, idempotente, atómico."""
        momento = self._ahora()
        fecha = fecha_escolar or momento.date()

        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session

            # actor
            if isinstance(operador_o_sistema, int):
                operador: UsuarioOperador | str = self._operador(session, operador_o_sistema)
                roles = self._roles(session)
                actor_usuario_id = operador.id
                actor_rol = rol_codigo(operador.rol)
            else:
                operador = operador_o_sistema
                roles = self._roles(session)
                actor_usuario_id = 0
                actor_rol = ACTOR_SYSTEM_CRON

            hora = hora_cierre or self._hora_cierre(session)
            calendario = self._calendario(session)

            # idempotencia: ¿ya hay cierre para la fecha?
            ya_cerrada = session.scalars(select(CierreDiarioModel.fecha_escolar)).all()
            fechas_ya_cerradas = set(ya_cerrada)

            alumnos = self._alumnos(session)
            asistencias = self._asistencias_dia(session, fecha)

            nuevas, evento = ServicioAforo.ejecutar_cierre_automatico(
                operador_o_sistema=operador,
                alumnos=alumnos,
                asistencias_existentes=asistencias,
                fecha_escolar=fecha,
                hora_cierre=hora,
                fechas_ya_cerradas=fechas_ya_cerradas,
                calendario=calendario,
                roles=roles,
            )

            for nueva in nuevas:
                self._guardar_asistencia(session, nueva, None)
                session.add(
                    AsistenciaHistorialModel(
                        asistencia_id=nueva.id,
                        usuario_id=actor_usuario_id or None,
                        rol_usuario=actor_rol,
                        estado_anterior=(
                            nueva.estado_anterior.value if nueva.estado_anterior else None
                        ),
                        estado_nuevo=nueva.estado.value,
                        motivo=nueva.motivo_correccion,
                        metodo=nueva.metodo.value,
                        auditoria_id=None,
                        fecha_hora=_naive(momento),
                    )
                )

            # auditoría PBI-16 del cierre (atómica)
            registrar_auditoria_pbi16(
                session,
                usuario_id=actor_usuario_id,
                rol_ejecutante=actor_rol,
                operacion=TipoOperacionAuditoria.CIERRE_ESCOLAR,
                entidad="ASISTENCIA",
                entidad_id=fecha.isoformat(),
                fecha_hora=momento,
                detalle={
                    "total_ausentes_marcados": evento.total_ausentes_marcados,
                    "alumnos_ids_afectados": evento.alumnos_ids_afectados,
                },
            )

            session.add(
                CierreDiarioModel(
                    evento_id=evento.id,
                    fecha_escolar=fecha,
                    hora_cierre=hora,
                    total_ausentes_marcados=evento.total_ausentes_marcados,
                    actor_ejecutante=actor_rol,
                    usuario_id=actor_usuario_id or None,
                )
            )

            uow.commit()
            return evento

    def notificar_ausencias_automaticas(
        self,
        *,
        fecha_escolar: date | None = None,
        hora_actual: time | None = None,
        hora_programada: time | None = None,
    ) -> list[NotificacionWhatsApp]:
        """Encola + despacha notificaciones de ausencia tras el cierre (PBI-17 RN-04)."""
        momento = self._ahora()
        fecha = fecha_escolar or momento.date()
        hora = hora_actual or momento.time().replace(microsecond=0, tzinfo=None)

        session = self._session_factory()
        try:
            # reconstruir evento de cierre desde CierreDiarioModel
            cierre_modelo = session.scalars(
                select(CierreDiarioModel).filter_by(fecha_escolar=fecha)
            ).first()
            if cierre_modelo is None:
                return []
            cierre = EventoCierreDiario(
                id=cierre_modelo.evento_id,
                fecha_escolar=cierre_modelo.fecha_escolar,
                hora_cierre=cierre_modelo.hora_cierre,
                total_ausentes_marcados=cierre_modelo.total_ausentes_marcados,
                alumnos_ids_afectados=[],
            )
            asistencias = self._asistencias_dia(session, fecha)
            alumnos = {a.id: a for a in self._alumnos(session)}
            contactos = {
                aid: c for aid in alumnos if (c := self._contacto_apoderado(aid)) is not None
            }
            calendario = self._calendario(session)
            programada = hora_programada or cierre.hora_cierre
            ya_notificados = set(
                session.scalars(
                    select(NotificacionWhatsappModel.estudiante_id).filter_by(
                        fecha_escolar=fecha, tipo=TipoNotificacion.AUSENCIA.value
                    )
                ).all()
            )
            ahora = _naive(momento)
            encolar = ServicioNotificacionesWhatsApp
            notificaciones = encolar.encolar_notificaciones_ausencia_automatica(
                cierre=cierre,
                asistencias_dia=asistencias,
                alumnos=alumnos,
                contactos=contactos,
                calendario=calendario,
                hora_actual=hora,
                hora_programada=programada,
                ahora=momento,
                ya_notificados=frozenset(ya_notificados),
            )
            # persistir + procesar envío (aislado), marca notificación_ausencia_enviada
            persistidas: list[NotificacionWhatsApp] = []
            for n in notificaciones:
                session.add(_notificacion_dominio_a_model(n))
            session.flush()
            _ = ahora
            for n in notificaciones:
                try:
                    procesada = ServicioNotificacionesWhatsApp.procesar_envio(
                        n, self._notificador, momento
                    )
                except Exception:
                    procesada = replace(n, estado=EstadoNotificacion.FALLIDO)
                modelo = session.get(NotificacionWhatsappModel, n.id)
                if modelo is not None:
                    modelo.estado = procesada.estado.value
                    modelo.intentos = procesada.intentos
                    modelo.referencia_proveedor = procesada.referencia_proveedor
                    modelo.detalle_error = procesada.detalle_error
                persistidas.append(procesada)
            session.commit()
            return persistidas
        finally:
            session.close()

    # ==================================================================
    # PBI-04 Justificaciones + períodos académicos
    # ==================================================================

    def registrar_justificacion(
        self,
        operador_id: int,
        *,
        asistencia_id: str,
        categoria: CategoriaJustificacion,
        motivo: str,
        fecha_solicitud: date | None = None,
        periodo_id: int | None = None,
        documento_adjunto: str | None = None,
        adjuntos: Sequence[AdjuntoJustificacion] = (),
    ) -> ResultadoOperacionJustificacion:
        momento = self._ahora()
        solicitud = fecha_solicitud or momento.date()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)

            asistencia_modelo = session.get(AsistenciaModel, asistencia_id)
            if asistencia_modelo is None:
                raise ValueError(f"La asistencia {asistencia_id} no existe.")
            asistencia = asistencia_model_a_dominio(asistencia_modelo)
            alumno_modelo = session.get(EstudianteModel, asistencia.alumno_id)
            alumno = alumno_model_a_dominio(alumno_modelo) if alumno_modelo else None

            periodo = self._periodo_para_asistencia(session, asistencia.fecha_escolar, periodo_id)

            resultado = ServicioJustificaciones.registrar_y_aprobar_justificacion(
                operador=operador,
                alumno=alumno,
                asistencia=asistencia,
                fecha_solicitud=solicitud,
                fecha_actual=momento.date(),
                categoria=categoria,
                motivo=motivo,
                periodo=periodo,
                documento_adjunto=documento_adjunto,
                adjuntos=adjuntos,
                roles=roles,
            )

            just = resultado.justificacion
            just_modelo = JustificacionModel(
                id=just.id,
                asistencia_id=just.asistencia_id,
                estudiante_id=just.alumno_id,
                periodo_id=periodo.id,
                usuario_id=just.usuario_id,
                rol_usuario=rol_codigo(just.rol_usuario),
                fecha_solicitud=just.fecha_solicitud,
                categoria=just.categoria.value,
                motivo=just.motivo,
                estado=just.estado.value,
                minutos_tardanza_original=just.minutos_tardanza_original,
                documento_adjunto=just.documento_adjunto,
                nivel=just.nivel,
                grado=just.grado,
                seccion=just.seccion,
                fecha_resolucion=_naive(just.fecha_resolucion) if just.fecha_resolucion else None,
            )
            session.add(just_modelo)
            session.flush()
            for i, adj in enumerate(just.adjuntos):
                session.add(
                    JustificacionAdjuntoModel(
                        justificacion_id=just.id,
                        nombre_archivo=adj.nombre,
                        extension=adj.extension,
                        tamano_bytes=adj.tamano_bytes,
                        ruta_almacenamiento=f"justificaciones/{just.id}/{adj.nombre}",
                    )
                )

            # actualizar asistencia -> JUSTIFICADO + historial + auditoría PBI-16 atómica
            actualizada = resultado.asistencia_actualizada
            self._aplicar_asistencia_actualizada(session, asistencia_modelo, actualizada)
            session.add(
                AsistenciaHistorialModel(
                    asistencia_id=actualizada.id,
                    usuario_id=operador.id,
                    rol_usuario=rol_codigo(operador.rol),
                    estado_anterior=(
                        actualizada.estado_anterior.value if actualizada.estado_anterior else None
                    ),
                    estado_nuevo=actualizada.estado.value,
                    motivo=actualizada.motivo_correccion,
                    metodo=actualizada.metodo.value,
                    auditoria_id=actualizada.auditoria_id,
                    fecha_hora=_naive(momento),
                )
            )
            registrar_auditoria_pbi16(
                session,
                usuario_id=operador.id,
                rol_ejecutante=rol_codigo(operador.rol),
                operacion=TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
                entidad="ASISTENCIA",
                entidad_id=actualizada.id,
                fecha_hora=momento,
                alumno_id=actualizada.alumno_id,
                metodo_asistencia=actualizada.metodo.value,
                estado_anterior=(
                    actualizada.estado_anterior.value if actualizada.estado_anterior else None
                ),
                estado_nuevo=actualizada.estado.value,
                motivo=actualizada.motivo_correccion,
            )

            uow.commit()
            return resultado

    def anular_justificacion(
        self, operador_id: int, *, justificacion_id: str, periodo_id: int | None = None
    ) -> RegistroAsistencia:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            just_modelo = session.get(JustificacionModel, justificacion_id)
            if just_modelo is None:
                raise ValueError(f"La justificación {justificacion_id} no existe.")
            asistencia_modelo = session.get(AsistenciaModel, just_modelo.asistencia_id)
            if asistencia_modelo is None:
                raise ValueError("La asistencia de la justificación no existe.")
            asistencia = asistencia_model_a_dominio(asistencia_modelo)
            justificacion = _justificacion_model_a_dominio(just_modelo)
            periodo = self._periodo_para_asistencia(
                session, asistencia.fecha_escolar, periodo_id or just_modelo.periodo_id
            )

            restaurada = ServicioJustificaciones.anular_justificacion(
                operador=operador,
                justificacion=justificacion,
                asistencia=asistencia,
                periodo=periodo,
                roles=roles,
            )
            self._aplicar_asistencia_actualizada(session, asistencia_modelo, restaurada)
            just_modelo.estado = EstadoJustificacion.RECHAZADA.value
            uow.commit()
            return restaurada

    def consultar_justificaciones(
        self, operador_id: int, filtro: FiltroJustificaciones | None = None
    ) -> list[Justificacion]:
        session = self._session_factory()
        try:
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            justificaciones = [
                _justificacion_model_a_dominio(m)
                for m in session.scalars(select(JustificacionModel)).all()
            ]
            return ServicioJustificaciones.consultar_justificaciones(
                justificaciones, filtro, operador=operador, roles=roles
            )
        finally:
            session.close()

    def _periodo_para_asistencia(
        self, session: Session, fecha: date, periodo_id: int | None
    ) -> PeriodoAcademico:
        if periodo_id is not None:
            modelo = session.get(PeriodoAcademicoModel, periodo_id)
            if modelo is not None:
                return periodo_model_a_dominio(modelo)
        modelo = session.scalars(
            select(PeriodoAcademicoModel)
            .where(PeriodoAcademicoModel.fecha_inicio <= fecha)
            .where(PeriodoAcademicoModel.fecha_fin >= fecha)
        ).first()
        if modelo is not None:
            return periodo_model_a_dominio(modelo)
        # período sintético por defecto para no bloquear (dominio exige período)
        return PeriodoAcademico(
            id=periodo_id or 0,
            nombre="Período",
            fecha_inicio=fecha.replace(day=1),
            fecha_fin=fecha.replace(day=28),
            cerrado=False,
            anio_lectivo=fecha.year,
        )

    def _aplicar_asistencia_actualizada(
        self, session: Session, modelo: AsistenciaModel, asistencia: RegistroAsistencia
    ) -> None:
        modelo.estado = asistencia.estado.value
        modelo.minutos_tardanza = asistencia.minutos_tardanza
        modelo.estado_anterior = (
            asistencia.estado_anterior.value if asistencia.estado_anterior else None
        )
        modelo.motivo_correccion = asistencia.motivo_correccion
        modelo.auditoria_id = asistencia.auditoria_id

    # ------------------------- Períodos académicos (PBI-04) ----------------

    def listar_periodos(self, *, anio_lectivo: int | None = None) -> list[PeriodoAcademico]:
        session = self._session_factory()
        try:
            stmt = select(PeriodoAcademicoModel).order_by(PeriodoAcademicoModel.orden)
            if anio_lectivo is not None:
                stmt = stmt.filter_by(anio_lectivo=anio_lectivo)
            return [periodo_model_a_dominio(m) for m in session.scalars(stmt).all()]
        finally:
            session.close()

    def crear_periodo(self, operador_id: int, periodo: PeriodoAcademico) -> PeriodoAcademico:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            existentes = [
                periodo_model_a_dominio(m)
                for m in session.scalars(select(PeriodoAcademicoModel)).all()
            ]
            validado = ServicioPeriodosAcademicos.crear_periodo(
                operador=operador, periodo=periodo, periodos_existentes=existentes, roles=roles
            )
            session.add(_periodo_a_model(validado))
            uow.commit()
            return validado

    def modificar_periodo(
        self,
        operador_id: int,
        periodo_id: int,
        **cambios,
    ) -> PeriodoAcademico:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(PeriodoAcademicoModel, periodo_id)
            if modelo is None:
                raise ValueError(f"El período {periodo_id} no existe.")
            existentes = [
                periodo_model_a_dominio(m)
                for m in session.scalars(select(PeriodoAcademicoModel)).all()
            ]
            actualizado = ServicioPeriodosAcademicos.modificar_periodo(
                operador=operador,
                periodo=periodo_model_a_dominio(modelo),
                periodos_existentes=existentes,
                roles=roles,
                **cambios,
            )
            _actualizar_modelo_periodo(modelo, actualizado)
            uow.commit()
            return actualizado

    def cambiar_estado_periodo(
        self, operador_id: int, periodo_id: int, *, cerrado: bool
    ) -> PeriodoAcademico:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(PeriodoAcademicoModel, periodo_id)
            if modelo is None:
                raise ValueError(f"El período {periodo_id} no existe.")
            actualizado = ServicioPeriodosAcademicos.cambiar_estado_periodo(
                operador=operador,
                periodo=periodo_model_a_dominio(modelo),
                cerrado=cerrado,
                roles=roles,
            )
            modelo.cerrado = cerrado
            uow.commit()
            return actualizado

    def eliminar_periodo(self, operador_id: int, periodo_id: int) -> bool:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.get(PeriodoAcademicoModel, periodo_id)
            if modelo is None:
                raise ValueError(f"El período {periodo_id} no existe.")
            existentes = [
                periodo_model_a_dominio(m)
                for m in session.scalars(select(PeriodoAcademicoModel)).all()
            ]
            justificaciones = [
                _justificacion_model_a_dominio(m)
                for m in session.scalars(select(JustificacionModel)).all()
            ]
            ServicioPeriodosAcademicos.eliminar_periodo(
                operador=operador,
                periodo=periodo_model_a_dominio(modelo),
                periodos_existentes=existentes,
                justificaciones=justificaciones,
                roles=roles,
            )
            session.delete(modelo)
            uow.commit()
            return True


def _justificacion_model_a_dominio(modelo: JustificacionModel) -> Justificacion:
    return Justificacion(
        id=modelo.id,
        asistencia_id=modelo.asistencia_id,
        alumno_id=modelo.estudiante_id,
        fecha_solicitud=modelo.fecha_solicitud or date.today(),
        categoria=_categoria(modelo.categoria),
        motivo=modelo.motivo,
        estado=_estado_just(modelo.estado),
        usuario_id=modelo.usuario_id,
        rol_usuario=modelo.rol_usuario or "",
        documento_adjunto=modelo.documento_adjunto,
        fecha_resolucion=modelo.fecha_resolucion,
        adjuntos=tuple(
            AdjuntoJustificacion(nombre=a.nombre_archivo, tamano_bytes=a.tamano_bytes)
            for a in modelo.adjuntos
        ),
        minutos_tardanza_original=modelo.minutos_tardanza_original,
        nivel=modelo.nivel,
        grado=modelo.grado,
        seccion=modelo.seccion,
    )


def _categoria(valor: str) -> CategoriaJustificacion:
    try:
        return CategoriaJustificacion(valor)
    except ValueError:
        return CategoriaJustificacion.OTRA


def _estado_just(valor: str) -> EstadoJustificacion:
    try:
        return EstadoJustificacion(valor)
    except ValueError:
        return EstadoJustificacion.APROBADA


def _periodo_a_model(p: PeriodoAcademico) -> PeriodoAcademicoModel:
    return PeriodoAcademicoModel(
        anio_lectivo=p.anio_lectivo,
        tipo_periodo=p.tipo_periodo.value,
        orden=p.orden,
        nombre=p.nombre,
        fecha_inicio=p.fecha_inicio,
        fecha_fin=p.fecha_fin,
        fecha_limite_notas=p.fecha_limite_notas,
        cerrado=p.cerrado,
    )


def _actualizar_modelo_periodo(modelo: PeriodoAcademicoModel, p: PeriodoAcademico) -> None:
    modelo.nombre = p.nombre
    modelo.fecha_inicio = p.fecha_inicio
    modelo.fecha_fin = p.fecha_fin
    modelo.fecha_limite_notas = p.fecha_limite_notas
    modelo.cerrado = p.cerrado


def _ahora_seguro(reloj: RelojServidor) -> datetime:
    try:
        momento = reloj()
    except Exception:
        momento = hora_actual_lima()
    if momento.tzinfo is None:
        return momento.replace(tzinfo=ZONA_HORARIA_LIMA)
    return momento


def src_carnet_model():
    from src.infraestructura.modelos import CarnetModel

    return CarnetModel
