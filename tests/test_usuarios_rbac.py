from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

try:
    from src.dominio.usuarios import (
        AccesoDenegadoException,
        CredencialesInvalidasException,
        CuentaInactivaException,
        EstadoUsuario,
        EventoAuditoriaUsuario,
        PermisoOperacion,
        Rol,
        RolInvalidoException,
        RolUsuario,
        ServicioAutenticacionYPermisos,
        ServicioGestionUsuarios,
        SesionInvalidaException,
        UltimoAdminException,
        Usuario,
        UsuarioDuplicadoException,
        UsuarioException,
        hashear_password,
        validar_politica_password,
        verificar_password,
    )
except ImportError:
    from usuarios_dominio import (  # type: ignore
        AccesoDenegadoException,
        CredencialesInvalidasException,
        CuentaInactivaException,
        EstadoUsuario,
        EventoAuditoriaUsuario,
        PermisoOperacion,
        Rol,
        RolInvalidoException,
        RolUsuario,
        ServicioAutenticacionYPermisos,
        ServicioGestionUsuarios,
        SesionInvalidaException,
        UltimoAdminException,
        Usuario,
        UsuarioDuplicadoException,
        UsuarioException,
        hashear_password,
        validar_politica_password,
        verificar_password,
    )


@pytest.fixture
def admin_user() -> Usuario:
    pwd_hash, salt = hashear_password("AdminSecure2026!")
    return Usuario(
        id=1,
        username="admin_central",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Gari Joel Chávez Huanca",
        rol=RolUsuario.ADMIN,
        estado=EstadoUsuario.ACTIVO,
    )


@pytest.fixture
def coordinador_user() -> Usuario:
    pwd_hash, salt = hashear_password("Coord2026*")
    return Usuario(
        id=2,
        username="coord_primaria",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Yhovana Quispe",
        rol=RolUsuario.COORDINADOR,
        estado=EstadoUsuario.ACTIVO,
    )


@pytest.fixture
def staff_user() -> Usuario:
    pwd_hash, salt = hashear_password("StaffPass123!")
    return Usuario(
        id=3,
        username="jluna_qa",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo="Jacob Luna",
        rol=RolUsuario.ADMIN_STAFF,
        estado=EstadoUsuario.ACTIVO,
    )


# --- PRUEBAS PBI-02: GESTIÓN DE USUARIOS ---


def test_escenario_01_crear_usuario_con_admin(admin_user: Usuario) -> None:
    """Escenario 1: ADMIN crea cuenta con rol oficial y genera auditoría."""
    nuevo, aud = ServicioGestionUsuarios.crear_usuario(
        operador=admin_user,
        username="dudu_frontend",
        password_plana="DuduPass2026",
        nombre_completo="Dudú Fabiano",
        rol=RolUsuario.ADMIN_STAFF,
        usuarios_existentes=[admin_user],
    )
    assert nuevo.id == 2
    assert nuevo.username == "dudu_frontend"
    assert nuevo.rol == RolUsuario.ADMIN_STAFF
    assert nuevo.estado == EstadoUsuario.ACTIVO
    assert nuevo.password_hash != "DuduPass2026"
    assert verificar_password("DuduPass2026", nuevo.password_hash, nuevo.salt)
    assert aud.operacion == "CREAR_USUARIO"
    assert aud.admin_id == admin_user.id


def test_escenario_02_impedir_creacion_por_no_admin(
    coordinador_user: Usuario, admin_user: Usuario
) -> None:
    """Escenario 2: COORDINADOR o ADMIN_STAFF no pueden crear cuentas."""
    with pytest.raises(AccesoDenegadoException, match="GESTIONAR_USUARIOS"):
        ServicioGestionUsuarios.crear_usuario(
            operador=coordinador_user,
            username="intruso",
            password_plana="Password123",
            nombre_completo="Intruso",
            rol=RolUsuario.ADMIN_STAFF,
            usuarios_existentes=[admin_user, coordinador_user],
        )


