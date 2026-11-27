"""Blueprints web del módulo de seguridad: login, usuarios, roles y auditoría.

Ola 4 - Miembro 1. Las rutas solo orquestan: leen la petición, delegan en la
capa de aplicación (:mod:`src.aplicacion.servicios_seguridad`) y renderizan.
No contienen reglas de negocio; las excepciones de dominio se traducen a
mensajes flash o a respuestas HTTP 400/401/403/404/409.
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Final, TypeVar

from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.aplicacion.servicios_seguridad import ServicioSeguridad
from src.dominio.auditoria import (
    AuditoriaException,
    FiltroAuditoria,
    ResultadoAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.usuarios import (
    AccesoDenegadoException,
    CredencialesInvalidasException,
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolInactivoException,
    RolInvalidoException,
    SesionInvalidaException,
    UltimoAdminException,
    Usuario,
    UsuarioDuplicadoException,
    UsuarioException,
    UsuarioNoEncontradoException,
)
from src.presentacion.seguridad import (
    AlmacenSesiones,
    generar_token_csrf,
    login_requerido,
    permiso_requerido,
    tiene_permiso,
)
from src.presentacion.tiempo import ZONA_HORARIA_LIMA

E = TypeVar("E", bound=StrEnum)

#: Orden de preferencia para el aterrizaje posterior al inicio de sesión.
CANDIDATOS_INICIO: Final[tuple[tuple[str, PermisoOperacion], ...]] = (
    ("main.aforo", PermisoOperacion.CONSULTAR_DASHBOARD_AFORO),
    ("asistencia.ver_asistencia", PermisoOperacion.REGISTRAR_ASISTENCIA),
    ("justificaciones.ver_justificaciones", PermisoOperacion.GESTIONAR_JUSTIFICACIONES),
    ("usuarios.listar_usuarios", PermisoOperacion.GESTIONAR_USUARIOS),
    ("auditoria.ver_auditoria", PermisoOperacion.CONSULTAR_AUDITORIA),
)

#: Títulos institucionales por código de error de dominio.
TITULOS_ERROR: Final[dict[int, str]] = {
    400: "Solicitud incorrecta",
    401: "No autorizado",
    403: "Acceso restringido",
    404: "Recurso no encontrado",
    409: "Conflicto de estado",
}


bp_auth = Blueprint("auth", __name__)
bp_usuarios = Blueprint("usuarios", __name__)
bp_roles = Blueprint("roles", __name__)
bp_auditoria = Blueprint("auditoria", __name__)


# ---------------------------------------------------------------------------
# Registro e infraestructura de la capa web
# ---------------------------------------------------------------------------


def registrar_blueprints_seguridad(app: Flask) -> None:
    """Registra los blueprints de seguridad y carga los roles para el RBAC.

    Contrato de integración (Miembro 5): la aplicación debe configurar
    ``SESSION_FACTORY`` (o la extensión ``session_factory``) con una fábrica
    de sesiones SQLAlchemy antes de atender peticiones.
    """
    if app.extensions.get("blueprints_seguridad_registrados"):
        return

    app.extensions.setdefault("almacen_sesiones", AlmacenSesiones())
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_usuarios)
    app.register_blueprint(bp_roles)
    app.register_blueprint(bp_auditoria)

    @app.before_request
    def cargar_roles_disponibles() -> None:
        """Expone los roles vigentes para validar también roles personalizados."""
        if getattr(g, "sesion_servidor", None) is None:
            g.roles_disponibles = None
            return
        g.roles_disponibles = obtener_servicio_seguridad().listar_roles()

    app.extensions["blueprints_seguridad_registrados"] = True


def obtener_servicio_seguridad() -> ServicioSeguridad:
    """Devuelve el servicio de seguridad, construyéndolo si aún no existe."""
    existente = current_app.extensions.get("servicio_seguridad")
    if isinstance(existente, ServicioSeguridad):
        return existente

    fabrica = current_app.config.get("SESSION_FACTORY")
    if fabrica is None:
        fabrica = current_app.extensions.get("session_factory")
    if fabrica is None:
        raise RuntimeError(
            "La aplicación no configuró SESSION_FACTORY para el módulo de seguridad."
        )

    servicio = ServicioSeguridad(fabrica)
    current_app.extensions["servicio_seguridad"] = servicio
    return servicio


def _almacen_sesiones() -> AlmacenSesiones:
    almacen = current_app.extensions.get("almacen_sesiones")
    if not isinstance(almacen, AlmacenSesiones):
        raise RuntimeError("La aplicación no inicializó el almacén de sesiones.")
    return almacen


def _usuario_actual() -> Usuario:
    usuario = getattr(g, "usuario", None)
    if not isinstance(usuario, Usuario):
        abort(401)
    return usuario


# ---------------------------------------------------------------------------
# Helpers de petición y de traducción de errores
# ---------------------------------------------------------------------------


def _texto(nombre: str) -> str:
    return (request.form.get(nombre) or "").strip()


def _arg(nombre: str) -> str:
    return (request.args.get(nombre) or "").strip()


def _entero_opcional(valor: str | None) -> int | None:
    if not valor:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _enum(tipo: type[E], valor: str | None) -> E | None:
    if not valor:
        return None
    try:
        return tipo(valor)
    except ValueError:
        return None


def _fecha(valor: str | None, *, fin_del_dia: bool) -> datetime | None:
    if not valor:
        return None
    try:
        dia = date.fromisoformat(valor)
    except ValueError:
        return None
    hora = time.max if fin_del_dia else time.min
    return datetime.combine(dia, hora, tzinfo=ZONA_HORARIA_LIMA)


def _error_dominio(exc: UsuarioException) -> tuple[str, int]:
    """Traduce una excepción de dominio a ``(mensaje, código HTTP)``."""
    if isinstance(exc, UsuarioNoEncontradoException):
        return ("El usuario solicitado no existe.", 404)
    if isinstance(exc, UsuarioDuplicadoException):
        return ("El nombre de usuario ya está registrado.", 409)
    if isinstance(exc, UltimoAdminException):
        return ("No se puede dejar el sistema sin un administrador activo.", 409)
    if isinstance(exc, RolInactivoException):
        return (str(exc), 409)
    if isinstance(exc, RolInvalidoException):
        detalle = str(exc).lower()
        conflicto = "ya existe" in detalle or "no puede" in detalle or "no pueden" in detalle
        return (str(exc), 409 if conflicto else 400)
    if isinstance(exc, AccesoDenegadoException):
        return ("No tiene permisos para realizar esta operación.", 403)
    if isinstance(exc, CredencialesInvalidasException):
        return ("Credenciales incorrectas.", 401)
    if isinstance(exc, SesionInvalidaException):
        return ("La sesión no es válida. Inicie sesión nuevamente.", 401)
    return (str(exc) or "No fue posible completar la operación.", 400)


def _redirigir(url: str):
    """Redirección PRG (303) tras una operación web exitosa."""
    return redirect(url, code=303)


def _respuesta_error(codigo: int, mensaje: str) -> tuple[str, int]:
    return (
        render_template(
            "error.html",
            codigo=codigo,
            titulo=TITULOS_ERROR.get(codigo, "Operación no completada"),
            mensaje=mensaje,
        ),
        codigo,
    )


def _primer_modulo_disponible() -> str | None:
    for endpoint, permiso in CANDIDATOS_INICIO:
        if endpoint not in current_app.view_functions:
            continue
        if not tiene_permiso(permiso):
            continue
        return url_for(endpoint)
    return None


def _permisos_ordenados() -> list[PermisoOperacion]:
    return sorted(PermisoOperacion, key=lambda permiso: permiso.value)


def _permisos_seleccionados() -> list[PermisoOperacion]:
    seleccionados: list[PermisoOperacion] = []
    for valor in request.form.getlist("permisos"):
        permiso = _enum(PermisoOperacion, valor)
        if permiso is not None:
            seleccionados.append(permiso)
    return seleccionados


def _buscar_rol(servicio: ServicioSeguridad, codigo: str) -> Rol | None:
    codigo_normalizado = codigo.strip().upper()
    return next(
        (rol for rol in servicio.listar_roles() if rol.codigo == codigo_normalizado),
        None,
    )


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    """Muestra el formulario de acceso y valida credenciales en el servidor."""
    if getattr(g, "sesion_servidor", None) is not None:
        return _redirigir(url_for("auth.inicio"))

    if request.method != "POST":
        return render_template("login.html")

    username = _texto("username")
    password = request.form.get("password") or ""
    if not username or not password:
        flash("Ingrese su usuario y contraseña.", "error")
        return render_template("login.html"), 400

    servicio = obtener_servicio_seguridad()
    try:
        sesion = servicio.iniciar_sesion(username, password)
        usuario = servicio.obtener_usuario(sesion.usuario_id)
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        flash(mensaje, "error")
        return render_template("login.html"), codigo

    _almacen_sesiones().guardar(sesion, usuario)
    session.clear()
    session["token"] = sesion.token
    generar_token_csrf()
    return _redirigir(url_for("auth.inicio"))


@bp_auth.route("/logout", methods=["POST"])
@login_requerido
def logout():
    """Cierra la sesión oficial y limpia la cookie del navegador."""
    token = session.get("token")
    if token:
        try:
            obtener_servicio_seguridad().cerrar_sesion(token)
        except UsuarioException:
            pass
        _almacen_sesiones().revocar(token)

    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return _redirigir(url_for("auth.login"))


@bp_auth.route("/")
@login_requerido
def inicio():
    """Redirige al primer módulo habilitado para el usuario autenticado."""
    destino = _primer_modulo_disponible()
    if destino is not None:
        return _redirigir(destino)
    return render_template("base.html")


# ---------------------------------------------------------------------------
# Gestión de usuarios
# ---------------------------------------------------------------------------


@bp_usuarios.route("/usuarios")
@permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
def listar_usuarios():
    """Lista y filtra usuarios por nombre, username, rol y estado."""
    servicio = obtener_servicio_seguridad()
    roles = servicio.listar_roles()
    rol_solicitado = _arg("rol").upper() or None
    codigos_roles = {rol.codigo for rol in roles}

    usuarios = servicio.listar_usuarios(
        nombre=_arg("nombre") or None,
        username=_arg("username") or None,
        rol=rol_solicitado if rol_solicitado in codigos_roles else None,
        estado=_enum(EstadoUsuario, _arg("estado")),
    )
    return render_template(
        "usuarios.html",
        usuarios=usuarios,
        roles=roles,
        filtros=request.args,
    )


@bp_usuarios.route("/usuarios/nuevo", methods=["GET", "POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
def crear_usuario():
    """Crea una cuenta de usuario delegando todas las reglas en el dominio."""
    servicio = obtener_servicio_seguridad()
    roles = servicio.listar_roles()

    if request.method == "GET":
        return render_template(
            "usuarios_form.html", usuario=None, roles=roles, datos={}
        )

    datos = {
        "username": _texto("username"),
        "nombre_completo": _texto("nombre_completo"),
        "rol": _texto("rol"),
    }
    password = request.form.get("password") or ""
    if not datos["username"] or not datos["nombre_completo"] or not datos["rol"]:
        flash("Complete usuario, nombre completo y rol.", "error")
        return render_template(
            "usuarios_form.html", usuario=None, roles=roles, datos=datos
        ), 400

    try:
        servicio.crear_usuario(
            _usuario_actual().id,
            username=datos["username"],
            password_plana=password,
            nombre_completo=datos["nombre_completo"],
            rol=datos["rol"],
        )
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        flash(mensaje, "error")
        return render_template(
            "usuarios_form.html", usuario=None, roles=roles, datos=datos
        ), codigo

    flash("Usuario creado correctamente.", "success")
    return _redirigir(url_for("usuarios.listar_usuarios"))


@bp_usuarios.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
def editar_usuario(usuario_id: int):
    """Modifica el nombre completo y el rol de una cuenta existente."""
    servicio = obtener_servicio_seguridad()
    roles = servicio.listar_roles()
    try:
        usuario = servicio.obtener_usuario(usuario_id)
    except UsuarioNoEncontradoException:
        abort(404)

    if request.method == "GET":
        datos = {
            "username": usuario.username,
            "nombre_completo": usuario.nombre_completo,
            "rol": str(usuario.rol),
        }
        return render_template(
            "usuarios_form.html", usuario=usuario, roles=roles, datos=datos
        )

    datos = {
        "username": usuario.username,
        "nombre_completo": _texto("nombre_completo"),
        "rol": _texto("rol"),
    }
    try:
        servicio.modificar_usuario(
            _usuario_actual().id,
            usuario_id,
            nuevo_nombre=datos["nombre_completo"] or None,
            nuevo_rol=datos["rol"] or None,
        )
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        flash(mensaje, "error")
        return render_template(
            "usuarios_form.html", usuario=usuario, roles=roles, datos=datos
        ), codigo

    flash("Usuario actualizado correctamente.", "success")
    return _redirigir(url_for("usuarios.listar_usuarios"))


@bp_usuarios.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
def cambiar_estado_usuario(usuario_id: int):
    """Activa o desactiva una cuenta y revoca sus sesiones cuando corresponde."""
    accion = _texto("accion").lower()
    if accion not in {"activar", "desactivar"}:
        abort(400)

    servicio = obtener_servicio_seguridad()
    try:
        if accion == "activar":
            servicio.activar_usuario(_usuario_actual().id, usuario_id)
            flash("Usuario activado correctamente.", "success")
        else:
            servicio.desactivar_usuario(_usuario_actual().id, usuario_id)
            flash("Usuario desactivado y sesiones revocadas.", "success")
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        return _respuesta_error(codigo, mensaje)

    return _redirigir(url_for("usuarios.listar_usuarios"))


@bp_usuarios.route("/usuarios/<int:usuario_id>/password", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_USUARIOS)
def restablecer_password(usuario_id: int):
    """Restablece la contraseña de una cuenta y revoca sus sesiones."""
    password = request.form.get("password") or ""
    confirmacion = request.form.get("confirmar") or ""
    if not password or password != confirmacion:
        flash("La contraseña y su confirmación deben coincidir.", "error")
        return _respuesta_error(400, "La contraseña y su confirmación deben coincidir.")

    servicio = obtener_servicio_seguridad()
    try:
        servicio.restablecer_password(
            _usuario_actual().id,
            usuario_id,
            nueva_password_plana=password,
        )
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        return _respuesta_error(codigo, mensaje)

    flash("Contraseña restablecida y sesiones revocadas.", "success")
    return _redirigir(url_for("usuarios.listar_usuarios"))


# ---------------------------------------------------------------------------
# Gestión de roles
# ---------------------------------------------------------------------------


@bp_roles.route("/roles")
@permiso_requerido(PermisoOperacion.GESTIONAR_ROLES)
def listar_roles():
    """Lista los roles base y personalizados con su estado y permisos."""
    servicio = obtener_servicio_seguridad()
    return render_template(
        "roles.html",
        roles=servicio.listar_roles(),
        total_permisos=len(PermisoOperacion),
    )


@bp_roles.route("/roles/nuevo", methods=["GET", "POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_ROLES)
def crear_rol():
    """Crea un rol personalizado con los permisos seleccionados."""
    servicio = obtener_servicio_seguridad()
    permisos = _permisos_ordenados()

    if request.method == "GET":
        return render_template(
            "roles_form.html",
            rol=None,
            datos={},
            permisos=permisos,
            seleccionados=set(),
        )

    datos = {
        "codigo": _texto("codigo"),
        "nombre": _texto("nombre"),
        "descripcion": _texto("descripcion"),
    }
    seleccionados = set(_permisos_seleccionados())
    if not datos["codigo"] or not datos["nombre"] or not datos["descripcion"]:
        flash("Complete código, nombre y descripción del rol.", "error")
        return render_template(
            "roles_form.html",
            rol=None,
            datos=datos,
            permisos=permisos,
            seleccionados=seleccionados,
        ), 400

    try:
        servicio.crear_rol(
            _usuario_actual().id,
            codigo=datos["codigo"],
            nombre=datos["nombre"],
            descripcion=datos["descripcion"],
            permisos=seleccionados,
        )
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        flash(mensaje, "error")
        return render_template(
            "roles_form.html",
            rol=None,
            datos=datos,
            permisos=permisos,
            seleccionados=seleccionados,
        ), codigo

    flash("Rol creado correctamente.", "success")
    return _redirigir(url_for("roles.listar_roles"))


@bp_roles.route("/roles/<codigo>/editar", methods=["GET", "POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_ROLES)
def editar_rol(codigo: str):
    """Modifica nombre, descripción y permisos de un rol personalizado."""
    servicio = obtener_servicio_seguridad()
    rol = _buscar_rol(servicio, codigo)
    if rol is None:
        abort(404)

    permisos = _permisos_ordenados()
    if request.method == "GET":
        datos = {
            "codigo": rol.codigo,
            "nombre": rol.nombre,
            "descripcion": rol.descripcion,
        }
        return render_template(
            "roles_form.html",
            rol=rol,
            datos=datos,
            permisos=permisos,
            seleccionados=set(rol.permisos),
        )

    datos = {
        "codigo": rol.codigo,
        "nombre": _texto("nombre"),
        "descripcion": _texto("descripcion"),
    }
    seleccionados = set(_permisos_seleccionados())
    try:
        servicio.modificar_rol(
            _usuario_actual().id,
            codigo=rol.codigo,
            nombre=datos["nombre"] or None,
            descripcion=datos["descripcion"] or None,
            permisos=seleccionados,
        )
    except UsuarioException as exc:
        mensaje, error_codigo = _error_dominio(exc)
        flash(mensaje, "error")
        return render_template(
            "roles_form.html",
            rol=rol,
            datos=datos,
            permisos=permisos,
            seleccionados=seleccionados,
        ), error_codigo

    flash("Rol actualizado correctamente.", "success")
    return _redirigir(url_for("roles.listar_roles"))


@bp_roles.route("/roles/<codigo>/estado", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_ROLES)
def cambiar_estado_rol(codigo: str):
    """Activa o desactiva un rol y revoca las sesiones de su rol al desactivar."""
    servicio = obtener_servicio_seguridad()
    if _buscar_rol(servicio, codigo) is None:
        abort(404)

    accion = _texto("accion").lower()
    if accion not in {"activar", "desactivar"}:
        abort(400)

    try:
        if accion == "activar":
            servicio.activar_rol(_usuario_actual().id, codigo=codigo)
            flash("Rol activado correctamente.", "success")
        else:
            servicio.desactivar_rol(_usuario_actual().id, codigo=codigo)
            flash("Rol desactivado y sesiones revocadas.", "success")
    except UsuarioException as exc:
        mensaje, error_codigo = _error_dominio(exc)
        return _respuesta_error(error_codigo, mensaje)

    return _redirigir(url_for("roles.listar_roles"))


@bp_roles.route("/roles/<codigo>/eliminar", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_ROLES)
def eliminar_rol(codigo: str):
    """Elimina un rol personalizado sin usuarios asignados."""
    servicio = obtener_servicio_seguridad()
    if _buscar_rol(servicio, codigo) is None:
        abort(404)

    try:
        servicio.eliminar_rol(_usuario_actual().id, codigo=codigo)
    except UsuarioException as exc:
        mensaje, error_codigo = _error_dominio(exc)
        return _respuesta_error(error_codigo, mensaje)

    flash("Rol eliminado correctamente.", "success")
    return _redirigir(url_for("roles.listar_roles"))


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------


@bp_auditoria.route("/auditoria")
@permiso_requerido(PermisoOperacion.CONSULTAR_AUDITORIA)
def ver_auditoria():
    """Consulta los eventos de auditoría con filtros combinables."""
    servicio = obtener_servicio_seguridad()
    try:
        filtro = FiltroAuditoria(
            fecha_desde=_fecha(request.args.get("fecha_desde"), fin_del_dia=False),
            fecha_hasta=_fecha(request.args.get("fecha_hasta"), fin_del_dia=True),
            usuario_id=_entero_opcional(request.args.get("usuario_id")),
            rol=_arg("rol") or None,
            operacion=_enum(TipoOperacionAuditoria, _arg("operacion")),
            entidad=_arg("entidad") or None,
            resultado=_enum(ResultadoAuditoria, _arg("resultado")),
        )
    except AuditoriaException as exc:
        return _respuesta_error(400, str(exc))

    eventos = servicio.consultar_auditoria(_usuario_actual().id, filtro)
    return render_template(
        "auditoria.html",
        eventos=eventos,
        filtros=request.args,
        operaciones=list(TipoOperacionAuditoria),
        resultados=list(ResultadoAuditoria),
    )


@bp_auditoria.route("/auditoria/verificar", methods=["POST"])
@permiso_requerido(PermisoOperacion.VERIFICAR_INTEGRIDAD_AUDITORIA)
def verificar_integridad():
    """Verifica la cadena SHA-256 de los eventos y muestra el resultado."""
    servicio = obtener_servicio_seguridad()
    try:
        resultado = servicio.verificar_integridad_auditoria(_usuario_actual().id)
    except UsuarioException as exc:
        mensaje, codigo = _error_dominio(exc)
        return _respuesta_error(codigo, mensaje)

    if resultado.integra:
        flash("La cadena de auditoría es íntegra: no se detectaron alteraciones.", "success")
    else:
        detalle = resultado.detalle or "Se detectaron alteraciones en la cadena."
        flash(f"La cadena de auditoría presenta alteraciones. {detalle}", "error")
    return _redirigir(url_for("auditoria.ver_auditoria"))
