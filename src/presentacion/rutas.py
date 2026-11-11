"""Rutas Flask delgadas: validan entrada web y delegan en los casos de uso."""

from datetime import date

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.aplicacion.casos_uso import MetodoRegistroInvalido
from src.dominio.aforo import AforoException
from src.dominio.asistencia import (
    AsistenciaException,
    EstadoAsistencia,
    FaltaMotivoCorreccionException,
    RegistroAsistencia,
)
from src.dominio.justificaciones import JustificacionException
from src.dominio.usuarios import (
    CredencialesInvalidasException,
    CuentaInactivaException,
    EstadoUsuario,
    RolUsuario,
    UsuarioException,
)
from src.infraestructura.datos_demo import CREDENCIALES_DEMO
from src.presentacion.seguridad import login_requerido, roles_requeridos

bp_auth = Blueprint("auth", __name__)
bp_principal = Blueprint("main", __name__)
bp_asistencia = Blueprint("asistencia", __name__)
bp_justificaciones = Blueprint("justificaciones", __name__)
bp_usuarios = Blueprint("usuarios", __name__)

ROLES_ASISTENCIA = (RolUsuario.ADMIN, RolUsuario.COORDINADOR, RolUsuario.ADMIN_STAFF)
ROLES_JUSTIFICACION = (RolUsuario.ADMIN, RolUsuario.ADMIN_STAFF)
ROLES_ADMIN = (RolUsuario.ADMIN,)


def _fecha_solicitada() -> date:
    valor = request.args.get("fecha")
    if not valor:
        return g.servicio.ahora().date()
    try:
        return date.fromisoformat(valor)
    except ValueError:
        flash("La fecha indicada no es válida; se muestra la fecha actual.", "warning")
        return g.servicio.ahora().date()


def _ruta_segura(destino: str | None) -> str:
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return url_for("main.aforo")


# ----------------------------------------------------------------------
# Autenticación
# ----------------------------------------------------------------------
@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    if getattr(g, "usuario", None) is not None:
        return redirect(url_for("main.aforo"))

    error = None
    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username:
            error = "El nombre de usuario es obligatorio."
        elif not password:
            error = "La contraseña es obligatoria."
        elif len(password) < 8:
            error = "La contraseña debe tener mínimo 8 caracteres."
        else:
            try:
                sesion_dominio = g.servicio.autenticar(username, password)
            except (CredencialesInvalidasException, CuentaInactivaException) as excepcion:
                error = str(excepcion)
            else:
                session.clear()
                session["usuario_id"] = sesion_dominio.usuario_id
                session["token"] = sesion_dominio.token
                session["rol"] = sesion_dominio.rol.value
                session["expiracion"] = sesion_dominio.fecha_expiracion.isoformat()
                flash(
                    f"Bienvenido(a), {sesion_dominio.username}.",
                    "success",
                )
                return redirect(_ruta_segura(request.args.get("next")))

    return render_template(
        "login.html",
        error=error,
        username=username,
        credenciales_demo=CREDENCIALES_DEMO,
    )


@bp_auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("La sesión se cerró correctamente.", "info")
    return redirect(url_for("auth.login"))


@bp_principal.route("/")
@login_requerido
def inicio():
    return redirect(url_for("main.aforo"))


# ----------------------------------------------------------------------
# Dashboard de aforo (PBI-03)
# ----------------------------------------------------------------------
@bp_principal.route("/aforo")
@login_requerido
def aforo():
    fecha = _fecha_solicitada()
    filtros = {
        "nivel": (request.args.get("nivel") or "").strip(),
        "grado": (request.args.get("grado") or "").strip(),
        "seccion": (request.args.get("seccion") or "").strip(),
    }
    metricas = g.servicio.obtener_metricas(
        g.usuario,
        fecha_escolar=fecha,
        nivel=filtros["nivel"] or None,
        grado=filtros["grado"] or None,
        seccion=filtros["seccion"] or None,
    )
    return render_template(
        "aforo.html",
        metricas=metricas,
        fecha=fecha,
        filtros=filtros,
        opciones=g.repositorio.opciones_academicas(),
        hora_cierre=g.repositorio.obtener_hora_cierre(),
        cierre_ejecutado=g.repositorio.existe_cierre(fecha),
        total_registros=g.repositorio.contar_asistencias(fecha),
    )


