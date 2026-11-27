"""Pruebas base de la capa web y presentación.

Verifica:
- Creación de app limpia vía Application Factory (crear_app)
- Obligatoriedad de SECRET_KEY y configuración segura de cookies (HttpOnly, SameSite=Lax)
- Zona horaria oficial America/Lima (UTC-5)
- Protección CSRF estricta con token por sesión en servidor y bypass configurable
- Validación de sesiones en servidor (no confiar solo en la cookie)
- Control de acceso RBAC con 401 (no autenticado) y 403 (permiso denegado)
- Manejo defensivo de errores (401, 403, 404, 500) sin fuga de datos sensibles
- Renderizado de base.html con navegación dinámica para los 5 módulos sin banner demo
"""

from datetime import UTC, datetime, timedelta
import pytest
from flask import Blueprint, abort, render_template

from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    RolUsuario,
    SesionUsuario,
    Usuario,
)
from src.presentacion.app import crear_app
from src.presentacion.seguridad import (
    AlmacenSesiones,
    generar_token_csrf,
    login_requerido,
    permiso_requerido,
)
from src.presentacion.tiempo import (
    DESPLAZAMIENTO_PERU,
    ZONA_HORARIA_LIMA,
    ahora_lima,
    hora_actual,
    hora_institucional,
)


def _crear_usuario(id_: int, username: str, rol: RolUsuario, activo: bool = True) -> Usuario:
    return Usuario(
        id=id_,
        username=username,
        password_hash="fakehash",
        salt="fakesalt",
        nombre_completo=f"Usuario {username}",
        rol=rol,
        estado=EstadoUsuario.ACTIVO if activo else EstadoUsuario.INACTIVO,
    )


def _crear_sesion(usuario: Usuario, activa: bool = True, expirada: bool = False) -> SesionUsuario:
    ahora = datetime.now(UTC)
    if expirada:
        inicio = ahora - timedelta(hours=2)
        expira = ahora - timedelta(hours=1)
    else:
        inicio = ahora
        expira = ahora + timedelta(hours=8)

    return SesionUsuario(
        token=f"tok-{usuario.username}-test",
        usuario_id=usuario.id,
        username=usuario.username,
        rol=usuario.rol,
        fecha_inicio=inicio,
        fecha_expiracion=expira,
        activa=activa,
    )


# ----------------------------------------------------------------------
# 1. Zona Horaria Oficial America/Lima (UTC-5)
# ----------------------------------------------------------------------
def test_zona_horaria_oficial_lima():
    assert ZONA_HORARIA_LIMA.tzname(None) == "America/Lima"
    assert ZONA_HORARIA_LIMA.utcoffset(None) == timedelta(hours=-5)
    assert DESPLAZAMIENTO_PERU == timedelta(hours=-5)

    ahora = ahora_lima()
    assert ahora.tzinfo == ZONA_HORARIA_LIMA

    inst = hora_institucional()
    assert inst is not None
    assert isinstance(hora_actual(), datetime.time().__class__)


# ----------------------------------------------------------------------
# 2. Application Factory y Configuración de Seguridad
# ----------------------------------------------------------------------
def test_crear_app_falla_sin_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="SECRET_KEY es obligatoria"):
        crear_app()


def test_crear_app_con_secret_key_configuracion():
    app = crear_app({"SECRET_KEY": "clave-secreta-de-prueba-12345"})
    assert app.config["SECRET_KEY"] == "clave-secreta-de-prueba-12345"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


# ----------------------------------------------------------------------
# 3. Protección CSRF
# ----------------------------------------------------------------------
def test_csrf_rechaza_post_sin_token():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": True})

    @app.route("/accion", methods=["POST"])
    def accion():
        return "ok"

    cliente = app.test_client()
    respuesta = cliente.post("/accion", data={"campo": "valor"})
    assert respuesta.status_code == 400
    assert "CSRF" in respuesta.get_data(as_text=True)


def test_csrf_permite_post_con_token_valido():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": True})

    @app.route("/formulario", methods=["GET"])
    def formulario():
        token = generar_token_csrf()
        return f'<form><input name="csrf_token" value="{token}"></form>'

    @app.route("/accion", methods=["POST"])
    def accion():
        return "operacion-exitosa"

    cliente = app.test_client()
    # Primera petición GET inicializa la sesión y obtiene token
    res_get = cliente.get("/formulario")
    assert res_get.status_code == 200

    with cliente.session_transaction() as sess:
        token = sess["_csrf_token"]

    # Envío en formulario
    res_post = cliente.post("/accion", data={"csrf_token": token, "campo": "valor"})
    assert res_post.status_code == 200
    assert "operacion-exitosa" in res_post.get_data(as_text=True)

    # Envío por cabecera X-CSRF-Token
    res_header = cliente.post("/accion", headers={"X-CSRF-Token": token})
    assert res_header.status_code == 200


def test_csrf_permite_desactivacion_en_tests():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})

    @app.route("/accion", methods=["POST"])
    def accion():
        return "exito-sin-csrf"

    cliente = app.test_client()
    respuesta = cliente.post("/accion", data={"dato": 123})
    assert respuesta.status_code == 200
    assert "exito-sin-csrf" in respuesta.get_data(as_text=True)


