"""PBI-11: asignación docente segura y aislamiento de ámbito académico."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from src.dominio.asistencia import UsuarioOperador
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    ContextoAcademicoAuditoria,
    RegistroAuditoria,
    ResultadoAuditoria,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.malla_curricular import GRADOS_POR_NIVEL, Curso, NivelEducativo, Salon
from src.dominio.usuarios import (
    AccesoDenegadoException,
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolUsuario,
    ServicioAutenticacionYPermisos,
    Usuario,
)

ActorDocente = Usuario | UsuarioOperador


class DocenteException(Exception):
    """Excepción base del dominio de asignación docente."""


class PermisoAsignacionDocenteException(AccesoDenegadoException, DocenteException):
    """Lanzada cuando el operador no está activo o carece de ASIGNAR_DOCENTES."""


class DocenteNoHabilitadoException(DocenteException):
    """Lanzada cuando el usuario a asignar está inactivo o no puede calificar."""


class AsignacionInvalidaException(DocenteException):
    """Lanzada cuando los datos de la asignación o su contexto son inválidos."""


class AsignacionDuplicadaException(DocenteException):
    """Lanzada ante una asignación activa duplicada o en conflicto de curso-salón."""


class AsignacionEnUsoException(DocenteException):
    """Lanzada al intentar eliminar físicamente una asignación con historial."""


class AccesoAmbitoDocenteDenegadoException(AccesoDenegadoException, DocenteException):
    """Lanzada cuando un docente intenta operar fuera de sus grupos asignados."""

    def __init__(self, mensaje: str, *, auditoria: RegistroAuditoria | None = None) -> None:
        super().__init__(mensaje)
        self.auditoria = auditoria


# Alias de retrocompatibilidad con nombres alternos de excepciones
PermisoDocenteException = PermisoAsignacionDocenteException
AmbitoDocenteDenegadoException = AccesoAmbitoDocenteDenegadoException


def _es_entero_positivo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _validar_entero_positivo(valor: object, campo: str) -> int:
    if not _es_entero_positivo(valor):
        raise AsignacionInvalidaException(f"El campo '{campo}' debe ser un entero positivo.")
    assert isinstance(valor, int)
    return valor


def _validar_entero_no_negativo(valor: object, campo: str) -> int:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        raise AsignacionInvalidaException(
            f"El campo '{campo}' debe ser un entero mayor o igual a cero."
        )
    return valor


def _validar_texto_no_vacio(valor: object, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise AsignacionInvalidaException(
            f"El campo '{campo}' es obligatorio y no puede estar vacío."
        )
    return valor.strip()


def _validar_anio_lectivo(anio_lectivo: object) -> int:
    if not isinstance(anio_lectivo, int) or isinstance(anio_lectivo, bool) or anio_lectivo < 2000:
        raise AsignacionInvalidaException("El año lectivo debe ser un entero mayor o igual a 2000.")
    return anio_lectivo


def _hora_actual_lima() -> datetime:
    return datetime.now(ZONA_HORARIA_LIMA)


def _normalizar_fecha_hora(fecha_hora: datetime) -> datetime:
    if not isinstance(fecha_hora, datetime):
        raise AsignacionInvalidaException("La fecha y hora debe ser una instancia datetime válida.")
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _actor_activo(actor: ActorDocente) -> bool:
    if isinstance(actor, Usuario):
        return actor.estado == EstadoUsuario.ACTIVO
    return actor.activo


def _codigo_rol(rol: RolUsuario | str) -> str:
    return rol.value if isinstance(rol, RolUsuario) else str(rol).strip().upper()


@dataclass(frozen=True)
class AsignacionDocente:
    """Representa la asignación de un docente a un curso y salón en un año lectivo."""

    id: str
    usuario_docente_id: int
    curso_id: int
    salon_id: int
    anio_lectivo: int
    activa: bool = True
    asignado_por: int = 0
    creado_en: datetime | None = None
    revocada_en: datetime | None = None
    motivo_revocacion: str | None = None

    def __post_init__(self) -> None:
        id_limpio = _validar_texto_no_vacio(self.id, "id")
        _validar_entero_positivo(self.usuario_docente_id, "usuario_docente_id")
        _validar_entero_positivo(self.curso_id, "curso_id")
        _validar_entero_positivo(self.salon_id, "salon_id")
        _validar_anio_lectivo(self.anio_lectivo)
        if not isinstance(self.activa, bool):
            raise AsignacionInvalidaException("El indicador 'activa' debe ser booleano.")
        _validar_entero_no_negativo(self.asignado_por, "asignado_por")

        creado_norm = _normalizar_fecha_hora(self.creado_en) if self.creado_en is not None else None
        revocada_norm = (
            _normalizar_fecha_hora(self.revocada_en) if self.revocada_en is not None else None
        )
        if creado_norm is not None and revocada_norm is not None and revocada_norm < creado_norm:
            raise AsignacionInvalidaException(
                "La fecha de revocación no puede ser anterior a la fecha de creación."
            )

        motivo_norm: str | None = None
        if self.motivo_revocacion is not None:
            motivo_norm = _validar_texto_no_vacio(self.motivo_revocacion, "motivo_revocacion")

        object.__setattr__(self, "id", id_limpio)
        object.__setattr__(self, "creado_en", creado_norm)
        object.__setattr__(self, "revocada_en", revocada_norm)
        object.__setattr__(self, "motivo_revocacion", motivo_norm)


def _validar_consistencia_curso_salon(
    curso: Curso,
    salon: Salon,
    anio_lectivo: int | None,
) -> int:
    if not curso.activo:
        raise AsignacionInvalidaException("No se puede asignar un docente a un curso inactivo.")
    if not salon.activo:
        raise AsignacionInvalidaException("No se puede asignar un docente a un salón inactivo.")
    if curso.anio_lectivo != salon.anio_lectivo:
        raise AsignacionInvalidaException("El año lectivo del curso y del salón debe coincidir.")
    if anio_lectivo is not None:
        anio_validado = _validar_anio_lectivo(anio_lectivo)
        if anio_validado != salon.anio_lectivo:
            raise AsignacionInvalidaException(
                "El año lectivo indicado no coincide con el del curso y salón."
            )
    if curso.nivel != salon.nivel or not isinstance(curso.nivel, NivelEducativo):
        raise AsignacionInvalidaException(
            "El nivel educativo del curso y del salón debe coincidir."
        )
    if curso.grado != salon.grado or curso.grado not in GRADOS_POR_NIVEL[curso.nivel]:
        raise AsignacionInvalidaException("El grado del curso y del salón debe coincidir.")
    return salon.anio_lectivo


def _registrar_auditoria_operacion(
    *,
    operador: ActorDocente,
    asignacion: AsignacionDocente,
    fecha_hora: datetime,
    estado_anterior: str | None,
    estado_nuevo: str,
    accion: str,
    eventos_auditoria_existentes: Sequence[RegistroAuditoria],
    persistir_auditoria: Callable[[RegistroAuditoria], None] | None,
    contexto_academico: ContextoAcademicoAuditoria | None = None,
    motivo: str | None = None,
    detalle_extra: dict[str, object] | None = None,
) -> RegistroAuditoria:
    detalle: dict[str, object] = {
        "accion": accion,
        "usuario_docente_id": asignacion.usuario_docente_id,
        "curso_id": asignacion.curso_id,
        "salon_id": asignacion.salon_id,
        "anio_lectivo": asignacion.anio_lectivo,
    }
    if detalle_extra:
        detalle.update(detalle_extra)
    return ServicioAuditoria.registrar_evento(
        usuario_id=operador.id,
        rol_ejecutante=_codigo_rol(operador.rol),
        operacion=TipoOperacionAuditoria.OTRA,
        entidad="ASIGNACION_DOCENTE",
        entidad_id=asignacion.id,
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=fecha_hora,
        eventos_existentes=eventos_auditoria_existentes,
        contexto_academico=contexto_academico,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        motivo=motivo,
        detalle=detalle,
        persistir=persistir_auditoria,
    )


def _auditar_y_denegar_ambito(
    *,
    docente: ActorDocente,
    curso_id: int,
    salon_id: int,
    anio_lectivo: int,
    mensaje: str,
    fecha_hora: datetime | None,
    eventos_auditoria_existentes: Sequence[RegistroAuditoria],
    persistir_auditoria: Callable[[RegistroAuditoria], None] | None,
) -> AccesoAmbitoDocenteDenegadoException:
    momento = _normalizar_fecha_hora(fecha_hora or _hora_actual_lima())
    registro = ServicioAuditoria.registrar_evento(
        usuario_id=docente.id,
        rol_ejecutante=_codigo_rol(docente.rol),
        operacion=TipoOperacionAuditoria.ACCESO_DENEGADO,
        entidad="ASIGNACION_DOCENTE",
        entidad_id=f"{curso_id}:{salon_id}:{anio_lectivo}",
        resultado=ResultadoAuditoria.FALLIDA,
        fecha_hora=momento,
        eventos_existentes=eventos_auditoria_existentes,
        detalle={
            "accion": "VALIDAR_AMBITO_DOCENTE",
            "curso_id": curso_id,
            "salon_id": salon_id,
            "anio_lectivo": anio_lectivo,
        },
        motivo=mensaje,
        persistir=persistir_auditoria,
    )
    return AccesoAmbitoDocenteDenegadoException(mensaje, auditoria=registro)


class ServicioAsignacionDocente:
    """Implementa las reglas de negocio del PBI-11 (Asignación Docente Segura)."""

    @staticmethod
    def validar_operador_asignacion(
        operador: ActorDocente,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso ASIGNAR_DOCENTES en servidor (RN-01)."""
        if not _actor_activo(operador):
            raise PermisoAsignacionDocenteException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.ASIGNAR_DOCENTES,
            roles=roles,
        ):
            raise PermisoAsignacionDocenteException(
                f"El rol {_codigo_rol(operador.rol)} no tiene permiso para asignar docentes."
            )

    @staticmethod
    def _validar_docente_habilitado(
        docente: ActorDocente,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        if not _actor_activo(docente):
            raise DocenteNoHabilitadoException(
                "El usuario docente debe encontrarse ACTIVO para ser asignado."
            )
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            docente.rol,
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            roles=roles,
        ):
            raise DocenteNoHabilitadoException(
                f"El rol {_codigo_rol(docente.rol)} no posee el permiso "
                f"'{PermisoOperacion.REGISTRAR_CALIFICACIONES.value}'."
            )

    @staticmethod
    def asignar_docente(
        operador: ActorDocente,
        docente: ActorDocente,
        curso: Curso,
        salon: Salon,
        asignaciones_existentes: Sequence[AsignacionDocente] = (),
        fecha_hora: datetime | None = None,
        roles: Sequence[Rol] | None = None,
        *,
        anio_lectivo: int | None = None,
        eventos_auditoria_existentes: Sequence[RegistroAuditoria] = (),
        persistir_auditoria: Callable[[RegistroAuditoria], None] | None = None,
    ) -> AsignacionDocente:
        """Asigna un docente habilitado a un curso y salón evitando duplicados activos."""
        ServicioAsignacionDocente.validar_operador_asignacion(operador, roles=roles)
        ServicioAsignacionDocente._validar_docente_habilitado(docente, roles=roles)
        anio = _validar_consistencia_curso_salon(curso, salon, anio_lectivo)

        for existente in asignaciones_existentes:
            if not existente.activa:
                continue
            if (
                existente.curso_id == curso.id
                and existente.salon_id == salon.id
                and existente.anio_lectivo == anio
            ):
                if existente.usuario_docente_id == docente.id:
                    raise AsignacionDuplicadaException(
                        "El docente ya posee una asignación activa para este curso, salón y año."
                    )
                raise AsignacionDuplicadaException(
                    "El curso y salón ya cuentan con otro docente asignado activamente en el año."
                )

        momento = _normalizar_fecha_hora(fecha_hora or _hora_actual_lima())
        asignacion = AsignacionDocente(
            id=f"asg-{uuid.uuid4().hex[:12]}",
            usuario_docente_id=docente.id,
            curso_id=curso.id,
            salon_id=salon.id,
            anio_lectivo=anio,
            activa=True,
            asignado_por=operador.id,
            creado_en=momento,
        )

        _registrar_auditoria_operacion(
            operador=operador,
            asignacion=asignacion,
            fecha_hora=momento,
            estado_anterior=None,
            estado_nuevo="ACTIVA",
            accion="ASIGNAR_DOCENTE",
            eventos_auditoria_existentes=eventos_auditoria_existentes,
            persistir_auditoria=persistir_auditoria,
            contexto_academico=ContextoAcademicoAuditoria(
                nivel=salon.nivel.value,
                grado=salon.grado,
                seccion=salon.seccion,
            ),
            detalle_extra={"curso_codigo": curso.codigo},
        )
        return asignacion

    @staticmethod
    def revocar_asignacion(
        operador: ActorDocente,
        asignacion: AsignacionDocente,
        fecha_hora: datetime | None = None,
        roles: Sequence[Rol] | None = None,
        *,
        motivo: str | None = None,
        eventos_auditoria_existentes: Sequence[RegistroAuditoria] = (),
        persistir_auditoria: Callable[[RegistroAuditoria], None] | None = None,
    ) -> AsignacionDocente:
        """Revoca lógicamente una asignación conservando el historial académico."""
        ServicioAsignacionDocente.validar_operador_asignacion(operador, roles=roles)
        if not asignacion.activa:
            raise AsignacionInvalidaException("La asignación ya se encuentra revocada.")

        motivo_limpio: str | None = None
        if motivo is not None:
            motivo_limpio = _validar_texto_no_vacio(motivo, "motivo")

        momento = _normalizar_fecha_hora(fecha_hora or _hora_actual_lima())
        revocada = replace(
            asignacion,
            activa=False,
            revocada_en=momento,
            motivo_revocacion=motivo_limpio,
        )
        _registrar_auditoria_operacion(
            operador=operador,
            asignacion=asignacion,
            fecha_hora=momento,
            estado_anterior="ACTIVA",
            estado_nuevo="REVOCADA",
            accion="REVOCAR_DOCENTE",
            eventos_auditoria_existentes=eventos_auditoria_existentes,
            persistir_auditoria=persistir_auditoria,
            motivo=motivo_limpio or "Revocación de asignación docente",
        )
        return revocada

    @staticmethod
    def eliminar_asignacion(
        operador: ActorDocente,
        asignacion: AsignacionDocente,
        tiene_calificaciones_asociadas: bool = False,
        fecha_hora: datetime | None = None,
        roles: Sequence[Rol] | None = None,
        eventos_auditoria_existentes: Sequence[RegistroAuditoria] = (),
        persistir_auditoria: Callable[[RegistroAuditoria], None] | None = None,
    ) -> RegistroAuditoria:
        """Permite eliminar una asignación solo si no posee calificaciones asociadas."""
        ServicioAsignacionDocente.validar_operador_asignacion(operador, roles=roles)
        if tiene_calificaciones_asociadas:
            raise AsignacionEnUsoException(
                "No se puede eliminar la asignación porque tiene calificaciones asociadas; "
                "utilice la revocación para preservar el historial."
            )
        momento = _normalizar_fecha_hora(fecha_hora or _hora_actual_lima())
        return _registrar_auditoria_operacion(
            operador=operador,
            asignacion=asignacion,
            fecha_hora=momento,
            estado_anterior="ACTIVA" if asignacion.activa else "REVOCADA",
            estado_nuevo="ELIMINADA",
            accion="ELIMINAR_ASIGNACION",
            eventos_auditoria_existentes=eventos_auditoria_existentes,
            persistir_auditoria=persistir_auditoria,
        )

    @staticmethod
    def validar_ambito_docente(
        docente: ActorDocente,
        curso_id: int,
        salon_id: int,
        anio_lectivo: int,
        asignaciones: Sequence[AsignacionDocente],
        roles: Sequence[Rol] | None = None,
        *,
        fecha_hora: datetime | None = None,
        eventos_auditoria_existentes: Sequence[RegistroAuditoria] = (),
        persistir_auditoria: Callable[[RegistroAuditoria], None] | None = None,
    ) -> AsignacionDocente:
        """Verifica que el docente esté habilitado y posea asignación activa en el grupo."""
        _validar_entero_positivo(curso_id, "curso_id")
        _validar_entero_positivo(salon_id, "salon_id")
        _validar_anio_lectivo(anio_lectivo)

        if not _actor_activo(docente):
            raise _auditar_y_denegar_ambito(
                docente=docente,
                curso_id=curso_id,
                salon_id=salon_id,
                anio_lectivo=anio_lectivo,
                mensaje="El usuario docente se encuentra inactivo.",
                fecha_hora=fecha_hora,
                eventos_auditoria_existentes=eventos_auditoria_existentes,
                persistir_auditoria=persistir_auditoria,
            )

        if not ServicioAutenticacionYPermisos.tiene_permiso(
            docente.rol,
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            roles=roles,
        ):
            raise _auditar_y_denegar_ambito(
                docente=docente,
                curso_id=curso_id,
                salon_id=salon_id,
                anio_lectivo=anio_lectivo,
                mensaje=(
                    f"El rol {_codigo_rol(docente.rol)} no tiene permiso para "
                    "registrar calificaciones."
                ),
                fecha_hora=fecha_hora,
                eventos_auditoria_existentes=eventos_auditoria_existentes,
                persistir_auditoria=persistir_auditoria,
            )

        for asignacion in asignaciones:
            if (
                asignacion.activa
                and asignacion.usuario_docente_id == docente.id
                and asignacion.curso_id == curso_id
                and asignacion.salon_id == salon_id
                and asignacion.anio_lectivo == anio_lectivo
            ):
                return asignacion

        raise _auditar_y_denegar_ambito(
            docente=docente,
            curso_id=curso_id,
            salon_id=salon_id,
            anio_lectivo=anio_lectivo,
            mensaje="El docente no cuenta con una asignación activa para el curso y salón.",
            fecha_hora=fecha_hora,
            eventos_auditoria_existentes=eventos_auditoria_existentes,
            persistir_auditoria=persistir_auditoria,
        )

    @staticmethod
    def listar_asignaciones_docente(
        usuario_docente_id: int | None,
        asignaciones: Sequence[AsignacionDocente],
        solo_activas: bool = True,
        *,
        curso_id: int | None = None,
        salon_id: int | None = None,
        anio_lectivo: int | None = None,
    ) -> list[AsignacionDocente]:
        """Filtra asignaciones por docente, curso, salón, año lectivo y estado."""
        resultado = list(asignaciones)
        if solo_activas:
            resultado = [a for a in resultado if a.activa]
        if usuario_docente_id is not None:
            resultado = [a for a in resultado if a.usuario_docente_id == usuario_docente_id]
        if curso_id is not None:
            resultado = [a for a in resultado if a.curso_id == curso_id]
        if salon_id is not None:
            resultado = [a for a in resultado if a.salon_id == salon_id]
        if anio_lectivo is not None:
            resultado = [a for a in resultado if a.anio_lectivo == anio_lectivo]
        return resultado
