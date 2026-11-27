"""Pruebas BDD/unitarias del PBI-15: RBAC dinámico y sesiones."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.dominio.usuarios import (
    MATRIZ_PERMISOS,
    AccesoDenegadoException,
    CuentaInactivaException,
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolInactivoException,
    RolInvalidoException,
    RolUsuario,
    ServicioAutenticacionYPermisos,
    ServicioGestionRoles,
    ServicioGestionUsuarios,
    SesionInvalidaException,
    Usuario,
    hashear_password,
)

FECHA = datetime(2026, 11, 23, 7, 0, tzinfo=UTC)

PERMISOS_ESPERADOS = frozenset(
    {
        "REGISTRAR_ASISTENCIA",
        "CORREGIR_AUSENTE",
        "CONSULTAR_HISTORIAL_ASISTENCIA",
        "CONSULTAR_DASHBOARD_AFORO",
        "CONFIGURAR_CIERRE_ASISTENCIA",
        "EJECUTAR_CIERRE_ASISTENCIA",
        "ADMINISTRAR_CALENDARIO_ESCOLAR",
        "GESTIONAR_JUSTIFICACIONES",
        "ADMINISTRAR_PERIODOS",
        "GESTIONAR_USUARIOS",
        "GESTIONAR_ROLES",
        "ASIGNAR_ROLES",
        "CONSULTAR_AUDITORIA",
        "VERIFICAR_INTEGRIDAD_AUDITORIA",
        "NOTIFICAR_AUSENCIAS_MANUAL",
        "CONFIGURAR_NOTIFICACIONES_WHATSAPP",
        "GESTIONAR_MATRICULA",
        "GESTIONAR_CARNETS",
        "GESTIONAR_PAGOS",
        "VER_ALERTA_PAGOS",
        "GESTIONAR_ESTADOS_ACADEMICOS",
        "CONFIGURAR_MALLA_CURRICULAR",
        "ASIGNAR_DOCENTES",
        "REGISTRAR_CALIFICACIONES",
        "CONSULTAR_CALIFICACIONES",
        "CONSULTAR_FICHA_ALUMNO",
        "EXPORTAR_ASISTENCIAS",
        "EMITIR_BOLETAS",
    }
)


@pytest.fixture
def admin_user() -> Usuario:
    pwd_hash, salt = hashear_password("AdminSecure2026!")
    return Usuario(
        id=1,
        username="admin_roles",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Admin Roles",
        rol=RolUsuario.ADMIN,
    )


@pytest.fixture
def coordinador_user() -> Usuario:
    pwd_hash, salt = hashear_password("Coord2026*")
    return Usuario(
        id=2,
        username="coord_roles",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Coordinador Roles",
        rol=RolUsuario.COORDINADOR,
    )


@pytest.fixture
def staff_user() -> Usuario:
    pwd_hash, salt = hashear_password("StaffPass123!")
    return Usuario(
        id=3,
        username="staff_roles",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Staff Roles",
        rol=RolUsuario.ADMIN_STAFF,
    )


@pytest.fixture
def docente_rol() -> Rol:
    return Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Rol personalizado para docentes",
        permisos=frozenset(
            {
                PermisoOperacion.REGISTRAR_CALIFICACIONES,
                PermisoOperacion.CONSULTAR_CALIFICACIONES,
            }
        ),
    )


@pytest.fixture
def docente_user() -> Usuario:
    pwd_hash, salt = hashear_password("DocentePass123!")
    return Usuario(
        id=10,
        username="docente_uno",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Docente Uno",
        rol="DOCENTE",  # type: ignore[arg-type]
    )


@pytest.fixture
def gestor_rol() -> Rol:
    return Rol(
        codigo="GESTOR",
        nombre="Gestor de roles",
        descripcion="Rol personalizado con permiso para gestionar roles",
        permisos=frozenset(
            {
                PermisoOperacion.GESTIONAR_ROLES,
                PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
            }
        ),
    )


@pytest.fixture
def gestor_user() -> Usuario:
    pwd_hash, salt = hashear_password("GestorPass123!")
    return Usuario(
        id=20,
        username="gestor_roles",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Gestor de Roles",
        rol="GESTOR",  # type: ignore[arg-type]
    )


def _solicitud_crear_rol(**cambios) -> dict[str, object]:
    datos = {
        "codigo": "DOCENTE",
        "nombre": "Docente",
        "descripcion": "Rol personalizado para docentes",
        "permisos": frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
        "roles_existentes": [],
        "fecha_hora": FECHA,
    }
    datos.update(cambios)
    return datos


# ----------------------------------------------------------------------
# Catálogo maestro y matriz de permisos
# ----------------------------------------------------------------------
def test_catalogo_maestro_tiene_exactamente_28_permisos() -> None:
    assert len(PermisoOperacion) == 28
    assert {permiso.value for permiso in PermisoOperacion} == PERMISOS_ESPERADOS


def test_admin_posee_todos_los_permisos() -> None:
    assert MATRIZ_PERMISOS[RolUsuario.ADMIN] == set(PermisoOperacion)


def test_coordinador_conserva_permisos_de_gestion_y_justificaciones() -> None:
    permisos = MATRIZ_PERMISOS[RolUsuario.COORDINADOR]

    assert PermisoOperacion.GESTIONAR_JUSTIFICACIONES in permisos
    assert PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL in permisos
    assert PermisoOperacion.GESTIONAR_CARNETS in permisos
    assert PermisoOperacion.CONSULTAR_CALIFICACIONES in permisos
    assert PermisoOperacion.CONSULTAR_FICHA_ALUMNO in permisos
    assert PermisoOperacion.EXPORTAR_ASISTENCIAS in permisos
    assert PermisoOperacion.GESTIONAR_ROLES not in permisos
    assert PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA not in permisos
    assert PermisoOperacion.CONSULTAR_AUDITORIA not in permisos


def test_admin_staff_conserva_permisos_operativos_y_no_administrativos() -> None:
    permisos = MATRIZ_PERMISOS[RolUsuario.ADMIN_STAFF]

    assert PermisoOperacion.GESTIONAR_JUSTIFICACIONES in permisos
    assert PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL in permisos
    assert PermisoOperacion.GESTIONAR_MATRICULA in permisos
    assert PermisoOperacion.GESTIONAR_CARNETS in permisos
    assert PermisoOperacion.VER_ALERTA_PAGOS in permisos
    assert PermisoOperacion.CONSULTAR_CALIFICACIONES in permisos
    assert PermisoOperacion.CONSULTAR_FICHA_ALUMNO in permisos
    assert PermisoOperacion.EXPORTAR_ASISTENCIAS in permisos
    assert PermisoOperacion.EMITIR_BOLETAS in permisos
    assert PermisoOperacion.GESTIONAR_ROLES not in permisos
    assert PermisoOperacion.GESTIONAR_PAGOS not in permisos
    assert PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR not in permisos


def test_obtener_roles_base_devuelve_tres_roles_inmutables() -> None:
    roles = ServicioGestionRoles.obtener_roles_base()

    assert len(roles) == 3
    assert {rol.codigo for rol in roles} == {"ADMIN", "COORDINADOR", "ADMIN_STAFF"}
    assert all(rol.es_sistema for rol in roles)
    assert all(rol.activo for rol in roles)
    admin = next(rol for rol in roles if rol.codigo == "ADMIN")
    assert admin.permisos == frozenset(PermisoOperacion)


# ----------------------------------------------------------------------
# Value object Rol
# ----------------------------------------------------------------------
def test_rol_normaliza_codigo_y_convierte_permisos() -> None:
    rol = Rol(
        codigo=" docente ",
        nombre="Docente",
        descripcion="Rol de docentes",
        permisos={PermisoOperacion.REGISTRAR_CALIFICACIONES},
    )

    assert rol.codigo == "DOCENTE"
    assert isinstance(rol.permisos, frozenset)
    assert rol.es_sistema is False
    assert rol.activo is True


@pytest.mark.parametrize(
    "cambios",
    [
        {"codigo": ""},
        {"codigo": "DOCENTE 1"},
        {"nombre": ""},
        {"descripcion": ""},
        {"permisos": frozenset()},
        {"permisos": frozenset({"NO_EXISTE"})},
    ],
)
def test_rol_rechaza_datos_invalidos(cambios: dict[str, object]) -> None:
    datos = {
        "codigo": "DOCENTE",
        "nombre": "Docente",
        "descripcion": "Rol de docentes",
        "permisos": frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
    }
    datos.update(cambios)

    with pytest.raises(RolInvalidoException):
        Rol(**datos)


# ----------------------------------------------------------------------
# Creación de roles personalizados
# ----------------------------------------------------------------------
def test_crear_rol_personalizado_y_auditar(admin_user: Usuario) -> None:
    rol, auditoria = ServicioGestionRoles.crear_rol(
        operador=admin_user,
        **_solicitud_crear_rol(
            codigo=" docente ",
            permisos={
                PermisoOperacion.REGISTRAR_CALIFICACIONES,
                PermisoOperacion.CONSULTAR_CALIFICACIONES,
            },
        ),
    )

    assert rol.codigo == "DOCENTE"
    assert rol.es_sistema is False
    assert rol.activo is True
    assert rol.permisos == frozenset(
        {
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            PermisoOperacion.CONSULTAR_CALIFICACIONES,
        }
    )
    assert auditoria.operacion == "CREAR_ROL"
    assert auditoria.admin_id == admin_user.id
    assert auditoria.detalle["entidad"] == "ROL"
    assert auditoria.detalle["codigo"] == "DOCENTE"


@pytest.mark.parametrize("codigo", ["docente", "ADMIN"])
def test_crear_rol_rechaza_codigo_duplicado(
    admin_user: Usuario, docente_rol: Rol, codigo: str
) -> None:
    with pytest.raises(RolInvalidoException, match="ya existe"):
        ServicioGestionRoles.crear_rol(
            operador=admin_user,
            **_solicitud_crear_rol(codigo=codigo, roles_existentes=[docente_rol]),
        )


@pytest.mark.parametrize("permisos", [set(), {"NO_EXISTE"}])
def test_crear_rol_rechaza_permisos_invalidos(
    admin_user: Usuario, permisos: set[object]
) -> None:
    with pytest.raises(RolInvalidoException, match="permiso"):
        ServicioGestionRoles.crear_rol(
            operador=admin_user,
            **_solicitud_crear_rol(permisos=permisos),
        )


def test_crear_rol_rechaza_codigo_invalido(admin_user: Usuario) -> None:
    with pytest.raises(RolInvalidoException, match="código"):
        ServicioGestionRoles.crear_rol(
            operador=admin_user,
            **_solicitud_crear_rol(codigo="DOCENTE 1"),
        )


def test_crear_rol_requiere_permiso_gestionar_roles(
    coordinador_user: Usuario, staff_user: Usuario
) -> None:
    for operador in (coordinador_user, staff_user):
        with pytest.raises(AccesoDenegadoException):
            ServicioGestionRoles.crear_rol(
                operador=operador,
                **_solicitud_crear_rol(),
            )


def test_crear_rol_rechaza_operador_inactivo(admin_user: Usuario) -> None:
    inactivo = replace(admin_user, estado=EstadoUsuario.INACTIVO)

    with pytest.raises(CuentaInactivaException):
        ServicioGestionRoles.crear_rol(
            operador=inactivo,
            **_solicitud_crear_rol(),
        )


def test_rol_personalizado_con_permiso_puede_gestionar_roles(
    gestor_user: Usuario, gestor_rol: Rol
) -> None:
    rol, _ = ServicioGestionRoles.crear_rol(
        operador=gestor_user,
        **_solicitud_crear_rol(
            codigo="AUXILIAR",
            roles_existentes=[gestor_rol],
        ),
    )

    assert rol.codigo == "AUXILIAR"


# ----------------------------------------------------------------------
# Actualización de permisos
# ----------------------------------------------------------------------
def test_actualizar_permisos_de_rol_personalizado(admin_user: Usuario, docente_rol: Rol) -> None:
    actualizado, auditoria = ServicioGestionRoles.actualizar_permisos_rol(
        operador=admin_user,
        rol=docente_rol,
        nuevos_permisos={PermisoOperacion.REGISTRAR_CALIFICACIONES},
        roles_existentes=[docente_rol],
        fecha_hora=FECHA,
    )

    assert actualizado.codigo == "DOCENTE"
    assert actualizado.permisos == frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES})
    assert auditoria.operacion == "MODIFICAR_ROL"
    assert auditoria.detalle["permisos_nuevos"] == "REGISTRAR_CALIFICACIONES"


def test_actualizar_permisos_rechaza_conjunto_vacio(admin_user: Usuario, docente_rol: Rol) -> None:
    with pytest.raises(RolInvalidoException, match="permiso"):
        ServicioGestionRoles.actualizar_permisos_rol(
            operador=admin_user,
            rol=docente_rol,
            nuevos_permisos=set(),
            roles_existentes=[docente_rol],
        )


def test_no_se_puede_reducir_permisos_del_rol_admin(admin_user: Usuario) -> None:
    admin_rol = next(
        rol for rol in ServicioGestionRoles.obtener_roles_base() if rol.codigo == "ADMIN"
    )

    with pytest.raises(RolInvalidoException, match="ADMIN"):
        ServicioGestionRoles.actualizar_permisos_rol(
            operador=admin_user,
            rol=admin_rol,
            nuevos_permisos={PermisoOperacion.REGISTRAR_ASISTENCIA},
            roles_existentes=[admin_rol],
        )


def test_no_se_pueden_modificar_otros_roles_del_sistema(admin_user: Usuario) -> None:
    coordinador_rol = next(
        rol for rol in ServicioGestionRoles.obtener_roles_base() if rol.codigo == "COORDINADOR"
    )

    with pytest.raises(RolInvalidoException, match="sistema"):
        ServicioGestionRoles.actualizar_permisos_rol(
            operador=admin_user,
            rol=coordinador_rol,
            nuevos_permisos={PermisoOperacion.REGISTRAR_ASISTENCIA},
            roles_existentes=[coordinador_rol],
        )


# ----------------------------------------------------------------------
# Activación / desactivación
# ----------------------------------------------------------------------
def test_cambiar_estado_rol_personalizado(admin_user: Usuario, docente_rol: Rol) -> None:
    inactivo, aud_desactivar = ServicioGestionRoles.cambiar_estado_rol(
        operador=admin_user,
        rol=docente_rol,
        activo=False,
        roles_existentes=[docente_rol],
        fecha_hora=FECHA,
    )

    assert inactivo.activo is False
    assert aud_desactivar.operacion == "DESACTIVAR_ROL"

    reactivado, aud_activar = ServicioGestionRoles.cambiar_estado_rol(
        operador=admin_user,
        rol=inactivo,
        activo=True,
        roles_existentes=[inactivo],
        fecha_hora=FECHA,
    )

    assert reactivado.activo is True
    assert aud_activar.operacion == "ACTIVAR_ROL"


def test_no_se_puede_desactivar_el_rol_admin(admin_user: Usuario) -> None:
    admin_rol = next(
        rol for rol in ServicioGestionRoles.obtener_roles_base() if rol.codigo == "ADMIN"
    )

    with pytest.raises(RolInvalidoException, match="ADMIN"):
        ServicioGestionRoles.cambiar_estado_rol(
            operador=admin_user,
            rol=admin_rol,
            activo=False,
            roles_existentes=[admin_rol],
        )


# ----------------------------------------------------------------------
# Eliminación
# ----------------------------------------------------------------------
def test_eliminar_rol_sin_usuarios_asignados(admin_user: Usuario, docente_rol: Rol) -> None:
    restantes, auditoria = ServicioGestionRoles.eliminar_rol(
        operador=admin_user,
        rol=docente_rol,
        roles_existentes=[docente_rol],
        usuarios=[],
        fecha_hora=FECHA,
    )

    assert restantes == []
    assert auditoria.operacion == "ELIMINAR_ROL"
    assert auditoria.detalle["codigo"] == "DOCENTE"


def test_no_se_puede_eliminar_rol_con_usuarios_asignados(
    admin_user: Usuario, docente_rol: Rol, docente_user: Usuario
) -> None:
    with pytest.raises(RolInvalidoException, match="usuarios asignados"):
        ServicioGestionRoles.eliminar_rol(
            operador=admin_user,
            rol=docente_rol,
            roles_existentes=[docente_rol],
            usuarios=[docente_user],
        )


def test_no_se_puede_eliminar_el_rol_admin(admin_user: Usuario) -> None:
    admin_rol = next(
        rol for rol in ServicioGestionRoles.obtener_roles_base() if rol.codigo == "ADMIN"
    )

    with pytest.raises(RolInvalidoException, match="ADMIN"):
        ServicioGestionRoles.eliminar_rol(
            operador=admin_user,
            rol=admin_rol,
            roles_existentes=[admin_rol],
            usuarios=[],
        )


def test_eliminar_rol_inexistente_es_rechazado(admin_user: Usuario, docente_rol: Rol) -> None:
    with pytest.raises(RolInvalidoException, match="no existe"):
        ServicioGestionRoles.eliminar_rol(
            operador=admin_user,
            rol=docente_rol,
            roles_existentes=[],
            usuarios=[],
        )


# ----------------------------------------------------------------------
# Asignación de roles personalizados a usuarios
# ----------------------------------------------------------------------
def test_crear_usuario_con_rol_personalizado(
    admin_user: Usuario, docente_rol: Rol
) -> None:
    nuevo, auditoria = ServicioGestionUsuarios.crear_usuario(
        operador=admin_user,
        username="docente_nuevo",
        password_plana="DocentePass2026",
        nombre_completo="Docente Nuevo",
        rol="DOCENTE",  # type: ignore[arg-type]
        usuarios_existentes=[admin_user],
        roles=[docente_rol],
    )

    assert nuevo.rol == "DOCENTE"
    assert auditoria.detalle["rol_asignado"] == "DOCENTE"


def test_modificar_usuario_a_rol_personalizado(
    admin_user: Usuario, staff_user: Usuario, docente_rol: Rol
) -> None:
    modificado, auditoria = ServicioGestionUsuarios.modificar_usuario(
        operador=admin_user,
        usuario_target=staff_user,
        nuevo_rol="DOCENTE",  # type: ignore[arg-type]
        roles=[docente_rol],
    )

    assert modificado.rol == "DOCENTE"
    assert auditoria.detalle["rol_nuevo"] == "DOCENTE"


def test_no_se_asigna_rol_personalizado_inexistente(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    with pytest.raises(RolInvalidoException):
        ServicioGestionUsuarios.modificar_usuario(
            operador=admin_user,
            usuario_target=staff_user,
            nuevo_rol="NO_EXISTE",  # type: ignore[arg-type]
            roles=[],
        )


# ----------------------------------------------------------------------
# Sesiones con roles personalizados
# ----------------------------------------------------------------------
def test_iniciar_sesion_con_rol_personalizado_activo(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        username="docente_uno",
        password_plana="DocentePass123!",
        usuarios=[docente_user],
        roles=[docente_rol],
    )

    assert sesion.activa is True
    assert sesion.rol == "DOCENTE"
    assert sesion.rol_codigo == "DOCENTE"


def test_iniciar_sesion_rechaza_rol_personalizado_inactivo(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    inactivo = replace(docente_rol, activo=False)

    with pytest.raises(RolInactivoException):
        ServicioAutenticacionYPermisos.iniciar_sesion(
            username="docente_uno",
            password_plana="DocentePass123!",
            usuarios=[docente_user],
            roles=[inactivo],
        )


def test_iniciar_sesion_rechaza_rol_personalizado_inexistente(
    docente_user: Usuario,
) -> None:
    with pytest.raises(RolInvalidoException):
        ServicioAutenticacionYPermisos.iniciar_sesion(
            username="docente_uno",
            password_plana="DocentePass123!",
            usuarios=[docente_user],
            roles=[],
        )


def test_validar_permiso_de_rol_personalizado(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "docente_uno", "DocentePass123!", [docente_user], roles=[docente_rol]
    )

    ServicioAutenticacionYPermisos.validar_permiso(
        sesion,
        PermisoOperacion.REGISTRAR_CALIFICACIONES,
        roles=[docente_rol],
    )

    with pytest.raises(AccesoDenegadoException):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion,
            PermisoOperacion.GESTIONAR_USUARIOS,
            roles=[docente_rol],
        )


def test_sesion_se_revoca_si_el_usuario_es_desactivado(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "docente_uno", "DocentePass123!", [docente_user], roles=[docente_rol]
    )
    inactivo = replace(docente_user, estado=EstadoUsuario.INACTIVO)

    with pytest.raises(SesionInvalidaException, match="revocada"):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion,
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            usuario_actual=inactivo,
            roles=[docente_rol],
        )


def test_sesion_se_revoca_si_cambia_el_rol_del_usuario(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "docente_uno", "DocentePass123!", [docente_user], roles=[docente_rol]
    )
    cambiado = replace(docente_user, rol=RolUsuario.ADMIN_STAFF)

    with pytest.raises(SesionInvalidaException, match="revocada"):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion,
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            usuario_actual=cambiado,
            roles=[docente_rol],
        )


def test_revocar_todas_las_sesiones_de_un_usuario(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    sesion_admin = ServicioAutenticacionYPermisos.iniciar_sesion(
        "admin_roles", "AdminSecure2026!", [admin_user]
    )
    sesion_staff = ServicioAutenticacionYPermisos.iniciar_sesion(
        "staff_roles", "StaffPass123!", [staff_user]
    )

    revocadas = ServicioAutenticacionYPermisos.revocar_sesiones_usuario(
        admin_user.id, [sesion_admin, sesion_staff]
    )

    assert revocadas[0].activa is False
    assert revocadas[1].activa is True


def test_revocar_sesiones_por_desactivacion_de_rol(
    docente_user: Usuario, docente_rol: Rol, admin_user: Usuario
) -> None:
    sesion_docente = ServicioAutenticacionYPermisos.iniciar_sesion(
        "docente_uno", "DocentePass123!", [docente_user], roles=[docente_rol]
    )
    sesion_admin = ServicioAutenticacionYPermisos.iniciar_sesion(
        "admin_roles", "AdminSecure2026!", [admin_user]
    )

    revocadas = ServicioAutenticacionYPermisos.revocar_sesiones_por_rol(
        "DOCENTE", [sesion_docente, sesion_admin]
    )

    assert revocadas[0].activa is False
    assert revocadas[1].activa is True


# ----------------------------------------------------------------------
# Evaluación por permiso y deny-by-default
# ----------------------------------------------------------------------
def test_tiene_permiso_por_rol_base_personalizado_y_desconocido(
    docente_rol: Rol,
) -> None:
    assert ServicioAutenticacionYPermisos.tiene_permiso(
        RolUsuario.ADMIN, PermisoOperacion.GESTIONAR_ROLES
    )
    assert not ServicioAutenticacionYPermisos.tiene_permiso(
        RolUsuario.COORDINADOR, PermisoOperacion.GESTIONAR_ROLES
    )
    assert ServicioAutenticacionYPermisos.tiene_permiso(
        "DOCENTE",
        PermisoOperacion.REGISTRAR_CALIFICACIONES,
        [docente_rol],
    )
    assert not ServicioAutenticacionYPermisos.tiene_permiso(
        "DOCENTE",
        PermisoOperacion.GESTIONAR_ROLES,
        [docente_rol],
    )
    assert not ServicioAutenticacionYPermisos.tiene_permiso(
        "DESCONOCIDO", PermisoOperacion.REGISTRAR_ASISTENCIA
    )


# ----------------------------------------------------------------------
# Cobertura de validaciones defensivas y revocación (REFACTOR)
# ----------------------------------------------------------------------
def test_normalizar_codigo_rol_rechaza_no_texto() -> None:
    with pytest.raises(RolInvalidoException, match="texto"):
        Rol(
            codigo=123,  # type: ignore[arg-type]
            nombre="Docente",
            descripcion="Rol de docentes",
            permisos=frozenset({PermisoOperacion.REGISTRAR_ASISTENCIA}),
        )


def test_rol_rechaza_permisos_no_iterables() -> None:
    with pytest.raises(RolInvalidoException, match="colección"):
        Rol(
            codigo="DOCENTE",
            nombre="Docente",
            descripcion="Rol de docentes",
            permisos="REGISTRAR_ASISTENCIA",  # type: ignore[arg-type]
        )


def test_rol_rechaza_permiso_de_tipo_invalido() -> None:
    with pytest.raises(RolInvalidoException, match="catálogo"):
        Rol(
            codigo="DOCENTE",
            nombre="Docente",
            descripcion="Rol de docentes",
            permisos=frozenset({123}),  # type: ignore[arg-type]
        )


def test_rol_rechaza_indicadores_no_booleanos() -> None:
    with pytest.raises(RolInvalidoException, match="booleanos"):
        Rol(
            codigo="DOCENTE",
            nombre="Docente",
            descripcion="Rol de docentes",
            permisos=frozenset({PermisoOperacion.REGISTRAR_ASISTENCIA}),
            es_sistema="si",  # type: ignore[arg-type]
        )


def test_no_se_asigna_rol_personalizado_inactivo(
    admin_user: Usuario, staff_user: Usuario, docente_rol: Rol
) -> None:
    with pytest.raises(RolInactivoException):
        ServicioGestionUsuarios.modificar_usuario(
            operador=admin_user,
            usuario_target=staff_user,
            nuevo_rol="DOCENTE",  # type: ignore[arg-type]
            roles=[replace(docente_rol, activo=False)],
        )


def test_tiene_permiso_deny_by_default_para_permiso_invalido() -> None:
    assert not ServicioAutenticacionYPermisos.tiene_permiso(
        RolUsuario.ADMIN,
        "NO_EXISTE",  # type: ignore[arg-type]
    )


def test_tiene_permiso_con_objeto_rol(docente_rol: Rol) -> None:
    assert ServicioAutenticacionYPermisos.tiene_permiso(
        docente_rol, PermisoOperacion.REGISTRAR_CALIFICACIONES
    )
    assert not ServicioAutenticacionYPermisos.tiene_permiso(
        replace(docente_rol, activo=False),
        PermisoOperacion.REGISTRAR_CALIFICACIONES,
    )


def test_tiene_permiso_con_codigo_de_rol_base() -> None:
    assert ServicioAutenticacionYPermisos.tiene_permiso(
        "ADMIN", PermisoOperacion.GESTIONAR_ROLES
    )
    assert not ServicioAutenticacionYPermisos.tiene_permiso(
        "COORDINADOR", PermisoOperacion.GESTIONAR_ROLES
    )


def test_sesion_revocada_por_usuario_distinto(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "docente_uno", "DocentePass123!", [docente_user], roles=[docente_rol]
    )
    otro_usuario = replace(docente_user, id=99)

    with pytest.raises(SesionInvalidaException, match="revocada"):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion,
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            usuario_actual=otro_usuario,
            roles=[docente_rol],
        )


def test_validar_permiso_rechaza_rol_actual_inactivo(
    docente_user: Usuario, docente_rol: Rol
) -> None:
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "docente_uno", "DocentePass123!", [docente_user], roles=[docente_rol]
    )

    with pytest.raises(AccesoDenegadoException, match="activo"):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion,
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            rol_actual=replace(docente_rol, activo=False),
            roles=[docente_rol],
        )


def test_roles_base_como_texto_son_aceptados_en_sesion_y_gestion(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    """Al hidratar usuarios desde BD el rol base llega como str y debe funcionar."""
    pwd_hash, salt = hashear_password("BaseStrPass2026!")
    admin_desde_bd = Usuario(
        id=90,
        username="admin_bd",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Admin BD",
        rol="ADMIN",
    )
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "admin_bd", "BaseStrPass2026!", [admin_desde_bd]
    )
    assert sesion.activa is True
    assert sesion.rol_codigo == "ADMIN"

    creado, _ = ServicioGestionUsuarios.crear_usuario(
        operador=admin_user,
        username="staff_texto",
        password_plana="StaffTexto2026!",
        nombre_completo="Staff Texto",
        rol="ADMIN_STAFF",
        usuarios_existentes=[admin_user, staff_user],
    )
    assert creado.rol == RolUsuario.ADMIN_STAFF

    modificado, _ = ServicioGestionUsuarios.modificar_usuario(
        operador=admin_user,
        usuario_target=staff_user,
        nuevo_rol="COORDINADOR",
    )
    assert modificado.rol == RolUsuario.COORDINADOR
