"""Blueprints web del módulo de Asistencia (PBI-01, PBI-03 y PBI-04).

Rutas delgadas: parsean la petición, delegan en ``ServicioAsistencia``
(:mod:`src.aplicacion.servicios_asistencia`) y renderizan HTML o JSON.
No contienen reglas de negocio: permisos, horarios, estados y validaciones
viven en el dominio y se reflejan aquí como respuestas HTTP 400/403/404/409.

Integración (la fábrica ``crear_app`` no se modifica en esta rama)::

    app = crear_app(config)
    registrar_modulo_asistencia(app, ServicioAsistencia(fabrica), ServicioSeguridad(fabrica))

Blueprints registrados:
- ``asistencia``: registro unificado, historial y dashboard de aforo.
- ``justificaciones``: justificaciones y períodos académicos.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Protocol

from flask import (
    Blueprint,
    Flask,
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from src.dominio.aforo import (
    AforoException,
    CierreYaEjecutadoException,
    PermisoAforoException,
)
from src.dominio.asistencia import (
    AlumnoNoEncontradoException,
    AsistenciaException,
    AsistenciaJustificadaException,
    MetodoRegistro,
    RegistroDuplicadoException,
    RolNoAutorizadoException,
)
from src.dominio.carnets import (
    CarnetException,
    CarnetNoEncontradoException,
    PermisoCarnetException,
)
from src.dominio.estados_academicos import (
    EstadoAcademicoException,
    PermisoEstadoAcademicoException,
)
from src.dominio.justificaciones import (
    AdjuntoJustificacion,
    CategoriaJustificacion,
    EstadoJustificacion,
    FiltroJustificaciones,
    JustificacionException,
    PeriodoAcademico,
    PeriodoConUsoException,
    PeriodoSolapadoException,
    PermisoJustificacionException,
    TipoPeriodo,
)
from src.dominio.usuarios import (
    AccesoDenegadoException,
    PermisoOperacion,
    Rol,
    UsuarioException,
)
from src.presentacion.seguridad import permiso_requerido

EXTENSION_SERVICIO_ASISTENCIA = "servicio_asistencia"
EXTENSION_SERVICIO_SEGURIDAD = "servicio_seguridad"

bp_asistencia = Blueprint("asistencia", __name__)
bp_justificaciones = Blueprint("justificaciones", __name__)


class ProveedorRoles(Protocol):
    def listar_roles(self) -> list[Rol]: ...


def registrar_modulo_asistencia(
    app: Flask,
    servicio_asistencia: Any,
    servicio_seguridad: ProveedorRoles | None = None,
) -> None:
    """Inyecta los servicios de aplicación y registra los blueprints del módulo."""
    app.extensions[EXTENSION_SERVICIO_ASISTENCIA] = servicio_asistencia
    if servicio_seguridad is not None:
        app.extensions[EXTENSION_SERVICIO_SEGURIDAD] = servicio_seguridad
    if bp_asistencia.name not in app.blueprints:
        app.register_blueprint(bp_asistencia)
    if bp_justificaciones.name not in app.blueprints:
        app.register_blueprint(bp_justificaciones)


def _servicio() -> Any:
    return current_app.extensions[EXTENSION_SERVICIO_ASISTENCIA]


def _operador_id() -> int:
    return g.sesion_servidor.usuario_id


@bp_asistencia.before_request
@bp_justificaciones.before_request
def _cargar_roles_personalizados() -> None:
    """Expone el catálogo de roles (incluye personalizados) a ``permiso_requerido``."""
    if getattr(g, "roles_disponibles", None) is not None:
        return
    proveedor: ProveedorRoles | None = current_app.extensions.get(EXTENSION_SERVICIO_SEGURIDAD)
    if proveedor is not None and getattr(g, "sesion_servidor", None) is not None:
        g.roles_disponibles = proveedor.listar_roles()


# ---------------------------------------------------------------------------
# Traducción de errores de dominio a HTTP (sin stack traces ni datos ajenos)
# ---------------------------------------------------------------------------


class SolicitudInvalidaError(Exception):
    """Datos de formulario o query string con formato inválido."""


ERRORES_DOMINIO: tuple[type[Exception], ...] = (
    SolicitudInvalidaError,
    AsistenciaException,
    AforoException,
    JustificacionException,
    CarnetException,
    EstadoAcademicoException,
    UsuarioException,
    ValueError,
)

_ERRORES_403 = (
    AccesoDenegadoException,
    PermisoAforoException,
    PermisoJustificacionException,
    PermisoCarnetException,
    PermisoEstadoAcademicoException,
    RolNoAutorizadoException,
)
_ERRORES_409 = (
    RegistroDuplicadoException,
    CierreYaEjecutadoException,
    PeriodoSolapadoException,
    PeriodoConUsoException,
    AsistenciaJustificadaException,
)
_ERRORES_404 = (AlumnoNoEncontradoException, CarnetNoEncontradoException)
# Validaciones de entrada y reglas de dominio incumplidas (todo salvo ValueError genérico).
_ERRORES_400 = ERRORES_DOMINIO[:-1]

MENSAJE_NO_ENCONTRADO = "El recurso solicitado no existe."
MENSAJE_PROHIBIDO = "Su rol o cuenta no tiene permisos para realizar esta operación."


@dataclass(frozen=True)
class ErrorWeb:
    codigo: int
    mensaje: str


def traducir_error(error: Exception) -> ErrorWeb:
    """Clasifica una excepción de dominio/aplicación en un código HTTP y mensaje seguro."""
    if isinstance(error, _ERRORES_403):
        return ErrorWeb(403, MENSAJE_PROHIBIDO)
    if isinstance(error, _ERRORES_409):
        return ErrorWeb(409, str(error))
    if isinstance(error, _ERRORES_404):
        return ErrorWeb(404, str(error))
    if isinstance(error, _ERRORES_400):
        return ErrorWeb(400, str(error))
    # ValueError de la capa de aplicación: entidad inexistente. No se expone el id.
    return ErrorWeb(404, MENSAJE_NO_ENCONTRADO)


def _respuesta_json_error(error: Exception) -> tuple[Response, int]:
    web = traducir_error(error)
    return jsonify({"ok": False, "error": web.mensaje}), web.codigo


def _pagina_con_error(error: Exception, renderizar: Callable[[], str]) -> tuple[str, int]:
    """Muestra el mensaje como flash y re-renderiza la página con el código HTTP."""
    web = traducir_error(error)
    flash(web.mensaje, "error")
    return renderizar(), web.codigo


# ---------------------------------------------------------------------------
# Parseo de entrada (sin reglas de negocio)
# ---------------------------------------------------------------------------


def _datos() -> Mapping[str, Any]:
    if request.is_json:
        cuerpo = request.get_json(silent=True)
        return cuerpo if isinstance(cuerpo, dict) else {}
    return request.form


def _texto(datos: Mapping[str, Any], campo: str) -> str | None:
    valor = datos.get(campo)
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _obligatorio(datos: Mapping[str, Any], campo: str, etiqueta: str) -> str:
    valor = _texto(datos, campo)
    if valor is None:
        raise SolicitudInvalidaError(f"El campo «{etiqueta}» es obligatorio.")
    return valor


def _entero(valor: str | None, etiqueta: str) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except ValueError as error:
        raise SolicitudInvalidaError(f"«{etiqueta}» debe ser un número entero.") from error


def _fecha(valor: str | None, etiqueta: str) -> date | None:
    if valor is None:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError as error:
        raise SolicitudInvalidaError(f"«{etiqueta}» debe tener formato AAAA-MM-DD.") from error


def _hora(valor: str, etiqueta: str) -> time:
    try:
        return time.fromisoformat(valor)
    except ValueError as error:
        raise SolicitudInvalidaError(f"«{etiqueta}» debe tener formato HH:MM.") from error


def _enum(enum_cls: Any, valor: str | None, etiqueta: str) -> Any:
    if valor is None:
        return None
    try:
        return enum_cls(valor.upper())
    except ValueError as error:
        raise SolicitudInvalidaError(f"«{etiqueta}» no es una opción válida.") from error


def _parametros_registro(datos: Mapping[str, Any]) -> dict[str, Any]:
    """Traduce el formulario unificado a argumentos de ``registrar_asistencia``."""
    metodo = _enum(MetodoRegistro, _obligatorio(datos, "metodo", "Método"), "Método")
    parametros: dict[str, Any] = {
        "metodo": metodo,
        "motivo_correccion": _texto(datos, "motivo_correccion"),
    }
    alumno_id = _entero(_texto(datos, "alumno_id"), "Alumno")
    if metodo == MetodoRegistro.CARNET:
        parametros["codigo_carnet"] = _obligatorio(datos, "valor", "Código de carnet")
    elif metodo == MetodoRegistro.MANUAL_DNI:
        parametros["dni_manual"] = _obligatorio(datos, "valor", "DNI")
    elif alumno_id is not None:
        parametros["alumno_id"] = alumno_id
    else:
        parametros["criterio_busqueda"] = _obligatorio(datos, "valor", "Búsqueda")
    return parametros


def _adjuntos_de_formulario() -> tuple[AdjuntoJustificacion, ...]:
    adjuntos: list[AdjuntoJustificacion] = []
    for archivo in request.files.getlist("adjuntos"):
        if not archivo or not archivo.filename:
            continue
        contenido = archivo.read()
        adjuntos.append(AdjuntoJustificacion(nombre=archivo.filename, tamano_bytes=len(contenido)))
    return tuple(adjuntos)


def _filtro_justificaciones() -> FiltroJustificaciones:
    args = request.args
    return FiltroJustificaciones(
        nivel=_texto(args, "nivel"),
        grado=_texto(args, "grado"),
        seccion=_texto(args, "seccion"),
        alumno_id=_entero(_texto(args, "alumno_id"), "Alumno"),
        categoria=_enum(CategoriaJustificacion, _texto(args, "categoria"), "Categoría"),
        estado=_enum(EstadoJustificacion, _texto(args, "estado"), "Estado"),
        fecha_desde=_fecha(_texto(args, "fecha_desde"), "Desde"),
        fecha_hasta=_fecha(_texto(args, "fecha_hasta"), "Hasta"),
    )


def _filtros_aforo() -> dict[str, Any]:
    args = request.args
    return {
        "fecha_escolar": _fecha(_texto(args, "fecha"), "Fecha"),
        "nivel": _texto(args, "nivel"),
        "grado": _texto(args, "grado"),
        "seccion": _texto(args, "seccion"),
    }


def _metricas_a_json(metricas: Any) -> dict[str, Any]:
    return {
        "total_matriculados": metricas.total_matriculados,
        "presentes": metricas.presentes,
        "tardanzas": metricas.tardanzas,
        "ausentes": metricas.ausentes,
        "justificados": metricas.justificados,
        "pendientes": metricas.pendientes,
        "porcentaje_asistencia": metricas.porcentaje_asistencia,
        "aforo_actual_plantel": metricas.aforo_actual_plantel,
        "fecha_escolar": metricas.fecha_escolar.isoformat(),
        "hora_consulta": metricas.hora_consulta.isoformat(),
        "hora_cierre_oficial": metricas.hora_cierre_oficial.isoformat(),
    }


# ---------------------------------------------------------------------------
# PBI-01: Registro unificado de asistencia
# ---------------------------------------------------------------------------


def _render_asistencia(historial: list[Any] | None = None) -> str:
    return render_template(
        "asistencia.html",
        metodos=list(MetodoRegistro),
        historial=historial,
        filtros=request.args,
    )


@bp_asistencia.get("/asistencia")
@permiso_requerido(PermisoOperacion.REGISTRAR_ASISTENCIA)
def ver_asistencia():
    return _render_asistencia()


@bp_asistencia.post("/asistencia/registrar")
@permiso_requerido(PermisoOperacion.REGISTRAR_ASISTENCIA)
def registrar_asistencia():
    try:
        parametros = _parametros_registro(_datos())
        resultado = _servicio().registrar_asistencia(_operador_id(), **parametros)
    except ERRORES_DOMINIO as error:
        if request.is_json:
            return _respuesta_json_error(error)
        return _pagina_con_error(error, _render_asistencia)

    asistencia = resultado.asistencia
    if request.is_json:
        return (
            jsonify(
                {
                    "ok": True,
                    "asistencia": {
                        "id": asistencia.id,
                        "alumno_id": asistencia.alumno_id,
                        "estado": asistencia.estado.value,
                        "hora_efectiva": asistencia.hora_efectiva.isoformat(),
                        "minutos_tardanza": asistencia.minutos_tardanza,
                        "nivel": asistencia.nivel,
                        "grado": asistencia.grado,
                        "seccion": asistencia.seccion,
                    },
                }
            ),
            201,
        )
    flash(
        f"Asistencia registrada: {asistencia.estado.value} a las "
        f"{asistencia.hora_efectiva.strftime('%H:%M')}.",
        "success",
    )
    return redirect(url_for("asistencia.ver_asistencia"))


@bp_asistencia.get("/asistencia/historial")
@permiso_requerido(PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA)
def historial_asistencia():
    try:
        args = request.args
        historial = _servicio().consultar_historial_modificaciones(
            _operador_id(),
            fecha_desde=_fecha(_texto(args, "fecha_desde"), "Desde"),
            fecha_hasta=_fecha(_texto(args, "fecha_hasta"), "Hasta"),
            alumno_id=_entero(_texto(args, "alumno_id"), "Alumno"),
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, lambda: _render_asistencia(historial=[]))
    return _render_asistencia(historial=historial)


# ---------------------------------------------------------------------------
# PBI-03: Dashboard de aforo y cierre de jornada
# ---------------------------------------------------------------------------


def _render_aforo(metricas: Any = None, detalle: Any = None) -> str:
    return render_template("aforo.html", metricas=metricas, detalle=detalle, filtros=request.args)


@bp_asistencia.get("/aforo")
@permiso_requerido(PermisoOperacion.CONSULTAR_DASHBOARD_AFORO)
def aforo():
    try:
        filtros = _filtros_aforo()
        servicio = _servicio()
        metricas = servicio.consultar_metricas_aforo(_operador_id(), **filtros)
        detalle = None
        if filtros["nivel"] and filtros["grado"] and filtros["seccion"]:
            detalle = servicio.obtener_detalle_salon(
                _operador_id(),
                nivel=filtros["nivel"],
                grado=filtros["grado"],
                seccion=filtros["seccion"],
                fecha_escolar=filtros["fecha_escolar"],
            )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_aforo)
    return _render_aforo(metricas, detalle)


@bp_asistencia.get("/aforo/metricas")
@permiso_requerido(PermisoOperacion.CONSULTAR_DASHBOARD_AFORO)
def metricas_aforo():
    try:
        metricas = _servicio().consultar_metricas_aforo(_operador_id(), **_filtros_aforo())
    except ERRORES_DOMINIO as error:
        return _respuesta_json_error(error)
    return jsonify({"ok": True, "metricas": _metricas_a_json(metricas)})


@bp_asistencia.post("/aforo/hora-cierre")
@permiso_requerido(PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA)
def configurar_hora_cierre():
    try:
        nueva = _hora(_obligatorio(request.form, "hora_cierre", "Hora de cierre"), "Hora de cierre")
        hora = _servicio().configurar_hora_cierre(_operador_id(), nueva)
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_aforo)
    flash(f"Hora oficial de cierre actualizada a las {hora.strftime('%H:%M')}.", "success")
    return redirect(url_for("asistencia.aforo"))


@bp_asistencia.post("/aforo/cierre")
@permiso_requerido(PermisoOperacion.EJECUTAR_CIERRE_ASISTENCIA)
def ejecutar_cierre():
    try:
        evento = _servicio().ejecutar_cierre_diario(
            _operador_id(),
            fecha_escolar=_fecha(_texto(request.form, "fecha"), "Fecha"),
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_aforo)
    flash(
        f"Cierre de jornada ejecutado: {evento.total_ausentes_marcados} alumno(s) "
        "marcados como ausentes.",
        "modal_success",
    )
    return redirect(url_for("asistencia.aforo"))


# ---------------------------------------------------------------------------
# PBI-04: Justificaciones
# ---------------------------------------------------------------------------


def _render_justificaciones(justificaciones: list[Any] | None = None) -> str:
    return render_template(
        "justificaciones.html",
        justificaciones=justificaciones or [],
        categorias=list(CategoriaJustificacion),
        estados=list(EstadoJustificacion),
        filtros=request.args,
    )


@bp_justificaciones.get("/justificaciones")
@permiso_requerido(PermisoOperacion.GESTIONAR_JUSTIFICACIONES)
def ver_justificaciones():
    try:
        justificaciones = _servicio().consultar_justificaciones(
            _operador_id(), _filtro_justificaciones()
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_justificaciones)
    return _render_justificaciones(justificaciones)


@bp_justificaciones.post("/justificaciones")
@permiso_requerido(PermisoOperacion.GESTIONAR_JUSTIFICACIONES)
def registrar_justificacion():
    formulario = request.form
    try:
        resultado = _servicio().registrar_justificacion(
            _operador_id(),
            asistencia_id=_obligatorio(formulario, "asistencia_id", "Asistencia"),
            categoria=_enum(
                CategoriaJustificacion,
                _obligatorio(formulario, "categoria", "Categoría"),
                "Categoría",
            ),
            motivo=_obligatorio(formulario, "motivo", "Motivo"),
            periodo_id=_entero(_texto(formulario, "periodo_id"), "Período"),
            adjuntos=_adjuntos_de_formulario(),
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_justificaciones)
    flash(
        f"Justificación aprobada. La asistencia quedó como "
        f"{resultado.asistencia_actualizada.estado.value}.",
        "modal_success",
    )
    return redirect(url_for("justificaciones.ver_justificaciones"))


@bp_justificaciones.post("/justificaciones/<justificacion_id>/anular")
@permiso_requerido(PermisoOperacion.GESTIONAR_JUSTIFICACIONES)
def anular_justificacion(justificacion_id: str):
    try:
        restaurada = _servicio().anular_justificacion(
            _operador_id(), justificacion_id=justificacion_id
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_justificaciones)
    flash(f"Justificación anulada. La asistencia volvió a {restaurada.estado.value}.", "success")
    return redirect(url_for("justificaciones.ver_justificaciones"))


# ---------------------------------------------------------------------------
# PBI-04: Períodos académicos
# ---------------------------------------------------------------------------


def _render_periodos(periodos: list[Any] | None = None) -> str:
    return render_template(
        "periodos.html", periodos=periodos or [], tipos=list(TipoPeriodo), filtros=request.args
    )


@bp_justificaciones.get("/periodos")
@permiso_requerido(PermisoOperacion.ADMINISTRAR_PERIODOS)
def ver_periodos():
    try:
        periodos = _servicio().listar_periodos(
            anio_lectivo=_entero(_texto(request.args, "anio_lectivo"), "Año lectivo")
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_periodos)
    return _render_periodos(periodos)


@bp_justificaciones.post("/periodos")
@permiso_requerido(PermisoOperacion.ADMINISTRAR_PERIODOS)
def crear_periodo():
    formulario = request.form
    try:
        periodo = PeriodoAcademico(
            id=0,
            nombre=_obligatorio(formulario, "nombre", "Nombre"),
            fecha_inicio=_fecha(_obligatorio(formulario, "fecha_inicio", "Inicio"), "Inicio"),
            fecha_fin=_fecha(_obligatorio(formulario, "fecha_fin", "Fin"), "Fin"),
            anio_lectivo=_entero(
                _obligatorio(formulario, "anio_lectivo", "Año lectivo"), "Año lectivo"
            ),
            tipo_periodo=_enum(
                TipoPeriodo, _obligatorio(formulario, "tipo_periodo", "Tipo"), "Tipo"
            ),
            orden=_entero(_obligatorio(formulario, "orden", "Orden"), "Orden"),
            fecha_limite_notas=_fecha(
                _texto(formulario, "fecha_limite_notas"), "Fecha límite de notas"
            ),
        )
        creado = _servicio().crear_periodo(_operador_id(), periodo)
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_periodos)
    flash(f"Período «{creado.nombre}» creado correctamente.", "success")
    return redirect(url_for("justificaciones.ver_periodos"))


@bp_justificaciones.post("/periodos/<int:periodo_id>/estado")
@permiso_requerido(PermisoOperacion.ADMINISTRAR_PERIODOS)
def cambiar_estado_periodo(periodo_id: int):
    cerrar = _texto(request.form, "cerrado") in {"1", "true", "on"}
    try:
        periodo = _servicio().cambiar_estado_periodo(_operador_id(), periodo_id, cerrado=cerrar)
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_periodos)
    estado = "cerrado" if periodo.cerrado else "reabierto"
    flash(f"Período «{periodo.nombre}» {estado}.", "success")
    return redirect(url_for("justificaciones.ver_periodos"))


@bp_justificaciones.post("/periodos/<int:periodo_id>/fecha-limite")
@permiso_requerido(PermisoOperacion.ADMINISTRAR_PERIODOS)
def prorrogar_fecha_limite(periodo_id: int):
    try:
        nueva = _fecha(
            _obligatorio(request.form, "fecha_limite_notas", "Fecha límite de notas"),
            "Fecha límite de notas",
        )
        periodo = _servicio().modificar_periodo(
            _operador_id(), periodo_id, fecha_limite_notas=nueva
        )
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_periodos)
    flash(
        f"Fecha límite de notas de «{periodo.nombre}» actualizada al "
        f"{periodo.fecha_limite_notas.strftime('%d/%m/%Y')}.",
        "success",
    )
    return redirect(url_for("justificaciones.ver_periodos"))


@bp_justificaciones.post("/periodos/<int:periodo_id>/eliminar")
@permiso_requerido(PermisoOperacion.ADMINISTRAR_PERIODOS)
def eliminar_periodo(periodo_id: int):
    try:
        _servicio().eliminar_periodo(_operador_id(), periodo_id)
    except ERRORES_DOMINIO as error:
        return _pagina_con_error(error, _render_periodos)
    flash("Período eliminado.", "success")
    return redirect(url_for("justificaciones.ver_periodos"))
