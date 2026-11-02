import uuid
from dataclasses import dataclass
from datetime import date, time
from typing import ClassVar

from src.dominio.asistencia import (
    Alumno,
    EstadoAlumno,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
)


class AforoException(Exception):
    """Excepción base para el módulo de Aforo y Dashboard."""


class PermisoAforoException(AforoException):
    """Lanzada cuando un rol no autorizado intenta consultar o configurar el dashboard."""


class CierreYaEjecutadoException(AforoException):
    """Lanzada cuando se intenta ejecutar el cierre sobre una fecha ya cerrada."""


@dataclass(frozen=True)
class ResumenSalon:
    nivel: str
    grado: str
    seccion: str
    total_matriculados: int
    presentes: int
    tardanzas: int
    ausentes: int
    justificados: int
    pendientes: int
    porcentaje_asistencia: float


@dataclass(frozen=True)
class MetricasAforo:
    total_matriculados: int
    presentes: int
    tardanzas: int
    ausentes: int
    justificados: int
    pendientes: int
    porcentaje_asistencia: float
    aforo_actual_plantel: int
    fecha_escolar: date
    hora_consulta: time
    hora_cierre_oficial: time
    desglose_salones: list[ResumenSalon]


@dataclass(frozen=True)
class EventoCierreDiario:
    id: str
    fecha_escolar: date
    hora_cierre: time
    total_ausentes_marcados: int
    alumnos_ids_afectados: list[int]