# ----------------------------------------------------------------------
# 4. Control de Acceso RBAC y Validación de Sesión en Servidor
# ----------------------------------------------------------------------
def test_login_requerido_sin_sesion_devuelve_401():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})

    @app.route("/privado")
    @login_requerido
    def privado():
        return "zona-privada"

    cliente = app.test_client()
    respuesta = cliente.get("/privado")
    assert respuesta.status_code == 401
    assert "401" in respuesta.get_data(as_text=True)


def test_login_requerido_con_sesion_activa_servidor():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario = _crear_usuario(1, "coordinador1", RolUsuario.COORDINADOR)
    sesion = _crear_sesion(usuario)
    almacen.guardar(sesion, usuario)

    @app.route("/privado")
    @login_requerido
    def privado():
        return "zona-privada-autorizada"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/privado")
    assert respuesta.status_code == 200
    assert "zona-privada-autorizada" in respuesta.get_data(as_text=True)


def test_no_confiar_en_rol_de_cookie_si_servidor_indica_lo_contrario():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    # Usuario en el servidor es COORDINADOR
    usuario = _crear_usuario(2, "coord_pepe", RolUsuario.COORDINADOR)
    sesion = _crear_sesion(usuario)
    almacen.guardar(sesion, usuario)

    @app.route("/solo-admin")
    @permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
    def solo_admin():
        return "panel-admin"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token
        sess["rol"] = "ADMIN"  # Intento de suplantación en cookie

    # El servidor evalúa contra el registro del servidor y rechaza con 403
    respuesta = cliente.get("/solo-admin")
    assert respuesta.status_code == 403
    assert "403" in respuesta.get_data(as_text=True)


def test_permiso_requerido_exitoso_para_admin():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    admin = _crear_usuario(3, "superadmin", RolUsuario.ADMIN)
    sesion = _crear_sesion(admin)
    almacen.guardar(sesion, admin)

    @app.route("/gestion-usuarios")
    @permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
    def gestion_usuarios():
        return "gestion-usuarios-ok"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/gestion-usuarios")
    assert respuesta.status_code == 200
    assert "gestion-usuarios-ok" in respuesta.get_data(as_text=True)


def test_sesion_expirada_o_inactiva_devuelve_401():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario = _crear_usuario(4, "vencido", RolUsuario.ADMIN)
    sesion = _crear_sesion(usuario, expirada=True)
    almacen.guardar(sesion, usuario)

    @app.route("/ruta-protegida")
    @login_requerido
    def ruta_protegida():
        return "no-debe-verse"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/ruta-protegida")
    assert respuesta.status_code == 401


# ----------------------------------------------------------------------
# 5. Páginas de Error Defensivas (401, 403, 404, 500)
# ----------------------------------------------------------------------
def test_manejadores_error_renderizan_sin_fuga_de_datos():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})

    @app.route("/error-500")
    def provocar_500():
        abort(500)

    cliente = app.test_client()

    # 404
    r_404 = cliente.get("/ruta-que-no-existe-xyz")
    assert r_404.status_code == 404
    assert "404" in r_404.get_data(as_text=True)
    assert "Página no encontrada" in r_404.get_data(as_text=True)

    # 500
    r_500 = cliente.get("/error-500")
    assert r_500.status_code == 500
    assert "500" in r_500.get_data(as_text=True)
    assert "Error interno" in r_500.get_data(as_text=True)
    # Sin fuga de traza
    assert "Traceback" not in r_500.get_data(as_text=True)


# ----------------------------------------------------------------------
# 6. Renderizado de base.html: Navegación Dinámica para 5 Módulos
# ----------------------------------------------------------------------
def test_base_html_navegacion_dinamica_segun_permisos():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    bp_prueba = Blueprint("prueba", __name__)

    @bp_prueba.route("/vista-test")
    def vista_test():
        return render_template("base.html")

    app.register_blueprint(bp_prueba)

    cliente = app.test_client()

    # Caso 1: ADMIN debe ver los 5 módulos
    admin = _crear_usuario(10, "admin_test", RolUsuario.ADMIN)
    sesion_admin = _crear_sesion(admin)
    almacen.guardar(sesion_admin, admin)

    with cliente.session_transaction() as sess:
        sess["token"] = sesion_admin.token

    res_admin = cliente.get("/vista-test")
    assert res_admin.status_code == 200
    html_admin = res_admin.get_data(as_text=True)

    # 5 módulos presentes
    assert "Dashboard de aforo" in html_admin
    assert "Registro de asistencia" in html_admin
    assert "Justificaciones" in html_admin
    assert "Gestión de usuarios" in html_admin
    assert "Auditoría" in html_admin

    # Sin banners demo
    assert "Demostración académica" not in html_admin
    assert "demo-banner" not in html_admin
    assert "demo-pill" not in html_admin

    # Caso 2: COORDINADOR (no debe ver Gestión de usuarios ni Auditoría)
    coord = _crear_usuario(11, "coord_test", RolUsuario.COORDINADOR)
    sesion_coord = _crear_sesion(coord)
    almacen.guardar(sesion_coord, coord)

    with cliente.session_transaction() as sess:
        sess["token"] = sesion_coord.token

    res_coord = cliente.get("/vista-test")
    html_coord = res_coord.get_data(as_text=True)

    assert "Dashboard de aforo" in html_coord
    assert "Registro de asistencia" in html_coord
    assert "Justificaciones" in html_coord
    assert "Gestión de usuarios" not in html_coord
    assert "Auditoría" not in html_coord
