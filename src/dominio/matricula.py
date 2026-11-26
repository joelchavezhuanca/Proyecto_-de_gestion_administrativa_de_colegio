"""PBI-05: Ficha de Matrícula Digital."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Final

from src.dominio.asistencia import UsuarioOperador, validar_formato_dni
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.malla_curricular import NivelEducativo, Salon
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

ZONA_HORARIA_LIMA: Final[timezone] = timezone(timedelta(hours=-5))
_PATRON_TEL_LOCAL: Final[re.Pattern[str]] = re.compile(r"^9\d{8}$")
_PATRON_TEL_E164: Final[re.Pattern[str]] = re.compile(r"^\+519\d{8}$")
_PATRON_TEL_PREFIJO: Final[re.Pattern[str]] = re.compile(r"^519\d{8}$")


class MatriculaException(Exception):
    """Excepción base del dominio de matrícula digital."""


class PermisoMatriculaException(MatriculaException):
    """Lanzada cuando el operador no está activo o carece de permiso."""


class ApoderadoInvalidoException(MatriculaException):
    """Lanzada cuando los datos del apoderado o la lista de apoderados son inválidos."""


class MatriculaDuplicadaException(MatriculaException):
    """Lanzada al detectar DNI, alumno o código de estudiante duplicado."""


class SalonSinVacantesException(MatriculaException):
    """Lanzada cuando el salón destino alcanzó su capacidad máxima de activos."""


class SalonInactivoException(MatriculaException):
    """Lanzada cuando se intenta matricular o trasladar a un salón inactivo."""


def _es_entero_valido(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _codigo_rol(rol: object) -> str:
    valor = getattr(rol, "value", rol)
    return str(valor).strip().upper()


def _normalizar_fecha_hora(fecha_hora: datetime) -> datetime:
    """Normaliza una marca temporal al huso institucional America/Lima (UTC-5)."""
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _validar_texto_no_vacio(
    valor: object,
    campo: str,
    exc_cls: type[MatriculaException],
) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise exc_cls(f"El campo {campo} es obligatorio y no puede estar vacío.")
    return valor.strip()


def normalizar_telefono_whatsapp_peru(telefono: str) -> str:
    """Valida y normaliza un celular peruano (9XXXXXXXX o +519XXXXXXXX) a E.164."""
    if not isinstance(telefono, str):
        raise ApoderadoInvalidoException(
            "El teléfono WhatsApp del apoderado debe ser una cadena de texto."
        )
    limpio = re.sub(r"[\s\-()]+", "", telefono.strip())
    if _PATRON_TEL_LOCAL.fullmatch(limpio):
        return f"+51{limpio}"
    if _PATRON_TEL_E164.fullmatch(limpio):
        return limpio
    if _PATRON_TEL_PREFIJO.fullmatch(limpio):
        return f"+{limpio}"
    raise ApoderadoInvalidoException(
        f"El teléfono WhatsApp '{telefono}' no tiene un formato peruano válido (+519XXXXXXXX)."
    )


@dataclass(frozen=True)
class Apoderado:
    """Representa a un apoderado vinculado a la matrícula digital de un alumno."""

    id: int
    nombres: str
    apellidos: str
    documento: str
    parentesco: str
    telefono_whatsapp: str
    es_principal: bool = False
    activo: bool = True

    def __post_init__(self) -> None:
        if not _es_entero_valido(self.id) or self.id < 0:
            raise ApoderadoInvalidoException(
                "El identificador del apoderado debe ser un entero no negativo."
            )
        nombres = _validar_texto_no_vacio(self.nombres, "nombres", ApoderadoInvalidoException)
        apellidos = _validar_texto_no_vacio(
            self.apellidos, "apellidos", ApoderadoInvalidoException
        )
        documento = _validar_texto_no_vacio(
            self.documento, "documento", ApoderadoInvalidoException
        )
        parentesco = _validar_texto_no_vacio(
            self.parentesco, "parentesco", ApoderadoInvalidoException
        )
        telefono = normalizar_telefono_whatsapp_peru(self.telefono_whatsapp)
        if not isinstance(self.es_principal, bool) or not isinstance(self.activo, bool):
            raise ApoderadoInvalidoException(
                "Los indicadores 'es_principal' y 'activo' del apoderado deben ser booleanos."
            )
        object.__setattr__(self, "nombres", nombres)
        object.__setattr__(self, "apellidos", apellidos)
        object.__setattr__(self, "documento", documento)
        object.__setattr__(self, "parentesco", parentesco)
        object.__setattr__(self, "telefono_whatsapp", telefono)


def _validar_apoderados(apoderados: Sequence[Apoderado]) -> tuple[Apoderado, ...]:
    if isinstance(apoderados, (str, bytes)) or not isinstance(apoderados, Sequence):
        raise ApoderadoInvalidoException("Los apoderados deben proporcionarse como una colección.")
    lista = tuple(apoderados)
    for apoderado in lista:
        if not isinstance(apoderado, Apoderado):
            raise ApoderadoInvalidoException(
                "Cada elemento de apoderados debe ser una instancia válida de Apoderado."
            )
    if not any(apoderado.activo and apoderado.es_principal for apoderado in lista):
        raise ApoderadoInvalidoException(
            "La matrícula requiere al menos un apoderado principal activo."
        )
    return lista


@dataclass(frozen=True)
class FichaMatricula:
    """Ficha de matrícula digital inmutable del estudiante para un año lectivo."""

    id: str
    alumno_id: int
    codigo_estudiante: str
    dni: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    anio_lectivo: int
    salon_id: int
    nivel: str
    grado: str
    seccion: str
    apoderados: tuple[Apoderado, ...]
    estado: EstadoAcademico = EstadoAcademico.ACTIVO
    creado_en: datetime | None = None

    def __post_init__(self) -> None:
        id_limpio = _validar_texto_no_vacio(self.id, "id", MatriculaException)
        if not _es_entero_valido(self.alumno_id) or self.alumno_id <= 0:
            raise MatriculaException("El identificador del alumno debe ser un entero positivo.")
        codigo = _validar_texto_no_vacio(
            self.codigo_estudiante, "código de estudiante", MatriculaException
        )
        validar_formato_dni(self.dni)
        nombres = _validar_texto_no_vacio(self.nombres, "nombres", MatriculaException)
        apellidos = _validar_texto_no_vacio(self.apellidos, "apellidos", MatriculaException)
        if not isinstance(self.fecha_nacimiento, date) or isinstance(
            self.fecha_nacimiento, datetime
        ):
            raise MatriculaException("La fecha de nacimiento debe ser una fecha válida.")
        if not _es_entero_valido(self.anio_lectivo) or self.anio_lectivo < 2000:
            raise MatriculaException("El año lectivo debe ser un entero mayor o igual a 2000.")
        if not _es_entero_valido(self.salon_id) or self.salon_id <= 0:
            raise MatriculaException("El identificador del salón debe ser un entero positivo.")
        nivel_raw = self.nivel.value if isinstance(self.nivel, NivelEducativo) else self.nivel
        nivel = _validar_texto_no_vacio(nivel_raw, "nivel", MatriculaException)
        grado = _validar_texto_no_vacio(self.grado, "grado", MatriculaException)
        seccion = _validar_texto_no_vacio(self.seccion, "sección", MatriculaException)
        if not isinstance(self.estado, EstadoAcademico):
            raise MatriculaException("El estado académico de la matrícula no es válido.")
        apoderados_validos = _validar_apoderados(self.apoderados)
        creado_normalizado = (
            _normalizar_fecha_hora(self.creado_en) if self.creado_en is not None else None
        )

        object.__setattr__(self, "id", id_limpio)
        object.__setattr__(self, "codigo_estudiante", codigo)
        object.__setattr__(self, "nombres", nombres)
        object.__setattr__(self, "apellidos", apellidos)
        object.__setattr__(self, "nivel", nivel)
        object.__setattr__(self, "grado", grado)
        object.__setattr__(self, "seccion", seccion)
        object.__setattr__(self, "apoderados", apoderados_validos)
        object.__setattr__(self, "creado_en", creado_normalizado)

    @property
    def apoderado_principal(self) -> Apoderado:
        """Devuelve el apoderado principal activo de la ficha."""
        return next(ap for ap in self.apoderados if ap.activo and ap.es_principal)


def _contar_matriculados_activos(
    salon: Salon,
    matriculas_existentes: Sequence[FichaMatricula],
    excluir_alumno_id: int | None = None,
) -> int:
    return sum(
        1
        for matricula in matriculas_existentes
        if matricula.salon_id == salon.id
        and matricula.anio_lectivo == salon.anio_lectivo
        and matricula.estado == EstadoAcademico.ACTIVO
        and (excluir_alumno_id is None or matricula.alumno_id != excluir_alumno_id)
    )


class ServicioMatricula:
    """Implementa las reglas de negocio del PBI-05 (Ficha de Matrícula Digital)."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso GESTIONAR_MATRICULA en servidor."""
        if not operador.activo:
            raise PermisoMatriculaException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.GESTIONAR_MATRICULA,
            roles=roles,
        ):
            raise PermisoMatriculaException(
                f"El rol {_codigo_rol(operador.rol)} no está autorizado para gestionar matrícula."
            )

    @staticmethod
    def matricular_estudiante(
        operador: UsuarioOperador,
        alumno_id: int,
        codigo_estudiante: str,
        dni: str,
        nombres: str,
        apellidos: str,
        fecha_nacimiento: date,
        salon: Salon,
        apoderados: Sequence[Apoderado],
        matriculas_existentes: Sequence[FichaMatricula],
        fecha_actual: date,
        roles: Sequence[Rol] | None = None,
        creado_en: datetime | None = None,
    ) -> FichaMatricula:
        """Registra una matrícula digital validando datos, apoderados, duplicados y vacantes."""
        ServicioMatricula.validar_operador(operador, roles=roles)

        if not salon.activo:
            raise SalonInactivoException(
                f"El salón {salon.grado} '{salon.seccion}' no se encuentra activo."
            )

        if not _es_entero_valido(alumno_id) or alumno_id <= 0:
            raise MatriculaException("El identificador del alumno debe ser un entero positivo.")

        validar_formato_dni(dni)
        codigo_limpio = _validar_texto_no_vacio(
            codigo_estudiante, "código de estudiante", MatriculaException
        )
        nombres_limpios = _validar_texto_no_vacio(nombres, "nombres", MatriculaException)
        apellidos_limpios = _validar_texto_no_vacio(apellidos, "apellidos", MatriculaException)

        if (
            not isinstance(fecha_nacimiento, date)
            or isinstance(fecha_nacimiento, datetime)
            or fecha_nacimiento >= fecha_actual
        ):
            raise MatriculaException(
                "La fecha de nacimiento debe ser anterior a la fecha actual."
            )

        apoderados_validos = _validar_apoderados(apoderados)
        codigo_norm = codigo_limpio.upper()

        for existente in matriculas_existentes:
            if existente.anio_lectivo == salon.anio_lectivo and (
                existente.dni == dni or existente.alumno_id == alumno_id
            ):
                raise MatriculaDuplicadaException(
                    f"El estudiante con DNI '{dni}' ya se encuentra matriculado en "
                    f"{salon.anio_lectivo}."
                )
            if existente.codigo_estudiante.strip().upper() == codigo_norm and (
                existente.anio_lectivo == salon.anio_lectivo
                or existente.alumno_id != alumno_id
                or existente.dni != dni
            ):
                raise MatriculaDuplicadaException(
                    f"El código de estudiante '{codigo_limpio}' ya está registrado."
                )

        if _contar_matriculados_activos(salon, matriculas_existentes) >= salon.capacidad_maxima:
            raise SalonSinVacantesException(
                f"El salón {salon.grado} '{salon.seccion}' ({salon.anio_lectivo}) "
                "no cuenta con vacantes disponibles."
            )

        momento = (
            _normalizar_fecha_hora(creado_en)
            if creado_en is not None
            else datetime.now(ZONA_HORARIA_LIMA)
        )

        return FichaMatricula(
            id=f"mat-{uuid.uuid4().hex[:12]}",
            alumno_id=alumno_id,
            codigo_estudiante=codigo_limpio,
            dni=dni,
            nombres=nombres_limpios,
            apellidos=apellidos_limpios,
            fecha_nacimiento=fecha_nacimiento,
            anio_lectivo=salon.anio_lectivo,
            salon_id=salon.id,
            nivel=salon.nivel.value,
            grado=salon.grado,
            seccion=salon.seccion,
            apoderados=apoderados_validos,
            estado=EstadoAcademico.ACTIVO,
            creado_en=momento,
        )

    @staticmethod
    def actualizar_apoderados(
        operador: UsuarioOperador,
        ficha: FichaMatricula,
        nuevos_apoderados: Sequence[Apoderado],
        roles: Sequence[Rol] | None = None,
    ) -> FichaMatricula:
        """Actualiza los apoderados manteniendo al menos un apoderado principal activo."""
        ServicioMatricula.validar_operador(operador, roles=roles)
        apoderados_validos = _validar_apoderados(nuevos_apoderados)
        return replace(ficha, apoderados=apoderados_validos)

    @staticmethod
    def cambiar_salon(
        operador: UsuarioOperador,
        ficha: FichaMatricula,
        nuevo_salon: Salon,
        matriculas_existentes: Sequence[FichaMatricula],
        roles: Sequence[Rol] | None = None,
    ) -> FichaMatricula:
        """Traslada internamente a un alumno ACTIVO verificando año lectivo y vacantes."""
        ServicioMatricula.validar_operador(operador, roles=roles)

        if ficha.estado != EstadoAcademico.ACTIVO:
            raise MatriculaException(
                "Solo se puede cambiar de salón a un estudiante en estado ACTIVO."
            )
        if not nuevo_salon.activo:
            raise SalonInactivoException(
                f"El salón {nuevo_salon.grado} '{nuevo_salon.seccion}' no se encuentra activo."
            )
        if nuevo_salon.anio_lectivo != ficha.anio_lectivo:
            raise MatriculaException(
                "El cambio interno de salón solo se permite dentro del mismo año lectivo."
            )
        if nuevo_salon.id == ficha.salon_id:
            raise MatriculaException("El estudiante ya pertenece al salón indicado.")

        ocupados = _contar_matriculados_activos(
            nuevo_salon,
            matriculas_existentes,
            excluir_alumno_id=ficha.alumno_id,
        )
        if ocupados >= nuevo_salon.capacidad_maxima:
            raise SalonSinVacantesException(
                f"El salón {nuevo_salon.grado} '{nuevo_salon.seccion}' ({nuevo_salon.anio_lectivo}) "
                "no cuenta con vacantes disponibles."
            )

        return replace(
            ficha,
            salon_id=nuevo_salon.id,
            nivel=nuevo_salon.nivel.value,
            grado=nuevo_salon.grado,
            seccion=nuevo_salon.seccion,
        )