def test_escenario_02_admin_inactivo_no_puede_operar(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    """Comprobar que un administrador inactivo no puede crear ni modificar cuentas."""
    admin_inactivo = Usuario(
        id=admin_user.id,
        username=admin_user.username,
        password_hash=admin_user.password_hash,
        salt=admin_user.salt,
        nombre_completo=admin_user.nombre_completo,
        rol=admin_user.rol,
        estado=EstadoUsuario.INACTIVO,
    )
    with pytest.raises(CuentaInactivaException, match="no cuenta con una cuenta activa"):
        ServicioGestionUsuarios.crear_usuario(
            operador=admin_inactivo,
            username="nuevo",
            password_plana="Pass12345",
            nombre_completo="Nuevo",
            rol=RolUsuario.ADMIN_STAFF,
            usuarios_existentes=[],
        )


def test_escenario_03_rechazar_username_duplicado(admin_user: Usuario) -> None:
    """Escenario 3: Rechazar creación si el username ya existe (case-insensitive)."""
    with pytest.raises(UsuarioDuplicadoException, match="ya está registrado"):
        ServicioGestionUsuarios.crear_usuario(
            operador=admin_user,
            username="ADMIN_CENTRAL",
            password_plana="OtraPassword123",
            nombre_completo="Otro Admin",
            rol=RolUsuario.ADMIN,
            usuarios_existentes=[admin_user],
        )


def test_escenario_04_modificar_datos_y_rol(admin_user: Usuario, staff_user: Usuario) -> None:
    """Escenario 4: ADMIN modifica nombre o rol, conservando trazabilidad."""
    modificado, aud = ServicioGestionUsuarios.modificar_usuario(
        operador=admin_user,
        usuario_target=staff_user,
        nuevo_nombre="Jacob Luna Basilio",
        nuevo_rol=RolUsuario.COORDINADOR,
    )
    assert modificado.nombre_completo == "Jacob Luna Basilio"
    assert modificado.rol == RolUsuario.COORDINADOR
    assert aud.operacion == "MODIFICAR_USUARIO"
    assert aud.detalle["rol_anterior"] == "ADMIN_STAFF"
    assert aud.detalle["rol_nuevo"] == "COORDINADOR"


def test_escenario_04_modificar_rol_invalido(admin_user: Usuario, staff_user: Usuario) -> None:
    """Rechazar modificación si se asigna un rol no reconocido."""
    with pytest.raises(RolInvalidoException, match="no es válido"):
        ServicioGestionUsuarios.modificar_usuario(
            operador=admin_user,
            usuario_target=staff_user,
            nuevo_rol="DIRECTOR",  # type: ignore
        )


def test_escenario_05_06_desactivar_y_reactivar_cuenta(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    """Escenarios 5 y 6: Desactivar cuenta a INACTIVA y luego reactivarla."""
    desactivado, aud_des = ServicioGestionUsuarios.cambiar_estado(
        operador=admin_user,
        usuario_target=staff_user,
        nuevo_estado=EstadoUsuario.INACTIVO,
    )
    assert desactivado.estado == EstadoUsuario.INACTIVO
    assert aud_des.operacion == "DESACTIVAR_CUENTA"

    reactivado, aud_act = ServicioGestionUsuarios.cambiar_estado(
        operador=admin_user,
        usuario_target=desactivado,
        nuevo_estado=EstadoUsuario.ACTIVO,
    )
    assert reactivado.estado == EstadoUsuario.ACTIVO
    assert aud_act.operacion == "ACTIVAR_CUENTA"


def test_escenario_07_consultar_y_filtrar_usuarios(
    admin_user: Usuario, coordinador_user: Usuario, staff_user: Usuario
) -> None:
    """Escenario 7: Filtrar usuarios por nombre, username, rol o estado."""
    inactivo = Usuario(
        id=4,
        username="bloqueado",
        password_hash="hash",
        salt="salt",
        nombre_completo="Usuario Bloqueado",
        rol=RolUsuario.ADMIN_STAFF,
        estado=EstadoUsuario.INACTIVO,
    )
    lista = [admin_user, coordinador_user, staff_user, inactivo]

    filtro_rol = ServicioGestionUsuarios.filtrar_usuarios(lista, rol=RolUsuario.ADMIN)
    assert len(filtro_rol) == 1
    assert filtro_rol[0].username == "admin_central"

    filtro_nombre = ServicioGestionUsuarios.filtrar_usuarios(lista, nombre="Quispe")
    assert len(filtro_nombre) == 1
    assert filtro_nombre[0].username == "coord_primaria"

    filtro_user = ServicioGestionUsuarios.filtrar_usuarios(lista, username="luna")
    assert len(filtro_user) == 1

    filtro_inactivo = ServicioGestionUsuarios.filtrar_usuarios(lista, estado=EstadoUsuario.INACTIVO)
    assert len(filtro_inactivo) == 1
    assert filtro_inactivo[0].username == "bloqueado"


def test_escenario_08_restablecer_password(admin_user: Usuario, staff_user: Usuario) -> None:
    """Escenario 8: ADMIN restablece contraseña sin conocer la anterior."""
    antiguo_hash = staff_user.password_hash
    actualizado, aud = ServicioGestionUsuarios.restablecer_password(
        operador=admin_user,
        usuario_target=staff_user,
        nueva_password_plana="NuevaPassSegura2026",
    )
    assert actualizado.password_hash != antiguo_hash
    assert verificar_password("NuevaPassSegura2026", actualizado.password_hash, actualizado.salt)
    assert aud.operacion == "RESTABLECER_CREDENCIAL"


def test_escenario_08_restablecer_password_corta(admin_user: Usuario, staff_user: Usuario) -> None:
    """Rechazar restablecimiento si la nueva contraseña tiene menos de 8 caracteres."""
    with pytest.raises(UsuarioException, match="al menos 8 caracteres"):
        ServicioGestionUsuarios.restablecer_password(
            operador=admin_user,
            usuario_target=staff_user,
            nueva_password_plana="123",
        )


def test_validacion_creacion_errores(admin_user: Usuario) -> None:
    """Verifica rechazo de username vacío, password corta o rol inválido."""
    with pytest.raises(UsuarioException, match="no puede estar vacío"):
        ServicioGestionUsuarios.crear_usuario(
            operador=admin_user,
            username="",
            password_plana="Pass1234",
            nombre_completo="Test",
            rol=RolUsuario.ADMIN,
            usuarios_existentes=[],
        )

    with pytest.raises(UsuarioException, match="al menos 8 caracteres"):
        ServicioGestionUsuarios.crear_usuario(
            operador=admin_user,
            username="valido",
            password_plana="123",
            nombre_completo="Test",
            rol=RolUsuario.ADMIN,
            usuarios_existentes=[],
        )

    with pytest.raises(RolInvalidoException):
        ServicioGestionUsuarios.crear_usuario(
            operador=admin_user,
            username="valido",
            password_plana="Pass1234",
            nombre_completo="Test",
            rol="PORTERO_ANTIGUO",  # type: ignore
            usuarios_existentes=[],
        )


# --- PRUEBAS PBI-15: CONTROL DE ACCESO BASADO EN ROLES (RBAC) ---


def test_rbac_iniciar_sesion_exitoso(staff_user: Usuario) -> None:
    """PBI-15 Escenario 1: Inicio de sesión válido genera sesión en servidor."""
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        username="jluna_qa",
        password_plana="StaffPass123!",
        usuarios=[staff_user],
    )
    assert sesion.activa is True
    assert sesion.username == "jluna_qa"
    assert sesion.rol == RolUsuario.ADMIN_STAFF
    assert sesion.token.startswith("tok-")


def test_rbac_rechazar_credenciales_incorrectas(staff_user: Usuario) -> None:
    """PBI-15 Escenario 2: Rechazar login ante contraseña errónea o usuario inexistente."""
    with pytest.raises(CredencialesInvalidasException):
        ServicioAutenticacionYPermisos.iniciar_sesion(
            username="jluna_qa",
            password_plana="WrongPassword",
            usuarios=[staff_user],
        )

    with pytest.raises(CredencialesInvalidasException):
        ServicioAutenticacionYPermisos.iniciar_sesion(
            username="no_existe",
            password_plana="CualquierPass",
            usuarios=[staff_user],
        )


def test_rbac_rechazar_cuenta_inactiva(staff_user: Usuario) -> None:
    """PBI-15 Escenario 3: Cuenta inactiva no puede iniciar sesión."""
    usuario_inactivo = Usuario(
        id=staff_user.id,
        username=staff_user.username,
        password_hash=staff_user.password_hash,
        salt=staff_user.salt,
        nombre_completo=staff_user.nombre_completo,
        rol=staff_user.rol,
        estado=EstadoUsuario.INACTIVO,
    )
    with pytest.raises(CuentaInactivaException):
        ServicioAutenticacionYPermisos.iniciar_sesion(
            username="jluna_qa",
            password_plana="StaffPass123!",
            usuarios=[usuario_inactivo],
        )


def test_rbac_matriz_permisos_oficial(
    admin_user: Usuario, coordinador_user: Usuario, staff_user: Usuario
) -> None:
    """PBI-15 Escenarios 4, 5, 6 y 8: Validar matriz de permisos en servidor."""
    sesion_admin = ServicioAutenticacionYPermisos.iniciar_sesion(
        "admin_central", "AdminSecure2026!", [admin_user]
    )
    sesion_coord = ServicioAutenticacionYPermisos.iniciar_sesion(
        "coord_primaria", "Coord2026*", [coordinador_user]
    )
    sesion_staff = ServicioAutenticacionYPermisos.iniciar_sesion(
        "jluna_qa", "StaffPass123!", [staff_user]
    )

    # 1. Operaciones de asistencia permitidas para los 3 roles
    for s in [sesion_admin, sesion_coord, sesion_staff]:
        ServicioAutenticacionYPermisos.validar_permiso(s, PermisoOperacion.REGISTRAR_ASISTENCIA)
        ServicioAutenticacionYPermisos.validar_permiso(s, PermisoOperacion.CORREGIR_AUSENTE)
        ServicioAutenticacionYPermisos.validar_permiso(
            s, PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA
        )
        ServicioAutenticacionYPermisos.validar_permiso(
            s, PermisoOperacion.CONSULTAR_DASHBOARD_AFORO
        )

    # 2. Operaciones administrativas exclusivas de ADMIN
    ServicioAutenticacionYPermisos.validar_permiso(
        sesion_admin, PermisoOperacion.GESTIONAR_USUARIOS
    )
    ServicioAutenticacionYPermisos.validar_permiso(sesion_admin, PermisoOperacion.ASIGNAR_ROLES)
    ServicioAutenticacionYPermisos.validar_permiso(
        sesion_admin, PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA
    )
    ServicioAutenticacionYPermisos.validar_permiso(
        sesion_admin, PermisoOperacion.ADMINISTRAR_PERIODOS
    )

    # 3. Denegar operaciones administrativas a COORDINADOR y ADMIN_STAFF
    for s in [sesion_coord, sesion_staff]:
        with pytest.raises(AccesoDenegadoException):
            ServicioAutenticacionYPermisos.validar_permiso(s, PermisoOperacion.GESTIONAR_USUARIOS)
        with pytest.raises(AccesoDenegadoException):
            ServicioAutenticacionYPermisos.validar_permiso(s, PermisoOperacion.ASIGNAR_ROLES)
        with pytest.raises(AccesoDenegadoException):
            ServicioAutenticacionYPermisos.validar_permiso(
                s, PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA
            )
        with pytest.raises(AccesoDenegadoException):
            ServicioAutenticacionYPermisos.validar_permiso(s, PermisoOperacion.ADMINISTRAR_PERIODOS)


def test_rbac_sesion_cerrada_o_expirada(staff_user: Usuario) -> None:
    """PBI-15 Escenarios 7 y 9: Sesión cerrada o expirada es rechazada."""
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "jluna_qa", "StaffPass123!", [staff_user], duracion_minutos=60
    )

    # Cerrar sesión
    sesion_cerrada = ServicioAutenticacionYPermisos.cerrar_sesion(sesion)
    with pytest.raises(SesionInvalidaException, match="cerrada"):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion_cerrada, PermisoOperacion.REGISTRAR_ASISTENCIA
        )

    # Simular expiración de sesión
    tiempo_futuro = datetime.now(UTC) + timedelta(minutes=61)
    with pytest.raises(SesionInvalidaException, match="expirado"):
        ServicioAutenticacionYPermisos.validar_permiso(
            sesion, PermisoOperacion.REGISTRAR_ASISTENCIA, tiempo_actual=tiempo_futuro
        )


