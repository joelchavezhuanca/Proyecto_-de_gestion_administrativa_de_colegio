"""Pruebas de integración web del módulo de seguridad (Ola 4 - Miembro 1).

Cubre:
- Login/Logout con sesión validada en servidor y CSRF.
- CRUD de usuarios (crear, editar, activar/desactivar, restablecer contraseña).
- CRUD de roles personalizados con los 28 permisos.
- Visor de auditoría PBI-16 y verificación de integridad SHA-256.
- Denegación 403 con roles base y rutas protegidas.
"""

import re
from collections.abc import Iterator

import pytest
from flask import Flask, g
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.exceptions import HTTPException

from src.aplicacion.servicios_seguridad import ServicioSeguridad
from src.dominio.auditoria import ResultadoVerificacionIntegridad
from src.dominio.usuarios import (
    PermisoOperacion,
    SesionInvalidaException,
    hashear_password,
)
from src.infraestructura.base_datos import (
    crear_motor,
    crear_session_factory,
    inicializar_bd,
)
from src.infraestructura.modelos import RolModel, SesionUsuarioModel, UsuarioModel
from src.presentacion.app import crear_app
from src.presentacion.bp_seguridad import (
    _almacen_sesiones,
    _usuario_actual,
    obtener_servicio_seguridad,
    registrar_blueprints_seguridad,
)

PASSWORD = "ClaveSegura123"
PATRON_CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')


# ---------------------------------------------------------------------------
# Infraestructura de pruebas
# ---------------------------------------------------------------------------


@pytest.fixture
def fabrica_sesiones() -> Iterator[sessionmaker[Session]]:
    engine = crear_motor("sqlite:///:memory:")
    inicializar_bd(engine)
    fabrica = crear_session_factory(engine)
    try:
        yield fabrica
    finally:
        engine.dispose()


def _crear_usuario_bd(
    fabrica: sessionmaker[Session],
    *,
    username: str,
    rol: str,
    activo: bool = True,
    password: str = PASSWORD,
) -> int:
    with fabrica() as session:
        modelo_rol = session.scalars(select(RolModel).filter_by(codigo=rol)).one()
        hash_pwd, salt = hashear_password(password)
        usuario = UsuarioModel(
            username=username,
            nombre_completo=f"Usuario {username}",
            password_hash=hash_pwd,
            salt=salt,
            rol=rol,
            rol_id=modelo_rol.id,
            estado="ACTIVO" if activo else "INACTIVO",
            activo=activo,
        )
        session.add(usuario)
        session.commit()
        return usuario.id


@pytest.fixture
def app(fabrica_sesiones: sessionmaker[Session]) -> Flask:
    aplicacion = crear_app(
        {
            "SECRET_KEY": "clave-de-pruebas-web-seguridad",
            "WTF_CSRF_ENABLED": False,
            "SESSION_FACTORY": fabrica_sesiones,
        }
    )
    registrar_blueprints_seguridad(aplicacion)
    _crear_usuario_bd(fabrica_sesiones, username="admin", rol="ADMIN")
    _crear_usuario_bd(fabrica_sesiones, username="coordinador", rol="COORDINADOR")
    _crear_usuario_bd(fabrica_sesiones, username="inactivo", rol="ADMIN", activo=False)
    return aplicacion


@pytest.fixture
def cliente(app: Flask):
    return app.test_client()


def _login(cliente, username: str = "admin", password: str = PASSWORD):
    return cliente.post("/login", data={"username": username, "password": password})


def _servicio(app: Flask) -> ServicioSeguridad:
    servicio = app.extensions.get("servicio_seguridad")
    if servicio is None:
        servicio = ServicioSeguridad(app.config["SESSION_FACTORY"])
        app.extensions["servicio_seguridad"] = servicio
    return servicio


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


def test_login_exitoso_crea_sesion_en_servidor(app: Flask, cliente) -> None:
    respuesta = _login(cliente)

    assert respuesta.status_code == 303
    with cliente.session_transaction() as sesion:
        token = sesion["token"]
    assert token
    almacen = app.extensions["almacen_sesiones"]
    assert almacen.obtener_sesion(token) is not None


