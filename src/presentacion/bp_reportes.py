"""Blueprints web de reportes: ficha del alumno, asistencias y boletas.

Ola 4 - Miembro 5 (PBI-12, PBI-13 y PBI-14). Las rutas solo orquestan la
petición: validan parámetros, delegan en :mod:`src.aplicacion.servicios_academico`
y renderizan o descargan el resultado. Las excepciones de dominio se traducen
a mensajes flash y respuestas HTTP 400/403/404 sin exponer trazas internas.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import cast

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    render_template,
    request,
)

from src.aplicacion.servicios_academico import (
    BoletaCalificaciones,
    ResultadoExportacionAsistencia,
    ServicioAcademico,
)
from src.aplicacion.servicios_asistencia import ServicioAsistencia
from src.dominio.calificaciones import CalificacionException
from src.dominio.exportacion_asistencia import (
    ExportacionException,
    FiltroExportacionAsistencia,
    FormatoExportacion,
)
from src.dominio.malla_curricular import NivelEducativo
from src.dominio.usuarios import (
    AccesoDenegadoException,
    PermisoOperacion,
    UsuarioException,
)
from src.presentacion.seguridad import permiso_requerido

bp_reportes = Blueprint("reportes", __name__, url_prefix="/reportes")

__all__ = ["AlmacenBoletas", "bp_reportes", "registrar_blueprints_reportes"]

_TITULOS_ERROR = {
    400: "Solicitud incorrecta",
    403: "Acceso restringido",
    404: "Recurso no encontrado",
}

_MIME_CSV = "text/csv; charset=utf-8"
_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MIME_TEXTO = "text/plain; charset=utf-8"


class AlmacenBoletas:
    """Caché de sesión para descargar boletas recién emitidas por su emisor.

    La clave incluye el identificador del operador para que ninguna boleta
    pueda descargarse desde la sesión de otro usuario.
    """

    def __init__(self) -> None:
        self._boletas: dict[tuple[int, str], BoletaCalificaciones] = {}

    def guardar(
        self, operador_id: int, boletas: Sequence[BoletaCalificaciones]
    ) -> None:
        for boleta in boletas:
            self._boletas[(operador_id, boleta.id)] = boleta

    def obtener(self, operador_id: int, boleta_id: str) -> BoletaCalificaciones | None:
        return self._boletas.get((operador_id, boleta_id))


def registrar_blueprints_reportes(app) -> None:  # noqa: ANN001
    """Registra el blueprint de reportes e inicializa su caché de boletas."""
    if app.extensions.get("blueprints_reportes_registrados"):
        return
    app.extensions.setdefault("almacen_boletas", AlmacenBoletas())
    app.register_blueprint(bp_reportes)
    app.extensions["blueprints_reportes_registrados"] = True


# ---------------------------------------------------------------------------
# Acceso a servicios y helpers de petición
# ---------------------------------------------------------------------------


def _servicio_academico() -> ServicioAcademico:
    return cast(ServicioAcademico, current_app.extensions["servicio_academico"])


def _servicio_asistencia() -> ServicioAsistencia:
    return cast(ServicioAsistencia, current_app.extensions["servicio_asistencia"])


def _almacen_boletas() -> AlmacenBoletas:
    return cast(AlmacenBoletas, current_app.extensions["almacen_boletas"])


def _operador_id() -> int:
    return g.usuario.id


def _anio_actual() -> int:
    reloj = current_app.config["RELOJ"]
    return reloj().year


def _respuesta_error(codigo: int, mensaje: str) -> tuple[str, int]:
    flash(mensaje, "error")
    return (
        render_template(
            "error.html",
            codigo=codigo,
            titulo=_TITULOS_ERROR.get(codigo, "Operación no completada"),
            mensaje=mensaje,
        ),
        codigo,
    )


def _mensaje_error(exc: Exception) -> tuple[str, int]:
    """Traduce una excepción de dominio a ``(mensaje, código HTTP)``."""
    if isinstance(exc, AccesoDenegadoException):
        return ("No tiene permisos para realizar esta operación.", 403)
    texto = str(exc).strip() or "No fue posible completar la operación."
    if "no existe" in texto.lower() or "no encontr" in texto.lower():
        return (texto, 404)
    return (texto, 400)


def _entero_formulario(nombre: str) -> int:
    crudo = (request.form.get(nombre) or "").strip()
    if not crudo:
        raise ValueError(f"Debe indicar el campo '{nombre}'.")
    try:
        return int(crudo)
    except ValueError as exc:
        raise ValueError(f"El campo '{nombre}' debe ser un número entero.") from exc


def _fecha_formulario(nombre: str) -> date:
    crudo = (request.form.get(nombre) or "").strip()
    if not crudo:
        raise ValueError(f"Debe indicar la fecha '{nombre}'.")
    try:
        return date.fromisoformat(crudo)
    except ValueError as exc:
        raise ValueError(
            f"La fecha '{nombre}' debe tener el formato AAAA-MM-DD."
        ) from exc


def _filtro_desde_formulario() -> FiltroExportacionAsistencia:
    formato_texto = (request.form.get("formato") or "CSV").strip().upper()
    formatos = {
        FormatoExportacion.CSV.value: FormatoExportacion.CSV,
        FormatoExportacion.XLSX.value: FormatoExportacion.XLSX,
    }
    if formato_texto not in formatos:
        raise ValueError("El formato solicitado no es válido. Use CSV o XLSX.")

    return FiltroExportacionAsistencia(
        fecha_desde=_fecha_formulario("fecha_desde"),
        fecha_hasta=_fecha_formulario("fecha_hasta"),
        formato=formatos[formato_texto],
        nivel=(request.form.get("nivel") or "").strip() or None,
        grado=(request.form.get("grado") or "").strip() or None,
        seccion=(request.form.get("seccion") or "").strip() or None,
    )


def _filtros_por_defecto() -> dict[str, str]:
    hoy = current_app.config["RELOJ"]().date()
    return {
        "fecha_desde": (hoy - timedelta(days=30)).isoformat(),
        "fecha_hasta": hoy.isoformat(),
        "nivel": "",
        "grado": "",
        "seccion": "",
        "formato": FormatoExportacion.CSV.value,
    }


def _render_formulario_exportacion(filtros, codigo: int = 200):  # noqa: ANN001
    return (
        render_template(
            "exportar_asistencia.html",
            filtros=filtros,
            niveles=list(NivelEducativo),
            salones=_servicio_academico().listar_salones(solo_activos=True),
        ),
        codigo,
    )


def _respuesta_descarga(
    resultado: ResultadoExportacionAsistencia,
) -> Response:
    filtro = resultado.documento.filtro
    if filtro.formato == FormatoExportacion.CSV:
        mimetype, extension = _MIME_CSV, "csv"
    else:
        mimetype, extension = _MIME_XLSX, "xlsx"

    nombre = (
        f"asistencias_{filtro.fecha_desde.isoformat()}_"
        f"{filtro.fecha_hasta.isoformat()}.{extension}"
    )
    respuesta = Response(resultado.contenido, content_type=mimetype)
    respuesta.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


def _contexto_boletas(
    boletas: Sequence[BoletaCalificaciones] = (),
) -> dict[str, object]:
    anio = _anio_actual()
    return {
        "boletas": tuple(boletas),
        "salones": _servicio_academico().listar_salones(anio_lectivo=anio),
        "periodos": _servicio_asistencia().listar_periodos(anio_lectivo=anio),
        "anio_lectivo": anio,
        "niveles": list(NivelEducativo),
    }


def _render_boletas(boletas: Sequence[BoletaCalificaciones] = ()):
    """Renderiza el módulo de boletas con su contexto completo."""
    return render_template("boletas.html", **_contexto_boletas(boletas))


# ---------------------------------------------------------------------------
# PBI-12: ficha informativa consolidada del alumno
# ---------------------------------------------------------------------------


def _render_ficha(alumno_id: int):
    try:
        ficha = _servicio_academico().construir_ficha_alumno(
            _operador_id(), alumno_id
        )
    except (UsuarioException, ValueError) as exc:
        mensaje, codigo = _mensaje_error(exc)
        return _respuesta_error(codigo, mensaje)

    return render_template(
        "ficha_alumno.html", ficha=ficha, alumno_id=alumno_id
    )


@bp_reportes.get("/ficha")
@permiso_requerido(PermisoOperacion.CONSULTAR_FICHA_ALUMNO)
def buscar_ficha():
    """Muestra el buscador o la ficha indicada por ``?alumno_id=``."""
    crudo = (request.args.get("alumno_id") or "").strip()
    if not crudo:
        return render_template("ficha_alumno.html", ficha=None, alumno_id=None)
    try:
        alumno_id = int(crudo)
    except ValueError:
        return _respuesta_error(
            400, "El identificador del alumno debe ser un número entero."
        )
    return _render_ficha(alumno_id)


@bp_reportes.get("/ficha/<int:alumno_id>")
@permiso_requerido(PermisoOperacion.CONSULTAR_FICHA_ALUMNO)
def ficha_alumno(alumno_id: int):
    """Consulta la ficha consolidada del alumno (PBI-12)."""
    return _render_ficha(alumno_id)


# ---------------------------------------------------------------------------
# PBI-13: exportación de listas de asistencia
# ---------------------------------------------------------------------------


@bp_reportes.route("/asistencias/exportar", methods=["GET", "POST"])
@permiso_requerido(PermisoOperacion.EXPORTAR_ASISTENCIAS)
def exportar_asistencia():
    """Presenta los filtros y genera la descarga CSV/XLSX (PBI-13)."""
    if request.method == "GET":
        return _render_formulario_exportacion(_filtros_por_defecto())

    try:
        filtro = _filtro_desde_formulario()
    except (ExportacionException, ValueError) as exc:
        flash(str(exc), "error")
        return _render_formulario_exportacion(request.form, codigo=400)

    try:
        resultado = _servicio_academico().exportar_asistencias(
            _operador_id(), filtro
        )
    except (ExportacionException, UsuarioException, ValueError) as exc:
        mensaje, codigo = _mensaje_error(exc)
        return _respuesta_error(codigo, mensaje)

    return _respuesta_descarga(resultado)


# ---------------------------------------------------------------------------
# PBI-14: emisión de boletas de calificaciones
# ---------------------------------------------------------------------------


@bp_reportes.get("/boletas")
@permiso_requerido(PermisoOperacion.EMITIR_BOLETAS)
def boletas():
    """Muestra los formularios de emisión individual y masiva (PBI-14)."""
    return _render_boletas()


@bp_reportes.post("/boletas/individual")
@permiso_requerido(PermisoOperacion.EMITIR_BOLETAS)
def emitir_boleta_individual():
    """Emite la boleta de un alumno para un período académico."""
    try:
        alumno_id = _entero_formulario("alumno_id")
        periodo_id = _entero_formulario("periodo_id")
    except ValueError as exc:
        return _respuesta_error(400, str(exc))

    try:
        boleta = _servicio_academico().emitir_boleta_individual(
            _operador_id(), alumno_id, periodo_id
        )
    except (CalificacionException, UsuarioException, ValueError) as exc:
        mensaje, codigo = _mensaje_error(exc)
        return _respuesta_error(codigo, mensaje)

    _almacen_boletas().guardar(_operador_id(), (boleta,))
    return _render_boletas((boleta,))


@bp_reportes.post("/boletas/salon")
@permiso_requerido(PermisoOperacion.EMITIR_BOLETAS)
def emitir_boletas_salon():
    """Emite una boleta por alumno del salón indicado."""
    try:
        anio_lectivo = _entero_formulario("anio_lectivo")
        periodo_id = _entero_formulario("periodo_id")
    except ValueError as exc:
        return _respuesta_error(400, str(exc))

    nivel = (request.form.get("nivel") or "").strip()
    grado = (request.form.get("grado") or "").strip()
    seccion = (request.form.get("seccion") or "").strip()
    if not nivel or not grado or not seccion:
        return _respuesta_error(400, "Debe indicar nivel, grado y sección del salón.")

    try:
        resultado = _servicio_academico().emitir_boletas_salon(
            _operador_id(),
            anio_lectivo=anio_lectivo,
            nivel=nivel,
            grado=grado,
            seccion=seccion,
            periodo_id=periodo_id,
        )
    except (CalificacionException, UsuarioException, ValueError) as exc:
        mensaje, codigo = _mensaje_error(exc)
        return _respuesta_error(codigo, mensaje)

    _almacen_boletas().guardar(_operador_id(), resultado.boletas)
    return _render_boletas(resultado.boletas)


@bp_reportes.get("/boletas/<boleta_id>/descargar")
@permiso_requerido(PermisoOperacion.EMITIR_BOLETAS)
def descargar_boleta(boleta_id: str):
    """Descarga en texto estructurado una boleta emitida por el operador."""
    boleta = _almacen_boletas().obtener(_operador_id(), boleta_id)
    if boleta is None:
        return _respuesta_error(
            404, "La boleta solicitada no existe o no está disponible."
        )

    contenido = _servicio_academico().exportar_boleta_texto(boleta)
    respuesta = Response(contenido, content_type=_MIME_TEXTO)
    respuesta.headers["Content-Disposition"] = (
        f'attachment; filename="boleta-{boleta.id}.txt"'
    )
    return respuesta
