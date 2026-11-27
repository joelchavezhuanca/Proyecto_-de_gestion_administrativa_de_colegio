"""Pruebas de integración Flask para Ola 4 - Miembro 3 (bp_alumnos).

Cubre:
- Matrícula Digital + Apoderados (PBI-05)
- Emisión, validación y anulación de Carnet QR (PBI-06)
- Transiciones de Estados Académicos (PBI-08)
- Gestión de Pagos y Panel Restringido de Alertas Silenciosas (PBI-07)
- Seguridad: sesión en servidor (401), CSRF (400), RBAC base y personalizado (403)
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session, sessionmaker

from src.aplicacion.servicios_academico import ServicioAcademico
from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.malla_curricular import NivelEducativo
from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolUsuario,
    ServicioAutenticacionYPermisos,
    Usuario,
    hashear_password,
)
from src.infraestructura.base_datos import crear_motor, crear_session_factory, inicializar_bd
from src.infraestructura.modelos import (
    AlertaPagoSilenciosaModel,
    AsistenciaModel,
)
from src.infraestructura.repositorios import RepositorioRoles, RepositorioUsuarios
from src.presentacion.app import crear_app
from src.presentacion.bp_alumnos import registrar_blueprints_alumnos
from src.presentacion.seguridad import AlmacenSesiones

AHORA_FIJA = datetime(2026, 4, 15, 8, 30, 0, tzinfo=ZONA_HORARIA_LIMA)


def _reloj_fijo() -> datetime:
    return AHORA_FIJA


@pytest.fixture
def entorno_web() -> dict[str, Any]:
    """Crea una app Flask real conectada a SQLite en memoria con BD sembrada."""
    engine = crear_motor("sqlite:///:memory:")
    inicializar_bd(engine)
    session_factory: sessionmaker[Session] = crear_session_factory(engine)

    with session_factory() as session:
        repo_roles = RepositorioRoles(session)
        rol_tesoreria = repo_roles.guardar(
            Rol(
                codigo="TESORERIA",
                nombre="Tesorería",
                descripcion="Gestión económica y alertas de pago",
                permisos=frozenset(
                    {
                        PermisoOperacion.GESTIONAR_PAGOS,
                        PermisoOperacion.VER_ALERTA_PAGOS,
                    }
                ),
            )
        )
        rol_docente = repo_roles.guardar(
            Rol(
                codigo="DOCENTE",
                nombre="Docente",
                descripcion="Docente de aula",
                permisos=frozenset(
                    {
                        PermisoOperacion.REGISTRAR_CALIFICACIONES,
                        PermisoOperacion.CONSULTAR_CALIFICACIONES,
                    }
                ),
            )
        )

        repo_usr = RepositorioUsuarios(session)
        pwd_hash, salt = hashear_password("ClaveSegura2026!")

        admin = repo_usr.guardar(
            Usuario(
                id=0,
                username="admin_web",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Admin Web",
                rol=RolUsuario.ADMIN,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        staff = repo_usr.guardar(
            Usuario(
                id=0,
                username="staff_web",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Staff Web",
                rol=RolUsuario.ADMIN_STAFF,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        coord = repo_usr.guardar(
            Usuario(
                id=0,
                username="coord_web",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Coordinador Web",
                rol=RolUsuario.COORDINADOR,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        tesorero = repo_usr.guardar(
            Usuario(
                id=0,
                username="tesorero_web",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Tesorero Web",
                rol=rol_tesoreria.codigo,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        docente = repo_usr.guardar(
            Usuario(
                id=0,
                username="docente_web",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Docente Web",
                rol=rol_docente.codigo,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        session.commit()

    servicio = ServicioAcademico(session_factory, reloj=_reloj_fijo)
    salon_a = servicio.crear_salon(
        admin.id,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
        capacidad_maxima=30,
    )
    salon_b = servicio.crear_salon(
        admin.id,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="B",
        capacidad_maxima=30,
    )

    app = crear_app(
        {
            "SECRET_KEY": "clave-pruebas-alumnos-2026",
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "RELOJ": _reloj_fijo,
        }
    )
    app.extensions["session_factory"] = session_factory
    app.extensions["servicio_academico"] = servicio
    registrar_blueprints_alumnos(app)
    registrar_blueprints_alumnos(app)  # Idempotente frente a auto-registro en app.py

    yield {
        "app": app,
        "session_factory": session_factory,
        "servicio": servicio,
        "admin": admin,
        "staff": staff,
        "coord": coord,
        "tesorero": tesorero,
        "docente": docente,
        "rol_tesoreria": rol_tesoreria,
        "rol_docente": rol_docente,
        "salon_a": salon_a,
        "salon_b": salon_b,
    }
    engine.dispose()


def _autenticar(
    app: Flask,
    usuario: Usuario,
    roles_extra: list[Rol] | None = None,
) -> tuple[FlaskClient, str]:
    """Inicia sesión en servidor en AlmacenSesiones y devuelve (cliente, csrf_token)."""
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        usuario.username,
        "ClaveSegura2026!",
        [usuario],
        fecha_hora=AHORA_FIJA,
        roles=roles_extra,
    )
    almacen.guardar(sesion, usuario)
    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token
        sess["_csrf_token"] = f"csrf-{usuario.username}-2026"
    return cliente, f"csrf-{usuario.username}-2026"


def _datos_matricula(
    csrf: str,
    salon_id: int,
    *,
    codigo: str = "ALU-2026-001",
    dni: str = "71234567",
    nombres: str = "Sofía",
    apellidos: str = "Ramírez Vega",
    fecha_nacimiento: str = "2012-05-10",
    con_segundo_apoderado: bool = False,
) -> dict[str, str]:
    datos = {
        "csrf_token": csrf,
        "codigo_estudiante": codigo,
        "dni": dni,
        "nombres": nombres,
        "apellidos": apellidos,
        "fecha_nacimiento": fecha_nacimiento,
        "salon_id": str(salon_id),
        "apoderado_nombres": "Carlos",
        "apoderado_apellidos": "Ramírez Soto",
        "apoderado_documento": "41234567",
        "apoderado_parentesco": "PADRE",
        "apoderado_telefono": "987654321",
    }
    if con_segundo_apoderado:
        datos.update(
            {
                "apoderado2_nombres": "Elena",
                "apoderado2_apellidos": "Vega Paredes",
                "apoderado2_documento": "42345678",
                "apoderado2_parentesco": "MADRE",
                "apoderado2_telefono": "+51912345678",
            }
        )
    return datos


# ===========================================================================
# 1. Seguridad: 401 sin sesión, 400 sin CSRF, 403 RBAC base y personalizado
# ===========================================================================


def test_rutas_alumnos_exigen_sesion_401(entorno_web: dict[str, Any]) -> None:
    cliente = entorno_web["app"].test_client()
    for ruta in ("/matricula", "/carnets", "/estados", "/pagos", "/pagos/alertas"):
        resp = cliente.get(ruta)
        assert resp.status_code == 401


def test_post_sin_csrf_devuelve_400(entorno_web: dict[str, Any]) -> None:
    cliente, _ = _autenticar(entorno_web["app"], entorno_web["admin"])
    resp = cliente.post("/matricula", data={"dni": "71234567"})
    assert resp.status_code == 400
    assert "CSRF" in resp.get_data(as_text=True)


def test_rbac_roles_base_y_personalizados(entorno_web: dict[str, Any]) -> None:
    app = entorno_web["app"]

    # COORDINADOR: puede /carnets, pero 403 en /matricula, /estados, /pagos y /pagos/alertas
    cli_coord, csrf_coord = _autenticar(app, entorno_web["coord"])
    assert cli_coord.get("/carnets").status_code == 200
    assert cli_coord.get("/matricula").status_code == 403
    assert cli_coord.get("/estados").status_code == 403
    assert cli_coord.get("/pagos").status_code == 403
    assert cli_coord.get("/pagos/alertas").status_code == 403
    assert cli_coord.post("/matricula", data={"csrf_token": csrf_coord}).status_code == 403

    # ADMIN_STAFF: puede /matricula, /carnets y /pagos/alertas (VER_ALERTA_PAGOS),
    # pero 403 en /estados y POST /pagos/obligaciones (GESTIONAR_PAGOS)
    cli_staff, csrf_staff = _autenticar(app, entorno_web["staff"])
    assert cli_staff.get("/matricula").status_code == 200
    assert cli_staff.get("/carnets").status_code == 200
    assert cli_staff.get("/pagos").status_code == 200
    assert cli_staff.get("/pagos/alertas").status_code == 200
    assert cli_staff.get("/estados").status_code == 403
    assert (
        cli_staff.post(
            "/pagos/obligaciones",
            data={"csrf_token": csrf_staff, "alumno_id": "1"},
        ).status_code
        == 403
    )

    # Rol personalizado TESORERIA: puede /pagos y /pagos/alertas, 403 en /matricula y /carnets
    cli_tes, _ = _autenticar(app, entorno_web["tesorero"], [entorno_web["rol_tesoreria"]])
    assert cli_tes.get("/pagos").status_code == 200
    assert cli_tes.get("/pagos/alertas").status_code == 200
    assert cli_tes.get("/matricula").status_code == 403
    assert cli_tes.get("/carnets").status_code == 403
    assert cli_tes.get("/estados").status_code == 403

    # Rol personalizado DOCENTE: 403 en todos los módulos administrativos de alumnos
    cli_doc, _ = _autenticar(app, entorno_web["docente"], [entorno_web["rol_docente"]])
    for ruta in ("/matricula", "/carnets", "/estados", "/pagos", "/pagos/alertas"):
        assert cli_doc.get(ruta).status_code == 403


# ===========================================================================
# 2. Matrícula Digital + Apoderados + Cambio de Salón (PBI-05)
# ===========================================================================


def test_matricula_flujo_completo_y_validaciones(entorno_web: dict[str, Any]) -> None:
    app = entorno_web["app"]
    salon_a = entorno_web["salon_a"]
    salon_b = entorno_web["salon_b"]
    cliente, csrf = _autenticar(app, entorno_web["admin"])

    # GET inicial con token CSRF en el HTML
    resp_get = cliente.get("/matricula")
    assert resp_get.status_code == 200
    html = resp_get.get_data(as_text=True)
    assert "Matrícula" in html
    assert csrf in html

    # POST válido con 2 apoderados
    resp_post = cliente.post(
        "/matricula",
        data=_datos_matricula(csrf, salon_a.id, con_segundo_apoderado=True),
        follow_redirects=True,
    )
    assert resp_post.status_code == 200
    texto = resp_post.get_data(as_text=True)
    assert "ALU-2026-001" in texto
    assert "Sofía" in texto

    # Filtro por salón en GET
    resp_filtro = cliente.get(f"/matricula?salon_id={salon_a.id}")
    assert resp_filtro.status_code == 200
    assert "ALU-2026-001" in resp_filtro.get_data(as_text=True)

    # Duplicado de DNI devuelve 409 con mensaje amigable
    resp_dup = cliente.post(
        "/matricula",
        data=_datos_matricula(csrf, salon_a.id, codigo="ALU-2026-002", dni="71234567"),
    )
    assert resp_dup.status_code == 409

    # Error de validación de fecha / campos inválidos devuelve 400
    resp_bad = cliente.post(
        "/matricula",
        data=_datos_matricula(
            csrf, salon_a.id, codigo="ALU-2026-003", dni="72222222", fecha_nacimiento="no-es-fecha"
        ),
    )
    assert resp_bad.status_code == 400

    # Cambio de salón exitoso
    resp_cambio = cliente.post(
        "/matricula/1/cambiar-salon",
        data={"csrf_token": csrf, "nuevo_salon_id": str(salon_b.id)},
        follow_redirects=True,
    )
    assert resp_cambio.status_code == 200
    assert "3ro" in resp_cambio.get_data(as_text=True)

    # Cambio de salón con alumno inexistente -> 404 y salón inválido -> 400
    assert (
        cliente.post(
            "/matricula/999/cambiar-salon",
            data={"csrf_token": csrf, "nuevo_salon_id": str(salon_b.id)},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/matricula/1/cambiar-salon",
            data={"csrf_token": csrf, "nuevo_salon_id": "abc"},
        ).status_code
        == 400
    )


# ===========================================================================
# 3. Carnets QR: Emisión, Validación y Anulación (PBI-06)
# ===========================================================================


def test_carnets_emision_validacion_anulacion_y_errores(entorno_web: dict[str, Any]) -> None:
    app = entorno_web["app"]
    salon_a = entorno_web["salon_a"]
    cliente, csrf = _autenticar(app, entorno_web["admin"])

    # Matricular primero al alumno 1
    cliente.post("/matricula", data=_datos_matricula(csrf, salon_a.id))

    # Emitir carnet inicial
    resp_emit = cliente.post(
        "/carnets/emitir",
        data={"csrf_token": csrf, "alumno_id": "1", "anio_lectivo": "2026"},
        follow_redirects=True,
    )
    assert resp_emit.status_code == 200
    html = resp_emit.get_data(as_text=True)
    assert "DSV-2026-" in html

    # Obtener el carnet emitido desde BD para validarlo y anularlo
    with entorno_web["session_factory"]() as session:
        from src.infraestructura.repositorios import RepositorioCarnets

        carnet = RepositorioCarnets(session).obtener_activo_por_alumno(1)
        assert carnet is not None

    # Validar QR activo
    resp_val = cliente.post(
        "/carnets/validar",
        data={"csrf_token": csrf, "codigo_qr": carnet.codigo_qr},
        follow_redirects=True,
    )
    assert resp_val.status_code == 200
    assert carnet.codigo_qr in resp_val.get_data(as_text=True)

    # Validar QR inexistente -> 404
    assert (
        cliente.post(
            "/carnets/validar",
            data={"csrf_token": csrf, "codigo_qr": "QR-INEXISTENTE"},
        ).status_code
        == 404
    )

    # Anular carnet con motivo inválido -> 400
    assert (
        cliente.post(
            f"/carnets/{carnet.id}/anular",
            data={"csrf_token": csrf, "motivo": "MOTIVO_MALO", "alumno_id": "1"},
        ).status_code
        == 400
    )

    # Anular carnet válido -> 200 tras redirect
    resp_anu = cliente.post(
        f"/carnets/{carnet.id}/anular",
        data={
            "csrf_token": csrf,
            "motivo": "EXTRAVIO",
            "detalle": "Extraviado en patio",
            "alumno_id": "1",
        },
        follow_redirects=True,
    )
    assert resp_anu.status_code == 200
    assert "ANULADO" in resp_anu.get_data(as_text=True)

    # Validar carnet anulado -> 400 y re-anular -> 409
    assert (
        cliente.post(
            "/carnets/validar",
            data={"csrf_token": csrf, "codigo_qr": carnet.codigo_qr},
        ).status_code
        == 400
    )
    assert (
        cliente.post(
            f"/carnets/{carnet.id}/anular",
            data={"csrf_token": csrf, "motivo": "DANO", "alumno_id": "1"},
        ).status_code
        == 409
    )

    # Anular carnet inexistente -> 404, emitir para alumno inexistente -> 404 / datos mal -> 400
    assert (
        cliente.post(
            "/carnets/carnet-no-existe/anular",
            data={"csrf_token": csrf, "motivo": "DANO"},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/carnets/emitir",
            data={"csrf_token": csrf, "alumno_id": "999", "anio_lectivo": "2026"},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/carnets/emitir",
            data={"csrf_token": csrf, "alumno_id": "abc", "anio_lectivo": "2026"},
        ).status_code
        == 400
    )


# ===========================================================================
# 4. Estados Académicos (PBI-08)
# ===========================================================================


def test_estados_academicos_transiciones_y_errores(entorno_web: dict[str, Any]) -> None:
    app = entorno_web["app"]
    salon_a = entorno_web["salon_a"]
    cliente, csrf = _autenticar(app, entorno_web["admin"])

    cliente.post("/matricula", data=_datos_matricula(csrf, salon_a.id))
    cliente.post(
        "/carnets/emitir",
        data={"csrf_token": csrf, "alumno_id": "1", "anio_lectivo": "2026"},
    )

    # GET /estados?alumno_id=1
    resp_get = cliente.get("/estados?alumno_id=1")
    assert resp_get.status_code == 200
    assert "Estados académicos" in resp_get.get_data(as_text=True)

    # Suspensión sin fechas -> 400
    assert (
        cliente.post(
            "/estados/1/cambiar",
            data={
                "csrf_token": csrf,
                "nuevo_estado": "SUSPENDIDO",
                "motivo": "Medida disciplinaria",
            },
        ).status_code
        == 400
    )

    # Suspensión válida con fechas
    resp_susp = cliente.post(
        "/estados/1/cambiar",
        data={
            "csrf_token": csrf,
            "nuevo_estado": "SUSPENDIDO",
            "motivo": "Suspensión temporal 3 días",
            "fecha_inicio_suspension": "2026-04-16",
            "fecha_fin_suspension": "2026-04-19",
        },
        follow_redirects=True,
    )
    assert resp_susp.status_code == 200
    assert "SUSPENDIDO" in resp_susp.get_data(as_text=True)

    # Transición a RETIRADO (anula carnet activo automáticamente)
    resp_ret = cliente.post(
        "/estados/1/cambiar",
        data={
            "csrf_token": csrf,
            "nuevo_estado": "RETIRADO",
            "motivo": "Retiro voluntario de familia",
        },
        follow_redirects=True,
    )
    assert resp_ret.status_code == 200
    assert "RETIRADO" in resp_ret.get_data(as_text=True)

    # Transición inválida (RETIRADO -> SUSPENDIDO) -> 409
    assert (
        cliente.post(
            "/estados/1/cambiar",
            data={
                "csrf_token": csrf,
                "nuevo_estado": "SUSPENDIDO",
                "motivo": "No permitido",
                "fecha_inicio_suspension": "2026-04-20",
                "fecha_fin_suspension": "2026-04-22",
            },
        ).status_code
        == 409
    )

    # Estado desconocido / fecha inválida -> 400; alumno inexistente -> 404
    assert (
        cliente.post(
            "/estados/1/cambiar",
            data={"csrf_token": csrf, "nuevo_estado": "INVALIDO", "motivo": "Test"},
        ).status_code
        == 400
    )
    assert (
        cliente.post(
            "/estados/999/cambiar",
            data={"csrf_token": csrf, "nuevo_estado": "RETIRADO", "motivo": "No existe"},
        ).status_code
        == 404
    )


# ===========================================================================
# 5. Pagos y Panel Restringido de Alertas Silenciosas (PBI-07)
# ===========================================================================


def test_pagos_y_alertas_silenciosas_flujo_completo(entorno_web: dict[str, Any]) -> None:
    app = entorno_web["app"]
    salon_a = entorno_web["salon_a"]
    cli_admin, csrf_admin = _autenticar(app, entorno_web["admin"])
    cli_admin.post("/matricula", data=_datos_matricula(csrf_admin, salon_a.id))

    # Sembrar asistencia + alerta silenciosa de pago en BD
    with entorno_web["session_factory"]() as session:
        ast = AsistenciaModel(
            id="ast-alerta-1",
            estudiante_id=1,
            usuario_id=entorno_web["admin"].id,
            fecha_escolar=date(2026, 4, 15),
            hora_efectiva=time(7, 10, 0),
            estado="PUNTUAL",
            minutos_tardanza=0,
            metodo="CARNET",
            rol_usuario="ADMIN",
        )
        alerta = AlertaPagoSilenciosaModel(
            id="alerta-pag-01",
            estudiante_id=1,
            asistencia_id="ast-alerta-1",
            fecha_escolar=date(2026, 4, 15),
            cantidad_obligaciones_vencidas=2,
            monto_vencido_total=Decimal("640.00"),
            revisada=False,
        )
        session.add(ast)
        session.flush()
        session.add(alerta)
        session.commit()

    # Rol personalizado TESORERIA registra 2 obligaciones, paga 1 y exonera 1
    cli_tes, csrf_tes = _autenticar(
        app, entorno_web["tesorero"], [entorno_web["rol_tesoreria"]]
    )
    resp_ob1 = cli_tes.post(
        "/pagos/obligaciones",
        data={
            "csrf_token": csrf_tes,
            "alumno_id": "1",
            "concepto": "Pensión Abril 2026",
            "monto": "320.50",
            "fecha_vencimiento": "2026-04-30",
        },
        follow_redirects=True,
    )
    assert resp_ob1.status_code == 200
    assert "Pensión Abril 2026" in resp_ob1.get_data(as_text=True)

    cli_tes.post(
        "/pagos/obligaciones",
        data={
            "csrf_token": csrf_tes,
            "alumno_id": "1",
            "concepto": "Pensión Mayo 2026",
            "monto": "320.00",
            "fecha_vencimiento": "2026-05-30",
        },
    )

    obligaciones = entorno_web["servicio"].listar_obligaciones(1)
    assert len(obligaciones) == 2
    ob1, ob2 = obligaciones[0], obligaciones[1]

    # Pagar ob1
    resp_pagar = cli_tes.post(
        f"/pagos/obligaciones/{ob1.id}/pagar",
        data={"csrf_token": csrf_tes, "alumno_id": "1"},
        follow_redirects=True,
    )
    assert resp_pagar.status_code == 200
    assert "PAGADO" in resp_pagar.get_data(as_text=True)

    # Re-pagar ob1 ya pagada -> 400
    assert (
        cli_tes.post(
            f"/pagos/obligaciones/{ob1.id}/pagar",
            data={"csrf_token": csrf_tes, "alumno_id": "1"},
        ).status_code
        == 400
    )

    # Exonerar ob2 con motivo
    resp_exo = cli_tes.post(
        f"/pagos/obligaciones/{ob2.id}/exonerar",
        data={"csrf_token": csrf_tes, "alumno_id": "1", "motivo": "Beca excelencia académica"},
        follow_redirects=True,
    )
    assert resp_exo.status_code == 200
    assert "EXONERADO" in resp_exo.get_data(as_text=True)

    # Validación monto inválido -> 400; obligación inexistente -> 404
    assert (
        cli_tes.post(
            "/pagos/obligaciones",
            data={
                "csrf_token": csrf_tes,
                "alumno_id": "1",
                "concepto": "Error",
                "monto": "no-decimal",
                "fecha_vencimiento": "2026-06-30",
            },
        ).status_code
        == 400
    )
    assert (
        cli_tes.post(
            "/pagos/obligaciones/ob-no-existe/pagar",
            data={"csrf_token": csrf_tes},
        ).status_code
        == 404
    )
    assert (
        cli_tes.post(
            "/pagos/obligaciones/ob-no-existe/exonerar",
            data={"csrf_token": csrf_tes, "motivo": "Motivo"},
        ).status_code
        == 404
    )

    # ADMIN_STAFF ve el panel de alertas silenciosas y marca la alerta como revisada
    cli_staff, csrf_staff = _autenticar(app, entorno_web["staff"])
    resp_alertas = cli_staff.get("/pagos/alertas")
    assert resp_alertas.status_code == 200
    assert "640.00" in resp_alertas.get_data(as_text=True)

    resp_rev = cli_staff.post(
        "/pagos/alertas/alerta-pag-01/revisar",
        data={"csrf_token": csrf_staff},
        follow_redirects=True,
    )
    assert resp_rev.status_code == 200
    assert entorno_web["servicio"].listar_alertas_pago(solo_activas=True) == []

    # Alerta inexistente -> 404
    assert (
        cli_staff.post(
            "/pagos/alertas/alerta-no-existe/revisar",
            data={"csrf_token": csrf_staff},
        ).status_code
        == 404
    )


def test_casos_borde_vacantes_filtros_y_servicio_perezoso(
    entorno_web: dict[str, Any],
) -> None:
    app = entorno_web["app"]
    servicio = entorno_web["servicio"]
    admin = entorno_web["admin"]
    salon_a = entorno_web["salon_a"]

    # Salón con capacidad máxima = 1 para validar SalonSinVacantesException (409)
    salon_lleno = servicio.crear_salon(
        admin.id,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        seccion="C",
        capacidad_maxima=1,
    )

    # Remover servicio pre-inyectado para ejercitar instanciación perezosa desde session_factory
    app.extensions.pop("servicio_academico", None)
    cliente, csrf = _autenticar(app, admin)

    # Parámetro de filtro no numérico y GET /estados sin alumno_id
    assert cliente.get("/matricula?salon_id=abc").status_code == 200
    assert cliente.get("/estados").status_code == 200

    # Ocupar la única vacante de salon_lleno y luego intentar segunda matrícula -> 409
    assert (
        cliente.post(
            "/matricula",
            data=_datos_matricula(csrf, salon_lleno.id, codigo="ALU-2026-101", dni="73000001"),
        ).status_code
        == 302
    )
    assert (
        cliente.post(
            "/matricula",
            data=_datos_matricula(csrf, salon_lleno.id, codigo="ALU-2026-102", dni="73000002"),
        ).status_code
        == 409
    )

    # Matricular otro alumno en salon_a e intentar moverlo a salon_lleno -> 409
    assert (
        cliente.post(
            "/matricula",
            data=_datos_matricula(csrf, salon_a.id, codigo="ALU-2026-103", dni="73000003"),
        ).status_code
        == 302
    )
    assert (
        cliente.post(
            "/matricula/2/cambiar-salon",
            data={"csrf_token": csrf, "nuevo_salon_id": str(salon_lleno.id)},
        ).status_code
        == 409
    )