# --- PRUEBAS PBI-02: ROLES DINÁMICOS, ÚLTIMO ADMIN Y REVOCACIÓN DE SESIONES ---


def _rol_personalizado(codigo: str, *permisos: PermisoOperacion) -> Rol:
    return Rol(
        codigo=codigo,
        nombre=f"Rol {codigo}",
        descripcion=f"Rol personalizado {codigo}",
        permisos=frozenset(permisos),
    )


def _usuario_con_rol(codigo_rol: str) -> Usuario:
    pwd_hash, salt = hashear_password("OperadorPass2026")
    return Usuario(
        id=10,
        username=f"operador_{codigo_rol.lower()}",
        password_hash=pwd_hash,
        salt=salt,
        nombre_completo=f"Operador {codigo_rol}",
        rol=codigo_rol,
        estado=EstadoUsuario.ACTIVO,
    )


def test_pbi02_rol_personalizado_con_permisos_crea_usuario(admin_user: Usuario) -> None:
    """RN-01/RN-02: un rol personalizado activo con permisos administra cuentas."""
    rol_gestor = _rol_personalizado(
        "GESTOR_USUARIOS",
        PermisoOperacion.GESTIONAR_USUARIOS,
        PermisoOperacion.ASIGNAR_ROLES,
    )
    operador = _usuario_con_rol("GESTOR_USUARIOS")

    nuevo, aud = ServicioGestionUsuarios.crear_usuario(
        operador=operador,
        username="nuevo_gestor",
        password_plana="Segura2026",
        nombre_completo="Nuevo Gestor",
        rol=RolUsuario.ADMIN_STAFF,
        usuarios_existentes=[admin_user],
        roles=[rol_gestor],
    )

    assert nuevo.username == "nuevo_gestor"
    assert nuevo.rol == RolUsuario.ADMIN_STAFF
    assert aud.operacion == "CREAR_USUARIO"


