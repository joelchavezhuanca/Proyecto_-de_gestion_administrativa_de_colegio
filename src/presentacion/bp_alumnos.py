"""Blueprint Flask para gestión de alumnos: Matrícula, Carnets, Estados y Pagos (Ola 4).

Reglas de diseño:
- Cero lógica de negocio en rutas: únicamente parseo HTTP -> ServicioAcademico -> respuesta.
- Protección estricta con @login_requerido, @permiso_requerido y CSRF (seguridad.py).
- Traducción limpia de excepciones de dominio a flash + códigos HTTP 400/403/404/409.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy.exc import IntegrityError

from src.aplicacion.servicios_academico import ServicioAcademico
from src.dominio.asistencia import DniInvalidoException
from src.dominio.carnets import (
    CarnetEscolar,
    CarnetException,
    CarnetNoEncontradoException,
    CarnetYaAnuladoException,
    MotivoAnulacionCarnet,
)
from src.dominio.estados_academicos import (
    EstadoAcademico,
    EstadoAcademicoException,
    HistorialEstadoAlumno,
    TransicionEstadoInvalidaException,
)
from src.dominio.matricula import (
    Apoderado,
    FichaMatricula,
    MatriculaDuplicadaException,
    MatriculaException,
    SalonSinVacantesException,
)
from src.dominio.pagos import PagosException
from src.dominio.usuarios import PermisoOperacion
from src.infraestructura.repositorios import (
    RepositorioCarnets,
    RepositorioEstadosAcademicos,
    RepositorioMatricula,
    RepositorioRoles,
)
from src.presentacion.seguridad import login_requerido, permiso_requerido, tiene_permiso
from src.presentacion.tiempo import hora_institucional

bp_alumnos = Blueprint("alumnos", __name__)


def registrar_blueprints_alumnos(app: Flask) -> None:
    """Registra el blueprint de alumnos de forma idempotente en la aplicación Flask."""
    if bp_alumnos.name not in app.blueprints:
        app.register_blueprint(bp_alumnos)


@bp_alumnos.before_request
def _cargar_roles_para_rbac() -> None:
    """Asegura que los roles personalizados en BD estén disponibles para @permiso_requerido."""
    if (
        getattr(g, "roles_disponibles", None) is None
        and "session_factory" in current_app.extensions
    ):
        session_factory = current_app.extensions["session_factory"]
        with session_factory() as session:
            g.roles_disponibles = RepositorioRoles(session).listar()


# ---------------------------------------------------------------------------
# Helpers de acceso a servicios y parseo defensivo de requests
# ---------------------------------------------------------------------------


def _obtener_session_factory():
    return current_app.extensions["session_factory"]


def _obtener_servicio() -> ServicioAcademico:
    servicio = current_app.extensions.get("servicio_academico")
    if servicio is not None:
        return servicio
    reloj = current_app.config.get("RELOJ", hora_institucional)
    return ServicioAcademico(_obtener_session_factory(), reloj=reloj)


def _operador_id() -> int:
    return int(g.sesion_servidor.usuario_id)


def _parsear_entero(raw: str | None, campo: str) -> int:
    texto = (raw or "").strip()
    try:
        return int(texto)
    except ValueError as error:
        raise ValueError(f"El campo '{campo}' debe ser un número entero válido.") from error


def _parsear_entero_opcional(raw: str | None) -> int | None:
    texto = (raw or "").strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def _parsear_fecha(raw: str | None, campo: str) -> date:
    texto = (raw or "").strip()
    try:
        return date.fromisoformat(texto)
    except ValueError as error:
        raise ValueError(
            f"El campo '{campo}' debe tener formato de fecha válido (AAAA-MM-DD)."
        ) from error


def _parsear_fecha_opcional(raw: str | None, campo: str) -> date | None:
    texto = (raw or "").strip()
    if not texto:
        return None
    return _parsear_fecha(texto, campo)


def _parsear_decimal(raw: str | None, campo: str) -> Decimal:
    texto = (raw or "").strip()
    try:
        return Decimal(texto)
    except InvalidOperation as error:
        raise ValueError(f"El campo '{campo}' debe ser un monto numérico válido.") from error


def _es_no_encontrado(error: Exception) -> bool:
    return "no existe" in str(error).lower()


def _listar_alumnos(salon_id: int | None = None) -> list[FichaMatricula]:
    with _obtener_session_factory()() as session:
        repo = RepositorioMatricula(session)
        if salon_id is not None:
            return repo.listar_por_salon(salon_id)
        return repo.listar_todas()


def _listar_carnets_alumno(alumno_id: int | None) -> list[CarnetEscolar]:
    if alumno_id is None:
        return []
    with _obtener_session_factory()() as session:
        return RepositorioCarnets(session).listar_por_alumno(alumno_id)


def _listar_historial_estados(alumno_id: int | None) -> list[HistorialEstadoAlumno]:
    if alumno_id is None:
        return []
    with _obtener_session_factory()() as session:
        return RepositorioEstadosAcademicos(session).listar_historial_alumno(alumno_id)


# ---------------------------------------------------------------------------
# 1. Matrícula Digital + Apoderados (PBI-05)
# ---------------------------------------------------------------------------


def _render_matricula(
    status: int = 200,
    *,
    salon_id_filtro: int | None = None,
) -> tuple[str, int]:
    servicio = _obtener_servicio()
    salones = servicio.listar_salones(solo_activos=True)
    alumnos = _listar_alumnos(salon_id=salon_id_filtro)
    return (
        render_template(
            "matricula.html",
            salones=salones,
            alumnos=alumnos,
            salon_id_filtro=salon_id_filtro,
        ),
        status,
    )


def _construir_apoderados_desde_form() -> list[Apoderado]:
    apoderados = [
        Apoderado(
            id=0,
            nombres=request.form.get("apoderado_nombres", ""),
            apellidos=request.form.get("apoderado_apellidos", ""),
            documento=request.form.get("apoderado_documento", ""),
            parentesco=request.form.get("apoderado_parentesco", ""),
            telefono_whatsapp=request.form.get("apoderado_telefono", ""),
            es_principal=True,
        )
    ]
    ap2_doc = request.form.get("apoderado2_documento", "").strip()
    ap2_nom = request.form.get("apoderado2_nombres", "").strip()
    if ap2_doc or ap2_nom:
        apoderados.append(
            Apoderado(
                id=0,
                nombres=ap2_nom,
                apellidos=request.form.get("apoderado2_apellidos", ""),
                documento=ap2_doc,
                parentesco=request.form.get("apoderado2_parentesco", ""),
                telefono_whatsapp=request.form.get("apoderado2_telefono", ""),
                es_principal=False,
            )
        )
    return apoderados


@bp_alumnos.route("/matricula", methods=["GET"])
@permiso_requerido(PermisoOperacion.GESTIONAR_MATRICULA)
def ver_matricula() -> tuple[str, int]:
    salon_id_filtro = _parsear_entero_opcional(request.args.get("salon_id"))
    return _render_matricula(200, salon_id_filtro=salon_id_filtro)


@bp_alumnos.route("/matricula", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_MATRICULA)
def registrar_matricula() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        salon_id = _parsear_entero(request.form.get("salon_id"), "salon_id")
        fecha_nacimiento = _parsear_fecha(request.form.get("fecha_nacimiento"), "fecha_nacimiento")
        apoderados = _construir_apoderados_desde_form()
        ficha = servicio.matricular(
            _operador_id(),
            codigo_estudiante=request.form.get("codigo_estudiante", ""),
            dni=request.form.get("dni", ""),
            nombres=request.form.get("nombres", ""),
            apellidos=request.form.get("apellidos", ""),
            fecha_nacimiento=fecha_nacimiento,
            salon_id=salon_id,
            apoderados=apoderados,
        )
    except (MatriculaDuplicadaException, SalonSinVacantesException) as error:
        flash(str(error), "error")
        return _render_matricula(409)
    except IntegrityError:
        flash("Ya existe un estudiante registrado con ese DNI o código.", "error")
        return _render_matricula(409)
    except (MatriculaException, DniInvalidoException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_matricula(status)

    flash(
        f"Matrícula registrada correctamente para {ficha.nombres} {ficha.apellidos} "
        f"({ficha.codigo_estudiante}).",
        "success",
    )
    return redirect(url_for("alumnos.ver_matricula"))


@bp_alumnos.route("/matricula/<int:alumno_id>/cambiar-salon", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_MATRICULA)
def cambiar_salon(alumno_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        nuevo_salon_id = _parsear_entero(request.form.get("nuevo_salon_id"), "nuevo_salon_id")
        ficha = servicio.cambiar_salon(_operador_id(), alumno_id, nuevo_salon_id)
    except SalonSinVacantesException as error:
        flash(str(error), "error")
        return _render_matricula(409)
    except (MatriculaException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_matricula(status)

    flash(
        f"Traslado de salón completado: {ficha.nivel} {ficha.grado} {ficha.seccion}.",
        "success",
    )
    return redirect(url_for("alumnos.ver_matricula"))


# ---------------------------------------------------------------------------
# 2. Carnets Escolares QR (PBI-06)
# ---------------------------------------------------------------------------


def _render_carnets(
    status: int = 200,
    *,
    alumno_id: int | None = None,
    carnet_validado: CarnetEscolar | None = None,
) -> tuple[str, int]:
    alumnos = _listar_alumnos()
    carnets = _listar_carnets_alumno(alumno_id)
    return (
        render_template(
            "carnets.html",
            alumnos=alumnos,
            alumno_seleccionado=alumno_id,
            carnets=carnets,
            motivos_anulacion=list(MotivoAnulacionCarnet),
            carnet_validado=carnet_validado,
        ),
        status,
    )


@bp_alumnos.route("/carnets", methods=["GET"])
@permiso_requerido(PermisoOperacion.GESTIONAR_CARNETS)
def ver_carnets() -> tuple[str, int]:
    alumno_id = _parsear_entero_opcional(request.args.get("alumno_id"))
    return _render_carnets(200, alumno_id=alumno_id)


@bp_alumnos.route("/carnets/emitir", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_CARNETS)
def emitir_carnet() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    alumno_id: int | None = None
    try:
        alumno_id = _parsear_entero(request.form.get("alumno_id"), "alumno_id")
        anio_lectivo = _parsear_entero(request.form.get("anio_lectivo"), "anio_lectivo")
        motivo_raw = request.form.get("motivo_reposicion", "").strip() or None
        detalle_raw = request.form.get("detalle_anulacion", "").strip() or None
        resultado = servicio.emitir_carnet(
            _operador_id(),
            alumno_id,
            anio_lectivo,
            motivo_reposicion=motivo_raw,
            detalle_anulacion=detalle_raw,
        )
    except (CarnetException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_carnets(status, alumno_id=alumno_id)

    flash(
        f"Carnet emitido correctamente con código QR {resultado.carnet_nuevo.codigo_qr}.",
        "success",
    )
    return redirect(url_for("alumnos.ver_carnets", alumno_id=alumno_id))


@bp_alumnos.route("/carnets/<carnet_id>/anular", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_CARNETS)
def anular_carnet(carnet_id: str) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    alumno_id = _parsear_entero_opcional(request.form.get("alumno_id"))
    try:
        motivo = request.form.get("motivo", "").strip()
        detalle = request.form.get("detalle", "").strip() or None
        anulado = servicio.anular_carnet(_operador_id(), carnet_id, motivo, detalle=detalle)
    except CarnetYaAnuladoException as error:
        flash(str(error), "error")
        return _render_carnets(409, alumno_id=alumno_id)
    except (CarnetException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_carnets(status, alumno_id=alumno_id)

    flash(f"Carnet {anulado.codigo_qr} anulado correctamente.", "success")
    return redirect(url_for("alumnos.ver_carnets", alumno_id=anulado.alumno_id))


@bp_alumnos.route("/carnets/validar", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_CARNETS)
def validar_carnet() -> tuple[str, int]:
    servicio = _obtener_servicio()
    codigo_qr = request.form.get("codigo_qr", "").strip()
    try:
        carnet = servicio.validar_carnet(codigo_qr)
    except CarnetNoEncontradoException as error:
        flash(str(error), "error")
        return _render_carnets(404)
    except CarnetException as error:
        flash(str(error), "error")
        return _render_carnets(400)

    flash(f"Carnet {carnet.codigo_qr} válido y habilitado para ingreso.", "success")
    return _render_carnets(200, alumno_id=carnet.alumno_id, carnet_validado=carnet)


# ---------------------------------------------------------------------------
# 3. Estados Académicos (PBI-08)
# ---------------------------------------------------------------------------


def _render_estados(
    status: int = 200,
    *,
    alumno_id: int | None = None,
) -> tuple[str, int]:
    alumnos = _listar_alumnos()
    historial = _listar_historial_estados(alumno_id)
    return (
        render_template(
            "estados.html",
            alumnos=alumnos,
            alumno_seleccionado=alumno_id,
            historial=historial,
            estados_posibles=list(EstadoAcademico),
        ),
        status,
    )


@bp_alumnos.route("/estados", methods=["GET"])
@permiso_requerido(PermisoOperacion.GESTIONAR_ESTADOS_ACADEMICOS)
def ver_estados() -> tuple[str, int]:
    alumno_id = _parsear_entero_opcional(request.args.get("alumno_id"))
    return _render_estados(200, alumno_id=alumno_id)


@bp_alumnos.route("/estados/<int:alumno_id>/cambiar", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_ESTADOS_ACADEMICOS)
def cambiar_estado(alumno_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        estado_raw = request.form.get("nuevo_estado", "").strip().upper()
        try:
            nuevo_estado = EstadoAcademico(estado_raw)
        except ValueError as error:
            raise ValueError(f"El estado académico '{estado_raw}' no es válido.") from error

        motivo = request.form.get("motivo", "")
        fecha_inicio = _parsear_fecha_opcional(
            request.form.get("fecha_inicio_suspension"), "fecha_inicio_suspension"
        )
        fecha_fin = _parsear_fecha_opcional(
            request.form.get("fecha_fin_suspension"), "fecha_fin_suspension"
        )
        resultado = servicio.cambiar_estado_academico(
            _operador_id(),
            alumno_id,
            nuevo_estado,
            motivo,
            fecha_inicio_suspension=fecha_inicio,
            fecha_fin_suspension=fecha_fin,
        )
    except TransicionEstadoInvalidaException as error:
        flash(str(error), "error")
        return _render_estados(409, alumno_id=alumno_id)
    except (EstadoAcademicoException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_estados(status, alumno_id=alumno_id)

    aviso_carnet = (
        " El carnet activo fue anulado automáticamente." if resultado.debe_anular_carnet else ""
    )
    flash(
        f"Estado académico actualizado a {resultado.estado_actual.value}.{aviso_carnet}",
        "success",
    )
    return redirect(url_for("alumnos.ver_estados", alumno_id=alumno_id))


# ---------------------------------------------------------------------------
# 4. Gestión de Pagos y Panel Restringido de Alertas Silenciosas (PBI-07)
# ---------------------------------------------------------------------------


def _render_pagos(
    status: int = 200,
    *,
    alumno_id: int | None = None,
    solo_alertas: bool = False,
) -> tuple[str, int]:
    servicio = _obtener_servicio()
    puede_gestionar = tiene_permiso(PermisoOperacion.GESTIONAR_PAGOS)
    puede_ver_alertas = tiene_permiso(PermisoOperacion.VER_ALERTA_PAGOS)

    alumnos = _listar_alumnos()
    obligaciones = (
        servicio.listar_obligaciones(alumno_id)
        if puede_gestionar and alumno_id is not None and not solo_alertas
        else []
    )
    alertas = servicio.listar_alertas_pago(solo_activas=True) if puede_ver_alertas else []
    return (
        render_template(
            "pagos.html",
            alumnos=alumnos,
            alumno_seleccionado=alumno_id,
            obligaciones=obligaciones,
            alertas=alertas,
            puede_gestionar_pagos=puede_gestionar,
            puede_ver_alertas=puede_ver_alertas,
            solo_alertas=solo_alertas,
        ),
        status,
    )


@bp_alumnos.route("/pagos", methods=["GET"])
@login_requerido
def ver_pagos() -> tuple[str, int]:
    if not (
        tiene_permiso(PermisoOperacion.GESTIONAR_PAGOS)
        or tiene_permiso(PermisoOperacion.VER_ALERTA_PAGOS)
    ):
        abort(403)
    alumno_id = _parsear_entero_opcional(request.args.get("alumno_id"))
    return _render_pagos(200, alumno_id=alumno_id)


@bp_alumnos.route("/pagos/obligaciones", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_PAGOS)
def registrar_obligacion() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    alumno_id: int | None = None
    try:
        alumno_id = _parsear_entero(request.form.get("alumno_id"), "alumno_id")
        concepto = request.form.get("concepto", "")
        monto = _parsear_decimal(request.form.get("monto"), "monto")
        fecha_vencimiento = _parsear_fecha(
            request.form.get("fecha_vencimiento"), "fecha_vencimiento"
        )
        obligacion = servicio.registrar_obligacion(
            _operador_id(),
            alumno_id,
            concepto,
            monto,
            fecha_vencimiento,
        )
    except (PagosException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_pagos(status, alumno_id=alumno_id)

    flash(
        f"Obligación '{obligacion.concepto}' por S/ {obligacion.monto:.2f} registrada.",
        "success",
    )
    return redirect(url_for("alumnos.ver_pagos", alumno_id=alumno_id))


@bp_alumnos.route("/pagos/obligaciones/<obligacion_id>/pagar", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_PAGOS)
def registrar_pago(obligacion_id: str) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    alumno_id = _parsear_entero_opcional(request.form.get("alumno_id"))
    try:
        pagada = servicio.registrar_pago(_operador_id(), obligacion_id)
    except (PagosException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_pagos(status, alumno_id=alumno_id)

    flash(f"Pago registrado para '{pagada.concepto}' ({pagada.estado.value}).", "success")
    return redirect(url_for("alumnos.ver_pagos", alumno_id=pagada.alumno_id))


@bp_alumnos.route("/pagos/obligaciones/<obligacion_id>/exonerar", methods=["POST"])
@permiso_requerido(PermisoOperacion.GESTIONAR_PAGOS)
def exonerar_obligacion(obligacion_id: str) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    alumno_id = _parsear_entero_opcional(request.form.get("alumno_id"))
    try:
        motivo = request.form.get("motivo", "")
        exonerada = servicio.exonerar_obligacion(_operador_id(), obligacion_id, motivo)
    except (PagosException, ValueError) as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_pagos(status, alumno_id=alumno_id)

    flash(f"Obligación '{exonerada.concepto}' exonerada ({exonerada.estado.value}).", "success")
    return redirect(url_for("alumnos.ver_pagos", alumno_id=exonerada.alumno_id))


@bp_alumnos.route("/pagos/alertas", methods=["GET"])
@permiso_requerido(PermisoOperacion.VER_ALERTA_PAGOS)
def ver_alertas_pago() -> tuple[str, int]:
    return _render_pagos(200, solo_alertas=True)


@bp_alumnos.route("/pagos/alertas/<alerta_id>/revisar", methods=["POST"])
@permiso_requerido(PermisoOperacion.VER_ALERTA_PAGOS)
def marcar_alerta_revisada(alerta_id: str) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        servicio.marcar_alerta_revisada(_operador_id(), alerta_id)
    except ValueError as error:
        flash(str(error), "error")
        status = 404 if _es_no_encontrado(error) else 400
        return _render_pagos(status, solo_alertas=True)

    flash("Alerta silenciosa marcada como revisada.", "success")
    return redirect(url_for("alumnos.ver_alertas_pago"))