@bp_principal.route("/aforo/hora-cierre", methods=["POST"])
@roles_requeridos(*ROLES_ADMIN)
def configurar_hora_cierre():
    hora_texto = (request.form.get("hora_cierre") or "").strip()
    try:
        nueva_hora = g.servicio.configurar_hora_cierre(g.usuario, hora_texto)
        g.db_sesion.commit()
    except AforoException as excepcion:
        g.db_sesion.rollback()
        flash(str(excepcion), "error")
    else:
        flash(
            f"La hora oficial de cierre se actualizó a {nueva_hora.strftime('%H:%M')}.",
            "success",
        )
    return redirect(url_for("main.aforo"))


@bp_principal.route("/aforo/cierre", methods=["POST"])
@roles_requeridos(*ROLES_ADMIN)
def ejecutar_cierre():
    if request.form.get("confirmo") != "si":
        flash("Debe confirmar que la jornada de ingreso ha concluido.", "warning")
        return redirect(url_for("main.aforo"))

    try:
        evento = g.servicio.ejecutar_cierre(g.usuario)
        g.db_sesion.commit()
    except AforoException as excepcion:
        g.db_sesion.rollback()
        flash(str(excepcion), "error")
    else:
        flash(
            "Cierre ejecutado: "
            f"{evento.total_ausentes_marcados} alumno(s) pasaron a AUSENTE.",
            "success",
        )
    return redirect(url_for("main.aforo"))


# ----------------------------------------------------------------------
# Registro de asistencia (PBI-01)
# ----------------------------------------------------------------------
def _contexto_asistencia(**extra):
    hoy = g.servicio.ahora().date()
    alumnos = {alumno.id: alumno for alumno in g.repositorio.listar_alumnos()}
    asistencias = sorted(
        g.repositorio.listar_asistencias(hoy),
        key=lambda registro: registro.hora_efectiva,
        reverse=True,
    )
    ids_con_registro = {registro.alumno_id for registro in asistencias}
    sugeridos = [
        alumno for alumno in alumnos.values() if alumno.id not in ids_con_registro
    ][:3]
    contexto = {
        "fecha": hoy,
        "recientes": [
            {"asistencia": registro, "alumno": alumnos.get(registro.alumno_id)}
            for registro in asistencias[:8]
        ],
        "sugeridos": sugeridos,
        "form": {},
        "error": None,
        "correccion": None,
        "resultado": None,
        "milisegundos": None,
    }
    contexto.update(extra)
    return contexto


def _quiere_json() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def _serializar_alumno(alumno) -> dict[str, object]:
    return {
        "id": alumno.id,
        "nombre": f"{alumno.nombres} {alumno.apellidos}",
        "codigo": alumno.codigo,
        "dni": alumno.dni,
        "carnet": alumno.carnet_codigo,
        "nivel": alumno.nivel,
        "grado": alumno.grado,
        "seccion": alumno.seccion,
        "salon": f"{alumno.nivel} · {alumno.grado} · Sección {alumno.seccion}",
    }


def _serializar_asistencia(registro: RegistroAsistencia | None) -> dict[str, object] | None:
    if registro is None:
        return None
    return {
        "id": registro.id,
        "estado": registro.estado.value,
        "hora": registro.hora_efectiva.strftime("%H:%M:%S"),
        "minutos_tardanza": registro.minutos_tardanza,
        "metodo": registro.metodo.value,
    }


def _mensaje_confirmacion(registro: RegistroAsistencia, milisegundos: int) -> str:
    detalle = registro.estado.value
    if registro.estado == EstadoAsistencia.TARDANZA:
        detalle += f" · {registro.minutos_tardanza} min de tardanza"
    return f"Registro confirmado: {detalle}. Procesado en {milisegundos} ms."


@bp_asistencia.route("/asistencia")
@roles_requeridos(*ROLES_ASISTENCIA)
def ver_asistencia():
    return render_template("asistencia.html", **_contexto_asistencia())


