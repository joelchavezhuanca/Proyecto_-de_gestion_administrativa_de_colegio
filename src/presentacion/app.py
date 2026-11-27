"""Fábrica de la aplicación Flask limpia para el Colegio Domingo Savio S.A.C.

Configura:
- Application Factory crear_app(config=None).
- Obligatoriedad estricta de SECRET_KEY.
- Cookies de sesión seguras (HttpOnly, SameSite='Lax').
- Persistencia SQLAlchemy y servicios de aplicación inyectados en ``app.extensions``.
- Registro de los cinco blueprints web de la Ola 4.
- Manejo defensivo de errores HTTP 400, 401, 403, 404 y 500 sin fuga de información sensible.
- Filtros de plantilla y funciones globales seguras (safe_url_for, tiene_permiso, csrf_token).
"""

import importlib
import os
from datetime import date, datetime, time
from pathlib import Path

from flask import Blueprint, Flask, current_app, g, render_template, url_for

from src.aplicacion.servicios_academico import ServicioAcademico
from src.aplicacion.servicios_asistencia import ServicioAsistencia
from src.aplicacion.servicios_seguridad import ServicioSeguridad
from src.dominio.usuarios import RolUsuario
from src.infraestructura.base_datos import crear_motor, crear_session_factory
from src.presentacion.seguridad import (
    AlmacenSesiones,
    cargar_contexto_sesion,
    generar_token_csrf,
    tiene_permiso,
    validar_csrf,
)
from src.presentacion.tiempo import hora_institucional

RAIZ_PRESENTACION = Path(__file__).resolve().parent

#: Blueprints web de la Ola 4 que la fábrica integra cuando están disponibles.
MODULOS_BLUEPRINTS = (
    "bp_seguridad",
    "bp_asistencia",
    "bp_alumnos",
    "bp_academico",
    "bp_reportes",
)

_ROLES_LEGIBLES = {
    "ADMIN": "Administrador",
    "COORDINADOR": "Coordinador",
    "ADMIN_STAFF": "Personal administrativo",
}

_ESTADOS_LEGIBLES = {
    "PUNTUAL": "Puntual",
    "TARDANZA": "Tardanza",
    "AUSENTE": "Ausente",
    "JUSTIFICADO": "Justificado",
    "PENDIENTE": "Pendiente",
    "ACTIVO": "Activa",
    "INACTIVO": "Inactiva",
    "APROBADA": "Aprobada",
    "RECHAZADA": "Anulada",
}


def crear_app(config: dict | None = None) -> Flask:
    """Crea y configura la instancia de la aplicación Flask."""
    app = Flask(
        __name__,
        template_folder=str(RAIZ_PRESENTACION / "templates"),
        static_folder=str(RAIZ_PRESENTACION / "static"),
    )

    # 1. Configuración de seguridad por defecto
    secret_key = os.environ.get("SECRET_KEY")
    if config and "SECRET_KEY" in config:
        secret_key = config["SECRET_KEY"]

    if not secret_key:
        raise ValueError(
            "SECRET_KEY es obligatoria. Configure la variable de entorno SECRET_KEY "
            "o pase una clave en la configuración de la aplicación."
        )

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        WTF_CSRF_ENABLED=True,
        CSRF_ENABLED=True,
    )

    if config:
        app.config.update(config)

    app.config.setdefault("RELOJ", hora_institucional)

    # 2. Persistencia, almacén de sesiones y servicios de aplicación
    app.extensions.setdefault("almacen_sesiones", AlmacenSesiones())
    _configurar_persistencia(app)
    _configurar_servicios(app)

    # 3. Blueprints de la Ola 4
    _registrar_blueprints(app)

    # 4. Ciclo de petición, filtros y manejo de errores
    _registrar_ciclo_peticion(app)
    _registrar_filtros_y_contexto(app)
    _registrar_manejadores_error(app)

    return app


# Alias de compatibilidad
create_app = crear_app


def _configurar_persistencia(app: Flask) -> None:
    """Inyecta una fábrica de sesiones SQLAlchemy en config y extensions.

    El orden de resolución es: ``SESSION_FACTORY`` explícita, ``DATABASE_URL``
    de la configuración y variable de entorno ``DATABASE_URL``. Si no hay
    configuración explícita, la fábrica queda sin definir y los servicios se
    crean de forma perezosa cuando el despliegue la proporcione.
    """
    fabrica = app.config.get("SESSION_FACTORY") or app.config.get("session_factory")
    if fabrica is None:
        url = app.config.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
        if url:
            motor = crear_motor(url)
            app.extensions["motor_bd"] = motor
            fabrica = crear_session_factory(motor)
            app.config["DATABASE_URL"] = url

    if fabrica is not None:
        app.config["SESSION_FACTORY"] = fabrica
        app.extensions["session_factory"] = fabrica


def _configurar_servicios(app: Flask) -> None:
    """Construye una sola vez los servicios de aplicación de la Ola 4."""
    fabrica = app.extensions.get("session_factory")
    if fabrica is None:
        return

    reloj = app.config["RELOJ"]
    if "servicio_seguridad" not in app.extensions:
        app.extensions["servicio_seguridad"] = ServicioSeguridad(fabrica, reloj=reloj)
    if "servicio_academico" not in app.extensions:
        app.extensions["servicio_academico"] = ServicioAcademico(fabrica, reloj=reloj)
    if "servicio_asistencia" not in app.extensions:
        app.extensions["servicio_asistencia"] = ServicioAsistencia(fabrica, reloj=reloj)


