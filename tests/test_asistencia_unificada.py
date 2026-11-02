from datetime import time

import pytest

from src.dominio.asistencia_unificada import AsistenciaUnificada


def test_ingreso_a_tiempo():
    resultado = AsistenciaUnificada.registrar_asistencia(time(7, 50))
    assert resultado["estado"] == "ASISTENCIA"
    assert resultado["minutos_tardanza"] == 0


def test_ingreso_con_tardanza():
    resultado = AsistenciaUnificada.registrar_asistencia(time(8, 5))
    assert resultado["estado"] == "TARDANZA"
    assert resultado["minutos_tardanza"] == 5


def test_ingreso_exacto_en_hora_limite_es_asistencia():
    resultado = AsistenciaUnificada.registrar_asistencia(time(8, 0))
    assert resultado["estado"] == "ASISTENCIA"
    assert resultado["minutos_tardanza"] == 0


@pytest.mark.parametrize(
    ("hora", "minutos_esperados"),
    [
        (time(8, 1), 1),
        (time(8, 30), 30),
        (time(9, 15), 75),
    ],
)
def test_calculo_de_minutos_de_tardanza(hora, minutos_esperados):
    resultado = AsistenciaUnificada.registrar_asistencia(hora)
    assert resultado["estado"] == "TARDANZA"
    assert resultado["minutos_tardanza"] == minutos_esperados


def test_hora_invalida_lanza_error():
    with pytest.raises(TypeError):
        AsistenciaUnificada.registrar_asistencia("08:00")
