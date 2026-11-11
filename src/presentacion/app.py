"""Fábrica de la aplicación Flask integrada con el dominio existente."""

import os
from datetime import date, datetime, time
from pathlib import Path

from flask import Flask, current_app, g, render_template, session

from src.aplicacion.casos_uso import ServicioAplicacionColegio
from src.dominio.usuarios import EstadoUsuario, RolUsuario
from src.infraestructura.base_datos import crear_engine, crear_fabrica_sesiones
from src.infraestructura.datos_demo import inicializar_datos_demo
from src.infraestructura.repositorios import RepositorioColegio
from src.presentacion.tiempo import hora_institucional

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_BASE_DEMO = RAIZ_PROYECTO / "instance" / "colegio_demo.db"

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


def create_app(configuracion: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "domingo-savio-demo-clave-local"),
        DATABASE_URL=os.environ.get(
            "DATABASE_URL", f"sqlite:///{RUTA_BASE_DEMO.as_posix()}"
        ),
        SEED_DEMO=True,
    )
    if configuracion:
        app.config.update(configuracion)
    app.config.setdefault("RELOJ", hora_institucional)

    engine = crear_engine(app.config["DATABASE_URL"])
    fabrica = crear_fabrica_sesiones(engine)
    app.extensions["colegio_engine"] = engine
    app.extensions["colegio_sesiones"] = fabrica

    if app.config.get("SEED_DEMO", True):
        with fabrica() as sesion:
            inicializar_datos_demo(sesion, ahora=app.config["RELOJ"]())

    _registrar_ciclo_peticion(app, fabrica)
    _registrar_filtros_y_contexto(app)
    _registrar_manejadores_error(app)

    from src.presentacion import rutas

    app.register_blueprint(rutas.bp_auth)
    app.register_blueprint(rutas.bp_principal)
    app.register_blueprint(rutas.bp_asistencia)
    app.register_blueprint(rutas.bp_justificaciones)
    app.register_blueprint(rutas.bp_usuarios)

    return app


def _registrar_ciclo_peticion(app: Flask, fabrica) -> None:
    @app.before_request
    def preparar_contexto() -> None:
        g.db_sesion = fabrica()
        g.repositorio = RepositorioColegio(g.db_sesion)
        g.servicio = ServicioAplicacionColegio(
            g.repositorio, reloj_institucional=current_app.config["RELOJ"]
        )
        g.usuario = _usuario_de_sesion(g.repositorio)

    @app.teardown_request
    def cerrar_contexto(error: BaseException | None) -> None:
        sesion = getattr(g, "db_sesion", None)
        if sesion is None:
            return
        try:
            if error is not None:
                sesion.rollback()
        finally:
            sesion.close()


def _usuario_de_sesion(repositorio: RepositorioColegio):
    usuario_id = session.get("usuario_id")
    expiracion = session.get("expiracion")
    if not usuario_id or not expiracion:
        return None

    try:
        vence = datetime.fromisoformat(expiracion)
    except ValueError:
        session.clear()
        return None

    if vence < current_app.config["RELOJ"]():
        session.clear()
        return None

    usuario = repositorio.obtener_usuario(int(usuario_id))
    if usuario is None or usuario.estado != EstadoUsuario.ACTIVO:
        session.clear()
        return None
    return usuario


def _registrar_filtros_y_contexto(app: Flask) -> None:
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
    def rol_legible(valor) -> str:
        texto = valor.value if isinstance(valor, RolUsuario) else str(valor)
        return _ROLES_LEGIBLES.get(texto, texto)

    @app.template_filter("estado_texto")
    def estado_texto(valor) -> str:
        texto = valor.value if hasattr(valor, "value") else str(valor)
        return _ESTADOS_LEGIBLES.get(texto, texto)

    @app.template_filter("estado_clase")
    def estado_clase(valor) -> str:
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
        usuario = getattr(g, "usuario", None)
        es_admin = bool(usuario and usuario.rol == RolUsuario.ADMIN)
        puede_justificar = bool(
            usuario and usuario.rol in (RolUsuario.ADMIN, RolUsuario.ADMIN_STAFF)
        )
        ahora = current_app.config["RELOJ"]()
        return {
            "usuario_actual": usuario,
            "es_admin": es_admin,
            "puede_justificar": puede_justificar,
            "hora_sistema": ahora,
            "anio_actual": ahora.year,
            "demo_password": "DemoSavio2026!",
        }


def _registrar_manejadores_error(app: Flask) -> None:
    @app.errorhandler(403)
    def acceso_denegado(error):
        return (
            render_template(
                "error.html",
                codigo=403,
                titulo="Acceso restringido",
                mensaje="Su rol no tiene permisos para realizar esta operación.",
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