def test_pbi02_rol_personalizado_sin_asignar_roles_no_crea_usuario(
    admin_user: Usuario,
) -> None:
    """RN-01: GESTIONAR_USUARIOS sin ASIGNAR_ROLES no permite crear cuentas."""
    rol_gestor = _rol_personalizado("GESTOR_USUARIOS", PermisoOperacion.GESTIONAR_USUARIOS)
    operador = _usuario_con_rol("GESTOR_USUARIOS")

    with pytest.raises(AccesoDenegadoException, match="ASIGNAR_ROLES"):
        ServicioGestionUsuarios.crear_usuario(
            operador=operador,
            username="sin_permiso",
            password_plana="Segura2026",
            nombre_completo="Sin Permiso",
            rol=RolUsuario.ADMIN_STAFF,
            usuarios_existentes=[admin_user],
            roles=[rol_gestor],
        )


def test_pbi02_modificar_rol_sin_asignar_roles_no_permite(
    staff_user: Usuario,
) -> None:
    """RN-01: cambiar el rol de una cuenta exige ASIGNAR_ROLES."""
    rol_gestor = _rol_personalizado("GESTOR_USUARIOS", PermisoOperacion.GESTIONAR_USUARIOS)
    operador = _usuario_con_rol("GESTOR_USUARIOS")

    with pytest.raises(AccesoDenegadoException, match="ASIGNAR_ROLES"):
        ServicioGestionUsuarios.modificar_usuario(
            operador=operador,
            usuario_target=staff_user,
            nuevo_rol=RolUsuario.COORDINADOR,
            roles=[rol_gestor],
        )


