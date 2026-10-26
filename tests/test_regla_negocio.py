from datetime import time

import pytest

from src.dominio.regla_negocio import (
    CarnetAnuladoException,
    evaluar_asistencia_estudiante,
)


def test_asistencia_puntual_antes_o_en_tolerancia():
    """Dado un alumno activo a las 07:00:00 (tolerancia 07:15:00), debe ser PUNTUAL con 0 min."""
    hora_ingreso = time(7, 0, 0)
    resultado = evaluar_asistencia_estudiante("CRN-72945", hora_ingreso, estado_carnet="ACTIVO")

    assert resultado["estado"] == "PUNTUAL"
    assert resultado["minutos_tardanza"] == 0


def test_asistencia_tardanza_a_las_07_30():
    """Dado un alumno a las 07:30:00, debe ser TARDANZA con 10 minutos."""
    hora_ingreso = time(7, 30, 0)
    resultado = evaluar_asistencia_estudiante("CRN-72945", hora_ingreso, estado_carnet="ACTIVO")

    assert resultado["estado"] == "TARDANZA"
    assert resultado["minutos_tardanza"] == 10


def test_asistencia_limite_exacto_07_15_es_puntual():
    """Caso Frontera: Marcación a las 07:15:00 exactas debe considerarse PUNTUAL."""
    hora_ingreso = time(7, 15, 0)
    resultado = evaluar_asistencia_estudiante("CRN-72945", hora_ingreso, estado_carnet="ACTIVO")

    assert resultado["estado"] == "PUNTUAL"
    assert resultado["minutos_tardanza"] == 0


def test_asistencia_carnet_anulado_lanza_excepcion():
    """Caso Excepcional: Carnet reportado como ANULADO debe lanzar excepción."""
    hora_ingreso = time(7, 5, 0)
    with pytest.raises(CarnetAnuladoException):
        evaluar_asistencia_estudiante("CRN-ANULADO-01", hora_ingreso, estado_carnet="ANULADO")
