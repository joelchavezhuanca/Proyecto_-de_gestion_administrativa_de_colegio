"""PBI-06: Emisión y Anulación de Carnet Escolar QR."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from src.dominio.asistencia import UsuarioOperador
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)


class EstadoCarnet(StrEnum):
    """Estados posibles de un carnet escolar."""

    ACTIVO = "ACTIVO"
    ANULADO = "ANULADO"


class MotivoAnulacionCarnet(StrEnum):
    """Motivos oficiales para anular o reponer un carnet escolar."""

    EXTRAVIO = "EXTRAVIO"
    DANO = "DANO"
    CAMBIO_DATOS = "CAMBIO_DATOS"
    BAJA_ESTUDIANTE = "BAJA_ESTUDIANTE"
    OTRO = "OTRO"


class CarnetException(Exception):
    """Excepción base del dominio de carnets escolares."""


class PermisoCarnetException(CarnetException):
    """Lanzada cuando el operador no está activo o carece de permiso."""


class AlumnoNoHabilitadoCarnetException(CarnetException):
    """Lanzada cuando el estado académico del alumno no permite emitir carnet."""


class CarnetNoEncontradoException(CarnetException):
    """Lanzada cuando el código QR no corresponde a ningún carnet registrado."""


class CarnetYaAnuladoException(CarnetException):
    """Lanzada al intentar anular un carnet que ya está anulado."""


class MotivoAnulacionRequeridoException(CarnetException):
    """Lanzada cuando falta el motivo de anulación o no es válido."""


class CarnetInactivoOAnuladoException(CarnetException):
    """Lanzada cuando un carnet anulado intenta usarse para el ingreso."""


def _validar_motivo(motivo: object) -> MotivoAnulacionCarnet:
    if isinstance(motivo, MotivoAnulacionCarnet):
        return motivo
    try:
        return MotivoAnulacionCarnet(motivo)
    except (TypeError, ValueError) as exc:
        raise MotivoAnulacionRequeridoException(
            f"El motivo de anulación '{motivo}' no es válido."
        ) from exc


@dataclass(frozen=True)
class CarnetEscolar:
    """Carnet escolar con código QR opaco y trazabilidad de emisión/anulación."""

    id: str
    alumno_id: int
    codigo_qr: str
    estado: EstadoCarnet
    emitido_por: int
    emitido_en: datetime
    anulado_en: datetime | None = None
    motivo_anulacion: MotivoAnulacionCarnet | None = None
    detalle_anulacion: str | None = None


@dataclass(frozen=True)
class ResultadoEmisionCarnet:
    """Resultado atómico de emitir un carnet, con el anterior anulado si aplica."""

    carnet_nuevo: CarnetEscolar
    carnet_anulado: CarnetEscolar | None


class ServicioCarnets:
    """Implementa las reglas de negocio del PBI-06 (Carnet Escolar QR)."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida que el operador esté activo y tenga permiso de gestión (RN-01)."""
        if not operador.activo:
            raise PermisoCarnetException(
                "El operador no cuenta con una cuenta activa."
            )
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.GESTIONAR_CARNETS,
            roles=roles,
        ):
            raise PermisoCarnetException(
                "El operador no tiene permiso para gestionar carnets escolares."
            )

    @staticmethod
    def generar_codigo_qr(
        anio_lectivo: int,
        codigos_existentes: Collection[str] = (),
    ) -> str:
        """Genera un código QR opaco y único para el año lectivo (RN-05)."""
        existentes = set(codigos_existentes)
        while True:
            codigo = f"DSV-{anio_lectivo}-{secrets.token_hex(6).upper()}"
            if codigo not in existentes:
                return codigo

    @classmethod
    def emitir_carnet(
        cls,
        operador: UsuarioOperador,
        alumno_id: int,
        estado_alumno: EstadoAcademico | str,
        anio_lectivo: int,
        carnets_existentes: Collection[CarnetEscolar],
        fecha_hora: datetime,
        motivo_reposicion: MotivoAnulacionCarnet | str | None = None,
        detalle_anulacion: str | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> ResultadoEmisionCarnet:
        """Emite un carnet nuevo y anula el activo previo si hay reposición (RN-02 a RN-05)."""
        cls.validar_operador(operador, roles)

        if estado_alumno != EstadoAcademico.ACTIVO and estado_alumno != "ACTIVO":
            raise AlumnoNoHabilitadoCarnetException(
                "Solo los alumnos en estado ACTIVO pueden recibir un carnet escolar."
            )

        carnets = list(carnets_existentes)
        carnet_activo = next(
            (
                carnet
                for carnet in carnets
                if carnet.alumno_id == alumno_id
                and carnet.estado == EstadoCarnet.ACTIVO
            ),
            None,
        )

        carnet_anulado: CarnetEscolar | None = None
        if carnet_activo is not None:
            if motivo_reposicion is None:
                raise MotivoAnulacionRequeridoException(
                    "La reposición de carnet exige un motivo de anulación."
                )
            carnet_anulado = replace(
                carnet_activo,
                estado=EstadoCarnet.ANULADO,
                anulado_en=fecha_hora,
                motivo_anulacion=_validar_motivo(motivo_reposicion),
                detalle_anulacion=detalle_anulacion,
            )

        codigo_qr = cls.generar_codigo_qr(
            anio_lectivo,
            {carnet.codigo_qr for carnet in carnets},
        )
        carnet_nuevo = CarnetEscolar(
            id=f"car-{uuid.uuid4().hex[:12]}",
            alumno_id=alumno_id,
            codigo_qr=codigo_qr,
            estado=EstadoCarnet.ACTIVO,
            emitido_por=operador.id,
            emitido_en=fecha_hora,
        )
        return ResultadoEmisionCarnet(
            carnet_nuevo=carnet_nuevo,
            carnet_anulado=carnet_anulado,
        )

    @classmethod
    def anular_carnet(
        cls,
        operador: UsuarioOperador,
        carnet: CarnetEscolar,
        motivo: MotivoAnulacionCarnet | str,
        fecha_hora: datetime,
        detalle: str | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> CarnetEscolar:
        """Anula un carnet activo dejando su trazabilidad completa (RN-04)."""
        cls.validar_operador(operador, roles)
        if carnet.estado == EstadoCarnet.ANULADO:
            raise CarnetYaAnuladoException("El carnet ya se encuentra anulado.")

        return replace(
            carnet,
            estado=EstadoCarnet.ANULADO,
            anulado_en=fecha_hora,
            motivo_anulacion=motivo,
            detalle_anulacion=detalle,
        )

    @staticmethod
    def validar_carnet_para_ingreso(
        codigo_qr: str,
        carnets_existentes: Collection[CarnetEscolar],
    ) -> CarnetEscolar:
        """Valida un carnet para el registro de asistencia (RN-06)."""
        for carnet in carnets_existentes:
            if carnet.codigo_qr == codigo_qr:
                if carnet.estado == EstadoCarnet.ANULADO:
                    raise CarnetInactivoOAnuladoException(
                        "El carnet se encuentra anulado y no habilita el ingreso."
                    )
                return carnet
        raise CarnetNoEncontradoException(
            f"No existe un carnet con el código QR '{codigo_qr}'."
        )