def test_login_redirige_al_inicio_y_este_al_primer_modulo(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/")

    assert respuesta.status_code == 303
    assert any(
        ruta in respuesta.headers["Location"] for ruta in ("/aforo", "/asistencia", "/usuarios")
    )


def test_login_con_credenciales_invalidas_devuelve_401(cliente) -> None:
    respuesta = _login(cliente, password="incorrecta")

    assert respuesta.status_code == 401
    assert "Credenciales incorrectas" in respuesta.get_data(as_text=True)


def test_login_de_usuario_inactivo_devuelve_401(cliente) -> None:
    respuesta = _login(cliente, username="inactivo")

    assert respuesta.status_code == 401


def test_login_sin_datos_devuelve_400(cliente) -> None:
    respuesta = cliente.post("/login", data={"username": "", "password": ""})

    assert respuesta.status_code == 400


def test_login_con_sesion_activa_redirige(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/login")

    assert respuesta.status_code == 303


def test_logout_cierra_la_sesion(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/logout")

    assert respuesta.status_code == 303
    with cliente.session_transaction() as sesion:
        assert "token" not in sesion


def test_ruta_protegida_sin_sesion_devuelve_401(cliente) -> None:
    respuesta = cliente.get("/usuarios")

    assert respuesta.status_code == 401


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


def test_coordinador_no_puede_acceder_a_usuarios(cliente) -> None:
    _login(cliente, username="coordinador")

    respuesta = cliente.get("/usuarios")

    assert respuesta.status_code == 403


def test_admin_lista_usuarios(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/usuarios")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "admin" in html
    assert "coordinador" in html


def test_crear_usuario(app: Flask, cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/usuarios/nuevo",
        data={
            "username": "nuevo_docente",
            "password": PASSWORD,
            "nombre_completo": "Nuevo Docente",
            "rol": "ADMIN_STAFF",
        },
    )

    assert respuesta.status_code == 303
    usernames = [u.username for u in _servicio(app).listar_usuarios()]
    assert "nuevo_docente" in usernames


def test_crear_usuario_duplicado_devuelve_409(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/usuarios/nuevo",
        data={
            "username": "admin",
            "password": PASSWORD,
            "nombre_completo": "Duplicado",
            "rol": "ADMIN",
        },
    )

    assert respuesta.status_code == 409
    assert "ya está registrado" in respuesta.get_data(as_text=True)


def test_crear_usuario_con_password_corta_devuelve_400(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/usuarios/nuevo",
        data={
            "username": "corto",
            "password": "123",
            "nombre_completo": "Password Corta",
            "rol": "ADMIN_STAFF",
        },
    )

    assert respuesta.status_code == 400


def test_editar_usuario(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"], username="editable", rol="ADMIN_STAFF"
    )
    _login(cliente)

    respuesta = cliente.post(
        f"/usuarios/{usuario_id}/editar",
        data={"nombre_completo": "Nombre Actualizado", "rol": "ADMIN_STAFF"},
    )

    assert respuesta.status_code == 303
    assert _servicio(app).obtener_usuario(usuario_id).nombre_completo == ("Nombre Actualizado")


def test_editar_usuario_inexistente_devuelve_404(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/usuarios/9999/editar")

    assert respuesta.status_code == 404


def test_desactivar_usuario_cambia_estado(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"], username="temporal", rol="ADMIN_STAFF"
    )
    _login(cliente)

    respuesta = cliente.post(f"/usuarios/{usuario_id}/estado", data={"accion": "desactivar"})

    assert respuesta.status_code == 303
    assert _servicio(app).obtener_usuario(usuario_id).estado.value == "INACTIVO"


def test_no_se_puede_desactivar_al_ultimo_admin(app: Flask, cliente) -> None:
    _login(cliente)
    admin_id = _servicio(app).listar_usuarios(username="admin")[0].id

    respuesta = cliente.post(f"/usuarios/{admin_id}/estado", data={"accion": "desactivar"})

    assert respuesta.status_code == 409


def test_restablecer_password(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"], username="reset", rol="ADMIN_STAFF"
    )
    _login(cliente)

    respuesta = cliente.post(
        f"/usuarios/{usuario_id}/password",
        data={"password": "NuevaClave456", "confirmar": "NuevaClave456"},
    )

    assert respuesta.status_code == 303
    with app.config["SESSION_FACTORY"]() as sesion:
        modelo = sesion.get(UsuarioModel, usuario_id)
        assert modelo is not None
        from src.dominio.usuarios import verificar_password

        assert verificar_password("NuevaClave456", modelo.password_hash, modelo.salt)


def test_restablecer_password_con_confirmacion_distinta_devuelve_400(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/usuarios/1/password",
        data={"password": "NuevaClave456", "confirmar": "OtraClave789"},
    )

    assert respuesta.status_code == 400


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def test_listar_roles_muestra_los_28_permisos(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/roles/nuevo")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert html.count('name="permisos"') == len(PermisoOperacion)


def test_crear_rol_con_permisos(app: Flask, cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "TESORERIA",
            "nombre": "Tesorería",
            "descripcion": "Gestiona pagos y alertas.",
            "permisos": ["VER_ALERTA_PAGOS", "GESTIONAR_PAGOS"],
        },
    )

    assert respuesta.status_code == 303
    roles = {rol.codigo: rol for rol in _servicio(app).listar_roles()}
    assert "TESORERIA" in roles
    assert roles["TESORERIA"].permisos == frozenset(
        {PermisoOperacion.VER_ALERTA_PAGOS, PermisoOperacion.GESTIONAR_PAGOS}
    )


def test_crear_rol_duplicado_devuelve_409(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "ADMIN",
            "nombre": "Duplicado",
            "descripcion": "No debe crearse.",
            "permisos": ["VER_ALERTA_PAGOS"],
        },
    )

    assert respuesta.status_code == 409


def test_editar_rol_actualiza_permisos(app: Flask, cliente) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "BIBLIOTECA",
            "nombre": "Biblioteca",
            "descripcion": "Solo consulta.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )

    respuesta = cliente.post(
        "/roles/BIBLIOTECA/editar",
        data={
            "nombre": "Biblioteca",
            "descripcion": "Consulta ampliada.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO", "EXPORTAR_ASISTENCIAS"],
        },
    )

    assert respuesta.status_code == 303
    roles = {rol.codigo: rol for rol in _servicio(app).listar_roles()}
    assert roles["BIBLIOTECA"].permisos == frozenset(
        {PermisoOperacion.CONSULTAR_FICHA_ALUMNO, PermisoOperacion.EXPORTAR_ASISTENCIAS}
    )


def test_desactivar_rol_personalizado(app: Flask, cliente) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "TEMPORAL",
            "nombre": "Temporal",
            "descripcion": "Rol temporal.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )

    respuesta = cliente.post("/roles/TEMPORAL/estado", data={"accion": "desactivar"})

    assert respuesta.status_code == 303
    roles = {rol.codigo: rol for rol in _servicio(app).listar_roles()}
    assert roles["TEMPORAL"].activo is False


def test_eliminar_rol_personalizado(app: Flask, cliente) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "BORRABLE",
            "nombre": "Borrable",
            "descripcion": "Rol eliminable.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )

    respuesta = cliente.post("/roles/BORRABLE/eliminar")

    assert respuesta.status_code == 303
    assert "BORRABLE" not in {rol.codigo for rol in _servicio(app).listar_roles()}


def test_eliminar_rol_de_sistema_devuelve_409(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/roles/ADMIN/eliminar")

    assert respuesta.status_code == 409


def test_desactivar_rol_revoca_sesiones_en_bd(
    app: Flask, cliente, fabrica_sesiones: sessionmaker[Session]
) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "SESIONABLE",
            "nombre": "Sesionable",
            "descripcion": "Rol con usuarios.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )
    _crear_usuario_bd(fabrica_sesiones, username="con_rol", rol="SESIONABLE")
    sesion = _servicio(app).iniciar_sesion("con_rol", PASSWORD)

    respuesta = cliente.post("/roles/SESIONABLE/estado", data={"accion": "desactivar"})

    assert respuesta.status_code == 303
    with fabrica_sesiones() as sesion_bd:
        modelo = sesion_bd.get(SesionUsuarioModel, sesion.token)
        assert modelo is not None
        assert modelo.activa is False


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------


def test_coordinador_no_puede_ver_auditoria(cliente) -> None:
    _login(cliente, username="coordinador")

    respuesta = cliente.get("/auditoria")

    assert respuesta.status_code == 403


def test_admin_ve_auditoria_con_eventos(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/auditoria")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "INICIAR_SESION" in html


def test_filtro_de_auditoria_por_operacion(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get(
        "/auditoria?operacion=INICIAR_SESION&fecha_desde=2020-01-01&fecha_hasta=2030-12-31"
    )

    assert respuesta.status_code == 200


def test_verificar_integridad_de_auditoria(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/auditoria/verificar", follow_redirects=True)

    assert respuesta.status_code == 200
    assert "íntegra" in respuesta.get_data(as_text=True).lower()


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def test_login_sin_token_csrf_devuelve_400(fabrica_sesiones) -> None:
    aplicacion = crear_app(
        {
            "SECRET_KEY": "clave-csrf",
            "WTF_CSRF_ENABLED": True,
            "SESSION_FACTORY": fabrica_sesiones,
        }
    )
    registrar_blueprints_seguridad(aplicacion)
    _crear_usuario_bd(fabrica_sesiones, username="admin", rol="ADMIN")

    respuesta = aplicacion.test_client().post(
        "/login", data={"username": "admin", "password": PASSWORD}
    )

    assert respuesta.status_code == 400


def test_login_con_token_csrf_valido_es_exitoso(fabrica_sesiones) -> None:
    aplicacion = crear_app(
        {
            "SECRET_KEY": "clave-csrf",
            "WTF_CSRF_ENABLED": True,
            "SESSION_FACTORY": fabrica_sesiones,
        }
    )
    registrar_blueprints_seguridad(aplicacion)
    _crear_usuario_bd(fabrica_sesiones, username="admin", rol="ADMIN")
    cliente = aplicacion.test_client()

    html = cliente.get("/login").get_data(as_text=True)
    token = PATRON_CSRF.search(html)
    assert token is not None

    respuesta = cliente.post(
        "/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": token.group(1),
        },
    )

    assert respuesta.status_code == 303


def test_post_de_usuario_sin_token_csrf_devuelve_400(fabrica_sesiones) -> None:
    aplicacion = crear_app(
        {
            "SECRET_KEY": "clave-csrf",
            "WTF_CSRF_ENABLED": True,
            "SESSION_FACTORY": fabrica_sesiones,
        }
    )
    registrar_blueprints_seguridad(aplicacion)
    _crear_usuario_bd(fabrica_sesiones, username="admin", rol="ADMIN")
    cliente = aplicacion.test_client()

    html = cliente.get("/login").get_data(as_text=True)
    token = PATRON_CSRF.search(html)
    assert token is not None
    cliente.post(
        "/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": token.group(1),
        },
    )

    respuesta = cliente.post(
        "/usuarios/nuevo",
        data={
            "username": "sin_csrf",
            "password": PASSWORD,
            "nombre_completo": "Sin CSRF",
            "rol": "ADMIN_STAFF",
        },
    )

    assert respuesta.status_code == 400


# ---------------------------------------------------------------------------
# Cobertura de ramas defensivas y de formularios
# ---------------------------------------------------------------------------


def test_registrar_blueprints_es_idempotente(app: Flask) -> None:
    registrar_blueprints_seguridad(app)


def test_servicio_seguridad_desde_extension(fabrica_sesiones) -> None:
    aplicacion = crear_app({"SECRET_KEY": "x", "WTF_CSRF_ENABLED": False})
    aplicacion.extensions["session_factory"] = fabrica_sesiones
    registrar_blueprints_seguridad(aplicacion)
    _crear_usuario_bd(fabrica_sesiones, username="admin", rol="ADMIN")

    respuesta = aplicacion.test_client().post(
        "/login", data={"username": "admin", "password": PASSWORD}
    )

    assert respuesta.status_code == 303


def test_servicio_sin_fabrica_lanza_error() -> None:
    aplicacion = crear_app({"SECRET_KEY": "x"})

    with aplicacion.app_context(), pytest.raises(RuntimeError):
        obtener_servicio_seguridad()


def test_almacen_sesiones_ausente_lanza_error(app: Flask) -> None:
    del app.extensions["almacen_sesiones"]

    with app.app_context(), pytest.raises(RuntimeError):
        _almacen_sesiones()


def test_usuario_actual_sin_usuario_aborta(app: Flask) -> None:
    with app.test_request_context("/"):
        g.usuario = None
        with pytest.raises(HTTPException) as error:
            _usuario_actual()

    assert error.value.code == 401


def test_inicio_sin_modulos_para_coordinador(cliente, monkeypatch) -> None:
    monkeypatch.setattr("src.presentacion.bp_seguridad.CANDIDATOS_INICIO", ())
    _login(cliente, username="coordinador")

    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "Colegio Domingo Savio" in respuesta.get_data(as_text=True)


def test_logout_tolera_error_al_cerrar_sesion(app: Flask, cliente, monkeypatch) -> None:
    _login(cliente)
    servicio = _servicio(app)

    def _fallar(token: str) -> None:
        raise SesionInvalidaException("La sesión ya fue cerrada.")

    monkeypatch.setattr(servicio, "cerrar_sesion", _fallar)

    respuesta = cliente.post("/logout")

    assert respuesta.status_code == 303


def test_get_formulario_nuevo_usuario(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/usuarios/nuevo")

    assert respuesta.status_code == 200
    assert "Nuevo usuario" in respuesta.get_data(as_text=True)


def test_crear_usuario_sin_datos_devuelve_400(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/usuarios/nuevo", data={})

    assert respuesta.status_code == 400


def test_get_formulario_editar_usuario(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"], username="editable_form", rol="ADMIN_STAFF"
    )
    _login(cliente)

    respuesta = cliente.get(f"/usuarios/{usuario_id}/editar")

    assert respuesta.status_code == 200
    assert "editable_form" in respuesta.get_data(as_text=True)


def test_editar_usuario_con_rol_inexistente_devuelve_400(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"], username="rol_malo", rol="ADMIN_STAFF"
    )
    _login(cliente)

    respuesta = cliente.post(
        f"/usuarios/{usuario_id}/editar",
        data={"nombre_completo": "Rol Malo", "rol": "NOEXISTE"},
    )

    assert respuesta.status_code == 400


def test_cambiar_estado_accion_invalida_devuelve_400(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"], username="accion_mala", rol="ADMIN_STAFF"
    )
    _login(cliente)

    respuesta = cliente.post(f"/usuarios/{usuario_id}/estado", data={"accion": "otra"})

    assert respuesta.status_code == 400


def test_activar_usuario(app: Flask, cliente) -> None:
    usuario_id = _crear_usuario_bd(
        app.config["SESSION_FACTORY"],
        username="reactivable",
        rol="ADMIN_STAFF",
        activo=False,
    )
    _login(cliente)

    respuesta = cliente.post(f"/usuarios/{usuario_id}/estado", data={"accion": "activar"})

    assert respuesta.status_code == 303
    assert _servicio(app).obtener_usuario(usuario_id).estado.value == "ACTIVO"


def test_restablecer_password_usuario_inexistente_devuelve_404(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/usuarios/9999/password",
        data={"password": "NuevaClave456", "confirmar": "NuevaClave456"},
    )

    assert respuesta.status_code == 404


def test_listar_roles_admin(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/roles")

    assert respuesta.status_code == 200
    assert "ADMIN" in respuesta.get_data(as_text=True)


def test_crear_rol_sin_datos_devuelve_400(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/roles/nuevo", data={})

    assert respuesta.status_code == 400


def test_editar_rol_inexistente_devuelve_404(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/roles/NOEXISTE/editar")

    assert respuesta.status_code == 404


def test_get_formulario_editar_rol(app: Flask, cliente) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "EDITABLE",
            "nombre": "Editable",
            "descripcion": "Rol editable.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )

    respuesta = cliente.get("/roles/EDITABLE/editar")

    assert respuesta.status_code == 200
    assert "EDITABLE" in respuesta.get_data(as_text=True)


def test_modificar_rol_de_sistema_devuelve_409(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post(
        "/roles/ADMIN/editar",
        data={
            "nombre": "Otro nombre",
            "descripcion": "Otra descripción",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )

    assert respuesta.status_code == 409


def test_cambiar_estado_rol_inexistente_devuelve_404(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/roles/NOEXISTE/estado", data={"accion": "desactivar"})

    assert respuesta.status_code == 404


def test_cambiar_estado_rol_accion_invalida_devuelve_400(app: Flask, cliente) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "ACCION_INVALIDA",
            "nombre": "Acción inválida",
            "descripcion": "Rol de prueba.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )

    respuesta = cliente.post("/roles/ACCION_INVALIDA/estado", data={"accion": "otra"})

    assert respuesta.status_code == 400


def test_activar_rol_personalizado(app: Flask, cliente) -> None:
    _login(cliente)
    cliente.post(
        "/roles/nuevo",
        data={
            "codigo": "REACTIVABLE",
            "nombre": "Reactivable",
            "descripcion": "Rol reactivable.",
            "permisos": ["CONSULTAR_FICHA_ALUMNO"],
        },
    )
    cliente.post("/roles/REACTIVABLE/estado", data={"accion": "desactivar"})

    respuesta = cliente.post("/roles/REACTIVABLE/estado", data={"accion": "activar"})

    assert respuesta.status_code == 303
    roles = {rol.codigo: rol for rol in _servicio(app).listar_roles()}
    assert roles["REACTIVABLE"].activo is True


def test_cambiar_estado_rol_sistema_devuelve_409(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/roles/ADMIN/estado", data={"accion": "desactivar"})

    assert respuesta.status_code == 409


def test_eliminar_rol_inexistente_devuelve_404(cliente) -> None:
    _login(cliente)

    respuesta = cliente.post("/roles/NOEXISTE/eliminar")

    assert respuesta.status_code == 404


def test_filtro_auditoria_con_fechas_invalidas_devuelve_400(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get("/auditoria?fecha_desde=2026-12-31&fecha_hasta=2026-01-01")

    assert respuesta.status_code == 400


def test_filtro_auditoria_con_parametros_invalidos(cliente) -> None:
    _login(cliente)

    respuesta = cliente.get(
        "/auditoria?usuario_id=abc&operacion=NO_EXISTE&resultado=NO_EXISTE&fecha_desde=no-fecha"
    )

    assert respuesta.status_code == 200


def test_verificar_integridad_con_error_de_dominio(app: Flask, cliente, monkeypatch) -> None:
    _login(cliente)
    servicio = _servicio(app)

    def _fallar(operador_id: int, **kwargs) -> None:
        raise SesionInvalidaException("La sesión no es válida.")

    monkeypatch.setattr(servicio, "verificar_integridad_auditoria", _fallar)

    respuesta = cliente.post("/auditoria/verificar")

    assert respuesta.status_code == 401


def test_verificar_integridad_alterada(app: Flask, cliente, monkeypatch) -> None:
    _login(cliente)
    servicio = _servicio(app)
    monkeypatch.setattr(
        servicio,
        "verificar_integridad_auditoria",
        lambda operador_id, **kwargs: ResultadoVerificacionIntegridad(integra=False),
    )

    respuesta = cliente.post("/auditoria/verificar", follow_redirects=True)

    assert respuesta.status_code == 200
    assert "alteraciones" in respuesta.get_data(as_text=True).lower()


def test_crear_usuario_sin_permiso_asignar_roles_devuelve_403(app: Flask, cliente) -> None:
    servicio = _servicio(app)
    admin_id = servicio.listar_usuarios(username="admin")[0].id
    servicio.crear_rol(
        admin_id,
        codigo="GESTOR",
        nombre="Gestor",
        descripcion="Solo gestiona usuarios.",
        permisos=[PermisoOperacion.GESTIONAR_USUARIOS],
    )
    _crear_usuario_bd(app.config["SESSION_FACTORY"], username="gestor", rol="GESTOR")

    _login(cliente, username="gestor")
    respuesta = cliente.post(
        "/usuarios/nuevo",
        data={
            "username": "otro",
            "password": PASSWORD,
            "nombre_completo": "Otro Usuario",
            "rol": "ADMIN_STAFF",
        },
    )

    assert respuesta.status_code == 403


def test_crear_usuario_con_rol_inactivo_devuelve_409(app: Flask, cliente) -> None:
    servicio = _servicio(app)
    admin_id = servicio.listar_usuarios(username="admin")[0].id
    servicio.crear_rol(
        admin_id,
        codigo="INACTIVO_ROL",
        nombre="Rol inactivo",
        descripcion="Rol desactivado.",
        permisos=[PermisoOperacion.CONSULTAR_FICHA_ALUMNO],
    )
    servicio.desactivar_rol(admin_id, codigo="INACTIVO_ROL")

    _login(cliente)
    respuesta = cliente.post(
        "/usuarios/nuevo",
        data={
            "username": "con_inactivo",
            "password": PASSWORD,
            "nombre_completo": "Con Rol Inactivo",
            "rol": "INACTIVO_ROL",
        },
    )

    assert respuesta.status_code == 409
