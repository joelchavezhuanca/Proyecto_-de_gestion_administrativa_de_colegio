"""Blueprint Flask para gestión académica: Malla, Docentes y Calificaciones (Ola 4).

Reglas de diseño:
- Cero lógica de negocio en rutas: únicamente parseo HTTP -> ServicioAcademico -> respuesta.
- Protección estricta con @login_requerido, @permiso_requerido y CSRF (seguridad.py).
- Registro idempotente mediante registrar_blueprints_academico(app).
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

from src.aplicacion.servicios_academico import ServicioAcademico
from src.dominio.calificaciones import (
    CalificacionException,
    FechaLimiteNotasVencidaException,
    PeriodoCalificacionCerradoException,
    PermisoCalificacionException,
)
from src.dominio.docentes import (
    AccesoAmbitoDocenteDenegadoException,
    AsignacionDuplicadaException,
    AsignacionEnUsoException,
    DocenteException,
)
from src.dominio.malla_curricular import (
    CursoDuplicadoException,
    EntidadEnUsoException,
    MallaCurricularException,
    NivelEducativo,
    SalonDuplicadoException,
)
from src.dominio.usuarios import PermisoOperacion
from src.infraestructura.repositorios import (
    RepositorioCalificaciones,
    RepositorioDocentes,
    RepositorioMatricula,
    RepositorioPeriodos,
    RepositorioRoles,
    RepositorioUsuarios,
)
from src.presentacion.seguridad import login_requerido, permiso_requerido, tiene_permiso
from src.presentacion.tiempo import hora_institucional

bp_academico = Blueprint("academico", __name__)


def registrar_blueprints_academico(app: Flask) -> None:
    """Registra el blueprint académico de forma idempotente en la aplicación Flask."""
    if bp_academico.name not in app.blueprints:
        app.register_blueprint(bp_academico)


@bp_academico.before_request
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
# Helpers de acceso a servicios y parseo defensivo
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


def _parsear_decimal(raw: str | None, campo: str) -> Decimal:
    texto = (raw or "").strip()
    try:
        return Decimal(texto)
    except InvalidOperation as error:
        raise ValueError(f"El campo '{campo}' debe ser un número decimal válido.") from error


def _status_por_error(error: Exception) -> int:
    return 404 if "no existe" in str(error).lower() else 400


# ---------------------------------------------------------------------------
# 1. Malla Curricular: Salones y Cursos (PBI-09)
# ---------------------------------------------------------------------------


def _render_malla(status: int = 200, *, anio_lectivo: int | None = None) -> tuple[str, int]:
    servicio = _obtener_servicio()
    salones = servicio.listar_salones(anio_lectivo=anio_lectivo, solo_activos=False)
    cursos = servicio.listar_cursos(anio_lectivo=anio_lectivo, solo_activos=False)
    return (
        render_template(
            "malla.html",
            salones=salones,
            cursos=cursos,
            niveles=list(NivelEducativo),
            anio_filtro=anio_lectivo,
        ),
        status,
    )


@bp_academico.route("/malla", methods=["GET"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def ver_malla() -> tuple[str, int]:
    anio = _parsear_entero_opcional(request.args.get("anio_lectivo"))
    return _render_malla(200, anio_lectivo=anio)


@bp_academico.route("/malla/salones", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def crear_salon() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        anio = _parsear_entero(request.form.get("anio_lectivo"), "anio_lectivo")
        capacidad = _parsear_entero(request.form.get("capacidad_maxima"), "capacidad_maxima")
        salon = servicio.crear_salon(
            _operador_id(),
            anio_lectivo=anio,
            nivel=request.form.get("nivel", "").strip(),
            grado=request.form.get("grado", "").strip(),
            seccion=request.form.get("seccion", "").strip(),
            capacidad_maxima=capacidad,
        )
    except SalonDuplicadoException as error:
        flash(str(error), "error")
        return _render_malla(409)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash(
        f"Salón {salon.nivel.value} {salon.grado} '{salon.seccion}' creado correctamente.",
        "success",
    )
    return redirect(url_for("academico.ver_malla"))


@bp_academico.route("/malla/salones/<int:salon_id>/capacidad", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def actualizar_capacidad_salon(salon_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        nueva = _parsear_entero(request.form.get("nueva_capacidad"), "nueva_capacidad")
        salon = servicio.actualizar_capacidad_salon(_operador_id(), salon_id, nueva)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash(f"Capacidad del salón actualizada a {salon.capacidad_maxima} vacantes.", "success")
    return redirect(url_for("academico.ver_malla"))


@bp_academico.route("/malla/salones/<int:salon_id>/desactivar", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def desactivar_salon(salon_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        servicio.desactivar_salon(_operador_id(), salon_id)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash("Salón desactivado correctamente.", "success")
    return redirect(url_for("academico.ver_malla"))


@bp_academico.route("/malla/salones/<int:salon_id>/eliminar", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def eliminar_salon(salon_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        servicio.eliminar_salon(_operador_id(), salon_id)
    except EntidadEnUsoException as error:
        flash(str(error), "error")
        return _render_malla(409)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash("Salón eliminado correctamente.", "success")
    return redirect(url_for("academico.ver_malla"))


@bp_academico.route("/malla/cursos", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def crear_curso() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        anio = _parsear_entero(request.form.get("anio_lectivo"), "anio_lectivo")
        horas = _parsear_entero(request.form.get("horas_semanales"), "horas_semanales")
        curso = servicio.crear_curso(
            _operador_id(),
            anio_lectivo=anio,
            nivel=request.form.get("nivel", "").strip(),
            grado=request.form.get("grado", "").strip(),
            codigo=request.form.get("codigo", "").strip(),
            nombre=request.form.get("nombre", "").strip(),
            area_curricular=request.form.get("area_curricular", "").strip(),
            horas_semanales=horas,
        )
    except CursoDuplicadoException as error:
        flash(str(error), "error")
        return _render_malla(409)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash(f"Curso {curso.codigo} · {curso.nombre} registrado correctamente.", "success")
    return redirect(url_for("academico.ver_malla"))


@bp_academico.route("/malla/cursos/<int:curso_id>/desactivar", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def desactivar_curso(curso_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        servicio.desactivar_curso(_operador_id(), curso_id)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash("Curso desactivado correctamente.", "success")
    return redirect(url_for("academico.ver_malla"))


@bp_academico.route("/malla/cursos/<int:curso_id>/eliminar", methods=["POST"])
@permiso_requerido(PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR)
def eliminar_curso(curso_id: int) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        servicio.eliminar_curso(_operador_id(), curso_id)
    except EntidadEnUsoException as error:
        flash(str(error), "error")
        return _render_malla(409)
    except (MallaCurricularException, ValueError) as error:
        flash(str(error), "error")
        return _render_malla(_status_por_error(error))

    flash("Curso eliminado correctamente.", "success")
    return redirect(url_for("academico.ver_malla"))


# ---------------------------------------------------------------------------
# 2. Asignación Docente Segura (PBI-11)
# ---------------------------------------------------------------------------


def _render_docentes(status: int = 200) -> tuple[str, int]:
    servicio = _obtener_servicio()
    salones = servicio.listar_salones(solo_activos=True)
    cursos = servicio.listar_cursos(solo_activos=True)
    with _obtener_session_factory()() as session:
        usuarios = RepositorioUsuarios(session).listar(solo_activos=True)
        asignaciones = RepositorioDocentes(session).listar_todas(solo_activas=False)
    mapa_usuarios = {u.id: u for u in usuarios}
    mapa_cursos = {c.id: c for c in cursos}
    mapa_salones = {s.id: s for s in salones}
    return (
        render_template(
            "docentes.html",
            usuarios=usuarios,
            cursos=cursos,
            salones=salones,
            asignaciones=asignaciones,
            mapa_usuarios=mapa_usuarios,
            mapa_cursos=mapa_cursos,
            mapa_salones=mapa_salones,
        ),
        status,
    )


@bp_academico.route("/docentes", methods=["GET"])
@permiso_requerido(PermisoOperacion.ASIGNAR_DOCENTES)
def ver_docentes() -> tuple[str, int]:
    return _render_docentes(200)


@bp_academico.route("/docentes/asignar", methods=["POST"])
@permiso_requerido(PermisoOperacion.ASIGNAR_DOCENTES)
def asignar_docente() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        docente_id = _parsear_entero(request.form.get("docente_id"), "docente_id")
        curso_id = _parsear_entero(request.form.get("curso_id"), "curso_id")
        salon_id = _parsear_entero(request.form.get("salon_id"), "salon_id")
        servicio.asignar_docente(_operador_id(), docente_id, curso_id, salon_id)
    except AsignacionDuplicadaException as error:
        flash(str(error), "error")
        return _render_docentes(409)
    except (DocenteException, ValueError) as error:
        flash(str(error), "error")
        return _render_docentes(_status_por_error(error))

    flash("Asignación docente registrada correctamente.", "success")
    return redirect(url_for("academico.ver_docentes"))


@bp_academico.route("/docentes/<asignacion_id>/revocar", methods=["POST"])
@permiso_requerido(PermisoOperacion.ASIGNAR_DOCENTES)
def revocar_asignacion(asignacion_id: str) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        motivo = request.form.get("motivo", "").strip() or None
        servicio.revocar_asignacion(_operador_id(), asignacion_id, motivo=motivo)
    except (DocenteException, ValueError) as error:
        flash(str(error), "error")
        return _render_docentes(_status_por_error(error))

    flash("Asignación docente revocada correctamente.", "success")
    return redirect(url_for("academico.ver_docentes"))


@bp_academico.route("/docentes/<asignacion_id>/eliminar", methods=["POST"])
@permiso_requerido(PermisoOperacion.ASIGNAR_DOCENTES)
def eliminar_asignacion(asignacion_id: str) -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    try:
        servicio.eliminar_asignacion(_operador_id(), asignacion_id)
    except AsignacionEnUsoException as error:
        flash(str(error), "error")
        return _render_docentes(409)
    except (DocenteException, ValueError) as error:
        flash(str(error), "error")
        return _render_docentes(_status_por_error(error))

    flash("Asignación docente eliminada correctamente.", "success")
    return redirect(url_for("academico.ver_docentes"))


# ---------------------------------------------------------------------------
# 3. Libro de Calificaciones de 3 niveles (PBI-10)
# ---------------------------------------------------------------------------


def _render_calificaciones(
    status: int = 200,
    *,
    asignacion_id: str | None = None,
    periodo_id: int | None = None,
) -> tuple[str, int]:
    puede_registrar = tiene_permiso(PermisoOperacion.REGISTRAR_CALIFICACIONES)
    puede_ver_todas = tiene_permiso(PermisoOperacion.ASIGNAR_DOCENTES) or not puede_registrar
    reloj = current_app.config.get("RELOJ", hora_institucional)
    hoy = reloj().date()

    with _obtener_session_factory()() as session:
        repo_doc = RepositorioDocentes(session)
        repo_per = RepositorioPeriodos(session)
        repo_cal = RepositorioCalificaciones(session)
        repo_mat = RepositorioMatricula(session)

        asignaciones = (
            repo_doc.listar_todas(solo_activas=True)
            if puede_ver_todas
            else repo_doc.listar_asignaciones_docente(_operador_id(), solo_activas=True)
        )
        periodos = repo_per.listar()

        asignacion_actual = next((a for a in asignaciones if a.id == asignacion_id), None)
        periodo_actual = next((p for p in periodos if p.id == periodo_id), None)

        rubros = []
        actividades_por_rubro: dict[str, list] = {}
        alumnos = []
        notas_mapa: dict[tuple[str, int], object] = {}
        bloqueado_por_fecha_limite = False

        if asignacion_actual is not None and periodo_actual is not None:
            rubros = repo_cal.listar_rubros_asignacion(asignacion_actual.id, periodo_actual.id)
            alumnos = repo_mat.listar_por_salon(asignacion_actual.salon_id)
            for rubro in rubros:
                acts = repo_cal.listar_actividades_rubro(rubro.id)
                actividades_por_rubro[rubro.id] = acts
                for act in acts:
                    for cal in repo_cal.listar_calificaciones_actividad(act.id):
                        notas_mapa[(act.id, cal.alumno_id)] = cal
            bloqueado_por_fecha_limite = bool(
                periodo_actual.cerrado
                or (
                    periodo_actual.fecha_limite_notas is not None
                    and hoy > periodo_actual.fecha_limite_notas
                )
            )

    return (
        render_template(
            "calificaciones.html",
            asignaciones=asignaciones,
            periodos=periodos,
            asignacion_actual=asignacion_actual,
            periodo_actual=periodo_actual,
            rubros=rubros,
            actividades_por_rubro=actividades_por_rubro,
            alumnos=alumnos,
            notas_mapa=notas_mapa,
            puede_registrar=puede_registrar,
            bloqueado_por_fecha_limite=bloqueado_por_fecha_limite,
        ),
        status,
    )


@bp_academico.route("/calificaciones", methods=["GET"])
@login_requerido
def ver_calificaciones() -> tuple[str, int]:
    if not (
        tiene_permiso(PermisoOperacion.CONSULTAR_CALIFICACIONES)
        or tiene_permiso(PermisoOperacion.REGISTRAR_CALIFICACIONES)
    ):
        abort(403)
    asignacion_id = request.args.get("asignacion_id", "").strip() or None
    periodo_id = _parsear_entero_opcional(request.args.get("periodo_id"))
    return _render_calificaciones(200, asignacion_id=asignacion_id, periodo_id=periodo_id)


@bp_academico.route("/calificaciones/rubros", methods=["POST"])
@permiso_requerido(PermisoOperacion.REGISTRAR_CALIFICACIONES)
def configurar_rubros() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    asignacion_id = request.form.get("asignacion_id", "").strip()
    periodo_id = _parsear_entero_opcional(request.form.get("periodo_id"))
    try:
        periodo_val = _parsear_entero(request.form.get("periodo_id"), "periodo_id")
        nombres = request.form.getlist("rubro_nombre")
        pesos = request.form.getlist("rubro_peso")
        rubros_propuestos = [
            (nombre.strip(), _parsear_decimal(peso, "rubro_peso"))
            for nombre, peso in zip(nombres, pesos, strict=False)
            if nombre.strip() or peso.strip()
        ]
        servicio.configurar_rubros(_operador_id(), asignacion_id, periodo_val, rubros_propuestos)
    except (PermisoCalificacionException, AccesoAmbitoDocenteDenegadoException) as error:
        flash(str(error), "error")
        return _render_calificaciones(403, asignacion_id=asignacion_id, periodo_id=periodo_id)
    except (PeriodoCalificacionCerradoException, FechaLimiteNotasVencidaException) as error:
        flash(str(error), "error")
        return _render_calificaciones(409, asignacion_id=asignacion_id, periodo_id=periodo_id)
    except (CalificacionException, ValueError) as error:
        flash(str(error), "error")
        return _render_calificaciones(
            _status_por_error(error), asignacion_id=asignacion_id, periodo_id=periodo_id
        )

    flash("Rubros de evaluación configurados correctamente (100%).", "success")
    return redirect(
        url_for(
            "academico.ver_calificaciones",
            asignacion_id=asignacion_id,
            periodo_id=periodo_id,
        )
    )


@bp_academico.route("/calificaciones/actividades", methods=["POST"])
@permiso_requerido(PermisoOperacion.REGISTRAR_CALIFICACIONES)
def crear_actividad() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    asignacion_id = request.form.get("asignacion_id", "").strip() or None
    periodo_id = _parsear_entero_opcional(request.form.get("periodo_id"))
    try:
        rubro_id = request.form.get("rubro_id", "").strip()
        titulo = request.form.get("titulo", "").strip()
        fecha_act = _parsear_fecha(request.form.get("fecha_actividad"), "fecha_actividad")
        servicio.crear_actividad(_operador_id(), rubro_id, titulo, fecha_act)
    except (PermisoCalificacionException, AccesoAmbitoDocenteDenegadoException) as error:
        flash(str(error), "error")
        return _render_calificaciones(403, asignacion_id=asignacion_id, periodo_id=periodo_id)
    except (PeriodoCalificacionCerradoException, FechaLimiteNotasVencidaException) as error:
        flash(str(error), "error")
        return _render_calificaciones(409, asignacion_id=asignacion_id, periodo_id=periodo_id)
    except (CalificacionException, ValueError) as error:
        flash(str(error), "error")
        return _render_calificaciones(
            _status_por_error(error), asignacion_id=asignacion_id, periodo_id=periodo_id
        )

    flash("Actividad evaluable creada correctamente.", "success")
    return redirect(
        url_for(
            "academico.ver_calificaciones",
            asignacion_id=asignacion_id,
            periodo_id=periodo_id,
        )
    )


@bp_academico.route("/calificaciones/notas", methods=["POST"])
@permiso_requerido(PermisoOperacion.REGISTRAR_CALIFICACIONES)
def registrar_calificacion() -> Response | tuple[str, int]:
    servicio = _obtener_servicio()
    asignacion_id = request.form.get("asignacion_id", "").strip() or None
    periodo_id = _parsear_entero_opcional(request.form.get("periodo_id"))
    try:
        actividad_id = request.form.get("actividad_id", "").strip()
        alumno_id = _parsear_entero(request.form.get("alumno_id"), "alumno_id")
        nota = _parsear_decimal(request.form.get("nota"), "nota")
        motivo = request.form.get("motivo_modificacion", "").strip() or None
        observacion = request.form.get("observacion", "").strip() or None
        servicio.registrar_calificacion(
            _operador_id(),
            actividad_id,
            alumno_id,
            nota,
            motivo_modificacion=motivo,
            observacion=observacion,
        )
    except (PermisoCalificacionException, AccesoAmbitoDocenteDenegadoException) as error:
        flash(str(error), "error")
        return _render_calificaciones(403, asignacion_id=asignacion_id, periodo_id=periodo_id)
    except (PeriodoCalificacionCerradoException, FechaLimiteNotasVencidaException) as error:
        flash(str(error), "error")
        return _render_calificaciones(409, asignacion_id=asignacion_id, periodo_id=periodo_id)
    except (CalificacionException, ValueError) as error:
        flash(str(error), "error")
        return _render_calificaciones(
            _status_por_error(error), asignacion_id=asignacion_id, periodo_id=periodo_id
        )

    flash("Calificación registrada correctamente.", "success")
    return redirect(
        url_for(
            "academico.ver_calificaciones",
            asignacion_id=asignacion_id,
            periodo_id=periodo_id,
        )
    )
