import uuid
from collections.abc import Collection, Sequence
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
from src.dominio.usuarios import (
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
)

ACTOR_SYSTEM_CRON = "SYSTEM_CRON"


class AforoException(Exception):
    """Excepción base para el módulo de Aforo y Dashboard."""


class PermisoAforoException(AforoException):
    """Lanzada cuando un rol no autorizado intenta consultar o configurar el dashboard."""


class CierreYaEjecutadoException(AforoException):
    """Lanzada cuando se intenta ejecutar el cierre sobre una fecha ya cerrada."""


class DiaNoLectivoException(AforoException):
    """Lanzada cuando se intenta ejecutar el cierre diario en una fecha no lectiva."""


@dataclass(frozen=True)
class CalendarioEscolar:
    """Calendario escolar institucional compartido (usado por PBI-03 y PBI-17)."""

    dias_no_lectivos: frozenset[date] = frozenset()
    excepciones_lectivas: frozenset[date] = frozenset()
    fines_de_semana_no_lectivos: bool = True

    def es_dia_lectivo(self, fecha: date) -> bool:
        """Determina si una fecha es día lectivo habilitado."""
        if fecha in self.excepciones_lectivas:
            return True
        if fecha in self.dias_no_lectivos:
            return False
        if self.fines_de_semana_no_lectivos and fecha.weekday() >= 5:
            return False
        return True


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
class DetalleAsistenciaAlumno:
    alumno_id: int
    codigo: str
    dni: str
    nombre_completo: str
    nivel: str
    grado: str
    seccion: str
    estado: EstadoAsistencia
    hora_efectiva: time | None
    minutos_tardanza: int
    metodo: MetodoRegistro | None


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


def _texto_rol(rol: RolUsuario | str) -> str:
    return rol.value if isinstance(rol, RolUsuario) else str(rol)


def _coincide_texto(valor: str, filtro: str | None) -> bool:
    return filtro is None or valor.strip().casefold() == filtro.strip().casefold()