def test_pbi02_sin_gestionar_usuarios_no_cambia_estado(
    staff_user: Usuario,
) -> None:
    """RN-01: un rol personalizado sin GESTIONAR_USUARIOS no administra cuentas."""
    rol_consulta = _rol_personalizado(
        "CONSULTA_USUARIOS", PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA
    )
    operador = _usuario_con_rol("CONSULTA_USUARIOS")

    with pytest.raises(AccesoDenegadoException, match="GESTIONAR_USUARIOS"):
        ServicioGestionUsuarios.cambiar_estado(
            operador=operador,
            usuario_target=staff_user,
            nuevo_estado=EstadoUsuario.INACTIVO,
            roles=[rol_consulta],
        )


def test_pbi02_no_desactiva_ultimo_admin_activo(admin_user: Usuario) -> None:
    """RN-10: no se puede desactivar al último ADMIN activo del sistema."""
    with pytest.raises(UltimoAdminException, match="último administrador"):
        ServicioGestionUsuarios.cambiar_estado(
            operador=admin_user,
            usuario_target=admin_user,
            nuevo_estado=EstadoUsuario.INACTIVO,
            usuarios_existentes=[admin_user],
        )


def test_pbi02_permite_desactivar_admin_si_hay_otro_activo(admin_user: Usuario) -> None:
    """RN-10: con otro ADMIN activo la desactivación está permitida."""
    segundo_admin = replace(admin_user, id=99, username="admin_secundario")

    desactivado, aud = ServicioGestionUsuarios.cambiar_estado(
        operador=admin_user,
        usuario_target=segundo_admin,
        nuevo_estado=EstadoUsuario.INACTIVO,
        usuarios_existentes=[admin_user, segundo_admin],
    )

    assert desactivado.estado == EstadoUsuario.INACTIVO
    assert aud.operacion == "DESACTIVAR_CUENTA"


