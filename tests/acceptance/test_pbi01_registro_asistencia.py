"""Pruebas de aceptación ATDD (pytest-bdd) para PBI-01: Registro Unificado de Asistencia."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.dominio.asistencia import (
    Alumno,
    AsistenciaException,
    EstadoAlumno,
    EstadoAsistencia,
    MetodoRegistro,
    RegistroAsistencia,
    RolUsuario,
    UsuarioOperador,
    registrar_asistencia_unificada,
)
from src.dominio.auditoria import ZONA_HORARIA_LIMA

scenarios("features/pbi01_registro_asistencia.feature")

FECHA_ESCOLAR = date(2026, 5, 11)


@pytest.fixture
def contexto() -> dict[str, Any]:
    return {}


@given(parsers.parse('un operador activo con rol "{rol}"'))
def operador_activo(contexto: dict[str, Any], rol: str) -> None:
    contexto["operador"] = UsuarioOperador(
        id=1,
        username="operador_atdd",
        rol=RolUsuario(rol),
        activo=True,
    )


@given(parsers.parse('un alumno ACTIVO con carnet vigente "{carnet}"'))
def alumno_activo(contexto: dict[str, Any], carnet: str) -> None:
    contexto["alumno"] = Alumno(
        id=101,
        codigo="ALU-2026-101",
        dni="71234567",
        nombres="Lucía",
        apellidos="Quispe Paredes",
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        carnet_codigo=carnet,
        estado=EstadoAlumno.ACTIVO,
    )
    contexto["carnet"] = carnet


@given(parsers.parse('un alumno INACTIVO con carnet "{carnet}"'))
def alumno_inactivo(contexto: dict[str, Any], carnet: str) -> None:
    contexto["alumno"] = Alumno(
        id=102,
        codigo="ALU-2026-102",
        dni="79876543",
        nombres="Diego",
        apellidos="Salas Ruiz",
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        carnet_codigo=carnet,
        estado=EstadoAlumno.INACTIVO,
    )
    contexto["carnet"] = carnet


@given(parsers.parse('el alumno ya tiene una asistencia previa en estado "{estado}"'))
def asistencia_previa(contexto: dict[str, Any], estado: str) -> None:
    alumno: Alumno = contexto["alumno"]
    contexto["asistencia_existente"] = RegistroAsistencia(
        id="ast-previa-001",
        alumno_id=alumno.id,
        fecha_escolar=FECHA_ESCOLAR,
        hora_efectiva=time(7, 10, 0),
        estado=EstadoAsistencia(estado),
        minutos_tardanza=0,
        metodo=MetodoRegistro.CARNET,
        usuario_id=1,
        rol_usuario=RolUsuario.ADMIN_STAFF,
        nivel=alumno.nivel,
        grado=alumno.grado,
        seccion=alumno.seccion,
    )


@when(parsers.parse('registra el ingreso por carnet a las "{hora}" hora oficial del servidor'))
def registrar_ingreso(contexto: dict[str, Any], hora: str) -> None:
    hora_servidor = time.fromisoformat(hora)
    try:
        contexto["resultado"] = registrar_asistencia_unificada(
            operador=contexto["operador"],
            alumno=contexto["alumno"],
            metodo=MetodoRegistro.CARNET,
            hora_servidor=hora_servidor,
            fecha_escolar=FECHA_ESCOLAR,
            asistencia_existente=contexto.get("asistencia_existente"),
            codigo_carnet=contexto["carnet"],
            timestamp_servidor=datetime.combine(
                FECHA_ESCOLAR, hora_servidor, tzinfo=ZONA_HORARIA_LIMA
            ),
        )
    except AsistenciaException as error:
        contexto["error"] = error


@when(parsers.parse('corrige el ingreso por carnet a las "{hora}" con motivo "{motivo}"'))
def corregir_ingreso(contexto: dict[str, Any], hora: str, motivo: str) -> None:
    hora_servidor = time.fromisoformat(hora)
    try:
        contexto["resultado"] = registrar_asistencia_unificada(
            operador=contexto["operador"],
            alumno=contexto["alumno"],
            metodo=MetodoRegistro.CARNET,
            hora_servidor=hora_servidor,
            fecha_escolar=FECHA_ESCOLAR,
            asistencia_existente=contexto.get("asistencia_existente"),
            motivo_correccion=motivo,
            codigo_carnet=contexto["carnet"],
            timestamp_servidor=datetime.combine(
                FECHA_ESCOLAR, hora_servidor, tzinfo=ZONA_HORARIA_LIMA
            ),
        )
    except AsistenciaException as error:
        contexto["error"] = error


@then(
    parsers.parse(
        'la asistencia queda confirmada con estado "{estado}" y {minutos:d} minutos de tardanza'
    )
)
def verificar_asistencia_confirmada(
    contexto: dict[str, Any], estado: str, minutos: int
) -> None:
    resultado = contexto["resultado"]
    assert resultado.asistencia.estado == EstadoAsistencia(estado)
    assert resultado.asistencia.minutos_tardanza == minutos
    assert resultado.registro_auditoria_pbi16 is not None


@then(parsers.parse('el sistema rechaza la asistencia con error "{nombre_error}"'))
def verificar_rechazo_asistencia(contexto: dict[str, Any], nombre_error: str) -> None:
    error = contexto.get("error")
    assert error is not None
    assert type(error).__name__ == nombre_error
