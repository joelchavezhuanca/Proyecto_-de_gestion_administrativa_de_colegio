import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class RolUsuario(StrEnum):
    ADMIN = "ADMIN"
    COORDINADOR = "COORDINADOR"
    ADMIN_STAFF = "ADMIN_STAFF"


class EstadoUsuario(StrEnum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class PermisoOperacion(StrEnum):
    REGISTRAR_ASISTENCIA = "REGISTRAR_ASISTENCIA"
    CORREGIR_AUSENTE = "CORREGIR_AUSENTE"
    CONSULTAR_HISTORIAL_ASISTENCIA = "CONSULTAR_HISTORIAL_ASISTENCIA"
    CONSULTAR_DASHBOARD_AFORO = "CONSULTAR_DASHBOARD_AFORO"
    GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"
    ASIGNAR_ROLES = "ASIGNAR_ROLES"
    CONFIGURAR_CIERRE_ASISTENCIA = "CONFIGURAR_CIERRE_ASISTENCIA"
    ADMINISTRAR_PERIODOS = "ADMINISTRAR_PERIODOS"


# Matriz oficial de permisos de la especificación (Sección 15.3)
MATRIZ_PERMISOS: dict[RolUsuario, set[PermisoOperacion]] = {
    RolUsuario.ADMIN: {
        PermisoOperacion.REGISTRAR_ASISTENCIA,
        PermisoOperacion.CORREGIR_AUSENTE,
        PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
        PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
        PermisoOperacion.GESTIONAR_USUARIOS,
        PermisoOperacion.ASIGNAR_ROLES,
        PermisoOperacion.CONFIGURAR_CIERRE_ASISTENCIA,
        PermisoOperacion.ADMINISTRAR_PERIODOS,
    },
    RolUsuario.COORDINADOR: {
        PermisoOperacion.REGISTRAR_ASISTENCIA,
        PermisoOperacion.CORREGIR_AUSENTE,
        PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
        PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
    },
    RolUsuario.ADMIN_STAFF: {
        PermisoOperacion.REGISTRAR_ASISTENCIA,
        PermisoOperacion.CORREGIR_AUSENTE,
        PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
        PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
    },
}


class UsuarioException(Exception):
    """Excepción base para el módulo de usuarios y seguridad."""


class AccesoDenegadoException(UsuarioException):
    """Lanzada cuando un usuario intenta ejecutar una acción no permitida por su rol."""


class CredencialesInvalidasException(UsuarioException):
    """Lanzada ante un error en el nombre de usuario o contraseña."""


class CuentaInactivaException(UsuarioException):
    """Lanzada cuando una cuenta suspendida o inactiva intenta autenticarse u operar."""


class UsuarioDuplicadoException(UsuarioException):
    """Lanzada cuando se intenta crear una cuenta con un username ya existente."""


class UsuarioNoEncontradoException(UsuarioException):
    """Lanzada cuando la cuenta de usuario no existe."""


class RolInvalidoException(UsuarioException):
    """Lanzada cuando se intenta asignar o usar un rol no oficial."""


class SesionInvalidaException(UsuarioException):
    """Lanzada ante una sesión expirada, cerrada o inválida."""


def hora_actual_utc() -> datetime:
    return datetime.now(UTC)


def hashear_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Genera un hash seguro PBKDF2-HMAC-SHA256 con salt criptográfica."""
    if salt is None:
        salt = secrets.token_hex(16)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return hash_bytes.hex(), salt


def verificar_password(password: str, hash_almacenado: str, salt: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con el hash almacenado."""
    hash_calculado, _ = hashear_password(password, salt)
    return secrets.compare_digest(hash_calculado, hash_almacenado)


@dataclass(frozen=True)
class Usuario:
    id: int
    username: str
    password_hash: str
    salt: str
    nombre_completo: str
    rol: RolUsuario
    estado: EstadoUsuario = EstadoUsuario.ACTIVO
    creado_en: datetime | None = None


@dataclass(frozen=True)
class SesionUsuario:
    token: str
    usuario_id: int
    username: str
    rol: RolUsuario
    fecha_inicio: datetime
    fecha_expiracion: datetime
    activa: bool = True


@dataclass(frozen=True)
class EventoAuditoriaUsuario:
    id: str
    admin_id: int
    admin_username: str
    fecha_hora: datetime
    operacion: str
    usuario_afectado_id: int
    usuario_afectado_username: str
    detalle: dict[str, str]


class ServicioGestionUsuarios:
    """Implementa las reglas de negocio del PBI-02 (Gestión de Usuarios)."""

    @staticmethod
    def validar_admin(operador: Usuario) -> None:
        """Verifica que el operador sea un ADMIN activo."""
        if operador.estado != EstadoUsuario.ACTIVO:
            raise CuentaInactivaException("El administrador no cuenta con una cuenta activa.")
        if operador.rol != RolUsuario.ADMIN:
            raise AccesoDenegadoException("Solo usuarios con rol ADMIN pueden administrar cuentas.")

    @staticmethod
    def crear_usuario(
        operador: Usuario,
        username: str,
        password_plana: str,
        nombre_completo: str,
        rol: RolUsuario,
        usuarios_existentes: list[Usuario],
        fecha_hora: datetime | None = None,
    ) -> tuple[Usuario, EventoAuditoriaUsuario]:
        """Crea una nueva cuenta de usuario (RN-01 a RN-05)."""
        ServicioGestionUsuarios.validar_admin(operador)

        if not isinstance(rol, RolUsuario):
            raise RolInvalidoException(f"El rol {rol} no es un rol oficial permitido.")

        username_limpio = username.strip().lower()
        if not username_limpio:
            raise UsuarioException("El nombre de usuario no puede estar vacío.")

        if any(u.username.lower() == username_limpio for u in usuarios_existentes):
            raise UsuarioDuplicadoException(
                f"El nombre de usuario '{username}' ya está registrado."
            )

        if not password_plana or len(password_plana) < 6:
            raise UsuarioException("La credencial inicial debe tener al menos 6 caracteres.")

        pwd_hash, salt = hashear_password(password_plana)
        nuevo_id = max([u.id for u in usuarios_existentes], default=0) + 1
        momento = fecha_hora or hora_actual_utc()

        nuevo_usuario = Usuario(
            id=nuevo_id,
            username=username_limpio,
            password_hash=pwd_hash,
            salt=salt,
            nombre_completo=nombre_completo.strip(),
            rol=rol,
            estado=EstadoUsuario.ACTIVO,
            creado_en=momento,
        )

        auditoria = EventoAuditoriaUsuario(
            id=f"aud-usr-{uuid.uuid4().hex[:10]}",
            admin_id=operador.id,
            admin_username=operador.username,
            fecha_hora=momento,
            operacion="CREAR_USUARIO",
            usuario_afectado_id=nuevo_usuario.id,
            usuario_afectado_username=nuevo_usuario.username,
            detalle={"rol_asignado": rol.value, "nombre": nuevo_usuario.nombre_completo},
        )

        return nuevo_usuario, auditoria

    @staticmethod
    def modificar_usuario(
        operador: Usuario,
        usuario_target: Usuario,
        nuevo_nombre: str | None = None,
        nuevo_rol: RolUsuario | None = None,
        fecha_hora: datetime | None = None,
    ) -> tuple[Usuario, EventoAuditoriaUsuario]:
        """Modifica datos y/o rol de una cuenta existente (RN-06)."""
        ServicioGestionUsuarios.validar_admin(operador)

        detalle: dict[str, str] = {}
        nombre_final = usuario_target.nombre_completo
        if nuevo_nombre is not None and nuevo_nombre.strip():
            detalle["nombre_anterior"] = usuario_target.nombre_completo
            detalle["nombre_nuevo"] = nuevo_nombre.strip()
            nombre_final = nuevo_nombre.strip()

        rol_final = usuario_target.rol
        if nuevo_rol is not None:
            if not isinstance(nuevo_rol, RolUsuario):
                raise RolInvalidoException(f"El rol {nuevo_rol} no es válido.")
            detalle["rol_anterior"] = usuario_target.rol.value
            detalle["rol_nuevo"] = nuevo_rol.value
            rol_final = nuevo_rol

        usuario_modificado = Usuario(
            id=usuario_target.id,
            username=usuario_target.username,
            password_hash=usuario_target.password_hash,
            salt=usuario_target.salt,
            nombre_completo=nombre_final,
            rol=rol_final,
            estado=usuario_target.estado,
            creado_en=usuario_target.creado_en,
        )

        momento = fecha_hora or hora_actual_utc()
        auditoria = EventoAuditoriaUsuario(
            id=f"aud-usr-{uuid.uuid4().hex[:10]}",
            admin_id=operador.id,
            admin_username=operador.username,
            fecha_hora=momento,
            operacion="MODIFICAR_USUARIO",
            usuario_afectado_id=usuario_target.id,
            usuario_afectado_username=usuario_target.username,
            detalle=detalle,
        )

        return usuario_modificado, auditoria

    @staticmethod
    def cambiar_estado(
        operador: Usuario,
        usuario_target: Usuario,
        nuevo_estado: EstadoUsuario,
        fecha_hora: datetime | None = None,
    ) -> tuple[Usuario, EventoAuditoriaUsuario]:
        """Activa o desactiva una cuenta sin eliminar historial (RN-07, RN-11)."""
        ServicioGestionUsuarios.validar_admin(operador)

        usuario_actualizado = Usuario(
            id=usuario_target.id,
            username=usuario_target.username,
            password_hash=usuario_target.password_hash,
            salt=usuario_target.salt,
            nombre_completo=usuario_target.nombre_completo,
            rol=usuario_target.rol,
            estado=nuevo_estado,
            creado_en=usuario_target.creado_en,
        )

        momento = fecha_hora or hora_actual_utc()
        operacion_nombre = (
            "ACTIVAR_CUENTA" if nuevo_estado == EstadoUsuario.ACTIVO else "DESACTIVAR_CUENTA"
        )

        auditoria = EventoAuditoriaUsuario(
            id=f"aud-usr-{uuid.uuid4().hex[:10]}",
            admin_id=operador.id,
            admin_username=operador.username,
            fecha_hora=momento,
            operacion=operacion_nombre,
            usuario_afectado_id=usuario_target.id,
            usuario_afectado_username=usuario_target.username,
            detalle={
                "estado_anterior": usuario_target.estado.value,
                "estado_nuevo": nuevo_estado.value,
            },
        )

        return usuario_actualizado, auditoria

    @staticmethod
    def restablecer_password(
        operador: Usuario,
        usuario_target: Usuario,
        nueva_password_plana: str,
        fecha_hora: datetime | None = None,
    ) -> tuple[Usuario, EventoAuditoriaUsuario]:
        """Restablece la credencial sin conocer la contraseña anterior (RN-12)."""
        ServicioGestionUsuarios.validar_admin(operador)

        if not nueva_password_plana or len(nueva_password_plana) < 6:
            raise UsuarioException("La nueva contraseña debe tener al menos 6 caracteres.")

        pwd_hash, salt = hashear_password(nueva_password_plana)
        usuario_actualizado = Usuario(
            id=usuario_target.id,
            username=usuario_target.username,
            password_hash=pwd_hash,
            salt=salt,
            nombre_completo=usuario_target.nombre_completo,
            rol=usuario_target.rol,
            estado=usuario_target.estado,
            creado_en=usuario_target.creado_en,
        )

        momento = fecha_hora or hora_actual_utc()
        auditoria = EventoAuditoriaUsuario(
            id=f"aud-usr-{uuid.uuid4().hex[:10]}",
            admin_id=operador.id,
            admin_username=operador.username,
            fecha_hora=momento,
            operacion="RESTABLECER_CREDENCIAL",
            usuario_afectado_id=usuario_target.id,
            usuario_afectado_username=usuario_target.username,
            detalle={"accion": "Password restablecida por el administrador"},
        )

        return usuario_actualizado, auditoria

    @staticmethod
    def filtrar_usuarios(
        usuarios: list[Usuario],
        nombre: str | None = None,
        username: str | None = None,
        rol: RolUsuario | None = None,
        estado: EstadoUsuario | None = None,
    ) -> list[Usuario]:
        """Consulta y filtra usuarios por nombre, username, rol y estado (RN-09)."""
        resultados = usuarios
        if nombre:
            q_nombre = nombre.strip().lower()
            resultados = [u for u in resultados if q_nombre in u.nombre_completo.lower()]
        if username:
            q_user = username.strip().lower()
            resultados = [u for u in resultados if q_user in u.username.lower()]
        if rol:
            resultados = [u for u in resultados if u.rol == rol]
        if estado:
            resultados = [u for u in resultados if u.estado == estado]
        return resultados


class ServicioAutenticacionYPermisos:
    """Implementa el control de acceso RBAC y manejo de sesiones del PBI-15."""

    @staticmethod
    def iniciar_sesion(
        username: str,
        password_plana: str,
        usuarios: list[Usuario],
        duracion_minutos: int = 480,
        fecha_hora: datetime | None = None,
    ) -> SesionUsuario:
        """Autentica al usuario y crea una sesión válida en el servidor (RN-01 a RN-07)."""
        username_limpio = username.strip().lower()
        usuario = next((u for u in usuarios if u.username.lower() == username_limpio), None)

        if usuario is None or not verificar_password(
            password_plana, usuario.password_hash, usuario.salt
        ):
            raise CredencialesInvalidasException("Credenciales incorrectas.")

        if usuario.estado != EstadoUsuario.ACTIVO:
            raise CuentaInactivaException(
                "La cuenta se encuentra inactiva. Contacte al administrador."
            )

        momento = fecha_hora or hora_actual_utc()
        return SesionUsuario(
            token=f"tok-{secrets.token_hex(20)}",
            usuario_id=usuario.id,
            username=usuario.username,
            rol=usuario.rol,
            fecha_inicio=momento,
            fecha_expiracion=momento + timedelta(minutes=duracion_minutos),
            activa=True,
        )

    @staticmethod
    def cerrar_sesion(sesion: SesionUsuario) -> SesionUsuario:
        """Invalida la sesión actual del usuario (Escenario 9)."""
        return SesionUsuario(
            token=sesion.token,
            usuario_id=sesion.usuario_id,
            username=sesion.username,
            rol=sesion.rol,
            fecha_inicio=sesion.fecha_inicio,
            fecha_expiracion=sesion.fecha_expiracion,
            activa=False,
        )

    @staticmethod
    def validar_permiso(
        sesion: SesionUsuario,
        permiso: PermisoOperacion,
        tiempo_actual: datetime | None = None,
    ) -> None:
        """Valida rigurosamente la sesión y los permisos en el servidor (RN-08)."""
        if not sesion.activa:
            raise SesionInvalidaException("La sesión ha sido cerrada.")

        momento = tiempo_actual or hora_actual_utc()
        if momento > sesion.fecha_expiracion:
            raise SesionInvalidaException("La sesión ha expirado. Inicie sesión nuevamente.")

        permisos_rol = MATRIZ_PERMISOS.get(sesion.rol, set())
        if permiso not in permisos_rol:
            raise AccesoDenegadoException(
                f"El rol {sesion.rol.value} no tiene permiso para la operación '{permiso.value}'."
            )