def test_pbi02_permite_desactivar_usuario_no_admin(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    """RN-10: la protección solo aplica a cuentas con rol ADMIN."""
    desactivado, _ = ServicioGestionUsuarios.cambiar_estado(
        operador=admin_user,
        usuario_target=staff_user,
        nuevo_estado=EstadoUsuario.INACTIVO,
        usuarios_existentes=[admin_user, staff_user],
    )

    assert desactivado.estado == EstadoUsuario.INACTIVO


def test_pbi02_admin_inactivo_no_cuenta_como_ultimo_activo(admin_user: Usuario) -> None:
    """RN-10: un ADMIN ya inactivo no bloquea la operación."""
    admin_inactivo = replace(
        admin_user,
        id=50,
        username="admin_viejo",
        estado=EstadoUsuario.INACTIVO,
    )

    desactivado, _ = ServicioGestionUsuarios.cambiar_estado(
        operador=admin_user,
        usuario_target=admin_inactivo,
        nuevo_estado=EstadoUsuario.INACTIVO,
        usuarios_existentes=[admin_user, admin_inactivo],
    )

    assert desactivado.estado == EstadoUsuario.INACTIVO


def test_pbi02_no_degrada_ultimo_admin(admin_user: Usuario) -> None:
    """RN-10: tampoco se puede cambiar de rol al último ADMIN activo."""
    with pytest.raises(UltimoAdminException, match="último administrador"):
        ServicioGestionUsuarios.modificar_usuario(
            operador=admin_user,
            usuario_target=admin_user,
            nuevo_rol=RolUsuario.COORDINADOR,
            usuarios_existentes=[admin_user],
        )


def test_pbi02_desactivar_cuenta_revoca_sesiones(admin_user: Usuario, staff_user: Usuario) -> None:
    """RN-09: desactivar una cuenta revoca de inmediato sus sesiones activas."""
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "jluna_qa", "StaffPass123!", [staff_user]
    )

    actualizado, aud, sesiones = ServicioGestionUsuarios.desactivar_y_revocar_sesiones(
        operador=admin_user,
        usuario_target=staff_user,
        sesiones=[sesion],
    )

    assert actualizado.estado == EstadoUsuario.INACTIVO
    assert aud.operacion == "DESACTIVAR_CUENTA"
    assert sesiones[0].activa is False


