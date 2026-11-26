"""PBI-07: Control de Pagos e Ingreso (Alerta Silenciosa)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from src.dominio.asistencia import EventoAsistenciaConfirmada, UsuarioOperador
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)


class EstadoObligacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"
    VENCIDO = "VENCIDO"
    EXONERADO = "EXONERADO"


class PagosException(Exception):
    """Excepción base del dominio de pagos y alerta silenciosa."""


class PermisoPagosException(PagosException):
    """Lanzada cuando el operador no está activo o carece del permiso requerido."""


class ObligacionInvalidaException(PagosException):
    """Lanzada cuando una obligación de pago tiene datos o estado inválidos."""


class PagoInvalidoException(PagosException):
    """Lanzada cuando una operación de pago o exoneración sobre deuda no es válida."""


def _codigo_rol(rol: object) -> str:
    valor = getattr(rol, "value", rol)
    return str(valor).strip().upper()


def _validar_texto_no_vacio(valor: object, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ObligacionInvalidaException(
            f"El campo '{campo}' es obligatorio y no puede estar vacío."
        )
    return valor.strip()


def _validar_entero_positivo(valor: object, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ObligacionInvalidaException(
            f"El campo '{campo}' debe ser un entero positivo."
        )
    return valor


def _validar_fecha(valor: object, campo: str) -> date:
    if not isinstance(valor, date) or isinstance(valor, datetime):
        raise ObligacionInvalidaException(
            f"El campo '{campo}' debe ser una fecha válida."
        )
    return valor


def _validar_monto_decimal(valor: object) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, Decimal):
        raise ObligacionInvalidaException(
            "El monto debe proporcionarse como Decimal (nunca float)."
        )
    if not valor.is_finite() or valor <= Decimal("0"):
        raise ObligacionInvalidaException(
            "El monto debe ser un Decimal finito mayor a cero."
        )
    return valor


@dataclass(frozen=True)
class ObligacionPago:
    """Representa una obligación económica escolar asignada a un alumno."""

    id: str
    alumno_id: int
    concepto: str
    monto: Decimal
    fecha_vencimiento: date
    estado: EstadoObligacion = EstadoObligacion.PENDIENTE
    pagado_en: datetime | None = None
    motivo_exoneracion: str | None = None

    def __post_init__(self) -> None:
        id_limpio = _validar_texto_no_vacio(self.id, "id")
        _validar_entero_positivo(self.alumno_id, "alumno_id")
        concepto_limpio = _validar_texto_no_vacio(self.concepto, "concepto")
        _validar_monto_decimal(self.monto)
        _validar_fecha(self.fecha_vencimiento, "fecha_vencimiento")
        if not isinstance(self.estado, EstadoObligacion):
            raise ObligacionInvalidaException("El estado de la obligación no es válido.")

        object.__setattr__(self, "id", id_limpio)
        object.__setattr__(self, "concepto", concepto_limpio)


@dataclass(frozen=True)
class AlertaSilenciosaPago:
    """Alerta interna no bloqueante generada al confirmar asistencia con deuda vencida."""

    id: str
    alumno_id: int
    asistencia_id: str
    fecha_escolar: date
    cantidad_obligaciones_vencidas: int
    monto_vencido_total: Decimal
    revisada: bool = False
    creado_en: datetime | None = None


class ServicioPagos:
    """Implementa las reglas de negocio del PBI-07 (Pagos y Alerta Silenciosa)."""

    @staticmethod
    def _validar_operador(
        operador: UsuarioOperador,
        permiso: PermisoOperacion,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        if not operador.activo:
            raise PermisoPagosException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol, permiso, roles=roles
        ):
            raise PermisoPagosException(
                f"El rol {_codigo_rol(operador.rol)} no está autorizado para "
                f"la operación '{permiso.value}'."
            )

    @staticmethod
    def registrar_obligacion(
        operador: UsuarioOperador,
        alumno_id: int,
        concepto: str,
        monto: Decimal,
        fecha_vencimiento: date,
        roles: Sequence[Rol] | None = None,
    ) -> ObligacionPago:
        """Registra una nueva obligación económica pendiente para un alumno (RN-01, RN-03)."""
        ServicioPagos._validar_operador(operador, PermisoOperacion.GESTIONAR_PAGOS, roles)
        return ObligacionPago(
            id=f"obl-{uuid.uuid4().hex[:12]}",
            alumno_id=alumno_id,
            concepto=concepto,
            monto=monto,
            fecha_vencimiento=fecha_vencimiento,
            estado=EstadoObligacion.PENDIENTE,
        )

    @staticmethod
    def registrar_pago(
        operador: UsuarioOperador,
        obligacion: ObligacionPago,
        fecha_hora: datetime,
        roles: Sequence[Rol] | None = None,
    ) -> ObligacionPago:
        """Registra el pago de una obligación pendiente o vencida (RN-01, RN-06)."""
        ServicioPagos._validar_operador(operador, PermisoOperacion.GESTIONAR_PAGOS, roles)
        if not isinstance(obligacion, ObligacionPago):
            raise PagoInvalidoException("La obligación proporcionada no es válida.")
        if not isinstance(fecha_hora, datetime):
            raise PagoInvalidoException("La fecha y hora del pago debe ser un datetime válido.")
        if obligacion.estado in (EstadoObligacion.PAGADO, EstadoObligacion.EXONERADO):
            raise PagoInvalidoException(
                f"No se puede registrar pago para una obligación en estado {obligacion.estado.value}."
            )
        return replace(
            obligacion,
            estado=EstadoObligacion.PAGADO,
            pagado_en=fecha_hora,
        )

    @staticmethod
    def exonerar_obligacion(
        operador: UsuarioOperador,
        obligacion: ObligacionPago,
        motivo: str,
        roles: Sequence[Rol] | None = None,
    ) -> ObligacionPago:
        """Exonera una obligación pendiente o vencida con motivo obligatorio (RN-01, RN-06)."""
        ServicioPagos._validar_operador(operador, PermisoOperacion.GESTIONAR_PAGOS, roles)
        if not isinstance(obligacion, ObligacionPago):
            raise ObligacionInvalidaException("La obligación proporcionada no es válida.")
        motivo_limpio = _validar_texto_no_vacio(motivo, "motivo")
        if obligacion.estado == EstadoObligacion.PAGADO:
            raise PagoInvalidoException(
                "No se puede exonerar una obligación que ya se encuentra PAGADO."
            )
        return replace(
            obligacion,
            estado=EstadoObligacion.EXONERADO,
            motivo_exoneracion=motivo_limpio,
        )

    @staticmethod
    def obligaciones_vencidas(
        alumno_id: int,
        obligaciones: Iterable[ObligacionPago],
        fecha_referencia: date,
    ) -> list[ObligacionPago]:
        """Devuelve las obligaciones vencidas del alumno a la fecha de referencia (RN-04)."""
        return [
            obligacion
            for obligacion in obligaciones
            if obligacion.alumno_id == alumno_id
            and (
                obligacion.estado == EstadoObligacion.VENCIDO
                or (
                    obligacion.estado == EstadoObligacion.PENDIENTE
                    and obligacion.fecha_vencimiento < fecha_referencia
                )
            )
        ]

    @staticmethod
    def evaluar_alerta_silenciosa(
        evento: EventoAsistenciaConfirmada,
        obligaciones: Iterable[ObligacionPago],
        alertas_existentes: Iterable[AlertaSilenciosaPago],
        ahora: datetime | None = None,
    ) -> AlertaSilenciosaPago | None:
        """Evalúa si corresponde emitir una alerta silenciosa sin bloquear el ingreso (RN-02).

        Cualquier error interno es contenido para garantizar que un fallo de pagos
        jamás afecte el flujo de confirmación de asistencia.
        """
        try:
            if not isinstance(evento, EventoAsistenciaConfirmada):
                return None

            existe_alerta = any(
                alerta.alumno_id == evento.alumno_id
                and alerta.fecha_escolar == evento.fecha_escolar
                for alerta in alertas_existentes
            )
            if existe_alerta:
                return None

            vencidas = ServicioPagos.obligaciones_vencidas(
                alumno_id=evento.alumno_id,
                obligaciones=obligaciones,
                fecha_referencia=evento.fecha_escolar,
            )
            if not vencidas:
                return None

            monto_total = sum((obligacion.monto for obligacion in vencidas), Decimal("0"))
            return AlertaSilenciosaPago(
                id=f"alr-{uuid.uuid4().hex[:12]}",
                alumno_id=evento.alumno_id,
                asistencia_id=evento.asistencia_id,
                fecha_escolar=evento.fecha_escolar,
                cantidad_obligaciones_vencidas=len(vencidas),
                monto_vencido_total=monto_total,
                revisada=False,
                creado_en=ahora,
            )
        except Exception:
            return None

    @staticmethod
    def consultar_alertas(
        operador: UsuarioOperador,
        alertas: Iterable[AlertaSilenciosaPago],
        fecha: date | None = None,
        solo_no_revisadas: bool = False,
        roles: Sequence[Rol] | None = None,
    ) -> list[AlertaSilenciosaPago]:
        """Consulta alertas silenciosas según permisos y filtros opcionales (RN-01)."""
        ServicioPagos._validar_operador(operador, PermisoOperacion.VER_ALERTA_PAGOS, roles)
        return [
            alerta
            for alerta in alertas
            if (fecha is None or alerta.fecha_escolar == fecha)
            and (not solo_no_revisadas or not alerta.revisada)
        ]

    @staticmethod
    def marcar_alerta_revisada(
        operador: UsuarioOperador,
        alerta: AlertaSilenciosaPago,
        roles: Sequence[Rol] | None = None,
    ) -> AlertaSilenciosaPago:
        """Marca una alerta silenciosa como revisada de forma inmutable (RN-01)."""
        ServicioPagos._validar_operador(operador, PermisoOperacion.VER_ALERTA_PAGOS, roles)
        if not isinstance(alerta, AlertaSilenciosaPago):
            raise PagosException("La alerta proporcionada no es válida.")
        return replace(alerta, revisada=True)
