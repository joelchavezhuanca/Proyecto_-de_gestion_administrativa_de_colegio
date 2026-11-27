"""Adaptadores de envío de WhatsApp para avisar al apoderado (PBI-17).

Implementa ``PuertoNotificadorWhatsApp`` del dominio con dos variantes:

* ``NotificadorSimulado``: modo local/pruebas, no usa red.
* ``NotificadorMetaCloud``: envía por HTTPS a Graph API de Meta con
  ``urllib.request`` y timeout estricto de 5 s. Ante cualquier error HTTP o de
  red devuelve ``ResultadoEnvioProveedor(exitoso=False, ...)`` sin propagar la
  excepción.

``WorkerNotificacionesAsincrono``: encola envíos en segundo plano con
``ThreadPoolExecutor(max_workers=2)`` garantizando retorno en < 5 ms.

Variables de entorno requeridas para Meta Cloud API:
  * ``META_WHATSAPP_TOKEN``           – Bearer token de acceso.
  * ``META_WHATSAPP_PHONE_NUMBER_ID`` – ID del número de teléfono registrado.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from src.dominio.notificaciones import (
    EstadoNotificacion,
    NotificacionWhatsApp,
    ResultadoEnvioProveedor,
)

logger = logging.getLogger(__name__)

# Timeout estricto para la llamada HTTP a Meta (< 5 s según PBI-17).
_TIMEOUT_META_SEGUNDOS = 5

# Versión de la Graph API de Meta que usamos.
_VERSION_API = "v21.0"


# ---------------------------------------------------------------------------
# Adaptador simulado (pruebas / local)
# ---------------------------------------------------------------------------


class NotificadorSimulado:
    """No realiza llamadas de red; devuelve siempre ENVIADO con referencia sintética.

    Implementa ``PuertoNotificadorWhatsApp`` para uso en pruebas y entornos
    locales donde no se dispone de credenciales de Meta.
    """

    def enviar(self, notificacion: NotificacionWhatsApp) -> ResultadoEnvioProveedor:
        referencia = f"sim-{uuid.uuid4().hex[:12]}"
        logger.info(
            "WhatsApp simulado → %s | ref=%s | contenido=%r",
            notificacion.telefono_destino,
            referencia,
            notificacion.contenido[:60],
        )
        return ResultadoEnvioProveedor(
            exitoso=True,
            estado_reportado=EstadoNotificacion.ENVIADO,
            referencia=referencia,
        )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _describir_error_http(error: urllib.error.HTTPError) -> str:
    """Lee hasta 400 bytes del cuerpo del error HTTP para diagnóstico."""
    try:
        cuerpo = error.read().decode("utf-8", errors="replace")[:400]
    except Exception:  # noqa: BLE001
        cuerpo = ""
    return f"HTTP {error.code}: {cuerpo}".strip()


def _publicar_json(url: str, cuerpo: dict, token: str) -> dict:
    """POST JSON a *url* con Bearer *token*; devuelve el JSON de respuesta."""
    datos = json.dumps(cuerpo).encode("utf-8")
    solicitud = urllib.request.Request(
        url,
        data=datos,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(solicitud, timeout=_TIMEOUT_META_SEGUNDOS) as respuesta:
        contenido = respuesta.read().decode("utf-8") or "{}"
    return json.loads(contenido)


# ---------------------------------------------------------------------------
# Adaptador Meta Cloud API
# ---------------------------------------------------------------------------


class NotificadorMetaCloud:
    """Envía mensajes de WhatsApp a través de la Graph API de Meta Cloud.

    * Usa ``urllib.request`` sin dependencias externas.
    * Timeout estricto de ``_TIMEOUT_META_SEGUNDOS`` (≤ 5 s).
    * Nunca lanza excepciones no controladas: ante cualquier error HTTP o de
      red devuelve ``ResultadoEnvioProveedor(exitoso=False, ...)``.

    Parámetros
    ----------
    token:
        Bearer token de acceso (``META_WHATSAPP_TOKEN``).
    phone_number_id:
        ID del número de teléfono registrado (``META_WHATSAPP_PHONE_NUMBER_ID``).
    version_api:
        Versión de la Graph API (``v21.0`` por defecto).
    """

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        version_api: str = _VERSION_API,
    ) -> None:
        self._token = token
        self._url = (
            f"https://graph.facebook.com/{version_api}/{phone_number_id}/messages"
        )

    # ------------------------------------------------------------------
    # Construcción del payload
    # ------------------------------------------------------------------

    def _construir_cuerpo(self, notificacion: NotificacionWhatsApp) -> dict:
        """Genera el payload para la Graph API usando la plantilla del dominio."""
        destino = (notificacion.telefono_destino or "").lstrip("+")
        return {
            "messaging_product": "whatsapp",
            "to": destino,
            "type": "template",
            "template": {
                "name": notificacion.plantilla,
                "language": {"code": "es"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": notificacion.contenido}
                        ],
                    }
                ],
            },
        }

    # ------------------------------------------------------------------
    # Puerto principal
    # ------------------------------------------------------------------

    def enviar(self, notificacion: NotificacionWhatsApp) -> ResultadoEnvioProveedor:
        """Envía *notificacion* a Meta Cloud; captura todos los errores de red/HTTP."""
        try:
            datos = _publicar_json(
                self._url,
                self._construir_cuerpo(notificacion),
                self._token,
            )
        except urllib.error.HTTPError as exc:
            detalle = _describir_error_http(exc)
            logger.warning("Meta Cloud API → error HTTP: %s", detalle)
            return ResultadoEnvioProveedor(
                exitoso=False,
                estado_reportado=EstadoNotificacion.FALLIDO,
                detalle_error=detalle,
            )
        except Exception as exc:  # noqa: BLE001 — red caída, timeout, etc.
            detalle = str(exc) or exc.__class__.__name__
            logger.warning("Meta Cloud API → error de red: %s", detalle)
            return ResultadoEnvioProveedor(
                exitoso=False,
                estado_reportado=EstadoNotificacion.FALLIDO,
                detalle_error=detalle,
            )

        mensajes = datos.get("messages") or [{}]
        referencia: str | None = mensajes[0].get("id")
        return ResultadoEnvioProveedor(
            exitoso=True,
            estado_reportado=EstadoNotificacion.ENVIADO,
            referencia=referencia,
        )


# ---------------------------------------------------------------------------
# Worker asíncrono (PBI-17 RN-02: nunca bloquea PBI-01)
# ---------------------------------------------------------------------------


class WorkerNotificacionesAsincrono:
    """Encola envíos de WhatsApp en segundo plano mediante un ``ThreadPoolExecutor``.

    Garantías:
    * ``encolar()`` retorna un ``Future`` en < 5 ms (sin bloqueo).
    * El pool usa exactamente ``max_workers=2`` hilos.
    * Los errores de envío se capturan y se pasan al ``callback_resultado``;
      nunca se propagan al hilo principal.

    Uso típico
    ----------
    ::

        worker = WorkerNotificacionesAsincrono(notificador)
        future = worker.encolar(notificacion, callback=lambda r: db.actualizar(r))
        # El hilo principal sigue ejecutándose inmediatamente.
    """

    def __init__(self, notificador: NotificadorSimulado | NotificadorMetaCloud) -> None:
        self._notificador = notificador
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def encolar(
        self,
        notificacion: NotificacionWhatsApp,
        callback_resultado: Callable[[ResultadoEnvioProveedor], None] | None = None,
    ) -> Future[ResultadoEnvioProveedor]:
        """Envía *notificacion* en segundo plano y llama al *callback_resultado* al terminar.

        La llamada retorna inmediatamente (< 5 ms) sin bloquear el hilo de registro
        de asistencia (PBI-01).

        Parámetros
        ----------
        notificacion:
            La notificación de dominio a enviar.
        callback_resultado:
            Función opcional que recibe el ``ResultadoEnvioProveedor`` cuando el
            envío termina (exitoso o no).

        Devuelve
        --------
        ``Future`` que se resolverá con el ``ResultadoEnvioProveedor``.
        """
        future: Future[ResultadoEnvioProveedor] = self._executor.submit(
            self._ejecutar_envio, notificacion, callback_resultado
        )
        return future

    # ------------------------------------------------------------------
    # Lógica interna (hilo secundario)
    # ------------------------------------------------------------------

    def _ejecutar_envio(
        self,
        notificacion: NotificacionWhatsApp,
        callback_resultado: Callable[[ResultadoEnvioProveedor], None] | None,
    ) -> ResultadoEnvioProveedor:
        """Ejecutado en el hilo del pool; captura todos los errores."""
        try:
            resultado = self._notificador.enviar(notificacion)
        except Exception as exc:  # noqa: BLE001
            resultado = ResultadoEnvioProveedor(
                exitoso=False,
                estado_reportado=EstadoNotificacion.FALLIDO,
                detalle_error=str(exc) or exc.__class__.__name__,
            )
        if callback_resultado is not None:
            try:
                callback_resultado(resultado)
            except Exception:  # noqa: BLE001
                logger.exception("Error en callback_resultado de WorkerNotificacionesAsincrono")
        return resultado

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def cerrar(self, esperar: bool = True) -> None:
        """Cierra el executor; útil al finalizar la aplicación."""
        self._executor.shutdown(wait=esperar)

    def __enter__(self) -> WorkerNotificacionesAsincrono:
        return self

    def __exit__(self, *_: object) -> None:
        self.cerrar()


# ---------------------------------------------------------------------------
# Fábrica desde variables de entorno
# ---------------------------------------------------------------------------


def crear_notificador_desde_entorno() -> NotificadorSimulado | NotificadorMetaCloud:
    """Devuelve ``NotificadorMetaCloud`` si las variables de entorno están presentes;
    en caso contrario, ``NotificadorSimulado``.
    """
    token = os.environ.get("META_WHATSAPP_TOKEN", "").strip()
    phone_id = os.environ.get("META_WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if token and phone_id:
        logger.info("WhatsApp: usando NotificadorMetaCloud (phone_id=%s)", phone_id)
        return NotificadorMetaCloud(token=token, phone_number_id=phone_id)
    logger.info("WhatsApp: usando NotificadorSimulado (faltan credenciales Meta)")
    return NotificadorSimulado()