@bp_asistencia.route("/asistencia/registrar", methods=["POST"])
@roles_requeridos(*ROLES_ASISTENCIA)
def registrar_asistencia():
    metodo = (request.form.get("metodo") or "").strip().upper()
    identificador = (request.form.get("identificador") or "").strip()
    alumno_id_texto = (request.form.get("alumno_id") or "").strip()
    motivo = (request.form.get("motivo") or "").strip() or None
    alumno_id = int(alumno_id_texto) if alumno_id_texto.isdigit() else None

    try:
        resultado, milisegundos = g.servicio.registrar_asistencia(
            g.usuario,
            metodo,
            identificador=identificador,
            alumno_id=alumno_id,
            motivo=motivo,
        )
        g.db_sesion.commit()
    except FaltaMotivoCorreccionException as excepcion:
        g.db_sesion.rollback()
        alumno, asistencia = g.servicio.obtener_contexto_alumno(
            metodo, identificador, alumno_id
        )
        if _quiere_json():
            return (
                jsonify(
                    {
                        "ok": False,
                        "requiere_motivo": True,
                        "mensaje": str(excepcion),
                        "alumno": _serializar_alumno(alumno),
                        "asistencia": _serializar_asistencia(asistencia),
                    }
                ),
                409,
            )
        return (
            render_template(
                "asistencia.html",
                **_contexto_asistencia(
                    form={"metodo": metodo, "identificador": identificador},
                    correccion={
                        "metodo": metodo,
                        "identificador": identificador,
                        "alumno_id": alumno.id,
                        "alumno": alumno,
                        "asistencia": asistencia,
                        "mensaje": str(excepcion),
                    },
                ),
            ),
            200,
        )
    except (AsistenciaException, MetodoRegistroInvalido, ValueError) as excepcion:
        g.db_sesion.rollback()
        if _quiere_json():
            return (
                jsonify({"ok": False, "requiere_motivo": False, "mensaje": str(excepcion)}),
                400,
            )
        return (
            render_template(
                "asistencia.html",
                **_contexto_asistencia(
                    error=str(excepcion),
                    form={"metodo": metodo, "identificador": identificador},
                ),
            ),
            200,
        )

    mensaje = _mensaje_confirmacion(resultado.asistencia, milisegundos)
    if _quiere_json():
        alumno = g.repositorio.obtener_alumno(resultado.asistencia.alumno_id)
        return jsonify(
            {
                "ok": True,
                "mensaje": mensaje,
                "alumno": _serializar_alumno(alumno) if alumno else None,
                "estado": resultado.asistencia.estado.value,
                "hora": resultado.asistencia.hora_efectiva.strftime("%H:%M:%S"),
                "minutos_tardanza": resultado.asistencia.minutos_tardanza,
                "metodo": resultado.asistencia.metodo.value,
                "milisegundos": milisegundos,
            }
        )

    flash(
        mensaje,
        "success" if resultado.asistencia.estado != EstadoAsistencia.TARDANZA else "warning",
    )
    return redirect(url_for("asistencia.ver_asistencia"))


@bp_asistencia.route("/api/alumnos")
@roles_requeridos(*ROLES_ASISTENCIA)
def api_alumnos():
    criterio = (request.args.get("q") or "").strip()
    if len(criterio) < 2:
        return jsonify({"resultados": []})

    resultados = [
        {
            "id": alumno.id,
            "nombre": f"{alumno.nombres} {alumno.apellidos}",
            "codigo": alumno.codigo,
            "dni": alumno.dni,
            "carnet": alumno.carnet_codigo,
            "salon": f"{alumno.nivel} · {alumno.grado} · Sección {alumno.seccion}",
            "estado": alumno.estado.value,
        }
        for alumno in g.servicio.buscar_alumnos(criterio)[:12]
    ]
    return jsonify({"resultados": resultados})


# ----------------------------------------------------------------------
# Justificaciones (PBI-04)
# ----------------------------------------------------------------------
def _contexto_justificaciones(**extra):
    fecha = _fecha_solicitada()
    contexto = {
        "fecha": fecha,
        "justificables": g.servicio.listar_justificables(fecha),
        "justificaciones": g.servicio.listar_justificaciones(fecha),
        "periodo": g.repositorio.periodo_por_fecha(fecha),
        "form": {},
        "abrir_wizard": False,
        "error": None,
    }
    contexto.update(extra)
    return contexto


@bp_justificaciones.route("/justificaciones")
@roles_requeridos(*ROLES_JUSTIFICACION)
def ver_justificaciones():
    return render_template("justificaciones.html", **_contexto_justificaciones())


