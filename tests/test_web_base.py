"""Pruebas base de la capa web y presentación.

Verifica:
- Creación de app limpia vía Application Factory (crear_app)
- Obligatoriedad de SECRET_KEY y configuración segura de cookies (HttpOnly, SameSite=Lax)
- Zona horaria oficial America/Lima (UTC-5)
- Protección CSRF estricta con token por sesión en servidor y bypass configurable
- Validación de sesiones en servidor (no confiar solo en la cookie)
- Control de acceso RBAC con 401 (no autenticado) y 403 (permiso denegado)
- Manejo defensivo de errores (400, 401, 403, 404, 500) sin fuga de datos sensibles
- Renderizado de base.html con navegación dinámica para los 5 módulos sin banner demo
- Filtros de plantilla y funciones globales auxiliares
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from flask import Blueprint, abort, render_template

from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    RolUsuario,
    SesionUsuario,
    Usuario,
)
from src.presentacion.app import crear_app, create_app
from src.presentacion.seguridad import (
    AlmacenSesiones,
    generar_token_csrf,
    login_requerido,
    permiso_requerido,
    tiene_permiso,
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


def _crear_sesion(
    usuario: Usuario,
    activa: bool = True,
    expirada: bool = False,
    naive: bool = False,
) -> SesionUsuario:
    ahora = datetime.now(UTC) if not naive else datetime.now(UTC).replace(tzinfo=None)
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
    assert isinstance(hora_actual(), time)


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
    assert create_app is crear_app


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
    res_get = cliente.get("/formulario")
    assert res_get.status_code == 200

    with cliente.session_transaction() as sess:
        token = sess["_csrf_token"]

    # Envío en formulario (csrf_token)
    res_post = cliente.post("/accion", data={"csrf_token": token, "campo": "valor"})
    assert res_post.status_code == 200
    assert "operacion-exitosa" in res_post.get_data(as_text=True)

    # Envío en formulario (_csrf_token)
    res_post_alt = cliente.post("/accion", data={"_csrf_token": token, "campo": "valor"})
    assert res_post_alt.status_code == 200

    # Envío en JSON
    res_json = cliente.post("/accion", json={"csrf_token": token, "dato": "xyz"})
    assert res_json.status_code == 200

    # Envío por cabecera X-CSRF-Token
    res_header = cliente.post("/accion", headers={"X-CSRF-Token": token})
    assert res_header.status_code == 200

    # Envío por cabecera X-CSRFToken
    res_header2 = cliente.post("/accion", headers={"X-CSRFToken": token})
    assert res_header2.status_code == 200

    # Token inválido
    res_invalido = cliente.post("/accion", data={"csrf_token": "token-falso"})
    assert res_invalido.status_code == 400


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
# 4. Almacén de Sesiones y Funcionalidades
# ----------------------------------------------------------------------
def test_almacen_sesiones_operaciones():
    almacen = AlmacenSesiones()
    usuario = _crear_usuario(1, "testusr", RolUsuario.ADMIN)
    sesion = _crear_sesion(usuario)

    almacen.guardar(sesion, usuario)
    assert almacen.obtener_sesion(sesion.token) == sesion
    assert almacen.obtener_usuario(usuario.id) == usuario

    # Revocar sesión existente
    almacen.revocar(sesion.token)
    sesion_revocada = almacen.obtener_sesion(sesion.token)
    assert sesion_revocada is not None
    assert sesion_revocada.activa is False

    # Revocar sesión inexistente no falla
    almacen.revocar("tok-inexistente")

    # Limpiar almacén
    almacen.limpiar()
    assert almacen.obtener_sesion(sesion.token) is None
    assert almacen.obtener_usuario(usuario.id) is None


# ----------------------------------------------------------------------
# 5. Control de Acceso RBAC y Validación de Sesión en Servidor
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


def test_login_requerido_usuario_inactivo_devuelve_401():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario_inactivo = _crear_usuario(2, "inactivo", RolUsuario.COORDINADOR, activo=False)
    sesion = _crear_sesion(usuario_inactivo)
    almacen.guardar(sesion, usuario_inactivo)

    @app.route("/privado-inactivo")
    @login_requerido
    def privado_inactivo():
        return "no-debe-verse"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/privado-inactivo")
    assert respuesta.status_code == 401


def test_login_requerido_con_reloj_aware_y_sesion_naive():
    # Cobertura de ramas de normalización de zonas horarias en login_requerido
    app = crear_app({
        "SECRET_KEY": "test-key",
        "WTF_CSRF_ENABLED": False,
        "RELOJ": lambda: datetime.now(UTC),
    })
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario = _crear_usuario(3, "usr_naive", RolUsuario.ADMIN)
    sesion_naive = _crear_sesion(usuario, naive=True)
    almacen.guardar(sesion_naive, usuario)

    @app.route("/privado-naive")
    @login_requerido
    def privado_naive():
        return "ok-naive"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion_naive.token

    respuesta = cliente.get("/privado-naive")
    assert respuesta.status_code == 200


def test_login_requerido_con_reloj_naive_y_sesion_aware():
    # Cobertura de rama inversa: reloj naive y sesión aware
    app = crear_app({
        "SECRET_KEY": "test-key",
        "WTF_CSRF_ENABLED": False,
        "RELOJ": lambda: datetime.now(UTC).replace(tzinfo=None),
    })
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario = _crear_usuario(4, "usr_aware", RolUsuario.ADMIN)
    sesion_aware = _crear_sesion(usuario, naive=False)
    almacen.guardar(sesion_aware, usuario)

    @app.route("/privado-aware")
    @login_requerido
    def privado_aware():
        return "ok-aware"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion_aware.token

    respuesta = cliente.get("/privado-aware")
    assert respuesta.status_code == 200


def test_no_confiar_en_rol_de_cookie_si_servidor_indica_lo_contrario():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario = _crear_usuario(5, "coord_pepe", RolUsuario.COORDINADOR)
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

    respuesta = cliente.get("/solo-admin")
    assert respuesta.status_code == 403
    assert "403" in respuesta.get_data(as_text=True)


def test_permiso_requerido_exitoso_para_admin():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    admin = _crear_usuario(6, "superadmin", RolUsuario.ADMIN)
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


def test_permiso_requerido_normaliza_tz_naive_reloj():
    app = crear_app({
        "SECRET_KEY": "test-key",
        "WTF_CSRF_ENABLED": False,
        "RELOJ": lambda: datetime.now(UTC).replace(tzinfo=None),
    })
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    admin = _crear_usuario(7, "admin_tz", RolUsuario.ADMIN)
    sesion = _crear_sesion(admin, naive=False)
    almacen.guardar(sesion, admin)

    @app.route("/gestion-tz")
    @permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
    def gestion_tz():
        return "tz-ok"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/gestion-tz")
    assert respuesta.status_code == 200


def test_permiso_requerido_normaliza_tz_aware_reloj_y_sesion_naive():
    app = crear_app({
        "SECRET_KEY": "test-key",
        "WTF_CSRF_ENABLED": False,
        "RELOJ": lambda: datetime.now(UTC),
    })
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    admin = _crear_usuario(8, "admin_tz2", RolUsuario.ADMIN)
    sesion = _crear_sesion(admin, naive=True)
    almacen.guardar(sesion, admin)

    @app.route("/gestion-tz2")
    @permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
    def gestion_tz2():
        return "tz2-ok"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/gestion-tz2")
    assert respuesta.status_code == 200


def test_permiso_requerido_sesion_invalida_en_validar_permiso():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario1 = _crear_usuario(9, "user1", RolUsuario.ADMIN)
    sesion = _crear_sesion(usuario1)
    usuario_modificado = _crear_usuario(9, "user1", RolUsuario.COORDINADOR)
    almacen.guardar(sesion, usuario_modificado)

    @app.route("/ruta-mismatch")
    @permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
    def ruta_mismatch():
        return "no-debe-verse"

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    respuesta = cliente.get("/ruta-mismatch")
    assert respuesta.status_code == 401


def test_sesion_expirada_devuelve_401():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    usuario = _crear_usuario(10, "vencido", RolUsuario.ADMIN)
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


def test_tiene_permiso_evaluaciones():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})
    almacen: AlmacenSesiones = app.extensions["almacen_sesiones"]

    # Sin sesión de servidor
    with app.test_request_context():
        assert tiene_permiso(PermisoOperacion.REGISTRAR_ASISTENCIA) is False

    # Con sesión activa de COORDINADOR
    usuario = _crear_usuario(11, "coord_eval", RolUsuario.COORDINADOR)
    sesion = _crear_sesion(usuario)
    almacen.guardar(sesion, usuario)

    cliente = app.test_client()
    with cliente.session_transaction() as sess:
        sess["token"] = sesion.token

    @app.route("/test-permisos")
    def test_permisos():
        p1 = tiene_permiso(PermisoOperacion.REGISTRAR_ASISTENCIA)
        p2 = tiene_permiso("REGISTRAR_ASISTENCIA")
        p3 = tiene_permiso("GESTIONAR_USUARIOS")
        p4 = tiene_permiso("PERMISO_TOTALMENTE_INVALIDO")
        p5 = tiene_permiso(12345)
        return f"{p1}|{p2}|{p3}|{p4}|{p5}"

    res = cliente.get("/test-permisos")
    assert res.get_data(as_text=True) == "True|True|False|False|False"


# ----------------------------------------------------------------------
# 6. Páginas de Error Defensivas (400, 401, 403, 404, 500)
# ----------------------------------------------------------------------
def test_manejadores_error_renderizan_sin_fuga_de_datos():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})

    @app.route("/error-500")
    def provocar_500():
        abort(500)

    @app.route("/error-400")
    def provocar_400():
        abort(400)

    @app.route("/error-403")
    def provocar_403():
        abort(403)

    cliente = app.test_client()

    # 400
    r_400 = cliente.get("/error-400")
    assert r_400.status_code == 400
    assert "400" in r_400.get_data(as_text=True)

    # 403
    r_403 = cliente.get("/error-403")
    assert r_403.status_code == 403
    assert "403" in r_403.get_data(as_text=True)

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
    assert "Traceback" not in r_500.get_data(as_text=True)


# ----------------------------------------------------------------------
# 7. Filtros Jinja2 y Helpers de Presentación
# ----------------------------------------------------------------------
def test_filtros_y_helpers_jinja():
    app = crear_app({"SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False})

    @app.route("/render-filtros")
    def render_filtros():
        plantilla = (
            "{{ f1|fecha_corta }}|"
            "{{ f2|fecha_corta }}|"
            "{{ h1|hora_corta }}|"
            "{{ h2|hora_corta }}|"
            "{{ h3|hora_corta }}|"
            "{{ r1|rol_legible }}|"
            "{{ r2|rol_legible }}|"
            "{{ e1|estado_texto }}|"
            "{{ e2|estado_texto }}|"
            "{{ c1|estado_clase }}|"
            "{{ c2|estado_clase }}|"
            "{{ safe_url_for('ruta_invalida', '/fallback') }}"
        )
        return render_template(
            app.jinja_env.from_string(plantilla),
            f1=date(2026, 11, 26),
            f2=None,
            h1=time(8, 30),
            h2=datetime(2026, 11, 26, 8, 30, 45),
            h3=None,
            r1=RolUsuario.ADMIN,
            r2="DOCENTE_EXTERNO",
            e1=EstadoUsuario.ACTIVO,
            e2="OTRO_ESTADO",
            c1=EstadoUsuario.ACTIVO,
            c2="DESCONOCIDO",
        )

    cliente = app.test_client()
    res = cliente.get("/render-filtros")
    assert res.status_code == 200
    esperado = (
        "26/11/2026|—|08:30|08:30:45|—|"
        "Administrador|DOCENTE_EXTERNO|"
        "Activa|OTRO_ESTADO|"
        "ok|neutral|/fallback"
    )
    assert res.get_data(as_text=True) == esperado


# ----------------------------------------------------------------------
# 8. Renderizado de base.html: Navegación Dinámica para 5 Módulos
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
    admin = _crear_usuario(20, "admin_test", RolUsuario.ADMIN)
    sesion_admin = _crear_sesion(admin)
    almacen.guardar(sesion_admin, admin)

    with cliente.session_transaction() as sess:
        sess["token"] = sesion_admin.token

    res_admin = cliente.get("/vista-test")
    assert res_admin.status_code == 200
    html_admin = res_admin.get_data(as_text=True)

    # Módulos completos visibles para ADMIN
    assert "Dashboard de aforo" in html_admin
    assert "Registro de asistencia" in html_admin
    assert "Justificaciones" in html_admin
    assert "Períodos académicos" in html_admin
    assert "Matrícula digital" in html_admin
    assert "Carnets QR" in html_admin
    assert "Estados académicos" in html_admin
    assert "Pagos y alertas" in html_admin
    assert "Malla curricular" in html_admin
    assert "Asignación docente" in html_admin
    assert "Calificaciones" in html_admin
    assert "Ficha del alumno" in html_admin
    assert "Exportar asistencia" in html_admin
    assert "Boletas" in html_admin
    assert "Gestión de usuarios" in html_admin
    assert "Roles y permisos" in html_admin
    assert "Auditoría" in html_admin

    # Sin banners demo
    assert "Demostración académica" not in html_admin
    assert "demo-banner" not in html_admin
    assert "demo-pill" not in html_admin

    # Caso 2: COORDINADOR (no debe ver módulos administrativos/financieros/seguridad)
    coord = _crear_usuario(21, "coord_test", RolUsuario.COORDINADOR)
    sesion_coord = _crear_sesion(coord)
    almacen.guardar(sesion_coord, coord)

    with cliente.session_transaction() as sess:
        sess["token"] = sesion_coord.token

    res_coord = cliente.get("/vista-test")
    html_coord = res_coord.get_data(as_text=True)

    assert "Dashboard de aforo" in html_coord
    assert "Registro de asistencia" in html_coord
    assert "Justificaciones" in html_coord
    assert "Carnets QR" in html_coord
    assert "Calificaciones" in html_coord
    assert "Ficha del alumno" in html_coord
    assert "Exportar asistencia" in html_coord
    assert "Matrícula digital" not in html_coord
    assert "Pagos y alertas" not in html_coord
    assert "Malla curricular" not in html_coord
    assert "Gestión de usuarios" not in html_coord
    assert "Roles y permisos" not in html_coord
    assert "Auditoría" not in html_coord