class ServicioAforo:
    """Implementa las reglas de negocio del PBI-03 (Dashboard de Aforo en Tiempo Real)."""

    ROLES_CONSULTA: ClassVar[set[RolUsuario]] = {
        RolUsuario.ADMIN,
        RolUsuario.COORDINADOR,
        RolUsuario.ADMIN_STAFF,
    }

    @classmethod
    def validar_acceso_consulta(cls, operador: UsuarioOperador) -> None:
        """RN-05 actualizada: ADMIN, COORDINADOR y ADMIN_STAFF pueden consultar el dashboard."""
        if not operador.activo:
            raise PermisoAforoException("El operador no tiene una cuenta activa.")
        if operador.rol not in cls.ROLES_CONSULTA:
            raise PermisoAforoException(
                f"El rol {operador.rol} no está autorizado para acceder al dashboard."
            )

    @classmethod
    def configurar_hora_cierre(
        cls, operador: UsuarioOperador, nueva_hora_cierre: time
    ) -> time:
        """RN-17 actualizada: únicamente ADMIN puede configurar la hora de cierre automático."""
        if not operador.activo:
            raise PermisoAforoException("El operador no tiene una cuenta activa.")
        if operador.rol != RolUsuario.ADMIN:
            raise PermisoAforoException(
                "Únicamente el rol ADMIN tiene permisos para configurar la hora de cierre."
            )
        return nueva_hora_cierre

    @classmethod
    def calcular_metricas(
        cls,
        operador: UsuarioOperador,
        alumnos: list[Alumno],
        asistencias_dia: list[RegistroAsistencia],
        fecha_escolar: date,
        hora_consulta: time,
        hora_cierre: time = time(9, 0, 0),
    ) -> MetricasAforo:
        """Calcula los indicadores globales y el desglose por salón (Nivel-Grado-Sección)."""
        cls.validar_acceso_consulta(operador)

        # Mapear asistencias por alumno_id
        mapa_asistencias = {ast.alumno_id: ast for ast in asistencias_dia}

        # Agrupar alumnos activos por salón (nivel, grado, seccion)
        salones_map: dict[tuple[str, str, str], list[Alumno]] = {}
        for al in alumnos:
            if al.estado != EstadoAlumno.ACTIVO:
                continue
            clave_salon = (al.nivel, al.grado, al.seccion)
            salones_map.setdefault(clave_salon, []).append(al)

        global_presentes = 0
        global_tardanzas = 0
        global_ausentes = 0
        global_justificados = 0
        global_pendientes = 0
        global_matriculados = 0

        desglose: list[ResumenSalon] = []

        es_cierre_efectuado = hora_consulta >= hora_cierre

        for (nivel, grado, seccion), lista_alumnos in sorted(salones_map.items()):
            tot_sal = len(lista_alumnos)
            pres_sal = 0
            tard_sal = 0
            aus_sal = 0
            just_sal = 0
            pend_sal = 0

            for al in lista_alumnos:
                ast = mapa_asistencias.get(al.id)
                if ast is None:
                    if es_cierre_efectuado:
                        aus_sal += 1
                    else:
                        pend_sal += 1
                else:
                    if ast.estado == EstadoAsistencia.PUNTUAL:
                        pres_sal += 1
                    elif ast.estado == EstadoAsistencia.TARDANZA:
                        tard_sal += 1
                    elif ast.estado == EstadoAsistencia.AUSENTE:
                        aus_sal += 1
                    elif ast.estado == EstadoAsistencia.JUSTIFICADO:
                        just_sal += 1
                    elif ast.estado == EstadoAsistencia.PENDIENTE:
                        if es_cierre_efectuado:
                            aus_sal += 1
                        else:
                            pend_sal += 1

            pct_sal = (
                round(((pres_sal + tard_sal) / tot_sal) * 100, 2)
                if tot_sal > 0
                else 0.0
            )

            desglose.append(
                ResumenSalon(
                    nivel=nivel,
                    grado=grado,
                    seccion=seccion,
                    total_matriculados=tot_sal,
                    presentes=pres_sal,
                    tardanzas=tard_sal,
                    ausentes=aus_sal,
                    justificados=just_sal,
                    pendientes=pend_sal,
                    porcentaje_asistencia=pct_sal,
                )
            )

            global_matriculados += tot_sal
            global_presentes += pres_sal
            global_tardanzas += tard_sal
            global_ausentes += aus_sal
            global_justificados += just_sal
            global_pendientes += pend_sal

        pct_global = (
            round(
                ((global_presentes + global_tardanzas) / global_matriculados) * 100,
                2,
            )
            if global_matriculados > 0
            else 0.0
        )

        # Aforo actual físico en el plantel: alumnos presentes + alumnos con tardanza
        aforo_fisico = global_presentes + global_tardanzas

        return MetricasAforo(
            total_matriculados=global_matriculados,
            presentes=global_presentes,
            tardanzas=global_tardanzas,
            ausentes=global_ausentes,
            justificados=global_justificados,
            pendientes=global_pendientes,
            porcentaje_asistencia=pct_global,
            aforo_actual_plantel=aforo_fisico,
            fecha_escolar=fecha_escolar,
            hora_consulta=hora_consulta,
            hora_cierre_oficial=hora_cierre,
            desglose_salones=desglose,
        )

    @classmethod
    def ejecutar_cierre_automatico(
        cls,
        operador_o_sistema: UsuarioOperador,
        alumnos: list[Alumno],
        asistencias_existentes: list[RegistroAsistencia],
        fecha_escolar: date,
        hora_cierre: time,
    ) -> tuple[list[RegistroAsistencia], EventoCierreDiario]:
        """Convierte alumnos sin registro al cierre en estado AUSENTE y genera eventos."""
        mapa_asistencias = {ast.alumno_id: ast for ast in asistencias_existentes}
        nuevas_ausencias: list[RegistroAsistencia] = []
        ids_afectados: list[int] = []

        for al in alumnos:
            if al.estado != EstadoAlumno.ACTIVO:
                continue
            if al.id not in mapa_asistencias:
                id_ast = f"ast-cie-{uuid.uuid4().hex[:10]}"
                nueva_ausencia = RegistroAsistencia(
                    id=id_ast,
                    alumno_id=al.id,
                    fecha_escolar=fecha_escolar,
                    hora_efectiva=hora_cierre,
                    estado=EstadoAsistencia.AUSENTE,
                    minutos_tardanza=0,
                    metodo=MetodoRegistro.MANUAL_BUSQUEDA,
                    usuario_id=operador_o_sistema.id,
                    rol_usuario=operador_o_sistema.rol,
                    estado_anterior=EstadoAsistencia.PENDIENTE,
                    motivo_correccion="CIERRE_AUTOMATICO_JORNADA",
                )
                nuevas_ausencias.append(nueva_ausencia)
                ids_afectados.append(al.id)

        evento = EventoCierreDiario(
            id=f"evt-cie-{uuid.uuid4().hex[:10]}",
            fecha_escolar=fecha_escolar,
            hora_cierre=hora_cierre,
            total_ausentes_marcados=len(nuevas_ausencias),
            alumnos_ids_afectados=ids_afectados,
        )

        return nuevas_ausencias, evento
