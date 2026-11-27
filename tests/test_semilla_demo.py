"""Pruebas de la semilla opcional de datos realistas para demostración."""

from __future__ import annotations

from datetime import date, datetime
from time import perf_counter

import pytest
from sqlalchemy import func, select

from src.aplicacion.servicios_asistencia import ServicioAsistencia
from src.dominio.asistencia import (
    AlumnoInactivoException,
    FaltaMotivoCorreccionException,
    MetodoRegistro,
)
from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.infraestructura.base_datos import crear_motor, crear_session_factory, inicializar_bd
from src.infraestructura.modelos import (
    AlertaPagoSilenciosaModel,
    AsistenciaModel,
    CalificacionModel,
    CarnetModel,
    CursoModel,
    EstudianteModel,
    JustificacionModel,
    ObligacionPagoModel,
    SalonModel,
    UsuarioModel,
)
from src.infraestructura.semilla_demo import debe_sembrar_demo, sembrar_datos_demo

FECHA_DEMO = date(2026, 11, 27)
RELOJ_DEMO = datetime(2026, 11, 27, 7, 10, 0, tzinfo=ZONA_HORARIA_LIMA)


def test_semilla_demo_apagada_por_defecto(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("SEMBRAR_DATOS_DEMO", raising=False)
    assert debe_sembrar_demo() is False

    motor = crear_motor(f"sqlite:///{(tmp_path / 'limpia.db').as_posix()}")
    try:
        inicializar_bd(motor)
        with crear_session_factory(motor)() as session:
            assert session.scalar(select(func.count(EstudianteModel.id))) == 0
            assert session.scalar(select(func.count(SalonModel.id))) == 0
    finally:
        motor.dispose()


def test_semilla_demo_puebla_escala_realista_y_es_idempotente(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("SEMBRAR_DATOS_DEMO", "true")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "Admin2026!")
    assert debe_sembrar_demo() is True

    motor = crear_motor(f"sqlite:///{(tmp_path / 'demo.db').as_posix()}")
    try:
        inicio = perf_counter()
        inicializar_bd(motor)
        duracion = perf_counter() - inicio
        assert duracion < 5.0

        fabrica = crear_session_factory(motor)
        with fabrica() as session:
            assert session.scalar(select(func.count(SalonModel.id))) == 11
            assert session.scalar(select(func.count(EstudianteModel.id))) == 220
            assert session.scalar(select(func.count(CursoModel.id))) == 33
            assert session.scalar(select(func.count(CarnetModel.id))) == 220
            assert session.scalar(select(func.count(CalificacionModel.id))) == 1980
            assert session.scalar(select(func.count(ObligacionPagoModel.id))) == 440
            assert session.scalar(select(func.count(JustificacionModel.id))) == 6
            assert (session.scalar(select(func.count(AlertaPagoSilenciosaModel.id))) or 0) > 10
            asistencias_antes = session.scalar(select(func.count(AsistenciaModel.id)))
            assert (asistencias_antes or 0) > 900

        # Segunda ejecución: completamente idempotente (no duplica nada)
        inicializar_bd(motor)
        with fabrica() as session:
            assert session.scalar(select(func.count(EstudianteModel.id))) == 220
            assert session.scalar(select(func.count(AsistenciaModel.id))) == asistencias_antes
    finally:
        motor.dispose()


def test_escenarios_en_vivo_qr_sobre_datos_demo(tmp_path) -> None:
    motor = crear_motor(f"sqlite:///{(tmp_path / 'vivo.db').as_posix()}")
    try:
        inicializar_bd(motor)
        fabrica = crear_session_factory(motor)
        with fabrica() as session:
            resumen = sembrar_datos_demo(session, fecha_referencia=FECHA_DEMO)
            session.commit()
            assert resumen.ejecutada is True
            assert resumen.estudiantes == 220
            admin = session.scalars(select(UsuarioModel).filter_by(username="admin_demo")).one()

        servicio = ServicioAsistencia(fabrica, reloj=lambda: RELOJ_DEMO)
        try:
            # 1. CRN-2026-0001 pendiente hoy -> ingresa PUNTUAL en vivo
            r1 = servicio.registrar_asistencia(
                admin.id, metodo=MetodoRegistro.CARNET, codigo_carnet="CRN-2026-0001"
            )
            assert r1.asistencia.estado.value == "PUNTUAL"

            # 2. CRN-2026-0010 deudor vencido -> ingresa sin bloqueo y dispara alerta silenciosa
            r10 = servicio.registrar_asistencia(
                admin.id, metodo=MetodoRegistro.CARNET, codigo_carnet="CRN-2026-0010"
            )
            servicio.esperar_despachos(r10)
            assert r10.asistencia.estado.value == "PUNTUAL"

            # 3. CRN-2026-0009 marcado AUSENTE hoy -> exige motivo y luego corrige
            with pytest.raises(FaltaMotivoCorreccionException):
                servicio.registrar_asistencia(
                    admin.id, metodo=MetodoRegistro.CARNET, codigo_carnet="CRN-2026-0009"
                )
            r9 = servicio.registrar_asistencia(
                admin.id,
                metodo=MetodoRegistro.CARNET,
                codigo_carnet="CRN-2026-0009",
                motivo_correccion="Ingreso autorizado por dirección",
            )
            assert r9.asistencia.estado_anterior is not None

            # 4. CRN-2026-0217 SUSPENDIDO -> acceso bloqueado (PBI-08)
            with pytest.raises(AlumnoInactivoException):
                servicio.registrar_asistencia(
                    admin.id, metodo=MetodoRegistro.CARNET, codigo_carnet="CRN-2026-0217"
                )

            # 5. Aforo real > 190 estudiantes presentes/tardanzas hoy
            metricas = servicio.consultar_metricas_aforo(admin.id, fecha_escolar=FECHA_DEMO)
            assert metricas.total_matriculados == 216
            assert metricas.aforo_actual_plantel >= 205
        finally:
            servicio.cerrar()
    finally:
        motor.dispose()