def _registrar_blueprints(app: Flask) -> None:
    """Registra los blueprints web disponibles sin acoplar módulos ausentes."""
    for nombre_modulo in MODULOS_BLUEPRINTS:
        try:
            modulo = importlib.import_module(f"src.presentacion.{nombre_modulo}")
        except ModuleNotFoundError as exc:
            if exc.name != f"src.presentacion.{nombre_modulo}":
                raise
            continue

        registrador = getattr(
            modulo,
            f"registrar_blueprints_{nombre_modulo.removeprefix('bp_')}",
            None,
        )
        if callable(registrador):
            registrador(app)
            continue

        for atributo in vars(modulo).values():
            if isinstance(atributo, Blueprint) and atributo.name not in app.blueprints:
                app.register_blueprint(atributo)

    # El blueprint de seguridad registra su propia carga de roles, que asume
    # una fábrica de sesiones disponible. La fábrica centralizada de esta app
    # reemplaza ese hook por uno tolerante a despliegues sin BD configurada.
    funciones = app.before_request_funcs.get(None)
    if funciones:
        app.before_request_funcs[None] = [
            funcion
            for funcion in funciones
            if getattr(funcion, "__name__", "") != "cargar_roles_disponibles"
        ]


def _registrar_ciclo_peticion(app: Flask) -> None:
    @app.before_request
    def antes_de_peticion() -> None:
        validar_csrf()
        cargar_contexto_sesion()
        _cargar_roles_disponibles()


def _cargar_roles_disponibles() -> None:
    """Carga los roles vigentes para habilitar roles personalizados en el RBAC.

    Si la aplicación no tiene una fábrica de servicios configurada (por
    ejemplo, una app creada solo con ``SECRET_KEY`` para pruebas unitarias),
    la lista queda en ``None``: el RBAC deniega por defecto sin romper la
    petición. Los roles base siguen resolviéndose con la matriz del dominio.
    """
    g.roles_disponibles = None
    if getattr(g, "sesion_servidor", None) is None:
        return

    servicio = current_app.extensions.get("servicio_seguridad")
    if not isinstance(servicio, ServicioSeguridad):
        return

    try:
        g.roles_disponibles = servicio.listar_roles()
    except Exception:  # noqa: BLE001 - fail-closed si la BD aún no está lista
        g.roles_disponibles = None


def _registrar_filtros_y_contexto(app: Flask) -> None:
    def safe_url_for(endpoint: str, fallback: str = "#", **kwargs) -> str:
        """Genera una URL para el endpoint o retorna un fallback seguro si no existe."""
        try:
            return url_for(endpoint, **kwargs)
        except Exception:
            return fallback

    app.jinja_env.globals["safe_url_for"] = safe_url_for
    app.jinja_env.globals["csrf_token"] = generar_token_csrf
    app.jinja_env.globals["tiene_permiso"] = tiene_permiso

    @app.template_filter("fecha_corta")
    def fecha_corta(valor: date | None) -> str:
        return valor.strftime("%d/%m/%Y") if valor else "—"

    @app.template_filter("hora_corta")
    def hora_corta(valor: time | datetime | None) -> str:
        if valor is None:
            return "—"
        formato = "%H:%M:%S" if isinstance(valor, datetime) else "%H:%M"
        return valor.strftime(formato)

    @app.template_filter("rol_legible")
    def rol_legible(valor: RolUsuario | str) -> str:
        texto = valor.value if isinstance(valor, RolUsuario) else str(valor)
        return _ROLES_LEGIBLES.get(texto, texto)

    @app.template_filter("estado_texto")
    def estado_texto(valor: object) -> str:
        texto = valor.value if hasattr(valor, "value") else str(valor)
        return _ESTADOS_LEGIBLES.get(texto, texto)

    @app.template_filter("estado_clase")
    def estado_clase(valor: object) -> str:
        texto = valor.value if hasattr(valor, "value") else str(valor)
        return {
            "PUNTUAL": "ok",
            "TARDANZA": "warn",
            "AUSENTE": "danger",
            "JUSTIFICADO": "info",
            "PENDIENTE": "neutral",
            "ACTIVO": "ok",
            "INACTIVO": "danger",
            "APROBADA": "ok",
            "RECHAZADA": "danger",
        }.get(texto, "neutral")

    @app.context_processor
    def inyectar_contexto() -> dict[str, object]:
        reloj = current_app.config.get("RELOJ", hora_institucional)
        ahora = reloj()
        return {
            "usuario_actual": getattr(g, "usuario", None),
            "hora_sistema": ahora,
            "anio_actual": ahora.year,
        }


def _registrar_manejadores_error(app: Flask) -> None:
    @app.errorhandler(400)
    def peticion_incorrecta(error):
        mensaje = getattr(error, "description", "La solicitud no pudo ser procesada.")
        return (
            render_template(
                "error.html",
                codigo=400,
                titulo="Solicitud incorrecta",
                mensaje=mensaje,
            ),
            400,
        )

    @app.errorhandler(401)
    def no_autorizado(error):
        return (
            render_template(
                "error.html",
                codigo=401,
                titulo="No autorizado",
                mensaje="Debe iniciar sesión para acceder a este recurso.",
            ),
            401,
        )

    @app.errorhandler(403)
    def acceso_denegado(error):
        return (
            render_template(
                "error.html",
                codigo=403,
                titulo="Acceso restringido",
                mensaje="Su rol o cuenta no tiene permisos para realizar esta operación.",
            ),
            403,
        )

    @app.errorhandler(404)
    def no_encontrado(error):
        return (
            render_template(
                "error.html",
                codigo=404,
                titulo="Página no encontrada",
                mensaje="La dirección solicitada no existe en el sistema.",
            ),
            404,
        )

    @app.errorhandler(500)
    def error_interno(error):
        return (
            render_template(
                "error.html",
                codigo=500,
                titulo="Error interno",
                mensaje="No fue posible completar la operación. Intente nuevamente.",
            ),
            500,
        )
