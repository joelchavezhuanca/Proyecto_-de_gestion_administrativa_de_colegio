"""PBI-06: Emisión y Anulación de Carnet Escolar QR."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Final

from src.dominio.asistencia import UsuarioOperador
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

ZONA_HORARIA_LIMA: Final[timezone] = timezone(timedelta(hours=-5))
MAX_INTENTOS_GENERACION_QR: Final[int] = 10
PREFIJO_CODIGO_QR: Final[str] = "DSV"


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


def _es_entero_positivo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _normalizar_fecha_hora(fecha_hora: datetime) -> datetime:
    """Normaliza una marca temporal al huso institucional America/Lima (UTC-5)."""
    if not isinstance(fecha_hora, datetime):
        raise CarnetException("La fecha y hora del carnet debe ser un datetime válido.")
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _normalizar_motivo(motivo: object) -> MotivoAnulacionCarnet:
    if isinstance(motivo, MotivoAnulacionCarnet):
        return motivo
    texto = str(motivo).strip().upper() if isinstance(motivo, str) else ""
    if not texto:
        raise MotivoAnulacionRequeridoException(
            "El motivo de anulación del carnet es obligatorio."
        )
    try:
        return MotivoAnulacionCarnet(texto)
    except ValueError as exc:
        raise MotivoAnulacionRequeridoException(
            f"El motivo de anulación '{motivo}' no es válido."
        ) from exc


def _normalizar_estado_academico(estado: object) -> EstadoAcademico:
    if isinstance(estado, EstadoAcademico):
        return estado
    texto = str(estado).strip().upper() if isinstance(estado, str) else ""
    try:
        return EstadoAcademico(texto)
    except ValueError as exc:
        raise AlumnoNoHabilitadoCarnetException(
            f"El estado académico '{estado}' no habilita la emisión de carnet."
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

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise CarnetException("El identificador del carnet es obligatorio.")
        if not _es_entero_positivo(self.alumno_id):
            raise CarnetException(
                "El identificador del alumno debe ser un entero positivo."
            )
        if not isinstance(self.codigo_qr, str) or not self.codigo_qr.strip():
            raise CarnetException("El código QR del carnet es obligatorio.")
        if not _es_entero_positivo(self.emitido_por):
            raise CarnetException(
                "El identificador del emisor debe ser un entero positivo."
            )
        if not isinstance(self.emitido_en, datetime):
            raise CarnetException("La fecha de emisión del carnet es obligatoria.")

        estado = self._normalizar_estado(self.estado)
        motivo = self._normalizar_motivo(self.motivo_anulacion)
        detalle = self._normalizar_detalle(self.detalle_anulacion)

        if self.anulado_en is not None and not isinstance(self.anulado_en, datetime):
            raise CarnetException("La fecha de anulación debe ser un datetime válido.")

        if estado == EstadoCarnet.ANULADO:
            if self.anulado_en is None or motivo is None:
                raise CarnetException(
                    "Un carnet anulado requiere fecha y motivo de anulación."
                )
        elif self.anulado_en is not None or motivo is not None or detalle is not None:
            raise CarnetException(
                "Un carnet activo no puede tener datos de anulación."
            )

        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "codigo_qr", self.codigo_qr.strip().upper())
        object.__setattr__(self, "estado", estado)
        object.__setattr__(self, "motivo_anulacion", motivo)
        object.__setattr__(self, "detalle_anulacion", detalle)

    @staticmethod
    def _normalizar_estado(estado: object) -> EstadoCarnet:
        if isinstance(estado, EstadoCarnet):
            return estado
        texto = str(estado).strip().upper() if isinstance(estado, str) else ""
        try:
            return EstadoCarnet(texto)
        except ValueError as exc:
            raise CarnetException(
                f"El estado '{estado}' del carnet no es válido."
            ) from exc

    @staticmethod
    def _normalizar_motivo(motivo: object) -> MotivoAnulacionCarnet | None:
        if motivo is None:
            return None
        if isinstance(motivo, MotivoAnulacionCarnet):
            return motivo
        texto = str(motivo).strip().upper() if isinstance(motivo, str) else ""
        try:
            return MotivoAnulacionCarnet(texto)
        except ValueError as exc:
            raise CarnetException(
                f"El motivo de anulación '{motivo}' no es válido."
            ) from exc

    @staticmethod
    def _normalizar_detalle(detalle: object) -> str | None:
        if detalle is None:
            return None
        if not isinstance(detalle, str):
            raise CarnetException("El detalle de anulación debe ser texto.")
        return detalle.strip() or None


@dataclass(frozen=True)
class ResultadoEmisionCarnet:
    """Resultado atómico de emitir un carnet, con el anterior anulado si aplica."""

    carnet_nuevo: CarnetEscolar
    carnet_anulado: CarnetEscolar | None

    def __post_init__(self) -> None:
        if not isinstance(self.carnet_nuevo, CarnetEscolar):
            raise CarnetException("El carnet nuevo debe ser un CarnetEscolar.")
        if self.carnet_anulado is not None and not isinstance(
            self.carnet_anulado, CarnetEscolar
        ):
            raise CarnetException(
                "El carnet anulado debe ser un CarnetEscolar o None."
            )


class ServicioCarnets:
    """Implementa las reglas de negocio del PBI-06 (Carnet Escolar QR)."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida que el operador esté activo y tenga permiso de gestión (RN-01)."""
        if operador is None or not getattr(operador, "activo", False):
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
        if not _es_entero_positivo(anio_lectivo):
            raise CarnetException("El año lectivo debe ser un entero positivo.")
        existentes = {
            str(codigo).strip().upper() for codigo in (codigos_existentes or ())
        }
        for _ in range(MAX_INTENTOS_GENERACION_QR):
            codigo = (
                f"{PREFIJO_CODIGO_QR}-{anio_lectivo}-"
                f"{secrets.token_hex(6).upper()}"
            )
            if codigo not in existentes:
                return codigo
        raise CarnetException(
            "No fue posible generar un código QR único para el carnet."
        )

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
        if not _es_entero_positivo(alumno_id):
            raise CarnetException(
                "El identificador del alumno debe ser un entero positivo."
            )

        estado = _normalizar_estado_academico(estado_alumno)
        if estado != EstadoAcademico.ACTIVO:
            raise AlumnoNoHabilitadoCarnetException(
                f"El alumno en estado {estado.value} no puede recibir carnet."
            )

        carnets = list(carnets_existentes or ())
        activos = [
            carnet
            for carnet in carnets
            if carnet.alumno_id == alumno_id
            and carnet.estado == EstadoCarnet.ACTIVO
        ]
        if len(activos) > 1:
            raise CarnetException(
                "El alumno tiene más de un carnet activo; "
                "regularice su estado antes de emitir."
            )

        carnet_anulado: CarnetEscolar | None = None
        if activos:
            motivo = _normalizar_motivo(motivo_reposicion)
            carnet_anulado = replace(
                activos[0],
                estado=EstadoCarnet.ANULADO,
                anulado_en=_normalizar_fecha_hora(fecha_hora),
                motivo_anulacion=motivo,
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
            emitido_en=_normalizar_fecha_hora(fecha_hora),
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
        if not isinstance(carnet, CarnetEscolar):
            raise CarnetException("El carnet proporcionado no es válido.")
        if carnet.estado == EstadoCarnet.ANULADO:
            raise CarnetYaAnuladoException("El carnet ya se encuentra anulado.")

        motivo_normalizado = _normalizar_motivo(motivo)
        return replace(
            carnet,
            estado=EstadoCarnet.ANULADO,
            anulado_en=_normalizar_fecha_hora(fecha_hora),
            motivo_anulacion=motivo_normalizado,
            detalle_anulacion=detalle,
        )

    @staticmethod
    def validar_carnet_para_ingreso(
        codigo_qr: str,
        carnets_existentes: Collection[CarnetEscolar],
    ) -> CarnetEscolar:
        """Valida un carnet para el registro de asistencia (RN-06)."""
        codigo = codigo_qr.strip().upper() if isinstance(codigo_qr, str) else ""
        if not codigo:
            raise CarnetNoEncontradoException(
                "El código QR del carnet es obligatorio."
            )
        for carnet in carnets_existentes or ():
            if carnet.codigo_qr.strip().upper() == codigo:
                if carnet.estado == EstadoCarnet.ANULADO:
                    raise CarnetInactivoOAnuladoException(
                        "El carnet se encuentra anulado y no habilita el ingreso."
                    )
                return carnet
        raise CarnetNoEncontradoException(
            f"No existe un carnet con el código QR '{codigo_qr}'."
        )
