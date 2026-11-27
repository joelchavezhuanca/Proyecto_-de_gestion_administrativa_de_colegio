"""Módulo de seguridad web, control de acceso y protección CSRF.

Implementa:
- Validación de sesiones en el servidor mediante ServicioAutenticacionYPermisos.
- Decoradores @login_requerido y @permiso_requerido(PermisoOperacion.X).
- Manejo seguro de roles (nunca confía únicamente en la cookie del cliente).
- Generación y validación estricta de tokens CSRF por sesión.
"""

import hmac
import secrets
from collections.abc import Callable, Sequence
from functools import wraps

from flask import abort, current_app, g, request, session

from src.dominio.usuarios import (
    AccesoDenegadoException,
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    ServicioAutenticacionYPermisos,
    SesionInvalidaException,
    SesionUsuario,
    Usuario,
)
from src.presentacion.tiempo import hora_institucional


class AlmacenSesiones:
    """Registro en memoria de sesiones activas del servidor para validación estricta."""

    def __init__(self) -> None:
        self._sesiones: dict[str, SesionUsuario] = {}
        self._usuarios: dict[int, Usuario] = {}

    def guardar(self, sesion: SesionUsuario, usuario: Usuario | None = None) -> None:
        self._sesiones[sesion.token] = sesion
        if usuario is not None:
            self._usuarios[usuario.id] = usuario

    def obtener_sesion(self, token: str) -> SesionUsuario | None:
        return self._sesiones.get(token)

    def obtener_usuario(self, usuario_id: int) -> Usuario | None:
        return self._usuarios.get(usuario_id)

    def revocar(self, token: str) -> None:
        sesion = self._sesiones.get(token)
        if sesion is not None:
            self._sesiones[token] = ServicioAutenticacionYPermisos.cerrar_sesion(sesion)

    def limpiar(self) -> None:
        self._sesiones.clear()
        self._usuarios.clear()


def generar_token_csrf() -> str:
    """Genera o recupera el token criptográfico CSRF asociado a la sesión."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def validar_csrf() -> None:
    """Valida la presencia y autenticidad del token CSRF en métodos no seguros."""
    if not current_app.config.get("WTF_CSRF_ENABLED", True) or not current_app.config.get(
        "CSRF_ENABLED", True
    ):
        return

    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return

    token_sesion = session.get("_csrf_token")
    if not token_sesion:
        abort(400, description="Token CSRF ausente o sesión no inicializada.")

    token_recibido = (
        request.headers.get("X-CSRF-Token")
        or request.headers.get("X-CSRFToken")
        or (request.form.get("csrf_token") if request.form else None)
        or (request.form.get("_csrf_token") if request.form else None)
    )

    if not token_recibido and request.is_json and isinstance(request.json, dict):
        token_recibido = request.json.get("csrf_token") or request.json.get("_csrf_token")

    if not token_recibido or not hmac.compare_digest(str(token_sesion), str(token_recibido)):
        abort(400, description="Token CSRF inválido o ausente.")


def cargar_contexto_sesion() -> None:
    """Recupera la sesión del servidor y el usuario autenticado desde el almacén oficial."""
    token = session.get("token")
    almacen: AlmacenSesiones | None = current_app.extensions.get("almacen_sesiones")

    g.sesion_servidor = None
    g.usuario = None

    if token and almacen:
        sesion = almacen.obtener_sesion(token)
        if sesion is not None:
            g.sesion_servidor = sesion
            g.usuario = almacen.obtener_usuario(sesion.usuario_id)


def tiene_permiso(permiso: PermisoOperacion | str) -> bool:
    """Evalúa si la sesión autenticada en el servidor cuenta con el permiso solicitado."""
    sesion: SesionUsuario | None = getattr(g, "sesion_servidor", None)
    if sesion is None or not sesion.activa:
        return False

    permiso_obj: PermisoOperacion | None
    if isinstance(permiso, PermisoOperacion):
        permiso_obj = permiso
    elif isinstance(permiso, str):
        try:
            permiso_obj = PermisoOperacion(permiso)
        except ValueError:
            permiso_obj = None
    else:
        permiso_obj = None

    if permiso_obj is None:
        return False

    roles: Sequence[Rol] | None = getattr(g, "roles_disponibles", None)
    return ServicioAutenticacionYPermisos.tiene_permiso(sesion.rol, permiso_obj, roles)


def login_requerido(funcion: Callable) -> Callable:
    """Exige una sesión activa y vigente validada contra el servidor."""

    @wraps(funcion)
    def envoltura(*args, **kwargs):
        sesion: SesionUsuario | None = getattr(g, "sesion_servidor", None)
        if sesion is None or not sesion.activa:
            abort(401)

        reloj = current_app.config.get("RELOJ", hora_institucional)
        ahora = reloj()
        expira = sesion.fecha_expiracion

        if ahora.tzinfo is not None and expira.tzinfo is None:
            ahora = ahora.replace(tzinfo=None)
        elif ahora.tzinfo is None and expira.tzinfo is not None:
            expira = expira.replace(tzinfo=None)

        if ahora > expira:
            abort(401)

        usuario: Usuario | None = getattr(g, "usuario", None)
        if usuario is not None and usuario.estado != EstadoUsuario.ACTIVO:
            abort(401)

        return funcion(*args, **kwargs)

    return envoltura


def permiso_requerido(permiso: PermisoOperacion) -> Callable:
    """Exige que el usuario posea un permiso específico validado por el servidor."""

    def decorador(funcion: Callable) -> Callable:
        @wraps(funcion)
        @login_requerido
        def envoltura(*args, **kwargs):
            sesion: SesionUsuario = g.sesion_servidor
            usuario: Usuario | None = getattr(g, "usuario", None)
            roles = getattr(g, "roles_disponibles", None)
            reloj = current_app.config.get("RELOJ", hora_institucional)
            ahora = reloj()

            if sesion.fecha_expiracion.tzinfo is not None and ahora.tzinfo is None:
                ahora = ahora.replace(tzinfo=sesion.fecha_expiracion.tzinfo)
            elif sesion.fecha_expiracion.tzinfo is None and ahora.tzinfo is not None:
                ahora = ahora.replace(tzinfo=None)

            try:
                ServicioAutenticacionYPermisos.validar_permiso(
                    sesion=sesion,
                    permiso=permiso,
                    tiempo_actual=ahora,
                    usuario_actual=usuario,
                    roles=roles,
                )
            except SesionInvalidaException:
                abort(401)
            except AccesoDenegadoException:
                abort(403)

            return funcion(*args, **kwargs)

        return envoltura

    return decorador
