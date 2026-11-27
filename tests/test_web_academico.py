"""Pruebas de integración Flask para Ola 4 - Miembro 4 (bp_academico).

Cubre:
- Configuración de Malla Curricular: Salones y Cursos (PBI-09)
- Asignación Docente segura y aislamiento de ámbito (PBI-11)
- Libro de Calificaciones de 3 niveles: Rubros (100%), Actividades y Notas [0, 20] (PBI-10)
- Bloqueo tras fecha_limite_notas, CSRF (400), sesión (401) y RBAC base/personalizado (403)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session, sessionmaker

from src.aplicacion.servicios_academico import ServicioAcademico
from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.justificaciones import PeriodoAcademico, TipoPeriodo
from src.dominio.matricula import Apoderado
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
from src.infraestructura.repositorios import (
    RepositorioPeriodos,
    RepositorioRoles,
    RepositorioUsuarios,
)
from src.presentacion.app import crear_app
from src.presentacion.bp_academico import registrar_blueprints_academico
from src.presentacion.seguridad import AlmacenSesiones

AHORA_EN_PLAZO = datetime(2026, 5, 10, 10, 0, 0, tzinfo=ZONA_HORARIA_LIMA)
AHORA_VENCIDA = datetime(2026, 6, 1, 10, 0, 0, tzinfo=ZONA_HORARIA_LIMA)


@pytest.fixture
def entorno_academico() -> dict[str, Any]:
    """Crea app Flask real con BD SQLite en memoria y reloj controlable."""
    engine = crear_motor("sqlite:///:memory:")
    inicializar_bd(engine)
    session_factory: sessionmaker[Session] = crear_session_factory(engine)
    reloj_estado = {"ahora": AHORA_EN_PLAZO}

    def reloj() -> datetime:
        return reloj_estado["ahora"]

    with session_factory() as session:
        repo_roles = RepositorioRoles(session)
        rol_docente = repo_roles.guardar(
            Rol(
                codigo="DOCENTE",
                nombre="Docente",
                descripcion="Docente de aula con permiso de calificación",
                permisos=frozenset(
                    {
                        PermisoOperacion.REGISTRAR_CALIFICACIONES,
                        PermisoOperacion.CONSULTAR_CALIFICACIONES,
                    }
                ),
            )
        )
        rol_tesoreria = repo_roles.guardar(
            Rol(
                codigo="TESORERIA",
                nombre="Tesorería",
                descripcion="Gestión de pagos",
                permisos=frozenset({PermisoOperacion.GESTIONAR_PAGOS}),
            )
        )

        repo_usr = RepositorioUsuarios(session)
        pwd_hash, salt = hashear_password("ClaveSegura2026!")

        admin = repo_usr.guardar(
            Usuario(
                id=0,
                username="admin_acad",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Admin Académico",
                rol=RolUsuario.ADMIN,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        coord = repo_usr.guardar(
            Usuario(
                id=0,
                username="coord_acad",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Coordinador Académico",
                rol=RolUsuario.COORDINADOR,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        docente1 = repo_usr.guardar(
            Usuario(
                id=0,
                username="docente_uno",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Docente Uno",
                rol=rol_docente.codigo,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        docente2 = repo_usr.guardar(
            Usuario(
                id=0,
                username="docente_dos",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Docente Dos",
                rol=rol_docente.codigo,
                estado=EstadoUsuario.ACTIVO,
            )
        )
        tesorero = repo_usr.guardar(
            Usuario(
                id=0,
                username="tesorero_acad",
                password_hash=pwd_hash,
                salt=salt,
                nombre_completo="Tesorero",
                rol=rol_tesoreria.codigo,
                estado=EstadoUsuario.ACTIVO,
            )
        )

        periodo = RepositorioPeriodos(session).guardar(
            PeriodoAcademico(
                id=0,
                nombre="Bimestre I - 2026",
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2026, 5, 15),
                cerrado=False,
                anio_lectivo=2026,
                tipo_periodo=TipoPeriodo.BIMESTRE,
                orden=1,
                fecha_limite_notas=date(2026, 5, 22),
            )
        )
        session.commit()

    servicio = ServicioAcademico(session_factory, reloj=reloj)
    app = crear_app(
        {
            "SECRET_KEY": "clave-pruebas-academico-2026",
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "RELOJ": reloj,
        }
    )
    app.extensions["session_factory"] = session_factory
    app.extensions["servicio_academico"] = servicio
    registrar_blueprints_academico(app)
    registrar_blueprints_academico(app)  # Idempotente

    yield {
        "app": app,
        "session_factory": session_factory,
        "servicio": servicio,
        "reloj_estado": reloj_estado,
        "admin": admin,
        "coord": coord,
        "docente1": docente1,
        "docente2": docente2,
        "tesorero": tesorero,
        "rol_docente": rol_docente,
        "rol_tesoreria": rol_tesoreria,
        "periodo": periodo,
    }
    engine.dispose()


def _autenticar(
    app: Flask,
    usuario: Usuario,
    ahora: datetime = AHORA_EN_PLAZO,
    roles_extra: list[Rol] | None = None,
) -> tuple[FlaskClient, str]:
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        usuario.username,
        "ClaveSegura2026!",
        [usuario],
        fecha_hora=ahora,
        roles=roles_extra,
    )
    almacen.guardar(sesion, usuario)
    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token
        sess["_csrf_token"] = f"csrf-{usuario.username}-2026"
    return cliente, f"csrf-{usuario.username}-2026"


# ===========================================================================
# 1. Seguridad: 401, CSRF 400 y RBAC 403 (base y personalizados)
# ===========================================================================


def test_seguridad_401_csrf_400_y_rbac_403(entorno_academico: dict[str, Any]) -> None:
    app = entorno_academico["app"]

    # Sin sesión -> 401
    anon = app.test_client()
    for ruta in ("/malla", "/docentes", "/calificaciones"):
        assert anon.get(ruta).status_code == 401

    # Sin CSRF -> 400
    cli_admin, _ = _autenticar(app, entorno_academico["admin"])
    assert cli_admin.post("/malla/salones", data={"grado": "3ro"}).status_code == 400

    # COORDINADOR: puede GET /calificaciones (CONSULTAR_CALIFICACIONES),
    # pero 403 en /malla, /docentes y POST /calificaciones/*
    cli_coord, csrf_coord = _autenticar(app, entorno_academico["coord"])
    assert cli_coord.get("/calificaciones").status_code == 200
    assert cli_coord.get("/malla").status_code == 403
    assert cli_coord.get("/docentes").status_code == 403
    assert (
        cli_coord.post(
            "/calificaciones/rubros", data={"csrf_token": csrf_coord}
        ).status_code
        == 403
    )

    # DOCENTE: puede /calificaciones, pero 403 en /malla y /docentes
    cli_doc, _ = _autenticar(
        app, entorno_academico["docente1"], roles_extra=[entorno_academico["rol_docente"]]
    )
    assert cli_doc.get("/calificaciones").status_code == 200
    assert cli_doc.get("/malla").status_code == 403
    assert cli_doc.get("/docentes").status_code == 403

    # TESORERIA: 403 en /malla, /docentes y /calificaciones
    cli_tes, _ = _autenticar(
        app, entorno_academico["tesorero"], roles_extra=[entorno_academico["rol_tesoreria"]]
    )
    for ruta in ("/malla", "/docentes", "/calificaciones"):
        assert cli_tes.get(ruta).status_code == 403


# ===========================================================================
# 2. Malla Curricular: Salones y Cursos (PBI-09)
# ===========================================================================


def test_malla_salones_y_cursos_crud_y_errores(entorno_academico: dict[str, Any]) -> None:
    app = entorno_academico["app"]
    cliente, csrf = _autenticar(app, entorno_academico["admin"])

    assert cliente.get("/malla").status_code == 200
    assert cliente.get("/malla?anio_lectivo=2026").status_code == 200
    assert cliente.get("/malla?anio_lectivo=abc").status_code == 200

    # Crear salón válido
    resp_sal = cliente.post(
        "/malla/salones",
        data={
            "csrf_token": csrf,
            "anio_lectivo": "2026",
            "nivel": "Secundaria",
            "grado": "3ro",
            "seccion": "A",
            "capacidad_maxima": "28",
        },
        follow_redirects=True,
    )
    assert resp_sal.status_code == 200
    assert "Secundaria" in resp_sal.get_data(as_text=True)

    # Salón duplicado -> 409; datos inválidos -> 400
    assert (
        cliente.post(
            "/malla/salones",
            data={
                "csrf_token": csrf,
                "anio_lectivo": "2026",
                "nivel": "Secundaria",
                "grado": "3ro",
                "seccion": "A",
                "capacidad_maxima": "28",
            },
        ).status_code
        == 409
    )
    assert (
        cliente.post(
            "/malla/salones",
            data={
                "csrf_token": csrf,
                "anio_lectivo": "abc",
                "nivel": "Secundaria",
                "grado": "3ro",
                "seccion": "B",
                "capacidad_maxima": "25",
            },
        ).status_code
        == 400
    )

    # Actualizar capacidad + errores (404 y 400)
    assert (
        cliente.post(
            "/malla/salones/1/capacidad",
            data={"csrf_token": csrf, "nueva_capacidad": "35"},
            follow_redirects=True,
        ).status_code
        == 200
    )
    assert (
        cliente.post(
            "/malla/salones/999/capacidad",
            data={"csrf_token": csrf, "nueva_capacidad": "35"},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/malla/salones/1/capacidad",
            data={"csrf_token": csrf, "nueva_capacidad": "no-num"},
        ).status_code
        == 400
    )

    # Crear segundo salón, desactivarlo y eliminarlo
    cliente.post(
        "/malla/salones",
        data={
            "csrf_token": csrf,
            "anio_lectivo": "2026",
            "nivel": "Secundaria",
            "grado": "3ro",
            "seccion": "B",
            "capacidad_maxima": "25",
        },
    )
    assert (
        cliente.post(
            "/malla/salones/2/desactivar",
            data={"csrf_token": csrf},
            follow_redirects=True,
        ).status_code
        == 200
    )
    assert (
        cliente.post(
            "/malla/salones/999/desactivar",
            data={"csrf_token": csrf},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/malla/salones/2/eliminar",
            data={"csrf_token": csrf},
            follow_redirects=True,
        ).status_code
        == 200
    )
    assert (
        cliente.post(
            "/malla/salones/999/eliminar",
            data={"csrf_token": csrf},
        ).status_code
        == 404
    )

    # Crear curso válido, duplicado (409), inválido (400), desactivar y eliminar
    resp_cur = cliente.post(
        "/malla/cursos",
        data={
            "csrf_token": csrf,
            "anio_lectivo": "2026",
            "nivel": "Secundaria",
            "grado": "3ro",
            "codigo": "MAT-3S",
            "nombre": "Matemática",
            "area_curricular": "Matemática",
            "horas_semanales": "6",
        },
        follow_redirects=True,
    )
    assert resp_cur.status_code == 200
    assert "MAT-3S" in resp_cur.get_data(as_text=True)

    assert (
        cliente.post(
            "/malla/cursos",
            data={
                "csrf_token": csrf,
                "anio_lectivo": "2026",
                "nivel": "Secundaria",
                "grado": "3ro",
                "codigo": "MAT-3S",
                "nombre": "Matemática Dup",
                "area_curricular": "Matemática",
                "horas_semanales": "6",
            },
        ).status_code
        == 409
    )
    assert (
        cliente.post(
            "/malla/cursos",
            data={
                "csrf_token": csrf,
                "anio_lectivo": "2026",
                "nivel": "Secundaria",
                "grado": "3ro",
                "codigo": "COM-3S",
                "nombre": "Comunicación",
                "area_curricular": "Comunicación",
                "horas_semanales": "abc",
            },
        ).status_code
        == 400
    )

    cliente.post(
        "/malla/cursos",
        data={
            "csrf_token": csrf,
            "anio_lectivo": "2026",
            "nivel": "Secundaria",
            "grado": "3ro",
            "codigo": "HIS-3S",
            "nombre": "Historia",
            "area_curricular": "Ciencias Sociales",
            "horas_semanales": "4",
        },
    )
    assert (
        cliente.post(
            "/malla/cursos/2/desactivar",
            data={"csrf_token": csrf},
            follow_redirects=True,
        ).status_code
        == 200
    )
    assert (
        cliente.post(
            "/malla/cursos/999/desactivar",
            data={"csrf_token": csrf},
        ).status_code
        == 404
    )
    assert (
        cliente.post(
            "/malla/cursos/2/eliminar",
            data={"csrf_token": csrf},
            follow_redirects=True,
        ).status_code
        == 200
    )
    assert (
        cliente.post(
            "/malla/cursos/999/eliminar",
            data={"csrf_token": csrf},
        ).status_code
        == 404
    )


# ===========================================================================
# 3. Asignación Docente + Libro de Calificaciones de 3 niveles (PBI-10 / 11)
# ===========================================================================


def test_docentes_y_calificaciones_3_niveles_y_bloqueo_fecha_limite(
    entorno_academico: dict[str, Any],
) -> None:
    app = entorno_academico["app"]
    servicio: ServicioAcademico = entorno_academico["servicio"]
    admin = entorno_academico["admin"]
    docente1 = entorno_academico["docente1"]
    docente2 = entorno_academico["docente2"]
    tesorero = entorno_academico["tesorero"]
    periodo = entorno_academico["periodo"]

    # Preparar salón, curso y alumno matriculado
    salon = servicio.crear_salon(
        admin.id,
        anio_lectivo=2026,
        nivel="Secundaria",
        grado="3ro",
        seccion="A",
        capacidad_maxima=30,
    )
    curso = servicio.crear_curso(
        admin.id,
        anio_lectivo=2026,
        nivel="Secundaria",
        grado="3ro",
        codigo="MAT-3S",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=6,
    )
    ficha = servicio.matricular(
        admin.id,
        codigo_estudiante="ALU-2026-901",
        dni="76543210",
        nombres="Mateo",
        apellidos="Torres Díaz",
        fecha_nacimiento=date(2012, 4, 12),
        salon_id=salon.id,
        apoderados=[
            Apoderado(
                id=0,
                nombres="Luis",
                apellidos="Torres",
                documento="44445555",
                parentesco="PADRE",
                telefono_whatsapp="987111222",
                es_principal=True,
            )
        ],
    )

    cli_admin, csrf_admin = _autenticar(app, admin)
    assert cli_admin.get("/docentes").status_code == 200

    # Asignar docente1 al curso y salón
    resp_asig = cli_admin.post(
        "/docentes/asignar",
        data={
            "csrf_token": csrf_admin,
            "docente_id": str(docente1.id),
            "curso_id": str(curso.id),
            "salon_id": str(salon.id),
        },
        follow_redirects=True,
    )
    assert resp_asig.status_code == 200
    assert "Docente Uno" in resp_asig.get_data(as_text=True)

    # Duplicado -> 409; usuario sin permiso docente (tesorero) -> 400; curso inexistente -> 404
    assert (
        cli_admin.post(
            "/docentes/asignar",
            data={
                "csrf_token": csrf_admin,
                "docente_id": str(docente1.id),
                "curso_id": str(curso.id),
                "salon_id": str(salon.id),
            },
        ).status_code
        == 409
    )
    assert (
        cli_admin.post(
            "/docentes/asignar",
            data={
                "csrf_token": csrf_admin,
                "docente_id": str(tesorero.id),
                "curso_id": str(curso.id),
                "salon_id": str(salon.id),
            },
        ).status_code
        == 400
    )
    assert (
        cli_admin.post(
            "/docentes/asignar",
            data={
                "csrf_token": csrf_admin,
                "docente_id": str(docente1.id),
                "curso_id": "999",
                "salon_id": str(salon.id),
            },
        ).status_code
        == 404
    )

    # Salón/curso en uso no pueden eliminarse -> 409
    assert (
        cli_admin.post(
            f"/malla/salones/{salon.id}/eliminar", data={"csrf_token": csrf_admin}
        ).status_code
        == 409
    )
    assert (
        cli_admin.post(
            f"/malla/cursos/{curso.id}/eliminar", data={"csrf_token": csrf_admin}
        ).status_code
        == 409
    )

    asignacion = servicio.listar_asignaciones_docente(docente1.id)[0]

    # --- Libro de Calificaciones con docente1 (asignado) ---
    cli_doc1, csrf_doc1 = _autenticar(
        app, docente1, roles_extra=[entorno_academico["rol_docente"]]
    )

    # Rubros que NO suman 100% -> 400
    assert (
        cli_doc1.post(
            "/calificaciones/rubros",
            data={
                "csrf_token": csrf_doc1,
                "asignacion_id": asignacion.id,
                "periodo_id": str(periodo.id),
                "rubro_nombre": ["Tareas", "Examen"],
                "rubro_peso": ["30", "50"],
            },
        ).status_code
        == 400
    )

    # Rubros válidos sumando 100% (40% + 60%)
    resp_rub = cli_doc1.post(
        "/calificaciones/rubros",
        data={
            "csrf_token": csrf_doc1,
            "asignacion_id": asignacion.id,
            "periodo_id": str(periodo.id),
            "rubro_nombre": ["Prácticas", "Examen Final"],
            "rubro_peso": ["40", "60"],
        },
        follow_redirects=True,
    )
    assert resp_rub.status_code == 200
    assert "Prácticas" in resp_rub.get_data(as_text=True)

    # Docente2 (NO asignado a este grupo) intenta configurar rubros -> 403
    cli_doc2, csrf_doc2 = _autenticar(
        app, docente2, roles_extra=[entorno_academico["rol_docente"]]
    )
    assert (
        cli_doc2.post(
            "/calificaciones/rubros",
            data={
                "csrf_token": csrf_doc2,
                "asignacion_id": asignacion.id,
                "periodo_id": str(periodo.id),
                "rubro_nombre": ["Unico"],
                "rubro_peso": ["100"],
            },
        ).status_code
        == 403
    )

    # Obtener rubro creado y crear actividad
    with entorno_academico["session_factory"]() as session:
        from src.infraestructura.repositorios import RepositorioCalificaciones

        rubros = RepositorioCalificaciones(session).listar_rubros_asignacion(
            asignacion.id, periodo.id
        )
        assert len(rubros) == 2
        rubro_practicas = rubros[0]

    resp_act = cli_doc1.post(
        "/calificaciones/actividades",
        data={
            "csrf_token": csrf_doc1,
            "rubro_id": rubro_practicas.id,
            "titulo": "Práctica Calificada 1",
            "fecha_actividad": "2026-04-20",
            "asignacion_id": asignacion.id,
            "periodo_id": str(periodo.id),
        },
        follow_redirects=True,
    )
    assert resp_act.status_code == 200
    assert "Práctica Calificada 1" in resp_act.get_data(as_text=True)

    # Actividad con rubro inexistente -> 404 y fecha inválida -> 400
    assert (
        cli_doc1.post(
            "/calificaciones/actividades",
            data={
                "csrf_token": csrf_doc1,
                "rubro_id": "rub-no-existe",
                "titulo": "Test",
                "fecha_actividad": "2026-04-20",
            },
        ).status_code
        == 404
    )
    assert (
        cli_doc1.post(
            "/calificaciones/actividades",
            data={
                "csrf_token": csrf_doc1,
                "rubro_id": rubro_practicas.id,
                "titulo": "Test",
                "fecha_actividad": "fecha-mala",
            },
        ).status_code
        == 400
    )

    with entorno_academico["session_factory"]() as session:
        from src.infraestructura.repositorios import RepositorioCalificaciones

        actividad = RepositorioCalificaciones(session).listar_actividades_rubro(
            rubro_practicas.id
        )[0]

    # Registrar nota válida [0, 20] y luego modificarla con motivo
    resp_nota = cli_doc1.post(
        "/calificaciones/notas",
        data={
            "csrf_token": csrf_doc1,
            "actividad_id": actividad.id,
            "alumno_id": str(ficha.alumno_id),
            "nota": "17.50",
            "observacion": "Buen desempeño",
            "asignacion_id": asignacion.id,
            "periodo_id": str(periodo.id),
        },
        follow_redirects=True,
    )
    assert resp_nota.status_code == 200
    assert "17.50" in resp_nota.get_data(as_text=True)

    # Nota fuera de rango (> 20) -> 400; texto no Decimal -> 400; actividad inexistente -> 404
    assert (
        cli_doc1.post(
            "/calificaciones/notas",
            data={
                "csrf_token": csrf_doc1,
                "actividad_id": actividad.id,
                "alumno_id": str(ficha.alumno_id),
                "nota": "25",
                "motivo_modificacion": "Error",
            },
        ).status_code
        == 400
    )
    assert (
        cli_doc1.post(
            "/calificaciones/notas",
            data={
                "csrf_token": csrf_doc1,
                "actividad_id": actividad.id,
                "alumno_id": str(ficha.alumno_id),
                "nota": "abc",
            },
        ).status_code
        == 400
    )
    assert (
        cli_doc1.post(
            "/calificaciones/notas",
            data={
                "csrf_token": csrf_doc1,
                "actividad_id": "act-no-existe",
                "alumno_id": str(ficha.alumno_id),
                "nota": "15",
            },
        ).status_code
        == 404
    )

    # Docente2 (ajeno al grupo) intenta calificar -> 403
    assert (
        cli_doc2.post(
            "/calificaciones/notas",
            data={
                "csrf_token": csrf_doc2,
                "actividad_id": actividad.id,
                "alumno_id": str(ficha.alumno_id),
                "nota": "10",
                "motivo_modificacion": "Intento ajeno",
            },
        ).status_code
        == 403
    )

    # Asignación con calificaciones no puede eliminarse -> 409; sí puede revocarse -> 200
    assert (
        cli_admin.post(
            f"/docentes/{asignacion.id}/eliminar", data={"csrf_token": csrf_admin}
        ).status_code
        == 409
    )
    assert (
        cli_admin.post(
            "/docentes/asig-no-existe/eliminar", data={"csrf_token": csrf_admin}
        ).status_code
        == 404
    )
    assert (
        cli_admin.post(
            "/docentes/asig-no-existe/revocar", data={"csrf_token": csrf_admin}
        ).status_code
        == 404
    )

    # --- Bloqueo tras fecha_limite_notas (2026-06-01 > 2026-05-22) -> 409 ---
    entorno_academico["reloj_estado"]["ahora"] = AHORA_VENCIDA
    cli_doc1_tarde, csrf_doc1_tarde = _autenticar(
        app,
        docente1,
        ahora=AHORA_VENCIDA,
        roles_extra=[entorno_academico["rol_docente"]],
    )
    resp_bloqueo_get = cli_doc1_tarde.get(
        f"/calificaciones?asignacion_id={asignacion.id}&periodo_id={periodo.id}"
    )
    assert resp_bloqueo_get.status_code == 200
    assert "bloqueado" in resp_bloqueo_get.get_data(as_text=True).lower()

    assert (
        cli_doc1_tarde.post(
            "/calificaciones/notas",
            data={
                "csrf_token": csrf_doc1_tarde,
                "actividad_id": actividad.id,
                "alumno_id": str(ficha.alumno_id),
                "nota": "18",
                "motivo_modificacion": "Fuera de plazo",
            },
        ).status_code
        == 409
    )
    assert (
        cli_doc1_tarde.post(
            "/calificaciones/actividades",
            data={
                "csrf_token": csrf_doc1_tarde,
                "rubro_id": rubro_practicas.id,
                "titulo": "Actividad tardía",
                "fecha_actividad": "2026-05-10",
            },
        ).status_code
        == 409
    )

    # Revocar asignación con admin y probar eliminar una asignación limpia
    cli_admin_tarde, csrf_admin_tarde = _autenticar(app, admin, ahora=AHORA_VENCIDA)
    assert (
        cli_admin_tarde.post(
            f"/docentes/{asignacion.id}/revocar",
            data={"csrf_token": csrf_admin_tarde, "motivo": "Cambio de docente"},
            follow_redirects=True,
        ).status_code
        == 200
    )

    # Crear asignación limpia para docente2 y eliminarla físicamente
    asig_limpia = servicio.asignar_docente(admin.id, docente2.id, curso.id, salon.id)
    assert (
        cli_admin_tarde.post(
            f"/docentes/{asig_limpia.id}/eliminar",
            data={"csrf_token": csrf_admin_tarde},
            follow_redirects=True,
        ).status_code
        == 200
    )

    # Instanciación perezosa de servicio cuando servicio_academico no está pre-inyectado
    app.extensions.pop("servicio_academico", None)
    assert cli_admin_tarde.get("/malla").status_code == 200
