"""PBI-16: auditoría inmutable de transacciones.

El módulo es dominio puro: no conoce Flask, SQLAlchemy ni la base de datos.
La persistencia se inyecta como un ``Callable`` para que la capa de aplicación
pueda envolver la operación de negocio y la auditoría en una sola transacción.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from types import MappingProxyType

from src.dominio.asistencia import EventoAuditoria
from src.dominio.usuarios import (
    MATRIZ_PERMISOS,
    EstadoUsuario,
    EventoAuditoriaUsuario,
    PermisoOperacion,
    Usuario,
)

ZONA_HORARIA_LIMA = timezone(timedelta(hours=-5))
HASH_GENESIS = "GENESIS"
LONGITUD_HASH_SHA256 = 64


class AuditoriaException(Exception):
    """Excepción base del módulo de auditoría."""


class DatoSensibleAuditoriaException(AuditoriaException):
    """Lanzada cuando el detalle contiene credenciales o tokens prohibidos."""


class AuditoriaInmutableException(AuditoriaException):
    """Lanzada cuando se intenta modificar o eliminar un evento append-only."""


class ErrorRegistroAuditoriaException(AuditoriaException):
    """Lanzada cuando no se puede persistir el evento y debe revertirse la operación."""


class PermisoAuditoriaException(AuditoriaException):
    """Lanzada cuando el operador no cuenta con el permiso requerido."""


class ResultadoAuditoria(StrEnum):
    CONFIRMADA = "CONFIRMADA"
    FALLIDA = "FALLIDA"


class TipoOperacionAuditoria(StrEnum):
    REGISTRO_ASISTENCIA = "REGISTRO_ASISTENCIA"
    CORRECCION_AUSENTE = "CORRECCION_AUSENTE"
    CREAR_USUARIO = "CREAR_USUARIO"
    MODIFICAR_USUARIO = "MODIFICAR_USUARIO"
    ACTIVAR_CUENTA = "ACTIVAR_CUENTA"
    DESACTIVAR_CUENTA = "DESACTIVAR_CUENTA"
    RESTABLECER_CREDENCIAL = "RESTABLECER_CREDENCIAL"
    CREAR_ROL = "CREAR_ROL"
    MODIFICAR_ROL = "MODIFICAR_ROL"
    ACTIVAR_ROL = "ACTIVAR_ROL"
    DESACTIVAR_ROL = "DESACTIVAR_ROL"
    ELIMINAR_ROL = "ELIMINAR_ROL"
    ASIGNAR_ROL = "ASIGNAR_ROL"
    INICIAR_SESION = "INICIAR_SESION"
    CERRAR_SESION = "CERRAR_SESION"
    ACCESO_DENEGADO = "ACCESO_DENEGADO"
    CIERRE_ESCOLAR = "CIERRE_ESCOLAR"
    EXPORTAR_ASISTENCIA = "EXPORTAR_ASISTENCIA"
    EMITIR_BOLETA = "EMITIR_BOLETA"
    NOTIFICAR_AUSENCIA = "NOTIFICAR_AUSENCIA"
    CONSULTAR_AUDITORIA = "CONSULTAR_AUDITORIA"
    VERIFICAR_INTEGRIDAD = "VERIFICAR_INTEGRIDAD"
    OTRA = "OTRA"


@dataclass(frozen=True)
class ContextoAcademicoAuditoria:
    nivel: str
    grado: str
    seccion: str

    def __post_init__(self) -> None:
        for nombre, valor in (
            ("nivel", self.nivel),
            ("grado", self.grado),
            ("seccion", self.seccion),
        ):
            if not isinstance(valor, str) or not valor.strip():
                raise AuditoriaException(
                    f"El campo '{nombre}' del contexto académico es obligatorio."
                )
            object.__setattr__(self, nombre, valor.strip())


@dataclass(frozen=True)
class RegistroAuditoria:
    id: str
    secuencia: int
    fecha_hora: datetime
    usuario_id: int
    rol_ejecutante: str
    operacion: TipoOperacionAuditoria
    entidad: str
    entidad_id: str
    resultado: ResultadoAuditoria
    detalle: Mapping[str, object] = field(default_factory=dict)
    alumno_id: int | None = None
    metodo_asistencia: str | None = None
    contexto_academico: ContextoAcademicoAuditoria | None = None
    estado_anterior: str | None = None
    estado_nuevo: str | None = None
    motivo: str | None = None
    hash_anterior: str = HASH_GENESIS
    hash_integridad: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise AuditoriaException("El identificador del evento de auditoría es obligatorio.")
        if self.secuencia < 1:
            raise AuditoriaException("La secuencia del evento debe ser mayor o igual a 1.")
        if not isinstance(self.fecha_hora, datetime):
            raise AuditoriaException("La fecha y hora del evento es obligatoria.")
        if self.usuario_id < 0:
            raise AuditoriaException("El identificador del usuario no puede ser negativo.")
        if not isinstance(self.rol_ejecutante, str) or not self.rol_ejecutante.strip():
            raise AuditoriaException("El rol del ejecutante es obligatorio.")

        operacion = self.operacion
        if not isinstance(operacion, TipoOperacionAuditoria):
            try:
                operacion = TipoOperacionAuditoria(str(operacion).upper())
            except ValueError as error:
                raise AuditoriaException(
                    f"Operación de auditoría desconocida: {operacion}"
                ) from error

        resultado = self.resultado
        if not isinstance(resultado, ResultadoAuditoria):
            try:
                resultado = ResultadoAuditoria(str(resultado).upper())
            except ValueError as error:
                raise AuditoriaException(
                    f"Resultado de auditoría desconocido: {resultado}"
                ) from error

        if not isinstance(self.entidad, str) or not self.entidad.strip():
            raise AuditoriaException("La entidad auditada es obligatoria.")
        if self.entidad_id is None or not str(self.entidad_id).strip():
            raise AuditoriaException("El identificador de la entidad auditada es obligatorio.")
        if self.hash_integridad and len(self.hash_integridad) != LONGITUD_HASH_SHA256:
            raise AuditoriaException(
                "El hash de integridad debe tener 64 caracteres hexadecimales."
            )

        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "rol_ejecutante", self.rol_ejecutante.strip().upper())
        object.__setattr__(self, "operacion", operacion)
        object.__setattr__(self, "resultado", resultado)
        object.__setattr__(self, "entidad", self.entidad.strip().upper())
        object.__setattr__(self, "entidad_id", str(self.entidad_id).strip())
        object.__setattr__(self, "fecha_hora", _normalizar_fecha_hora(self.fecha_hora))
        if not isinstance(self.detalle, Mapping):
            raise AuditoriaException("El detalle de auditoría debe ser un mapa de datos.")
        object.__setattr__(self, "detalle", MappingProxyType(dict(self.detalle)))


@dataclass(frozen=True)
class FiltroAuditoria:
    fecha_desde: datetime | None = None
    fecha_hasta: datetime | None = None
    usuario_id: int | None = None
    rol: str | None = None
    operacion: TipoOperacionAuditoria | str | None = None
    entidad: str | None = None
    alumno_id: int | None = None
    resultado: ResultadoAuditoria | None = None

    def __post_init__(self) -> None:
        if self.fecha_desde is not None:
            object.__setattr__(self, "fecha_desde", _normalizar_fecha_hora(self.fecha_desde))
        if self.fecha_hasta is not None:
            object.__setattr__(self, "fecha_hasta", _normalizar_fecha_hora(self.fecha_hasta))
        if (
            self.fecha_desde is not None
            and self.fecha_hasta is not None
            and self.fecha_desde > self.fecha_hasta
        ):
            raise AuditoriaException(
                "El rango de fechas es inválido: fecha_desde no puede ser posterior a fecha_hasta."
            )
        if self.usuario_id is not None and self.usuario_id < 0:
            raise AuditoriaException("El filtro de usuario no puede ser negativo.")
        if self.alumno_id is not None and self.alumno_id < 1:
            raise AuditoriaException("El filtro de alumno debe ser un identificador positivo.")


@dataclass(frozen=True)
class ResultadoVerificacionIntegridad:
    integra: bool
    ids_alterados: tuple[str, ...] = ()
    eventos_faltantes: tuple[int, ...] = ()
    detalle: str = ""


def _normalizar_fecha_hora(fecha_hora: datetime) -> datetime:
    """Normaliza cualquier fecha al huso institucional America/Lima (UTC-5)."""
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _a_jsonable(valor: object) -> object:
    if isinstance(valor, ContextoAcademicoAuditoria):
        return {
            "nivel": valor.nivel,
            "grado": valor.grado,
            "seccion": valor.seccion,
        }
    if isinstance(valor, Mapping):
        return {str(clave): _a_jsonable(item) for clave, item in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [_a_jsonable(item) for item in valor]
    if isinstance(valor, StrEnum):
        return valor.value
    if isinstance(valor, datetime):
        return _normalizar_fecha_hora(valor).isoformat()
    return valor


def _normalizar_clave(clave: str) -> str:
    return clave.strip().lower().replace("-", "_").replace(" ", "_")


class ServicioAuditoria:
    """Registra, consulta y verifica la bitácora inmutable del sistema."""

    CLAVES_SENSIBLES: frozenset[str] = frozenset(
        {
            "password",
            "password_hash",
            "hash_password",
            "salt",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "authorization",
            "cookie",
            "contrasena",
            "contraseña",
        }
    )
    ROLES_SISTEMA: frozenset[str] = frozenset({"SYSTEM", "SYSTEM_CRON"})

    @staticmethod
    def registrar_evento(
        *,
        usuario_id: int,
        rol_ejecutante: str,
        operacion: TipoOperacionAuditoria | str,
        entidad: str,
        entidad_id: str,
        resultado: ResultadoAuditoria,
        fecha_hora: datetime,
        eventos_existentes: Sequence[RegistroAuditoria] = (),
        detalle: Mapping[str, object] | None = None,
        alumno_id: int | None = None,
        metodo_asistencia: str | None = None,
        contexto_academico: ContextoAcademicoAuditoria | None = None,
        estado_anterior: str | None = None,
        estado_nuevo: str | None = None,
        motivo: str | None = None,
        id_evento: str | None = None,
        persistir: Callable[[RegistroAuditoria], None] | None = None,
    ) -> RegistroAuditoria:
        """Crea un evento encadenado por hash y, opcionalmente, lo persiste."""
        rol_normalizado = rol_ejecutante.strip().upper() if isinstance(rol_ejecutante, str) else ""
        if not rol_normalizado:
            raise AuditoriaException("El rol del ejecutante es obligatorio.")
        if usuario_id < 0 or (
            usuario_id == 0 and rol_normalizado not in ServicioAuditoria.ROLES_SISTEMA
        ):
            raise AuditoriaException(
                "El actor de auditoría es inválido: se requiere un usuario positivo "
                "o un proceso SYSTEM/SYSTEM_CRON."
            )

        detalle_normalizado = dict(detalle or {})
        ServicioAuditoria._validar_detalle(detalle_normalizado)

        secuencia = len(eventos_existentes) + 1
        hash_anterior = (
            eventos_existentes[-1].hash_integridad if eventos_existentes else HASH_GENESIS
        )
        if eventos_existentes and not hash_anterior:
            raise AuditoriaException("El evento anterior no cuenta con hash de integridad.")

        registro = RegistroAuditoria(
            id=id_evento or f"aud-{uuid.uuid4().hex[:12]}",
            secuencia=secuencia,
            fecha_hora=fecha_hora,
            usuario_id=usuario_id,
            rol_ejecutante=rol_normalizado,
            operacion=operacion,
            entidad=entidad,
            entidad_id=entidad_id,
            resultado=resultado,
            detalle=detalle_normalizado,
            alumno_id=alumno_id,
            metodo_asistencia=metodo_asistencia,
            contexto_academico=contexto_academico,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            motivo=motivo,
            hash_anterior=hash_anterior,
        )
        registro = _reemplazar_hash(registro, ServicioAuditoria._calcular_hash(registro))

        if persistir is not None:
            try:
                persistir(registro)
            except Exception as error:
                raise ErrorRegistroAuditoriaException(
                    "No fue posible registrar la auditoría; la operación debe revertirse."
                ) from error

        return registro

    @staticmethod
    def verificar_integridad(
        eventos: Sequence[RegistroAuditoria],
        *,
        operador: Usuario,
        total_esperado: int | None = None,
    ) -> ResultadoVerificacionIntegridad:
        """Recalcula la cadena y detecta alteraciones, reordenamientos o borrados."""
        ServicioAuditoria._validar_permiso(
            operador, PermisoOperacion.VERIFICAR_INTEGRIDAD_AUDITORIA
        )

        alterados: list[str] = []
        hash_anterior = HASH_GENESIS
        secuencia_esperada = 1

        for evento in eventos:
            if evento.secuencia != secuencia_esperada:
                alterados.append(evento.id)
            if evento.hash_anterior != hash_anterior:
                alterados.append(evento.id)
            if ServicioAuditoria._calcular_hash(evento) != evento.hash_integridad:
                alterados.append(evento.id)
            hash_anterior = evento.hash_integridad
            secuencia_esperada += 1

        faltantes: tuple[int, ...] = ()
        if total_esperado is not None and total_esperado > len(eventos):
            faltantes = tuple(range(len(eventos) + 1, total_esperado + 1))

        ids_alterados = tuple(dict.fromkeys(alterados))
        integra = not ids_alterados and not faltantes
        if integra:
            detalle = "Cadena de auditoría íntegra."
        elif faltantes:
            detalle = "La cadena presenta eventos faltantes."
        else:
            detalle = "La cadena presenta eventos alterados o fuera de orden."

        return ResultadoVerificacionIntegridad(
            integra=integra,
            ids_alterados=ids_alterados,
            eventos_faltantes=faltantes,
            detalle=detalle,
        )

    @staticmethod
    def consultar_eventos(
        eventos: Sequence[RegistroAuditoria],
        filtro: FiltroAuditoria | None = None,
        *,
        operador: Usuario,
    ) -> list[RegistroAuditoria]:
        """Consulta la bitácora aplicando filtros y validando el permiso del operador."""
        ServicioAuditoria._validar_permiso(operador, PermisoOperacion.CONSULTAR_AUDITORIA)
        criterio = filtro or FiltroAuditoria()

        resultados = []
        for evento in eventos:
            if (
                criterio.fecha_desde is not None
                and evento.fecha_hora < criterio.fecha_desde
            ):
                continue
            if criterio.fecha_hasta is not None and evento.fecha_hora > criterio.fecha_hasta:
                continue
            if criterio.usuario_id is not None and evento.usuario_id != criterio.usuario_id:
                continue
            if criterio.rol is not None and evento.rol_ejecutante != criterio.rol.strip().upper():
                continue
            if criterio.operacion is not None:
                operacion_filtro = getattr(
                    criterio.operacion, "value", str(criterio.operacion)
                ).upper()
                if evento.operacion.value != operacion_filtro:
                    continue
            if criterio.entidad is not None and evento.entidad != criterio.entidad.strip().upper():
                continue
            if criterio.alumno_id is not None and evento.alumno_id != criterio.alumno_id:
                continue
            if criterio.resultado is not None and evento.resultado != criterio.resultado:
                continue
            resultados.append(evento)

        return sorted(resultados, key=lambda evento: evento.secuencia)

    @staticmethod
    def desde_evento_asistencia(
        evento: EventoAuditoria,
        *,
        asistencia_id: str,
        contexto: ContextoAcademicoAuditoria,
        eventos_existentes: Sequence[RegistroAuditoria] = (),
        resultado: ResultadoAuditoria = ResultadoAuditoria.CONFIRMADA,
        persistir: Callable[[RegistroAuditoria], None] | None = None,
    ) -> RegistroAuditoria:
        """Adapta el DTO de auditoría de asistencia al registro inmutable del PBI-16."""
        estado_anterior = evento.estado_anterior.value if evento.estado_anterior else None
        return ServicioAuditoria.registrar_evento(
            usuario_id=evento.usuario_id,
            rol_ejecutante=evento.rol.value,
            operacion=evento.operacion,
            entidad="ASISTENCIA",
            entidad_id=asistencia_id,
            resultado=resultado,
            fecha_hora=evento.fecha_hora,
            eventos_existentes=eventos_existentes,
            detalle={"evento_tipo": evento.evento_tipo},
            alumno_id=evento.alumno_id,
            metodo_asistencia=evento.metodo.value,
            contexto_academico=contexto,
            estado_anterior=estado_anterior,
            estado_nuevo=evento.estado_nuevo.value,
            motivo=evento.motivo,
            id_evento=evento.id,
            persistir=persistir,
        )

    @staticmethod
    def desde_evento_usuario(
        evento: EventoAuditoriaUsuario,
        *,
        rol_ejecutante: str,
        eventos_existentes: Sequence[RegistroAuditoria] = (),
        resultado: ResultadoAuditoria = ResultadoAuditoria.CONFIRMADA,
        persistir: Callable[[RegistroAuditoria], None] | None = None,
    ) -> RegistroAuditoria:
        """Adapta el DTO de auditoría de usuarios al registro inmutable del PBI-16."""
        return ServicioAuditoria.registrar_evento(
            usuario_id=evento.admin_id,
            rol_ejecutante=rol_ejecutante,
            operacion=evento.operacion,
            entidad="USUARIO",
            entidad_id=str(evento.usuario_afectado_id),
            resultado=resultado,
            fecha_hora=evento.fecha_hora,
            eventos_existentes=eventos_existentes,
            detalle=evento.detalle,
            id_evento=evento.id,
            persistir=persistir,
        )

    @staticmethod
    def prohibir_modificacion(*_args: object, **_kwargs: object) -> None:
        """Los eventos son append-only: cualquier modificación debe fallar."""
        raise AuditoriaInmutableException(
            "Los registros de auditoría son inmutables: no se pueden modificar."
        )

    @staticmethod
    def prohibir_eliminacion(*_args: object, **_kwargs: object) -> None:
        """Los eventos son append-only: cualquier eliminación debe fallar."""
        raise AuditoriaInmutableException(
            "Los registros de auditoría son inmutables: no se pueden eliminar."
        )

    @staticmethod
    def _validar_detalle(detalle: object) -> None:
        if isinstance(detalle, Mapping):
            for clave, valor in detalle.items():
                if _normalizar_clave(str(clave)) in ServicioAuditoria.CLAVES_SENSIBLES:
                    raise DatoSensibleAuditoriaException(
                        "El detalle de auditoría no puede almacenar credenciales ni tokens."
                    )
                ServicioAuditoria._validar_detalle(valor)
        elif isinstance(detalle, (list, tuple, set, frozenset)):
            for item in detalle:
                ServicioAuditoria._validar_detalle(item)

    @staticmethod
    def _calcular_hash(registro: RegistroAuditoria) -> str:
        payload = {
            "id": registro.id,
            "secuencia": registro.secuencia,
            "fecha_hora": registro.fecha_hora.isoformat(),
            "usuario_id": registro.usuario_id,
            "rol_ejecutante": registro.rol_ejecutante,
            "operacion": registro.operacion.value,
            "entidad": registro.entidad,
            "entidad_id": registro.entidad_id,
            "resultado": registro.resultado.value,
            "detalle": _a_jsonable(registro.detalle),
            "alumno_id": registro.alumno_id,
            "metodo_asistencia": registro.metodo_asistencia,
            "contexto_academico": _a_jsonable(registro.contexto_academico),
            "estado_anterior": registro.estado_anterior,
            "estado_nuevo": registro.estado_nuevo,
            "motivo": registro.motivo,
        }
        canonico = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(f"{canonico}{registro.hash_anterior}".encode()).hexdigest()

    @staticmethod
    def _validar_permiso(operador: Usuario, permiso: PermisoOperacion) -> None:
        if operador.estado != EstadoUsuario.ACTIVO:
            raise PermisoAuditoriaException(
                "La cuenta del operador no se encuentra activa para consultar auditoría."
            )
        if permiso not in MATRIZ_PERMISOS.get(operador.rol, set()):
            raise PermisoAuditoriaException(
                f"El rol {operador.rol.value} no tiene permiso para la operación '{permiso.value}'."
            )


def _reemplazar_hash(registro: RegistroAuditoria, hash_integridad: str) -> RegistroAuditoria:
    """Devuelve una copia con el hash calculado sin mutar el objeto original."""
    return replace(registro, hash_integridad=hash_integridad)