def test_pbi02_restablecer_password_revoca_sesiones(
    admin_user: Usuario, staff_user: Usuario
) -> None:
    """RN-09/RN-12: restablecer la credencial revoca las sesiones vigentes."""
    sesion = ServicioAutenticacionYPermisos.iniciar_sesion(
        "jluna_qa", "StaffPass123!", [staff_user]
    )

    actualizado, aud, sesiones = ServicioGestionUsuarios.restablecer_password_y_revocar_sesiones(
        operador=admin_user,
        usuario_target=staff_user,
        nueva_password_plana="NuevaClave2026",
        sesiones=[sesion],
    )

    assert actualizado.password_hash != staff_user.password_hash
    assert verificar_password("NuevaClave2026", actualizado.password_hash, actualizado.salt)
    assert aud.operacion == "RESTABLECER_CREDENCIAL"
    assert sesiones[0].activa is False


def test_pbi02_politica_password_unificada() -> None:
    """RN-05: política mínima de 8 caracteres y opción alfanumérica."""
    with pytest.raises(UsuarioException, match="al menos 8 caracteres"):
        validar_politica_password("Corta1")

    validar_politica_password("Segura2026")

    with pytest.raises(UsuarioException, match="letras y números"):
        validar_politica_password("sololetras", exigir_alfanumerico=True)

    validar_politica_password("Segura2026", exigir_alfanumerico=True)


def test_pbi02_crear_usuario_aplica_longitud_minima_configurable(
    admin_user: Usuario,
) -> None:
    """RN-05: la longitud mínima puede ajustarse de forma explícita."""
    with pytest.raises(UsuarioException, match="al menos 10 caracteres"):
        ServicioGestionUsuarios.crear_usuario(
            operador=admin_user,
            username="clave_corta",
            password_plana="Corta2026",
            nombre_completo="Clave Corta",
            rol=RolUsuario.ADMIN_STAFF,
            usuarios_existentes=[admin_user],
            longitud_minima=10,
        )


def test_pbi02_auditoria_no_expone_credenciales(admin_user: Usuario) -> None:
    """RN-13: los eventos de auditoría nunca incluyen contraseñas, hashes ni salts."""
    _, aud = ServicioGestionUsuarios.crear_usuario(
        operador=admin_user,
        username="auditado",
        password_plana="Segura2026",
        nombre_completo="Auditado",
        rol=RolUsuario.ADMIN_STAFF,
        usuarios_existentes=[admin_user],
    )

    prohibidas = {"password", "password_plana", "password_hash", "salt", "token"}
    assert not prohibidas.intersection(aud.detalle)

    with pytest.raises(UsuarioException, match="sensible"):
        EventoAuditoriaUsuario(
            id="aud-usr-test",
            admin_id=admin_user.id,
            admin_username=admin_user.username,
            fecha_hora=datetime.now(UTC),
            operacion="CREAR_USUARIO",
            usuario_afectado_id=2,
            usuario_afectado_username="auditado",
            detalle={"password": "secreto"},
        )


def test_pbi02_validar_admin_retrocompatible(
    admin_user: Usuario, coordinador_user: Usuario
) -> None:
    """Mantiene el contrato previo de validar_admin para código existente."""
    ServicioGestionUsuarios.validar_admin(admin_user)

    with pytest.raises(AccesoDenegadoException, match="Solo usuarios con rol ADMIN"):
        ServicioGestionUsuarios.validar_admin(coordinador_user)

    admin_inactivo = replace(admin_user, estado=EstadoUsuario.INACTIVO)
    with pytest.raises(CuentaInactivaException, match="no cuenta con una cuenta activa"):
        ServicioGestionUsuarios.validar_admin(admin_inactivo)
