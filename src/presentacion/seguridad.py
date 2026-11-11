"""Decoradores de protección de rutas basados en la sesión y el rol."""

from functools import wraps

from flask import abort, flash, g, redirect, request, url_for

from src.dominio.usuarios import RolUsuario


def login_requerido(funcion):
    """Exige una sesión vigente; conserva el destino original."""

    @wraps(funcion)
    def envoltura(*args, **kwargs):
        if getattr(g, "usuario", None) is None:
            flash("Debe iniciar sesión para acceder a esta sección.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return funcion(*args, **kwargs)

    return envoltura


def roles_requeridos(*roles_permitidos) -> callable:
    """Exige que el rol autenticado pertenezca a la lista indicada."""
    permitidos = {
        rol.value if isinstance(rol, RolUsuario) else str(rol) for rol in roles_permitidos
    }

    def decorador(funcion):
        @wraps(funcion)
        @login_requerido
        def envoltura(*args, **kwargs):
            usuario = getattr(g, "usuario", None)
            if usuario is None or usuario.rol.value not in permitidos:
                abort(403)
            return funcion(*args, **kwargs)

        return envoltura

    return decorador
