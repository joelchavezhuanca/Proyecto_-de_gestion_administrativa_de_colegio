import pytest
from datetime import time
from src.dominio.asistencia_unificada import AsistenciaUnificada

def test_ingreso_a_tiempo():
    resultado = AsistenciaUnificada.registrar_asistencia(time(7, 50))
    assert resultado["estado"] == "ASISTENCIA"
    assert resultado["minutos_tardanza"] == 0

def test_ingreso_con_tardanza():
    resultado = AsistenciaUnificada.registrar_asistencia(time(8, 5))
    assert resultado["estado"] == "TARDANZA"
    assert resultado["minutos_tardanza"] == 5