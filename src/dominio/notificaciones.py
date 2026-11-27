"""PBI-17: notificaciones a apoderados por WhatsApp.

Dominio puro: no realiza llamadas de red. El envío real se delega en un adaptador
que implementa ``PuertoNotificadorWhatsApp``; el registro de asistencia (PBI-01)
solo encola notificaciones y nunca espera al proveedor.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from enum import StrEnum
from typing import Protocol

from src.dominio.aforo import CalendarioEscolar, EventoCierreDiario
from src.dominio.asistencia import (
    Alumno,
    EstadoAsistencia,
    EventoAsistenciaConfirmada,
    RegistroAsistencia,
    UsuarioOperador,
)
from src.dominio.usuarios import PermisoOperacion, Rol, ServicioAutenticacionYPermisos

DETALLE_CONTACTO_INVALIDO = "Contacto de apoderado inválido o ausente"
_PATRON_TELEFONO_PERU = re.compile(r"(?:\+?51)?(9\d{8})")


class TipoNotificacion(StrEnum):
    PUNTUAL = "PUNTUAL"
    TARDANZA = "TARDANZA"
    AUSENCIA = "AUSENCIA"


class EstadoNotificacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    ENVIADO = "ENVIADO"
    ENTREGADO = "ENTREGADO"
    FALLIDO = "FALLIDO"


class NotificacionException(Exception):
    """Excepción base del dominio de notificaciones WhatsApp."""


class PermisoNotificacionException(NotificacionException):
    """Lanzada cuando el operador no está activo o carece del permiso requerido."""


class VentanaBloqueoActivaException(NotificacionException):
    """Lanzada al intentar la notificación manual dentro de la ventana de ±5 minutos."""


class ConfirmacionReenvioRequeridaException(NotificacionException):
    """Lanzada al reenviar una ausencia ya notificada sin confirmación explícita."""


class NotificacionDuplicadaException(NotificacionException):
    """Lanzada cuando ya existe una notificación con la misma clave de idempotencia."""


_ESTADOS_YA_ENVIADOS = frozenset({EstadoNotificacion.ENVIADO, EstadoNotificacion.ENTREGADO})
_ESTADOS_WEBHOOK = frozenset({EstadoNotificacion.ENTREGADO, EstadoNotificacion.FALLIDO})


@dataclass(frozen=True)
class ContactoApoderado:
    alumno_id: int
    nombre_apoderado: str
    telefono: str | None


@dataclass(frozen=True)
class ResultadoEnvioProveedor:
    exitoso: bool
    estado_reportado: EstadoNotificacion
    referencia: str | None = None
    detalle_error: str | None = None


@dataclass(frozen=True)
class NotificacionWhatsApp:
    id: str
    clave_idempotencia: str
    evento_origen_id: str | None
    asistencia_id: str
    alumno_id: int
    fecha_escolar: date
    apoderado_nombre: str | None
    telefono_destino: str | None
    tipo: TipoNotificacion
    plantilla: str
    contenido: str
    estado: EstadoNotificacion
    intentos: int
    referencia_proveedor: str | None
    detalle_error: str | None
    creado_en: datetime
    actualizado_en: datetime


class PuertoNotificadorWhatsApp(Protocol):
    """Puerto de salida hacia la API oficial de WhatsApp Business."""

    def enviar(self, notificacion: NotificacionWhatsApp) -> ResultadoEnvioProveedor: ...


def _segundos_del_dia(hora: time) -> int:
    return hora.hour * 3600 + hora.minute * 60 + hora.second


class ServicioNotificacionesWhatsApp:
    """Encola, envía y da seguimiento a las notificaciones a apoderados."""

    HORA_DEFECTO_AUSENCIAS = time(9, 0, 0)
    MARGEN_BLOQUEO_MINUTOS = 5
    MAX_INTENTOS_DEFECTO = 3

    # ------------------------------------------------------------------
    # Validaciones y utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _validar_operador(
        operador: UsuarioOperador,
        permiso: PermisoOperacion,
        roles: Sequence[Rol] | None,
    ) -> None:
        if not operador.activo:
            raise PermisoNotificacionException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(operador.rol, permiso, roles=roles):
            raise PermisoNotificacionException(
                f"El rol {operador.rol} no cuenta con el permiso {permiso.value}."
            )

    @staticmethod
    def normalizar_telefono_peru(telefono: str | None) -> str | None:
        """Devuelve el celular peruano en formato ``+519XXXXXXXX`` o ``None`` si es inválido."""
        if not isinstance(telefono, str):
            return None
        limpio = re.sub(r"[\s\-]", "", telefono)
        coincidencia = _PATRON_TELEFONO_PERU.fullmatch(limpio)
        return f"+51{coincidencia.group(1)}" if coincidencia else None

    @staticmethod
    def configurar_hora_notificacion_ausencias(
        operador: UsuarioOperador,
        nueva_hora: time,
        roles: Sequence[Rol] | None = None,
    ) -> time:
        """Configura la hora automática de aviso de ausencias (RN-06)."""
        ServicioNotificacionesWhatsApp._validar_operador(
            operador, PermisoOperacion.CONFIGURAR_NOTIFICACIONES_WHATSAPP, roles
        )
        if not isinstance(nueva_hora, time):
            raise NotificacionException("La hora de notificación debe ser una hora válida.")
        return nueva_hora

    @staticmethod
    def esta_en_ventana_bloqueo_manual(
        hora_actual: time,
        hora_programada: time,
        margen_minutos: int = MARGEN_BLOQUEO_MINUTOS,
    ) -> bool:
        """RN-10: ventana inclusiva ``[programada - margen, programada + margen]``."""
        diferencia = abs(_segundos_del_dia(hora_actual) - _segundos_del_dia(hora_programada))
        return diferencia <= margen_minutos * 60

    @staticmethod
    def construir_contenido_plantilla(
        tipo: TipoNotificacion,
        alumno: Alumno,
        fecha_escolar: date,
        hora_efectiva: time | None = None,
        minutos_tardanza: int = 0,
    ) -> tuple[str, str]:
        """RN-17: genera ``(nombre_plantilla, texto)`` para PUNTUAL, TARDANZA o AUSENCIA."""
        nombre = f"{alumno.nombres} {alumno.apellidos}"
        fecha = fecha_escolar.strftime("%d/%m/%Y")

        if tipo == TipoNotificacion.AUSENCIA:
            return (
                "ausencia_alumno",
                f"Estimado apoderado: {nombre} no registró asistencia el {fecha}. "
                "Si la inasistencia tiene un motivo válido, puede presentar la "
                "justificación en la secretaría del colegio dentro del plazo establecido.",
            )

        if hora_efectiva is None:
            raise NotificacionException("La hora de ingreso es obligatoria para esta plantilla.")
        hora = hora_efectiva.strftime("%H:%M")

        if tipo == TipoNotificacion.PUNTUAL:
            return (
                "ingreso_puntual",
                f"Estimado apoderado: {nombre} ingresó puntualmente al colegio "
                f"el {fecha} a las {hora}.",
            )
        return (
            "ingreso_tardanza",
            f"Estimado apoderado: {nombre} ingresó al colegio el {fecha} a las {hora} "
            f"con una tardanza de {minutos_tardanza} minuto(s).",
        )

    @staticmethod
    def _crear_notificacion(
        *,
        clave_idempotencia: str,
        evento_origen_id: str | None,
        asistencia_id: str,
        alumno: Alumno,
        fecha_escolar: date,
        contacto: ContactoApoderado | None,
        tipo: TipoNotificacion,
        hora_efectiva: time | None,
        minutos_tardanza: int,
        ahora: datetime,
    ) -> NotificacionWhatsApp:
        """Crea el registro PENDIENTE, o FALLIDO si no hay celular válido (RN-16)."""
        plantilla, contenido = ServicioNotificacionesWhatsApp.construir_contenido_plantilla(
            tipo, alumno, fecha_escolar, hora_efectiva, minutos_tardanza
        )
        telefono = ServicioNotificacionesWhatsApp.normalizar_telefono_peru(
            contacto.telefono if contacto else None
        )
        return NotificacionWhatsApp(
            id=f"ntf-{uuid.uuid4().hex[:12]}",
            clave_idempotencia=clave_idempotencia,
            evento_origen_id=evento_origen_id,
            asistencia_id=asistencia_id,
            alumno_id=alumno.id,
            fecha_escolar=fecha_escolar,
            apoderado_nombre=contacto.nombre_apoderado if contacto else None,
            telefono_destino=telefono,
            tipo=tipo,
            plantilla=plantilla,
            contenido=contenido,
            estado=EstadoNotificacion.PENDIENTE if telefono else EstadoNotificacion.FALLIDO,
            intentos=0,
            referencia_proveedor=None,
            detalle_error=None if telefono else DETALLE_CONTACTO_INVALIDO,
            creado_en=ahora,
            actualizado_en=ahora,
        )

    @staticmethod
    def _clave_ausencia(asistencia: RegistroAsistencia) -> str:
        return (
            f"{asistencia.id}:{TipoNotificacion.AUSENCIA.value}:"
            f"{asistencia.fecha_escolar.isoformat()}"
        )

    @staticmethod
    def _crear_ausencia(
        asistencia: RegistroAsistencia,
        alumno: Alumno,
        contacto: ContactoApoderado | None,
        ahora: datetime,
        evento_origen_id: str | None,
        clave_idempotencia: str,
    ) -> NotificacionWhatsApp:
        return ServicioNotificacionesWhatsApp._crear_notificacion(
            clave_idempotencia=clave_idempotencia,
            evento_origen_id=evento_origen_id,
            asistencia_id=asistencia.id,
            alumno=alumno,
            fecha_escolar=asistencia.fecha_escolar,
            contacto=contacto,
            tipo=TipoNotificacion.AUSENCIA,
            hora_efectiva=None,
            minutos_tardanza=0,
            ahora=ahora,
        )

    # ------------------------------------------------------------------
    # Encolado
    # ------------------------------------------------------------------

    @staticmethod
    def encolar_notificacion_ingreso(
        evento: EventoAsistenciaConfirmada,
        alumno: Alumno,
        contacto: ContactoApoderado | None,
        ahora: datetime,
        claves_existentes: Collection[str] = (),
    ) -> NotificacionWhatsApp:
        """RN-02/03: encola PUNTUAL o TARDANZA sin invocar al proveedor."""
        if evento.estado not in (EstadoAsistencia.PUNTUAL, EstadoAsistencia.TARDANZA):
            raise NotificacionException(
                f"Solo se notifican ingresos PUNTUAL o TARDANZA, no {evento.estado}."
            )
        tipo = TipoNotificacion(evento.estado.value)
        clave = f"{evento.asistencia_id}:{tipo.value}:{evento.fecha_escolar.isoformat()}"
        if clave in claves_existentes:
            raise NotificacionDuplicadaException(
                f"Ya existe una notificación con la clave {clave}."
            )
        return ServicioNotificacionesWhatsApp._crear_notificacion(
            clave_idempotencia=clave,
            evento_origen_id=evento.id,
            asistencia_id=evento.asistencia_id,
            alumno=alumno,
            fecha_escolar=evento.fecha_escolar,
            contacto=contacto,
            tipo=tipo,
            hora_efectiva=evento.hora_efectiva,
            minutos_tardanza=evento.minutos_tardanza,
            ahora=ahora,
        )

    @staticmethod
    def encolar_notificaciones_ausencia_automatica(
        cierre: EventoCierreDiario,
        asistencias_dia: Sequence[RegistroAsistencia],
        alumnos: Mapping[int, Alumno],
        contactos: Mapping[int, ContactoApoderado],
        calendario: CalendarioEscolar,
        hora_actual: time,
        hora_programada: time,
        ahora: datetime,
        ya_notificados: frozenset[int] = frozenset(),
    ) -> list[NotificacionWhatsApp]:
        """RN-04 a RN-07: encola ausencias confirmadas tras el cierre de PBI-03."""
        if not calendario.es_dia_lectivo(cierre.fecha_escolar) or hora_actual < hora_programada:
            return []

        notificaciones: list[NotificacionWhatsApp] = []
        for asistencia in asistencias_dia:
            alumno = alumnos.get(asistencia.alumno_id)
            if (
                asistencia.fecha_escolar != cierre.fecha_escolar
                or asistencia.estado != EstadoAsistencia.AUSENTE
                or asistencia.alumno_id in ya_notificados
                or alumno is None
            ):
                continue
            notificaciones.append(
                ServicioNotificacionesWhatsApp._crear_ausencia(
                    asistencia,
                    alumno,
                    contactos.get(asistencia.alumno_id),
                    ahora,
                    evento_origen_id=cierre.id,
                    clave_idempotencia=ServicioNotificacionesWhatsApp._clave_ausencia(asistencia),
                )
            )
        return notificaciones

    @staticmethod
    def encolar_notificaciones_ausencia_manual(
        operador: UsuarioOperador,
        asistencias_ausentes: Sequence[RegistroAsistencia],
        alumnos: Mapping[int, Alumno],
        contactos: Mapping[int, ContactoApoderado],
        hora_actual: time,
        hora_programada: time,
        ahora: datetime,
        ya_notificados: frozenset[int] = frozenset(),
        confirmacion_reenvio: bool = False,
        roles: Sequence[Rol] | None = None,
    ) -> list[NotificacionWhatsApp]:
        """RN-08 a RN-12: acción manual «Notificar Ausencias a Apoderados»."""
        ServicioNotificacionesWhatsApp._validar_operador(
            operador, PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL, roles
        )
        if ServicioNotificacionesWhatsApp.esta_en_ventana_bloqueo_manual(
            hora_actual, hora_programada
        ):
            raise VentanaBloqueoActivaException(
                "La notificación manual está bloqueada 5 minutos antes y después "
                "de la notificación automática."
            )

        ausentes = [a for a in asistencias_ausentes if a.estado == EstadoAsistencia.AUSENTE]
        if not confirmacion_reenvio and any(a.alumno_id in ya_notificados for a in ausentes):
            raise ConfirmacionReenvioRequeridaException(
                "Hay ausencias ya notificadas; confirme el reenvío para continuar."
            )

        notificaciones: list[NotificacionWhatsApp] = []
        for asistencia in ausentes:
            alumno = alumnos.get(asistencia.alumno_id)
            if alumno is None:
                continue
            clave = ServicioNotificacionesWhatsApp._clave_ausencia(asistencia)
            if asistencia.alumno_id in ya_notificados:
                clave = f"{clave}:REENVIO:{ahora.isoformat()}"
            notificaciones.append(
                ServicioNotificacionesWhatsApp._crear_ausencia(
                    asistencia,
                    alumno,
                    contactos.get(asistencia.alumno_id),
                    ahora,
                    evento_origen_id=None,
                    clave_idempotencia=clave,
                )
            )
        return notificaciones

    # ------------------------------------------------------------------
    # Envío y seguimiento
    # ------------------------------------------------------------------

    @staticmethod
    def procesar_envio(
        notificacion: NotificacionWhatsApp,
        proveedor: PuertoNotificadorWhatsApp,
        ahora: datetime,
        max_intentos: int = MAX_INTENTOS_DEFECTO,
    ) -> NotificacionWhatsApp:
        """RN-13 a RN-16: envía con reintentos limitados y aislamiento total de fallos."""
        if notificacion.estado in _ESTADOS_YA_ENVIADOS:
            return notificacion

        if notificacion.intentos >= max_intentos:
            return replace(
                notificacion,
                estado=EstadoNotificacion.FALLIDO,
                detalle_error=f"Se alcanzó el máximo de {max_intentos} intentos de envío.",
                actualizado_en=ahora,
            )

        if notificacion.telefono_destino is None:
            return replace(
                notificacion,
                estado=EstadoNotificacion.FALLIDO,
                detalle_error=DETALLE_CONTACTO_INVALIDO,
                actualizado_en=ahora,
            )

        intentos = notificacion.intentos + 1
        try:
            resultado = proveedor.enviar(notificacion)
        except Exception as error:  # aislamiento: un fallo del proveedor no se propaga
            return replace(
                notificacion,
                estado=EstadoNotificacion.FALLIDO,
                intentos=intentos,
                detalle_error=f"Error del proveedor: {error}",
                actualizado_en=ahora,
            )

        if not resultado.exitoso:
            return replace(
                notificacion,
                estado=EstadoNotificacion.FALLIDO,
                intentos=intentos,
                referencia_proveedor=resultado.referencia or notificacion.referencia_proveedor,
                detalle_error=resultado.detalle_error or "El proveedor rechazó el envío.",
                actualizado_en=ahora,
            )

        estado = (
            resultado.estado_reportado
            if resultado.estado_reportado == EstadoNotificacion.ENTREGADO
            else EstadoNotificacion.ENVIADO
        )
        return replace(
            notificacion,
            estado=estado,
            intentos=intentos,
            referencia_proveedor=resultado.referencia,
            detalle_error=None,
            actualizado_en=ahora,
        )

    @staticmethod
    def actualizar_estado_proveedor(
        notificacion: NotificacionWhatsApp,
        estado: EstadoNotificacion,
        ahora: datetime,
        referencia: str | None = None,
        detalle_error: str | None = None,
    ) -> NotificacionWhatsApp:
        """RN-18: webhook ``ENVIADO -> ENTREGADO | FALLIDO`` conservando la referencia."""
        if estado not in _ESTADOS_WEBHOOK:
            raise NotificacionException("El webhook solo admite los estados ENTREGADO o FALLIDO.")
        if notificacion.estado == estado:
            return notificacion
        if notificacion.estado != EstadoNotificacion.ENVIADO:
            raise NotificacionException(
                f"Solo una notificación ENVIADO puede pasar a {estado}; "
                f"estado actual: {notificacion.estado}."
            )
        return replace(
            notificacion,
            estado=estado,
            referencia_proveedor=referencia or notificacion.referencia_proveedor,
            detalle_error=detalle_error if estado == EstadoNotificacion.FALLIDO else None,
            actualizado_en=ahora,
        )
