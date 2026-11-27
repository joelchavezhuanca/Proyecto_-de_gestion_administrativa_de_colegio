"""Repositorios de infraestructura para control de pagos, alertas silenciosas y WhatsApp."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.dominio.notificaciones import EstadoNotificacion, NotificacionWhatsApp, TipoNotificacion
from src.dominio.pagos import AlertaSilenciosaPago, EstadoObligacion, ObligacionPago
from src.infraestructura.modelos import (
    AlertaPagoSilenciosaModel,
    NotificacionWhatsappModel,
    ObligacionPagoModel,
)

ZONA_LIMA = timezone(timedelta(hours=-5), name="America/Lima")


def _normalizar_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZONA_LIMA)
    return dt.astimezone(ZONA_LIMA)


class RepositorioPagos:
    """Acceso a datos de obligaciones económicas y alertas de pago silenciosas (PBI-07)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    # -- Obligaciones de pago -------------------------------------------
    @staticmethod
    def _obligacion_a_dominio(modelo: ObligacionPagoModel) -> ObligacionPago:
        return ObligacionPago(
            id=modelo.id,
            alumno_id=modelo.estudiante_id,
            concepto=modelo.concepto,
            monto=Decimal(str(modelo.monto)),
            fecha_vencimiento=modelo.fecha_vencimiento,
            estado=EstadoObligacion(modelo.estado),
            pagado_en=_normalizar_dt(modelo.pagado_en),
            motivo_exoneracion=modelo.motivo_exoneracion,
        )

    def guardar_obligacion(self, obligacion: ObligacionPago) -> ObligacionPago:
        modelo = self.sesion.get(ObligacionPagoModel, obligacion.id)
        if modelo is None:
            modelo = ObligacionPagoModel(
                id=obligacion.id,
                estudiante_id=obligacion.alumno_id,
                concepto=obligacion.concepto,
                monto=obligacion.monto,
                fecha_vencimiento=obligacion.fecha_vencimiento,
                estado=obligacion.estado.value,
                pagado_en=obligacion.pagado_en,
                motivo_exoneracion=obligacion.motivo_exoneracion,
            )
            self.sesion.add(modelo)
        else:
            modelo.concepto = obligacion.concepto
            modelo.monto = obligacion.monto
            modelo.fecha_vencimiento = obligacion.fecha_vencimiento
            modelo.estado = obligacion.estado.value
            modelo.pagado_en = obligacion.pagado_en
            modelo.motivo_exoneracion = obligacion.motivo_exoneracion

        self.sesion.flush()
        return self._obligacion_a_dominio(modelo)

    def obtener_obligacion_por_id(self, obligacion_id: str) -> ObligacionPago | None:
        modelo = self.sesion.get(ObligacionPagoModel, obligacion_id)
        return self._obligacion_a_dominio(modelo) if modelo else None

    def listar_obligaciones_alumno(
        self,
        alumno_id: int,
        estados: Sequence[EstadoObligacion] | None = None,
    ) -> list[ObligacionPago]:
        stmt = select(ObligacionPagoModel).where(ObligacionPagoModel.estudiante_id == alumno_id)
        if estados:
            valores = [e.value if isinstance(e, EstadoObligacion) else str(e) for e in estados]
            stmt = stmt.where(ObligacionPagoModel.estado.in_(valores))

        modelos = self.sesion.scalars(
            stmt.order_by(ObligacionPagoModel.fecha_vencimiento.asc())
        ).all()
        return [self._obligacion_a_dominio(m) for m in modelos]

    def obtener_obligaciones_vencidas(
        self, alumno_id: int, fecha_referencia: date
    ) -> list[ObligacionPago]:
        modelos = self.sesion.scalars(
            select(ObligacionPagoModel)
            .where(
                ObligacionPagoModel.estudiante_id == alumno_id,
                ObligacionPagoModel.estado == EstadoObligacion.PENDIENTE.value,
                ObligacionPagoModel.fecha_vencimiento < fecha_referencia,
            )
            .order_by(ObligacionPagoModel.fecha_vencimiento.asc())
        ).all()
        return [self._obligacion_a_dominio(m) for m in modelos]

    def marcar_como_pagada(self, obligacion_id: str, pagado_en: datetime) -> ObligacionPago:
        modelo = self.sesion.get(ObligacionPagoModel, obligacion_id)
        if modelo is None:
            raise ValueError(f"No existe la obligación con id '{obligacion_id}'.")

        modelo.estado = EstadoObligacion.PAGADO.value
        modelo.pagado_en = pagado_en
        self.sesion.flush()
        return self._obligacion_a_dominio(modelo)

    def exonerar_obligacion(self, obligacion_id: str, motivo: str) -> ObligacionPago:
        modelo = self.sesion.get(ObligacionPagoModel, obligacion_id)
        if modelo is None:
            raise ValueError(f"No existe la obligación con id '{obligacion_id}'.")

        modelo.estado = EstadoObligacion.EXONERADO.value
        modelo.motivo_exoneracion = motivo
        self.sesion.flush()
        return self._obligacion_a_dominio(modelo)

    # -- Alertas silenciosas de pago ------------------------------------
    @staticmethod
    def _alerta_a_dominio(modelo: AlertaPagoSilenciosaModel) -> AlertaSilenciosaPago:
        return AlertaSilenciosaPago(
            id=modelo.id,
            alumno_id=modelo.estudiante_id,
            asistencia_id=modelo.asistencia_id,
            fecha_escolar=modelo.fecha_escolar,
            cantidad_obligaciones_vencidas=modelo.cantidad_obligaciones_vencidas,
            monto_vencido_total=Decimal(str(modelo.monto_vencido_total)),
            revisada=modelo.revisada,
            creado_en=_normalizar_dt(modelo.creado_en),
        )

    def guardar_alerta(self, alerta: AlertaSilenciosaPago) -> AlertaSilenciosaPago:
        modelo = self.sesion.get(AlertaPagoSilenciosaModel, alerta.id)
        if modelo is None:
            modelo = AlertaPagoSilenciosaModel(
                id=alerta.id,
                estudiante_id=alerta.alumno_id,
                asistencia_id=alerta.asistencia_id,
                fecha_escolar=alerta.fecha_escolar,
                cantidad_obligaciones_vencidas=alerta.cantidad_obligaciones_vencidas,
                monto_vencido_total=alerta.monto_vencido_total,
                revisada=alerta.revisada,
                creado_en=alerta.creado_en or datetime.now(ZONA_LIMA),
            )
            self.sesion.add(modelo)
        else:
            modelo.cantidad_obligaciones_vencidas = alerta.cantidad_obligaciones_vencidas
            modelo.monto_vencido_total = alerta.monto_vencido_total
            modelo.revisada = alerta.revisada

        self.sesion.flush()
        return self._alerta_a_dominio(modelo)

    def obtener_alerta_por_id(self, alerta_id: str) -> AlertaSilenciosaPago | None:
        modelo = self.sesion.get(AlertaPagoSilenciosaModel, alerta_id)
        return self._alerta_a_dominio(modelo) if modelo else None

    def obtener_alerta_por_asistencia(self, asistencia_id: str) -> AlertaSilenciosaPago | None:
        modelo = self.sesion.scalars(
            select(AlertaPagoSilenciosaModel).where(
                AlertaPagoSilenciosaModel.asistencia_id == asistencia_id
            )
        ).first()
        return self._alerta_a_dominio(modelo) if modelo else None

    def obtener_alerta_por_estudiante_y_fecha(
        self, estudiante_id: int, fecha_escolar: date
    ) -> AlertaSilenciosaPago | None:
        modelo = self.sesion.scalars(
            select(AlertaPagoSilenciosaModel).where(
                AlertaPagoSilenciosaModel.estudiante_id == estudiante_id,
                AlertaPagoSilenciosaModel.fecha_escolar == fecha_escolar,
            )
        ).first()
        return self._alerta_a_dominio(modelo) if modelo else None

    def listar_alertas_alumno(self, alumno_id: int) -> list[AlertaSilenciosaPago]:
        modelos = self.sesion.scalars(
            select(AlertaPagoSilenciosaModel)
            .where(AlertaPagoSilenciosaModel.estudiante_id == alumno_id)
            .order_by(AlertaPagoSilenciosaModel.fecha_escolar.desc())
        ).all()
        return [self._alerta_a_dominio(m) for m in modelos]

    def marcar_alerta_revisada(self, alerta_id: str) -> AlertaSilenciosaPago:
        modelo = self.sesion.get(AlertaPagoSilenciosaModel, alerta_id)
        if modelo is None:
            raise ValueError(f"No existe la alerta con id '{alerta_id}'.")

        modelo.revisada = True
        self.sesion.flush()
        return self._alerta_a_dominio(modelo)


