import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum


class EstadoAsistencia(StrEnum):
    PUNTUAL = "PUNTUAL"
    TARDANZA = "TARDANZA"
    AUSENTE = "AUSENTE"
    JUSTIFICADO = "JUSTIFICADO"
    PENDIENTE = "PENDIENTE"


class MetodoRegistro(StrEnum):
    CARNET = "CARNET"
    MANUAL_DNI = "MANUAL_DNI"
    MANUAL_BUSQUEDA = "MANUAL_BUSQUEDA"


class RolUsuario(StrEnum):
    ADMIN = "ADMIN"
    COORDINADOR = "COORDINADOR"
    ADMIN_STAFF = "ADMIN_STAFF"


class EstadoAlumno(StrEnum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class AsistenciaException(Exception):
    """Excepción base del dominio de asistencia escolar."""


class RolNoAutorizadoException(AsistenciaException):
    """Lanzada cuando un rol no oficial o sin permisos intenta registrar asistencia."""


class AlumnoNoEncontradoException(AsistenciaException):
    """Lanzada cuando el alumno o su identificador no existe en el sistema."""


class AlumnoInactivoException(AsistenciaException):
    """Lanzada cuando se intenta registrar asistencia de un alumno no ACTIVO."""


class DniInvalidoException(AsistenciaException):
    """Lanzada ante un DNI que no tiene exactamente 8 dígitos numéricos."""


class RegistroDuplicadoException(AsistenciaException):
    """Lanzada cuando ya existe una asistencia registrada no corregible."""


class AsistenciaJustificadaException(AsistenciaException):
    """Lanzada cuando se intenta sobreescribir una asistencia en estado JUSTIFICADO."""


class FaltaMotivoCorreccionException(AsistenciaException):
    """Lanzada al corregir un estado AUSENTE sin ingresar un motivo justificado."""


class CarnetInvalidoException(AsistenciaException):
    """Lanzada cuando el código de carnet no coincide con el del alumno."""


@dataclass(frozen=True)
class Alumno:
    id: int
    codigo: str
    dni: str
    nombres: str
    apellidos: str
    nivel: str
    grado: str
    seccion: str
    carnet_codigo: str
    estado: EstadoAlumno = EstadoAlumno.ACTIVO


@dataclass(frozen=True)
class UsuarioOperador:
    id: int
    username: str
    rol: RolUsuario
    activo: bool = True


@dataclass(frozen=True)
class RegistroAsistencia:
    id: str
    alumno_id: int
    fecha_escolar: date
    hora_efectiva: time
    estado: EstadoAsistencia
    minutos_tardanza: int
    metodo: MetodoRegistro
    usuario_id: int
    rol_usuario: RolUsuario
    estado_anterior: EstadoAsistencia | None = None
    motivo_correccion: str | None = None
    auditoria_id: str | None = None


@dataclass(frozen=True)
class EventoAuditoria:
    id: str
    evento_tipo: str
    usuario_id: int
    rol: RolUsuario
    fecha_hora: datetime
    operacion: str
    metodo: MetodoRegistro
    alumno_id: int
    estado_anterior: EstadoAsistencia | None
    estado_nuevo: EstadoAsistencia
    motivo: str | None


@dataclass(frozen=True)
class EventoAsistenciaConfirmada:
    id: str
    asistencia_id: str
    alumno_id: int
    fecha_escolar: date
    hora_efectiva: time
    estado: EstadoAsistencia
    minutos_tardanza: int
    metodo: MetodoRegistro
    usuario_id: int


@dataclass(frozen=True)
class ResultadoRegistroAsistencia:
    asistencia: RegistroAsistencia
    auditoria: EventoAuditoria
    evento_whatsapp: EventoAsistenciaConfirmada | None


HORA_OFICIAL_INGRESO = time(7, 0, 0)
HORA_LIMITE_TOLERANCIA = time(7, 15, 0)


def calcular_estado_y_tardanza(hora_ingreso: time) -> tuple[EstadoAsistencia, int]:
    """Calcula la puntualidad y minutos de tardanza con redondeo ceil hacia arriba."""
    if hora_ingreso <= HORA_LIMITE_TOLERANCIA:
        return EstadoAsistencia.PUNTUAL, 0

    seg_ingreso = hora_ingreso.hour * 3600 + hora_ingreso.minute * 60 + hora_ingreso.second
    seg_tolerancia = 7 * 3600 + 15 * 60
    delta_segundos = seg_ingreso - seg_tolerancia
    minutos = math.ceil(delta_segundos / 60)
    return EstadoAsistencia.TARDANZA, minutos


def validar_operador(operador: UsuarioOperador) -> None:
    """Verifica autenticación, estado activo y rol oficial autorizado."""
    if not operador.activo:
        raise RolNoAutorizadoException("El operador no cuenta con una cuenta activa.")

    roles_permitidos = {RolUsuario.ADMIN, RolUsuario.COORDINADOR, RolUsuario.ADMIN_STAFF}
    if operador.rol not in roles_permitidos:
        raise RolNoAutorizadoException(f"El rol {operador.rol} no está autorizado.")


def validar_alumno(alumno: Alumno | None) -> None:
    """Verifica que el alumno exista y tenga estado ACTIVO."""
    if alumno is None:
        raise AlumnoNoEncontradoException("El alumno especificado no fue encontrado.")
    if alumno.estado != EstadoAlumno.ACTIVO:
        raise AlumnoInactivoException(f"El alumno {alumno.codigo} no se encuentra ACTIVO.")


def validar_formato_dni(dni: str) -> None:
    """Verifica que el DNI contenga exactamente 8 dígitos numéricos."""
    if not (isinstance(dni, str) and len(dni) == 8 and dni.isdigit()):
        raise DniInvalidoException(
            f"El DNI '{dni}' es inválido. Debe contener exactamente 8 dígitos numéricos."
        )


def buscar_alumnos_activos(criterio: str, alumnos: list[Alumno]) -> list[Alumno]:
    """Búsqueda asistida por nombres, apellidos, DNI o código; solo alumnos ACTIVO."""
    criterio_norm = criterio.strip().lower()
    if not criterio_norm:
        return []

    resultados = []
    for al in alumnos:
        if al.estado != EstadoAlumno.ACTIVO:
            continue
        nombre_completo = f"{al.nombres} {al.apellidos}".lower()
        if (
            criterio_norm in nombre_completo
            or criterio_norm in al.dni.lower()
            or criterio_norm in al.codigo.lower()
        ):
            resultados.append(al)
    return resultados


def registrar_asistencia_unificada(
    operador: UsuarioOperador,
    alumno: Alumno | None,
    metodo: MetodoRegistro,
    hora_servidor: time,
    fecha_escolar: date,
    asistencia_existente: RegistroAsistencia | None = None,
    motivo_correccion: str | None = None,
    codigo_carnet: str | None = None,
    dni_manual: str | None = None,
    timestamp_servidor: datetime | None = None,
) -> ResultadoRegistroAsistencia:
    """Ejecuta el registro unificado de asistencia cumpliendo las reglas RN-01 a RN-30."""
    validar_operador(operador)
    validar_alumno(alumno)
    assert alumno is not None

    if timestamp_servidor is None:
        timestamp_servidor = datetime.combine(fecha_escolar, hora_servidor)

    # Validaciones específicas por método de registro
    if metodo == MetodoRegistro.MANUAL_DNI:
        if dni_manual is None:
            raise DniInvalidoException("Debe proporcionar el DNI para registro manual.")
        validar_formato_dni(dni_manual)
        if dni_manual != alumno.dni:
            raise AlumnoNoEncontradoException(
                f"El DNI {dni_manual} no coincide con el alumno {alumno.codigo}."
            )

    elif metodo == MetodoRegistro.CARNET and (
        codigo_carnet is not None and codigo_carnet != alumno.carnet_codigo
    ):
        raise CarnetInvalidoException("El código de carnet no coincide con el alumno.")

    # Verificación de duplicados y transiciones de estado
    estado_anterior: EstadoAsistencia | None = None
    if asistencia_existente is not None:
        if asistencia_existente.estado == EstadoAsistencia.JUSTIFICADO:
            raise AsistenciaJustificadaException(
                "La asistencia se encuentra JUSTIFICADO y no puede ser alterada ordinariamente."
            )

        if asistencia_existente.estado in (EstadoAsistencia.PUNTUAL, EstadoAsistencia.TARDANZA):
            raise RegistroDuplicadoException(
                f"El alumno ya cuenta con asistencia {asistencia_existente.estado} para la fecha."
            )

        if asistencia_existente.estado == EstadoAsistencia.AUSENTE:
            if not motivo_correccion or not motivo_correccion.strip():
                raise FaltaMotivoCorreccionException(
                    "Debe especificar el motivo de corrección para un estado AUSENTE."
                )
            estado_anterior = EstadoAsistencia.AUSENTE

    # Cálculo oficial de puntualidad y minutos de tardanza
    nuevo_estado, minutos_tardanza = calcular_estado_y_tardanza(hora_servidor)

    id_auditoria = f"aud-{uuid.uuid4().hex[:12]}"
    id_asistencia = (
        asistencia_existente.id if asistencia_existente else f"ast-{uuid.uuid4().hex[:12]}"
    )

    asistencia = RegistroAsistencia(
        id=id_asistencia,
        alumno_id=alumno.id,
        fecha_escolar=fecha_escolar,
        hora_efectiva=hora_servidor,
        estado=nuevo_estado,
        minutos_tardanza=minutos_tardanza,
        metodo=metodo,
        usuario_id=operador.id,
        rol_usuario=operador.rol,
        estado_anterior=estado_anterior,
        motivo_correccion=motivo_correccion if estado_anterior else None,
        auditoria_id=id_auditoria,
    )

    auditoria = EventoAuditoria(
        id=id_auditoria,
        evento_tipo="ASISTENCIA_REGISTRADA" if not estado_anterior else "ASISTENCIA_CORREGIDA",
        usuario_id=operador.id,
        rol=operador.rol,
        fecha_hora=timestamp_servidor,
        operacion="CORRECCION_AUSENTE" if estado_anterior else "REGISTRO_ASISTENCIA",
        metodo=metodo,
        alumno_id=alumno.id,
        estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado,
        motivo=motivo_correccion if estado_anterior else None,
    )

    evento_whatsapp = None
    if nuevo_estado in (EstadoAsistencia.PUNTUAL, EstadoAsistencia.TARDANZA):
        evento_whatsapp = EventoAsistenciaConfirmada(
            id=f"evt-{uuid.uuid4().hex[:12]}",
            asistencia_id=asistencia.id,
            alumno_id=alumno.id,
            fecha_escolar=fecha_escolar,
            hora_efectiva=hora_servidor,
            estado=nuevo_estado,
            minutos_tardanza=minutos_tardanza,
            metodo=metodo,
            usuario_id=operador.id,
        )

    return ResultadoRegistroAsistencia(
        asistencia=asistencia,
        auditoria=auditoria,
        evento_whatsapp=evento_whatsapp,
    )
