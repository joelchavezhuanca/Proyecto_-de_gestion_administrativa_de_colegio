"""Adaptadores de envío de WhatsApp para avisar al apoderado (PBI-17).

El sistema solo depende de la interfaz ``NotificadorWhatsApp``. Por defecto se
usa ``NotificadorSimulado``, que no sale a internet y deja el mensaje
registrado en la bandeja del sistema. Para el envío real basta con definir las
variables de entorno de un proveedor:

* ``WHATSAPP_PROVEEDOR=meta``: WhatsApp Cloud API de Meta.
  ``META_WHATSAPP_TOKEN``, ``META_WHATSAPP_PHONE_NUMBER_ID`` y, para mensajes
  iniciados por el colegio, ``META_WHATSAPP_PLANTILLA`` (plantilla aprobada con
  4 variables: alumno, fecha, hora y estado) y ``META_WHATSAPP_IDIOMA``.
* ``WHATSAPP_PROVEEDOR=twilio``: Twilio WhatsApp.
  ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN`` y ``TWILIO_WHATSAPP_FROM``
  (por ejemplo ``+14155238886`` en el sandbox).

Si faltan variables, se vuelve al modo simulado y se deja constancia en el log.
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

ESTADO_ENVIADO = "ENVIADO"
ESTADO_SIMULADO = "SIMULADO"
ESTADO_ERROR = "ERROR"

TIEMPO_ESPERA_SEGUNDOS = 8


@dataclass(frozen=True)
class MensajeWhatsApp:
    """Mensaje listo para enviar. ``variables`` alimenta las plantillas de Meta."""

    destino: str
    texto: str
    variables: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResultadoEnvio:
    estado: str
    proveedor: str
    referencia: str | None = None
    detalle: str | None = None


class NotificadorWhatsApp(Protocol):
    proveedor: str

    def enviar(self, mensaje: MensajeWhatsApp) -> ResultadoEnvio: ...


class NotificadorSimulado:
    """No envía nada fuera del sistema: el mensaje queda en la bandeja."""

    proveedor = "SIMULADO"

    def enviar(self, mensaje: MensajeWhatsApp) -> ResultadoEnvio:
        logger.info("WhatsApp simulado a %s: %s", mensaje.destino, mensaje.texto)
        return ResultadoEnvio(estado=ESTADO_SIMULADO, proveedor=self.proveedor)


def _publicar(url: str, cuerpo: bytes, cabeceras: dict[str, str]) -> dict:
    solicitud = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method="POST")
    with urllib.request.urlopen(solicitud, timeout=TIEMPO_ESPERA_SEGUNDOS) as respuesta:
        contenido = respuesta.read().decode("utf-8") or "{}"
    return json.loads(contenido)


def _describir_error(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            cuerpo = error.read().decode("utf-8")[:300]
        except Exception:  # noqa: BLE001 - solo es información de diagnóstico
            cuerpo = ""
        return f"HTTP {error.code}: {cuerpo}".strip()
    return str(error) or error.__class__.__name__


class NotificadorMetaCloud:
    """WhatsApp Cloud API (graph.facebook.com)."""

    proveedor = "META"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        plantilla: str = "",
        idioma: str = "es",
        version_api: str = "v21.0",
    ) -> None:
        self._token = token
        self._url = f"https://graph.facebook.com/{version_api}/{phone_number_id}/messages"
        self._plantilla = plantilla
        self._idioma = idioma

    def construir_cuerpo(self, mensaje: MensajeWhatsApp) -> dict:
        destino = mensaje.destino.lstrip("+")
        if self._plantilla:
            return {
                "messaging_product": "whatsapp",
                "to": destino,
                "type": "template",
                "template": {
                    "name": self._plantilla,
                    "language": {"code": self._idioma},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": valor} for valor in mensaje.variables
                            ],
                        }
                    ],
                },
            }
        # Sin plantilla, Meta solo entrega texto libre dentro de la ventana de 24 h.
        return {
            "messaging_product": "whatsapp",
            "to": destino,
            "type": "text",
            "text": {"body": mensaje.texto},
        }

    def enviar(self, mensaje: MensajeWhatsApp) -> ResultadoEnvio:
        try:
            datos = _publicar(
                self._url,
                json.dumps(self.construir_cuerpo(mensaje)).encode("utf-8"),
                {
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
        except Exception as error:  # noqa: BLE001 - el registro de asistencia no debe caer
            logger.warning("Fallo el envío por Meta: %s", error)
            return ResultadoEnvio(ESTADO_ERROR, self.proveedor, detalle=_describir_error(error))
        mensajes = datos.get("messages") or [{}]
        return ResultadoEnvio(ESTADO_ENVIADO, self.proveedor, referencia=mensajes[0].get("id"))


class NotificadorTwilio:
    """Twilio Programmable Messaging con el canal WhatsApp."""

    proveedor = "TWILIO"

    def __init__(self, account_sid: str, auth_token: str, remitente: str) -> None:
        self._url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        )
        credencial = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        self._autorizacion = f"Basic {credencial}"
        if not remitente.startswith("whatsapp:"):
            remitente = f"whatsapp:{remitente}"
        self._remitente = remitente

    def enviar(self, mensaje: MensajeWhatsApp) -> ResultadoEnvio:
        cuerpo = urllib.parse.urlencode(
            {
                "From": self._remitente,
                "To": f"whatsapp:{mensaje.destino}",
                "Body": mensaje.texto,
            }
        ).encode("utf-8")
        try:
            datos = _publicar(
                self._url,
                cuerpo,
                {
                    "Authorization": self._autorizacion,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except Exception as error:  # noqa: BLE001 - el registro de asistencia no debe caer
            logger.warning("Fallo el envío por Twilio: %s", error)
            return ResultadoEnvio(ESTADO_ERROR, self.proveedor, detalle=_describir_error(error))
        return ResultadoEnvio(ESTADO_ENVIADO, self.proveedor, referencia=datos.get("sid"))


def crear_notificador_desde_entorno(
    entorno: Mapping[str, str] | None = None,
) -> NotificadorWhatsApp:
    """Elige el proveedor según ``WHATSAPP_PROVEEDOR`` (simulado por defecto)."""
    entorno = os.environ if entorno is None else entorno
    proveedor = (entorno.get("WHATSAPP_PROVEEDOR") or "simulado").strip().lower()

    if proveedor == "meta":
        token = entorno.get("META_WHATSAPP_TOKEN", "")
        numero = entorno.get("META_WHATSAPP_PHONE_NUMBER_ID", "")
        if token and numero:
            return NotificadorMetaCloud(
                token,
                numero,
                plantilla=entorno.get("META_WHATSAPP_PLANTILLA", ""),
                idioma=entorno.get("META_WHATSAPP_IDIOMA", "es"),
            )
        logger.warning("Faltan META_WHATSAPP_TOKEN o META_WHATSAPP_PHONE_NUMBER_ID; modo simulado.")
    elif proveedor == "twilio":
        sid = entorno.get("TWILIO_ACCOUNT_SID", "")
        token = entorno.get("TWILIO_AUTH_TOKEN", "")
        remitente = entorno.get("TWILIO_WHATSAPP_FROM", "")
        if sid and token and remitente:
            return NotificadorTwilio(sid, token, remitente)
        logger.warning("Faltan credenciales de Twilio; se usa el modo simulado.")
    elif proveedor != "simulado":
        logger.warning("WHATSAPP_PROVEEDOR=%s no es válido; se usa el modo simulado.", proveedor)

    return NotificadorSimulado()