class RepositorioNotificacionesWhatsApp:
    """Acceso a datos de cola de notificaciones WhatsApp con clave de idempotencia (PBI-17)."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    @staticmethod
    def _a_dominio(modelo: NotificacionWhatsappModel) -> NotificacionWhatsApp:
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
            creado_en=_normalizar_dt(modelo.creado_en),  # type: ignore[arg-type]
            actualizado_en=_normalizar_dt(modelo.actualizado_en),  # type: ignore[arg-type]
        )

    def guardar(self, notificacion: NotificacionWhatsApp) -> NotificacionWhatsApp:
        modelo = self.sesion.get(NotificacionWhatsappModel, notificacion.id)
        if modelo is None:
            modelo = NotificacionWhatsappModel(
                id=notificacion.id,
                clave_idempotencia=notificacion.clave_idempotencia,
                evento_origen_id=notificacion.evento_origen_id,
                asistencia_id=notificacion.asistencia_id,
                estudiante_id=notificacion.alumno_id,
                fecha_escolar=notificacion.fecha_escolar,
                apoderado_nombre=notificacion.apoderado_nombre,
                telefono_destino=notificacion.telefono_destino,
                tipo=notificacion.tipo.value,
                plantilla=notificacion.plantilla,
                contenido=notificacion.contenido,
                estado=notificacion.estado.value,
                intentos=notificacion.intentos,
                referencia_proveedor=notificacion.referencia_proveedor,
                detalle_error=notificacion.detalle_error,
                creado_en=notificacion.creado_en,
                actualizado_en=notificacion.actualizado_en,
            )
            self.sesion.add(modelo)
        else:
            modelo.estado = notificacion.estado.value
            modelo.intentos = notificacion.intentos
            modelo.referencia_proveedor = notificacion.referencia_proveedor
            modelo.detalle_error = notificacion.detalle_error
            modelo.actualizado_en = notificacion.actualizado_en

        self.sesion.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, notificacion_id: str) -> NotificacionWhatsApp | None:
        modelo = self.sesion.get(NotificacionWhatsappModel, notificacion_id)
        return self._a_dominio(modelo) if modelo else None

    def obtener_por_clave_idempotencia(self, clave: str) -> NotificacionWhatsApp | None:
        modelo = self.sesion.scalars(
            select(NotificacionWhatsappModel).where(
                NotificacionWhatsappModel.clave_idempotencia == clave.strip()
            )
        ).first()
        return self._a_dominio(modelo) if modelo else None

    def listar_por_alumno(self, alumno_id: int, limite: int = 50) -> list[NotificacionWhatsApp]:
        modelos = self.sesion.scalars(
            select(NotificacionWhatsappModel)
            .where(NotificacionWhatsappModel.estudiante_id == alumno_id)
            .order_by(NotificacionWhatsappModel.creado_en.desc())
            .limit(limite)
        ).all()
        return [self._a_dominio(m) for m in modelos]

    def listar_por_fecha(self, fecha_escolar: date) -> list[NotificacionWhatsApp]:
        modelos = self.sesion.scalars(
            select(NotificacionWhatsappModel)
            .where(NotificacionWhatsappModel.fecha_escolar == fecha_escolar)
            .order_by(NotificacionWhatsappModel.creado_en.asc())
        ).all()
        return [self._a_dominio(m) for m in modelos]

    def listar_pendientes(self, limite: int = 100) -> list[NotificacionWhatsApp]:
        modelos = self.sesion.scalars(
            select(NotificacionWhatsappModel)
            .where(NotificacionWhatsappModel.estado == EstadoNotificacion.PENDIENTE.value)
            .order_by(NotificacionWhatsappModel.creado_en.asc())
            .limit(limite)
        ).all()
        return [self._a_dominio(m) for m in modelos]

    def actualizar_estado(
        self,
        notificacion_id: str,
        nuevo_estado: EstadoNotificacion,
        intentos: int,
        referencia: str | None = None,
        detalle_error: str | None = None,
        actualizado_en: datetime | None = None,
    ) -> NotificacionWhatsApp:
        modelo = self.sesion.get(NotificacionWhatsappModel, notificacion_id)
        if modelo is None:
            raise ValueError(f"No existe la notificación con id '{notificacion_id}'.")

        modelo.estado = nuevo_estado.value
        modelo.intentos = intentos
        modelo.referencia_proveedor = referencia
        modelo.detalle_error = detalle_error
        modelo.actualizado_en = actualizado_en or datetime.now(ZONA_LIMA)

        self.sesion.flush()
        return self._a_dominio(modelo)