@bp_justificaciones.route("/justificaciones/registrar", methods=["POST"])
@roles_requeridos(*ROLES_JUSTIFICACION)
def registrar_justificacion():
    asistencia_id = (request.form.get("asistencia_id") or "").strip()
    categoria = (request.form.get("categoria") or "").strip()
    fecha_texto = (request.form.get("fecha_solicitud") or "").strip()
    motivo = (request.form.get("motivo") or "").strip()
    documento = (request.form.get("documento_adjunto") or "").strip() or None

    form = {
        "asistencia_id": asistencia_id,
        "categoria": categoria,
        "fecha_solicitud": fecha_texto,
        "motivo": motivo,
        "documento_adjunto": documento or "",
    }

    try:
        fecha_solicitud = date.fromisoformat(fecha_texto)
        justificacion = g.servicio.registrar_justificacion(
            g.usuario,
            asistencia_id=asistencia_id,
            categoria=categoria,
            fecha_solicitud=fecha_solicitud,
            motivo=motivo,
            documento_adjunto=documento,
        )
        g.db_sesion.commit()
    except (JustificacionException, ValueError) as excepcion:
        g.db_sesion.rollback()
        return (
            render_template(
                "justificaciones.html",
                **_contexto_justificaciones(form=form, abrir_wizard=True, error=str(excepcion)),
            ),
            200,
        )

    flash(
        "Justificación registrada. La asistencia quedó en estado "
        f"{EstadoAsistencia.JUSTIFICADO.value}.",
        "success",
    )
    return redirect(
        url_for(
            "justificaciones.ver_justificaciones",
            fecha=justificacion.fecha_solicitud,
        )
    )


@bp_justificaciones.route("/justificaciones/<codigo>/anular", methods=["POST"])
@roles_requeridos(*ROLES_JUSTIFICACION)
def anular_justificacion(codigo: str):
    try:
        g.servicio.anular_justificacion(g.usuario, codigo)
        g.db_sesion.commit()
    except (JustificacionException, UsuarioException) as excepcion:
        g.db_sesion.rollback()
        flash(str(excepcion), "error")
    else:
        flash("La justificación se anuló y la asistencia recuperó su estado anterior.", "success")
    return redirect(url_for("justificaciones.ver_justificaciones"))


# ----------------------------------------------------------------------
# Gestión de usuarios (PBI-02 / PBI-15)
# ----------------------------------------------------------------------
@bp_usuarios.route("/usuarios")
@roles_requeridos(*ROLES_ADMIN)
def listar_usuarios():
    filtros = {
        "nombre": (request.args.get("nombre") or "").strip(),
        "username": (request.args.get("username") or "").strip(),
        "rol": (request.args.get("rol") or "").strip(),
        "estado": (request.args.get("estado") or "").strip(),
    }
    usuarios = g.servicio.listar_usuarios(
        nombre=filtros["nombre"] or None,
        username=filtros["username"] or None,
        rol=filtros["rol"] or None,
        estado=filtros["estado"] or None,
    )
    return render_template(
        "usuarios.html",
        usuarios=usuarios,
        filtros=filtros,
        roles=list(RolUsuario),
        estados=list(EstadoUsuario),
    )


