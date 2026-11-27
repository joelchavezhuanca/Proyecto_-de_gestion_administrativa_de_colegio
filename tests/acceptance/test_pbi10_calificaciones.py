"""Pruebas de aceptación ATDD (pytest-bdd) para PBI-10: Libro de Calificaciones 3 Niveles."""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/pbi10_calificaciones.feature")
