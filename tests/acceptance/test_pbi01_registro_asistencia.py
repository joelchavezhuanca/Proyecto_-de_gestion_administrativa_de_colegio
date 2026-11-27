"""Pruebas de aceptación ATDD (pytest-bdd) para PBI-01: Registro Unificado de Asistencia."""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/pbi01_registro_asistencia.feature")
