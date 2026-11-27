"""Pruebas de aceptación ATDD (pytest-bdd) para PBI-10: Libro de Calificaciones 3 Niveles."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.calificaciones import (
    CalificacionException,
    EscalaLiteral,
    ServicioCalificaciones,
)
from src.dominio.docentes import AsignacionDocente
from src.dominio.justificaciones import PeriodoAcademico, TipoPeriodo
from src.dominio.usuarios import EstadoUsuario, PermisoOperacion, Rol, Usuario

scenarios("features/pbi10_calificaciones.feature")


@pytest.fixture
def contexto() -> dict[str, Any]:
    return {}


@given(parsers.parse('un docente asignado al curso "{curso}" en "{grupo}"'))
def docente_asignado(contexto: dict[str, Any], curso: str, grupo: str) -> None:
    rol_docente = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion=f"Docente de {curso} en {grupo}",
        permisos=frozenset(
            {
                PermisoOperacion.REGISTRAR_CALIFICACIONES,
                PermisoOperacion.CONSULTAR_CALIFICACIONES,
            }
        ),
    )
    docente = Usuario(
        id=10,
        username="docente_atdd",
        password_hash="h",
        salt="s",
        nombre_completo="Docente ATDD",
        rol=rol_docente.codigo,
        estado=EstadoUsuario.ACTIVO,
    )
    asignacion = AsignacionDocente(
        id="asg-atdd-01",
        usuario_docente_id=docente.id,
        curso_id=1,
        salon_id=1,
        anio_lectivo=2026,
        activa=True,
        asignado_por=1,
    )
    contexto["roles"] = [rol_docente]
    contexto["docente"] = docente
    contexto["asignacion"] = asignacion
    contexto["asignaciones"] = [asignacion]


@given(parsers.parse('un período académico abierto con fecha límite "{fecha_limite}"'))
def periodo_abierto(contexto: dict[str, Any], fecha_limite: str) -> None:
    contexto["periodo"] = PeriodoAcademico(
        id=1,
        nombre="Bimestre I - 2026",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 5, 15),
        cerrado=False,
        anio_lectivo=2026,
        tipo_periodo=TipoPeriodo.BIMESTRE,
        orden=1,
        fecha_limite_notas=date.fromisoformat(fecha_limite),
    )


@given(parsers.parse("rubros ponderados configurados con pesos {peso1:d} y {peso2:d} por ciento"))
def rubros_configurados(contexto: dict[str, Any], peso1: int, peso2: int) -> None:
    fecha_config = datetime(2026, 5, 1, 9, 0, 0, tzinfo=ZONA_HORARIA_LIMA)
    rubros = ServicioCalificaciones.configurar_rubros(
        docente=contexto["docente"],
        asignacion=contexto["asignacion"],
        periodo=contexto["periodo"],
        rubros_propuestos=[
            ("Prácticas", Decimal(str(peso1))),
            ("Examen Final", Decimal(str(peso2))),
        ],
        fecha_actual=fecha_config,
        asignaciones=contexto["asignaciones"],
        roles=contexto["roles"],
    )
    actividad = ServicioCalificaciones.crear_actividad(
        docente=contexto["docente"],
        asignacion=contexto["asignacion"],
        periodo=contexto["periodo"],
        rubro=rubros[0],
        titulo="Evaluación ATDD 1",
        fecha_actividad=date(2026, 5, 5),
        fecha_actual=fecha_config,
        asignaciones=contexto["asignaciones"],
        roles=contexto["roles"],
    )
    contexto["rubros"] = rubros
    contexto["actividad"] = actividad


@when(parsers.parse('registra la nota "{nota}" en la actividad del rubro único el día "{dia}"'))
def registrar_nota(contexto: dict[str, Any], nota: str, dia: str) -> None:
    fecha_registro = datetime.combine(
        date.fromisoformat(dia),
        datetime.min.time(),
        tzinfo=ZONA_HORARIA_LIMA,
    )
    try:
        contexto["calificacion"] = ServicioCalificaciones.registrar_calificacion(
            docente=contexto["docente"],
            asignacion=contexto["asignacion"],
            periodo=contexto["periodo"],
            actividad=contexto["actividad"],
            alumno_id=501,
            nota=Decimal(nota),
            fecha_hora=fecha_registro,
            asignaciones=contexto["asignaciones"],
            roles=contexto["roles"],
        )
    except CalificacionException as error:
        contexto["error"] = error


@when(
    parsers.parse(
        'intenta configurar rubros con pesos {peso1:d} y {peso2:d} por ciento el día "{dia}"'
    )
)
def intentar_rubros(contexto: dict[str, Any], peso1: int, peso2: int, dia: str) -> None:
    fecha_config = datetime.combine(
        date.fromisoformat(dia),
        datetime.min.time(),
        tzinfo=ZONA_HORARIA_LIMA,
    )
    try:
        ServicioCalificaciones.configurar_rubros(
            docente=contexto["docente"],
            asignacion=contexto["asignacion"],
            periodo=contexto["periodo"],
            rubros_propuestos=[
                ("Prácticas", Decimal(str(peso1))),
                ("Examen Final", Decimal(str(peso2))),
            ],
            fecha_actual=fecha_config,
            asignaciones=contexto["asignaciones"],
            roles=contexto["roles"],
        )
    except CalificacionException as error:
        contexto["error"] = error


@then(
    parsers.parse('la nota queda registrada con valor exacto "{nota}" y escala literal "{escala}"')
)
def verificar_nota_y_escala(contexto: dict[str, Any], nota: str, escala: str) -> None:
    calificacion = contexto["calificacion"]
    assert calificacion.nota == Decimal(nota)
    assert ServicioCalificaciones.convertir_a_literal(calificacion.nota) == EscalaLiteral(escala)


@then(parsers.parse('el sistema rechaza la calificación con error "{nombre_error}"'))
def verificar_rechazo_calificacion(contexto: dict[str, Any], nombre_error: str) -> None:
    error = contexto.get("error")
    assert error is not None
    assert type(error).__name__ == nombre_error
