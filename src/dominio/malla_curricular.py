"""PBI-09: configuración de malla curricular (niveles, salones y cursos)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, TypeVar

from src.dominio.asistencia import UsuarioOperador
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)


class NivelEducativo(StrEnum):
    """Niveles educativos oficiales soportados por el colegio."""

    PRIMARIA = "Primaria"
    SECUNDARIA = "Secundaria"


GRADOS_POR_NIVEL: dict[NivelEducativo, tuple[str, ...]] = {
    NivelEducativo.PRIMARIA: ("1ro", "2do", "3ro", "4to", "5to", "6to"),
    NivelEducativo.SECUNDARIA: ("1ro", "2do", "3ro", "4to", "5to"),
}


class MallaCurricularException(Exception):
    """Excepción base del dominio de malla curricular."""


class PermisoMallaException(MallaCurricularException):
    """Lanzada cuando un operador carece de cuenta activa o permiso requerido."""


class SalonInvalidoException(MallaCurricularException):
    """Lanzada cuando los datos o capacidad de un salón son inválidos."""


class SalonDuplicadoException(MallaCurricularException):
    """Lanzada cuando ya existe un salón para el mismo año, nivel, grado y sección."""


class CursoInvalidoException(MallaCurricularException):
    """Lanzada cuando los datos de un curso incumplen las reglas de negocio."""


class CursoDuplicadoException(MallaCurricularException):
    """Lanzada cuando el código de curso ya existe en el mismo año, nivel y grado."""


class EntidadEnUsoException(MallaCurricularException):
    """Lanzada al intentar eliminar físicamente un salón o curso con registros asociados."""


class _EntidadAcademica(Protocol):
    anio_lectivo: int
    nivel: NivelEducativo
    grado: str
    activo: bool


TEntidad = TypeVar("TEntidad", bound=_EntidadAcademica)


def _es_entero_valido(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_ubicacion_academica(
    anio_lectivo: int,
    nivel: NivelEducativo,
    grado: str,
    exc_cls: type[MallaCurricularException],
) -> str:
    if not _es_entero_valido(anio_lectivo) or anio_lectivo < 2000:
        raise exc_cls("El año lectivo debe ser un entero mayor o igual a 2000.")
    if not isinstance(nivel, NivelEducativo):
        raise exc_cls(f"El nivel educativo '{nivel}' no es válido.")
    if not isinstance(grado, str):
        raise exc_cls("El grado debe ser una cadena de texto válida.")
    grado_norm = grado.strip().lower()
    if grado_norm not in GRADOS_POR_NIVEL[nivel]:
        raise exc_cls(f"El grado '{grado}' no es válido para el nivel {nivel.value}.")
    return grado_norm


def _validar_texto_no_vacio(
    valor: object,
    campo: str,
    exc_cls: type[MallaCurricularException],
) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise exc_cls(f"El campo {campo} es obligatorio y no puede estar vacío.")
    return valor.strip()


def _filtrar_entidades(
    entidades: Sequence[TEntidad],
    anio_lectivo: int | None,
    nivel: NivelEducativo | None,
    grado: str | None,
    solo_activos: bool,
) -> list[TEntidad]:
    resultado = list(entidades)
    if solo_activos:
        resultado = [entidad for entidad in resultado if entidad.activo]
    if anio_lectivo is not None:
        resultado = [entidad for entidad in resultado if entidad.anio_lectivo == anio_lectivo]
    if nivel is not None:
        resultado = [entidad for entidad in resultado if entidad.nivel == nivel]
    if grado is not None:
        grado_norm = grado.strip().lower()
        resultado = [entidad for entidad in resultado if entidad.grado.lower() == grado_norm]
    return resultado


@dataclass(frozen=True)
class Salon:
    """Representa un salón/sección por año lectivo, nivel y grado."""

    id: int
    anio_lectivo: int
    nivel: NivelEducativo
    grado: str
    seccion: str
    capacidad_maxima: int = 30
    activo: bool = True

    def __post_init__(self) -> None:
        grado_norm = _validar_ubicacion_academica(
            self.anio_lectivo,
            self.nivel,
            self.grado,
            SalonInvalidoException,
        )
        seccion_limpia = _validar_texto_no_vacio(
            self.seccion,
            "sección",
            SalonInvalidoException,
        ).upper()
        if not re.fullmatch(r"[A-Z0-9]{1,5}", seccion_limpia):
            raise SalonInvalidoException(
                "La sección debe contener entre 1 y 5 caracteres alfanuméricos."
            )
        if not _es_entero_valido(self.capacidad_maxima) or self.capacidad_maxima <= 0:
            raise SalonInvalidoException("La capacidad máxima del salón debe ser mayor a 0.")
        if not isinstance(self.activo, bool):
            raise SalonInvalidoException("El indicador 'activo' del salón debe ser booleano.")
        object.__setattr__(self, "grado", grado_norm)
        object.__setattr__(self, "seccion", seccion_limpia)


@dataclass(frozen=True)
class Curso:
    """Representa un curso asignable a un grado, nivel y año lectivo."""

    id: int
    anio_lectivo: int
    nivel: NivelEducativo
    grado: str
    codigo: str
    nombre: str
    area_curricular: str
    horas_semanales: int
    activo: bool = True

    def __post_init__(self) -> None:
        grado_norm = _validar_ubicacion_academica(
            self.anio_lectivo,
            self.nivel,
            self.grado,
            CursoInvalidoException,
        )
        codigo = _validar_texto_no_vacio(self.codigo, "código", CursoInvalidoException)
        nombre = _validar_texto_no_vacio(self.nombre, "nombre", CursoInvalidoException)
        area = _validar_texto_no_vacio(
            self.area_curricular,
            "área curricular",
            CursoInvalidoException,
        )
        if not _es_entero_valido(self.horas_semanales) or self.horas_semanales <= 0:
            raise CursoInvalidoException("Las horas semanales del curso deben ser mayores a 0.")
        if not isinstance(self.activo, bool):
            raise CursoInvalidoException("El indicador 'activo' del curso debe ser booleano.")
        object.__setattr__(self, "grado", grado_norm)
        object.__setattr__(self, "codigo", codigo)
        object.__setattr__(self, "nombre", nombre)
        object.__setattr__(self, "area_curricular", area)


class ServicioMallaCurricular:
    """Implementa las reglas de negocio del PBI-09 (Configuración de Malla Curricular)."""

    @staticmethod
    def validar_operador(
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso CONFIGURAR_MALLA_CURRICULAR en servidor."""
        if not operador.activo:
            raise PermisoMallaException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR,
            roles=roles,
        ):
            raise PermisoMallaException(
                "El operador no tiene permiso para configurar la malla curricular."
            )

    @staticmethod
    def crear_salon(
        operador: UsuarioOperador,
        salon: Salon,
        salones_existentes: Sequence[Salon],
        roles: Sequence[Rol] | None = None,
    ) -> Salon:
        """Registra un nuevo salón validando unicidad por año, nivel, grado y sección."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        clave_nueva = (
            salon.anio_lectivo,
            salon.nivel,
            salon.grado.lower(),
            salon.seccion.strip().upper(),
        )
        for existente in salones_existentes:
            clave_existente = (
                existente.anio_lectivo,
                existente.nivel,
                existente.grado.lower(),
                existente.seccion.strip().upper(),
            )
            if clave_existente == clave_nueva:
                raise SalonDuplicadoException(
                    f"Ya existe el salón {salon.grado} '{salon.seccion}' para "
                    f"{salon.nivel.value} {salon.anio_lectivo}."
                )
        return salon

    @staticmethod
    def actualizar_capacidad_salon(
        operador: UsuarioOperador,
        salon: Salon,
        nueva_capacidad: int,
        matriculados_actuales: int = 0,
        roles: Sequence[Rol] | None = None,
    ) -> Salon:
        """Actualiza la capacidad máxima de un salón verificando alumnos matriculados."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        if not _es_entero_valido(nueva_capacidad) or nueva_capacidad <= 0:
            raise SalonInvalidoException("La nueva capacidad debe ser mayor a 0.")
        if not _es_entero_valido(matriculados_actuales) or matriculados_actuales < 0:
            raise SalonInvalidoException("La cantidad de matriculados actuales no es válida.")
        if nueva_capacidad < matriculados_actuales:
            raise SalonInvalidoException(
                "La nueva capacidad no puede ser menor a los alumnos matriculados actuales."
            )
        return replace(salon, capacidad_maxima=nueva_capacidad)

    @staticmethod
    def desactivar_salon(
        operador: UsuarioOperador,
        salon: Salon,
        tiene_alumnos_activos: bool = False,
        roles: Sequence[Rol] | None = None,
    ) -> Salon:
        """Realiza la baja lógica de un salón incluso si tiene alumnos asociados."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        _ = tiene_alumnos_activos
        return replace(salon, activo=False)

    @staticmethod
    def eliminar_salon(
        operador: UsuarioOperador,
        salon: Salon,
        tiene_alumnos_asociados: bool = False,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Permite eliminar un salón solo si no tiene alumnos asociados."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        if tiene_alumnos_asociados:
            raise EntidadEnUsoException(
                f"No se puede eliminar el salón {salon.grado} '{salon.seccion}' "
                "porque tiene alumnos asociados."
            )

    @staticmethod
    def crear_curso(
        operador: UsuarioOperador,
        curso: Curso,
        cursos_existentes: Sequence[Curso],
        roles: Sequence[Rol] | None = None,
    ) -> Curso:
        """Registra un curso validando código único por año, nivel y grado."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        clave_nueva = (
            curso.anio_lectivo,
            curso.nivel,
            curso.grado.lower(),
            curso.codigo.strip().upper(),
        )
        for existente in cursos_existentes:
            clave_existente = (
                existente.anio_lectivo,
                existente.nivel,
                existente.grado.lower(),
                existente.codigo.strip().upper(),
            )
            if clave_existente == clave_nueva:
                raise CursoDuplicadoException(
                    f"Ya existe un curso con código '{curso.codigo}' para "
                    f"{curso.grado} de {curso.nivel.value} {curso.anio_lectivo}."
                )
        return curso

    @staticmethod
    def desactivar_curso(
        operador: UsuarioOperador,
        curso: Curso,
        roles: Sequence[Rol] | None = None,
    ) -> Curso:
        """Realiza la baja lógica de un curso preservando el historial académico."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        return replace(curso, activo=False)

    @staticmethod
    def eliminar_curso(
        operador: UsuarioOperador,
        curso: Curso,
        tiene_calificaciones: bool = False,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Permite eliminar un curso solo si no tiene calificaciones registradas."""
        ServicioMallaCurricular.validar_operador(operador, roles=roles)
        if tiene_calificaciones:
            raise EntidadEnUsoException(
                f"No se puede eliminar el curso '{curso.codigo}' "
                "porque tiene calificaciones registradas."
            )

    @staticmethod
    def listar_salones(
        salones: Sequence[Salon],
        anio_lectivo: int | None = None,
        nivel: NivelEducativo | None = None,
        grado: str | None = None,
        solo_activos: bool = True,
    ) -> list[Salon]:
        """Lista salones filtrando opcionalmente por año lectivo, nivel, grado y estado."""
        return _filtrar_entidades(salones, anio_lectivo, nivel, grado, solo_activos)

    @staticmethod
    def listar_cursos(
        cursos: Sequence[Curso],
        anio_lectivo: int | None = None,
        nivel: NivelEducativo | None = None,
        grado: str | None = None,
        solo_activos: bool = True,
    ) -> list[Curso]:
        """Lista cursos filtrando opcionalmente por año lectivo, nivel, grado y estado."""
        return _filtrar_entidades(cursos, anio_lectivo, nivel, grado, solo_activos)