class ServicioAforo:
    """Implementa las reglas de negocio del PBI-03 (Dashboard de Aforo en Tiempo Real)."""

    ROLES_CONSULTA: ClassVar[set[RolUsuario]] = {
        RolUsuario.ADMIN,
        RolUsuario.COORDINADOR,
        RolUsuario.ADMIN_STAFF,
    }

    @staticmethod
    def _validar_permiso_operador(
        operador: UsuarioOperador,
        permiso: PermisoOperacion,
        mensaje_denegado: str,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        if not operador.activo:
            raise PermisoAforoException("El operador no tiene una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(operador.rol, permiso, roles=roles):
            raise PermisoAforoException(mensaje_denegado)

    @classmethod
    def validar_acceso_consulta(
        cls,
        operador: UsuarioOperador,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida cuenta activa y permiso CONSULTAR_DASHBOARD_AFORO (roles base y dinámicos)."""
        cls._validar_permiso_operador(
            operador,
            PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
            f"El rol {_texto_rol(operador.rol)} no está autorizado para acceder al dashboard.",
            roles=roles,
        )

    @classmethod
    def configurar_hora_cierre(
        cls,
        operador: UsuarioOperador,
        nueva_hora_cierre: time,
        roles: Sequence[Rol] | None = None,
    ) -> time:
        """Valida cuenta activa y permiso CONFIGURAR_CIERRE_ASISTENCIA."""
        cls._validar_permiso_operador(
            operador,
            PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA,
            (
                "Únicamente el rol ADMIN o un rol con permiso CONFIGURAR_CIERRE_ASISTENCIA "
                "puede configurar la hora de cierre."
            ),
            roles=roles,
        )
        return nueva_hora_cierre

    @classmethod
    def _validar_actor_cierre(
        cls,
        operador_o_sistema: UsuarioOperador | str,
        roles: Sequence[Rol] | None = None,
    ) -> tuple[int, RolUsuario | str]:
        """Valida que el ejecutor del cierre sea SYSTEM_CRON o un operador autorizado."""
        if isinstance(operador_o_sistema, str):
            if operador_o_sistema == ACTOR_SYSTEM_CRON:
                return 0, ACTOR_SYSTEM_CRON
            raise PermisoAforoException(
                f"El actor '{operador_o_sistema}' no está autorizado para ejecutar el cierre."
            )
        cls._validar_permiso_operador(
            operador_o_sistema,
            PermisoOperacion.EJECUTAR_CIERRE_ASISTENCIA,
            (
                f"El rol {_texto_rol(operador_o_sistema.rol)} no está autorizado "
                "para ejecutar el cierre diario."
            ),
            roles=roles,
        )
        return operador_o_sistema.id, operador_o_sistema.rol

    @classmethod
    def calcular_metricas(
        cls,
        operador: UsuarioOperador,
        alumnos: Sequence[Alumno],
        asistencias_dia: Sequence[RegistroAsistencia],
        fecha_escolar: date,
        hora_consulta: time,
        hora_cierre: time = time(9, 0, 0),
        nivel: str | None = None,
        grado: str | None = None,
        seccion: str | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> MetricasAforo:
        """Calcula indicadores globales y por salón con filtros opcionales."""
        cls.validar_acceso_consulta(operador, roles=roles)

        mapa_asistencias = {ast.alumno_id: ast for ast in asistencias_dia}

        salones_map: dict[tuple[str, str, str], list[Alumno]] = {}
        for al in alumnos:
            if al.estado != EstadoAlumno.ACTIVO:
                continue
            if not (
                _coincide_texto(al.nivel, nivel)
                and _coincide_texto(al.grado, grado)
                and _coincide_texto(al.seccion, seccion)
            ):
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

        for (sal_nivel, sal_grado, sal_seccion), lista_alumnos in sorted(salones_map.items()):
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
                elif ast.estado == EstadoAsistencia.PUNTUAL:
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

            pct_sal = round(((pres_sal + tard_sal) / tot_sal) * 100, 2) if tot_sal > 0 else 0.0

            desglose.append(
                ResumenSalon(
                    nivel=sal_nivel,
                    grado=sal_grado,
                    seccion=sal_seccion,
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
            round(((global_presentes + global_tardanzas) / global_matriculados) * 100, 2)
            if global_matriculados > 0
            else 0.0
        )

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
    def obtener_detalle_salon(
        cls,
        operador: UsuarioOperador,
        alumnos: Sequence[Alumno],
        asistencias_dia: Sequence[RegistroAsistencia],
        nivel: str,
        grado: str,
        seccion: str,
        hora_consulta: time,
        hora_cierre: time = time(9, 0, 0),
        roles: Sequence[Rol] | None = None,
    ) -> list[DetalleAsistenciaAlumno]:
        """Retorna el detalle individual de asistencia para los alumnos activos de un salón."""
        cls.validar_acceso_consulta(operador, roles=roles)

        mapa_asistencias = {ast.alumno_id: ast for ast in asistencias_dia}
        es_cierre_efectuado = hora_consulta >= hora_cierre

        alumnos_salon = [
            al
            for al in alumnos
            if al.estado == EstadoAlumno.ACTIVO
            and _coincide_texto(al.nivel, nivel)
            and _coincide_texto(al.grado, grado)
            and _coincide_texto(al.seccion, seccion)
        ]
        alumnos_salon.sort(key=lambda al: (al.apellidos.casefold(), al.nombres.casefold(), al.id))

        detalles: list[DetalleAsistenciaAlumno] = []
        for al in alumnos_salon:
            ast = mapa_asistencias.get(al.id)
            if ast is None:
                estado = (
                    EstadoAsistencia.AUSENTE if es_cierre_efectuado else EstadoAsistencia.PENDIENTE
                )
                hora_efectiva: time | None = None
                minutos_tardanza = 0
                metodo: MetodoRegistro | None = None
            elif ast.estado == EstadoAsistencia.PENDIENTE and es_cierre_efectuado:
                estado = EstadoAsistencia.AUSENTE
                hora_efectiva = ast.hora_efectiva
                minutos_tardanza = 0
                metodo = ast.metodo
            else:
                estado = ast.estado
                hora_efectiva = ast.hora_efectiva
                minutos_tardanza = ast.minutos_tardanza
                metodo = ast.metodo

            detalles.append(
                DetalleAsistenciaAlumno(
                    alumno_id=al.id,
                    codigo=al.codigo,
                    dni=al.dni,
                    nombre_completo=f"{al.nombres} {al.apellidos}".strip(),
                    nivel=al.nivel,
                    grado=al.grado,
                    seccion=al.seccion,
                    estado=estado,
                    hora_efectiva=hora_efectiva,
                    minutos_tardanza=minutos_tardanza,
                    metodo=metodo,
                )
            )
        return detalles

    @classmethod
    def consultar_historial_modificaciones(
        cls,
        operador: UsuarioOperador,
        asistencias: Sequence[RegistroAsistencia],
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        alumno_id: int | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> list[RegistroAsistencia]:
        """Consulta registros de asistencia modificados/corregidos/justificados (RN-05)."""
        cls._validar_permiso_operador(
            operador,
            PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
            (
                f"El rol {_texto_rol(operador.rol)} no está autorizado "
                "para consultar el historial de asistencia."
            ),
            roles=roles,
        )

        if fecha_desde is not None and fecha_hasta is not None and fecha_desde > fecha_hasta:
            raise AforoException("El rango de fechas del historial es inválido.")

        resultados: list[RegistroAsistencia] = []
        for ast in asistencias:
            if ast.estado_anterior is None:
                continue
            if fecha_desde is not None and ast.fecha_escolar < fecha_desde:
                continue
            if fecha_hasta is not None and ast.fecha_escolar > fecha_hasta:
                continue
            if alumno_id is not None and ast.alumno_id != alumno_id:
                continue
            resultados.append(ast)

        resultados.sort(key=lambda ast: (ast.fecha_escolar, ast.hora_efectiva, ast.id))
        return resultados

    @classmethod
    def ejecutar_cierre_automatico(
        cls,
        operador_o_sistema: UsuarioOperador | str,
        alumnos: Sequence[Alumno],
        asistencias_existentes: Sequence[RegistroAsistencia],
        fecha_escolar: date,
        hora_cierre: time,
        fechas_ya_cerradas: Collection[date] | None = None,
        calendario: CalendarioEscolar | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> tuple[list[RegistroAsistencia], EventoCierreDiario]:
        """Convierte alumnos sin registro (o en PENDIENTE) al cierre en estado AUSENTE."""
        actor_id, actor_rol = cls._validar_actor_cierre(operador_o_sistema, roles=roles)

        if fechas_ya_cerradas is not None and fecha_escolar in fechas_ya_cerradas:
            raise CierreYaEjecutadoException(
                f"El cierre diario para la fecha {fecha_escolar} ya fue ejecutado."
            )

        if calendario is not None and not calendario.es_dia_lectivo(fecha_escolar):
            raise DiaNoLectivoException(
                f"La fecha {fecha_escolar} no es un día lectivo habilitado para cierre."
            )

        mapa_asistencias = {ast.alumno_id: ast for ast in asistencias_existentes}
        nuevas_ausencias: list[RegistroAsistencia] = []
        ids_afectados: list[int] = []

        for al in alumnos:
            if al.estado != EstadoAlumno.ACTIVO:
                continue
            ast_actual = mapa_asistencias.get(al.id)
            if ast_actual is None or ast_actual.estado == EstadoAsistencia.PENDIENTE:
                id_ast = (
                    ast_actual.id if ast_actual is not None else f"ast-cie-{uuid.uuid4().hex[:10]}"
                )
                nueva_ausencia = RegistroAsistencia(
                    id=id_ast,
                    alumno_id=al.id,
                    fecha_escolar=fecha_escolar,
                    hora_efectiva=hora_cierre,
                    estado=EstadoAsistencia.AUSENTE,
                    minutos_tardanza=0,
                    metodo=MetodoRegistro.MANUAL_BUSQUEDA,
                    usuario_id=actor_id,
                    rol_usuario=actor_rol,  # type: ignore[arg-type]
                    estado_anterior=EstadoAsistencia.PENDIENTE,
                    motivo_correccion="CIERRE_AUTOMATICO_JORNADA",
                    nivel=(ast_actual.nivel if ast_actual is not None else None) or al.nivel,
                    grado=(ast_actual.grado if ast_actual is not None else None) or al.grado,
                    seccion=(
                        (ast_actual.seccion if ast_actual is not None else None) or al.seccion
                    ),
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