@bp_usuarios.route("/usuarios/nuevo", methods=["GET", "POST"])
@roles_requeridos(*ROLES_ADMIN)
def nuevo_usuario():
    form = {
        "nombre_completo": "",
        "username": "",
        "rol": RolUsuario.ADMIN_STAFF.value,
        "estado": EstadoUsuario.ACTIVO.value,
    }
    if request.method == "POST":
        form = {
            "nombre_completo": (request.form.get("nombre_completo") or "").strip(),
            "username": (request.form.get("username") or "").strip().lower(),
            "rol": (request.form.get("rol") or "").strip(),
            "estado": (request.form.get("estado") or EstadoUsuario.ACTIVO.value).strip(),
        }
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""

        try:
            if not form["nombre_completo"]:
                raise UsuarioException("El nombre completo es obligatorio.")
            if not form["username"]:
                raise UsuarioException("El nombre de usuario es obligatorio.")
            if password != password_confirm:
                raise UsuarioException("Las contraseñas no coinciden.")

            creado = g.servicio.crear_usuario(
                g.usuario,
                username=form["username"],
                password=password,
                nombre_completo=form["nombre_completo"],
                rol=form["rol"],
            )
            if form["estado"] == EstadoUsuario.INACTIVO.value:
                g.servicio.cambiar_estado_usuario(
                    g.usuario, creado.id, EstadoUsuario.INACTIVO.value
                )
            g.db_sesion.commit()
        except (UsuarioException, ValueError) as excepcion:
            g.db_sesion.rollback()
            mensaje = str(excepcion)
            paso = 1
            if "rol" in mensaje.lower():
                paso = 2
            elif "contraseña" in mensaje.lower():
                paso = 3
            return (
                render_template(
                    "usuario_nuevo.html",
                    form=form,
                    roles=list(RolUsuario),
                    paso=paso,
                    error=mensaje,
                ),
                200,
            )

        flash(f"La cuenta '{creado.username}' se creó correctamente.", "success")
        return redirect(url_for("usuarios.detalle_usuario", usuario_id=creado.id))

    return render_template(
        "usuario_nuevo.html",
        form=form,
        roles=list(RolUsuario),
        paso=1,
        error=None,
    )


@bp_usuarios.route("/usuarios/<int:usuario_id>")
@roles_requeridos(*ROLES_ADMIN)
def detalle_usuario(usuario_id: int):
    usuario = g.repositorio.obtener_usuario(usuario_id)
    if usuario is None:
        abort(404)
    return render_template(
        "usuario_detalle.html",
        usuario=usuario,
        roles=list(RolUsuario),
        estados=list(EstadoUsuario),
    )


@bp_usuarios.route("/usuarios/<int:usuario_id>/editar", methods=["POST"])
@roles_requeridos(*ROLES_ADMIN)
def editar_usuario(usuario_id: int):
    nombre = (request.form.get("nombre_completo") or "").strip()
    rol = (request.form.get("rol") or "").strip()
    if not nombre:
        flash("El nombre completo no puede quedar vacío.", "error")
        return redirect(url_for("usuarios.detalle_usuario", usuario_id=usuario_id))

    try:
        g.servicio.modificar_usuario(g.usuario, usuario_id, nombre, rol)
        g.db_sesion.commit()
    except UsuarioException as excepcion:
        flash(str(excepcion), "error")
    else:
        flash("Los datos de la cuenta se actualizaron.", "success")
    return redirect(url_for("usuarios.detalle_usuario", usuario_id=usuario_id))


@bp_usuarios.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])
@roles_requeridos(*ROLES_ADMIN)
def cambiar_estado(usuario_id: int):
    nuevo_estado = (request.form.get("nuevo_estado") or "").strip()
    try:
        g.servicio.cambiar_estado_usuario(g.usuario, usuario_id, nuevo_estado)
        g.db_sesion.commit()
    except UsuarioException as excepcion:
        flash(str(excepcion), "error")
    else:
        flash(f"El estado de la cuenta cambió a {nuevo_estado}.", "success")
    return redirect(url_for("usuarios.detalle_usuario", usuario_id=usuario_id))


@bp_usuarios.route("/usuarios/<int:usuario_id>/password", methods=["POST"])
@roles_requeridos(*ROLES_ADMIN)
def restablecer_password(usuario_id: int):
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""
    try:
        if password != password_confirm:
            raise UsuarioException("Las contraseñas no coinciden.")
        g.servicio.restablecer_password(g.usuario, usuario_id, password)
        g.db_sesion.commit()
    except UsuarioException as excepcion:
        flash(str(excepcion), "error")
    else:
        flash("La credencial se restableció correctamente.", "success")
    return redirect(url_for("usuarios.detalle_usuario", usuario_id=usuario_id))


@bp_usuarios.route("/api/usuarios/disponible")
@roles_requeridos(*ROLES_ADMIN)
def api_usuario_disponible():
    username = (request.args.get("username") or "").strip().lower()
    if not username:
        return jsonify({"disponible": False, "mensaje": "Ingrese un nombre de usuario."})
    existe = g.repositorio.obtener_usuario_por_username(username) is not None
    return jsonify(
        {
            "disponible": not existe,
            "mensaje": "Nombre de usuario disponible" if not existe else "Ya está registrado",
        }
    )
