import hashlib
import re
import secrets
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
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
    CONFIGURAR_CIERRE_ASISTENCIA = "CONFIGURAR_CIERRE_ASISTENCIA"
    EJECUTAR_CIERRE_ASISTENCIA = "EJECUTAR_CIERRE_ASISTENCIA"
    ADMINISTRAR_CALENDARIO_ESCOLAR = "ADMINISTRAR_CALENDARIO_ESCOLAR"
    GESTIONAR_JUSTIFICACIONES = "GESTIONAR_JUSTIFICACIONES"
    ADMINISTRAR_PERIODOS = "ADMINISTRAR_PERIODOS"
    GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"
    GESTIONAR_ROLES = "GESTIONAR_ROLES"
    ASIGNAR_ROLES = "ASIGNAR_ROLES"
    CONSULTAR_AUDITORIA = "CONSULTAR_AUDITORIA"
    VERIFICAR_INTEGRIDAD_AUDITORIA = "VERIFICAR_INTEGRIDAD_AUDITORIA"
    NOTIFICAR_AUSENCIAS_MANUAL = "NOTIFICAR_AUSENCIAS_MANUAL"
    CONFIGURAR_NOTIFICACIONES_WHATSAPP = "CONFIGURAR_NOTIFICACIONES_WHATSAPP"
    GESTIONAR_MATRICULA = "GESTIONAR_MATRICULA"
    GESTIONAR_CARNETS = "GESTIONAR_CARNETS"
    GESTIONAR_PAGOS = "GESTIONAR_PAGOS"
    VER_ALERTA_PAGOS = "VER_ALERTA_PAGOS"
    GESTIONAR_ESTADOS_ACADEMICOS = "GESTIONAR_ESTADOS_ACADEMICOS"
    CONFIGURAR_MALLA_CURRICULAR = "CONFIGURAR_MALLA_CURRICULAR"
    ASIGNAR_DOCENTES = "ASIGNAR_DOCENTES"
    REGISTRAR_CALIFICACIONES = "REGISTRAR_CALIFICACIONES"
    CONSULTAR_CALIFICACIONES = "CONSULTAR_CALIFICACIONES"
    CONSULTAR_FICHA_ALUMNO = "CONSULTAR_FICHA_ALUMNO"
    EXPORTAR_ASISTENCIAS = "EXPORTAR_ASISTENCIAS"
    EMITIR_BOLETAS = "EMITIR_BOLETAS"


# Matriz oficial de permisos (docs/README.md, sección 2)
MATRIZ_PERMISOS: dict[RolUsuario, set[PermisoOperacion]] = {
    RolUsuario.ADMIN: set(PermisoOperacion),
    RolUsuario.COORDINADOR: {
        PermisoOperacion.REGISTRAR_ASISTENCIA,
        PermisoOperacion.CORREGIR_AUSENTE,
        PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
        PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
        PermisoOperacion.GESTIONAR_JUSTIFICACIONES,
        PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL,
        PermisoOperacion.GESTIONAR_CARNETS,
        PermisoOperacion.CONSULTAR_CALIFICACIONES,
        PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
        PermisoOperacion.EXPORTAR_ASISTENCIAS,
    },
    RolUsuario.ADMIN_STAFF: {
        PermisoOperacion.REGISTRAR_ASISTENCIA,
        PermisoOperacion.CORREGIR_AUSENTE,
        PermisoOperacion.CONSULTAR_HISTORIAL_ASISTENCIA,
        PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
        PermisoOperacion.GESTIONAR_JUSTIFICACIONES,
        PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL,
        PermisoOperacion.GESTIONAR_MATRICULA,
        PermisoOperacion.GESTIONAR_CARNETS,
        PermisoOperacion.VER_ALERTA_PAGOS,
        PermisoOperacion.CONSULTAR_CALIFICACIONES,
        PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
        PermisoOperacion.EXPORTAR_ASISTENCIAS,
        PermisoOperacion.EMITIR_BOLETAS,
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


class RolInactivoException(UsuarioException):
    """Lanzada cuando un rol personalizado desactivado intenta operar o iniciar sesión."""


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


def _codigo_rol(rol: RolUsuario | str) -> str:
    if isinstance(rol, RolUsuario):
        return rol.value
    return str(rol).strip().upper()


def _normalizar_codigo_rol(codigo: str) -> str:
    if not isinstance(codigo, str):
        raise RolInvalidoException("El código del rol debe ser texto.")
    normalizado = codigo.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalizado):
        raise RolInvalidoException(
            "El código del rol es inválido. Use letras, números y guiones bajos."
        )
    return normalizado


def _normalizar_permisos(permisos: Iterable[object]) -> frozenset[PermisoOperacion]:
    if not isinstance(permisos, Iterable) or isinstance(permisos, (str, bytes)):
        raise RolInvalidoException("Los permisos del rol deben ser una colección válida.")
    normalizados: set[PermisoOperacion] = set()
    for permiso in permisos:
        if isinstance(permiso, PermisoOperacion):
            normalizados.add(permiso)
        elif isinstance(permiso, str):
            try:
                normalizados.add(PermisoOperacion(permiso.strip().upper()))
            except ValueError as error:
                raise RolInvalidoException(
                    f"El permiso de operación '{permiso}' no existe en el catálogo oficial."
                ) from error
        else:
            raise RolInvalidoException("Cada permiso debe pertenecer al catálogo oficial.")
    if not normalizados:
        raise RolInvalidoException("El rol debe tener al menos un permiso válido.")
    return frozenset(normalizados)


@dataclass(frozen=True)
class Rol:
    codigo: str
    nombre: str
    descripcion: str
    permisos: frozenset[PermisoOperacion]
    es_sistema: bool = False
    activo: bool = True

    def __post_init__(self) -> None:
        codigo = _normalizar_codigo_rol(self.codigo)
        nombre = self.nombre.strip() if isinstance(self.nombre, str) else ""
        descripcion = self.descripcion.strip() if isinstance(self.descripcion, str) else ""
        if not nombre:
            raise RolInvalidoException("El nombre del rol es obligatorio.")
        if not descripcion:
            raise RolInvalidoException("La descripción del rol es obligatoria.")
        if not isinstance(self.es_sistema, bool) or not isinstance(self.activo, bool):
            raise RolInvalidoException("Los indicadores del rol deben ser booleanos.")
        permisos = _normalizar_permisos(self.permisos)
        object.__setattr__(self, "codigo", codigo)
        object.__setattr__(self, "nombre", nombre)
        object.__setattr__(self, "descripcion", descripcion)
        object.__setattr__(self, "permisos", permisos)


def _roles_base() -> tuple[Rol, ...]:
    metadatos: dict[RolUsuario, tuple[str, str]] = {
        RolUsuario.ADMIN: ("Administrador", "Control total del sistema"),
        RolUsuario.COORDINADOR: ("Coordinador", "Gestión académica y operativa"),
        RolUsuario.ADMIN_STAFF: ("Personal administrativo", "Gestión administrativa"),
    }
    return tuple(
        Rol(
            codigo=rol.value,
            nombre=metadatos[rol][0],
            descripcion=metadatos[rol][1],
            permisos=frozenset(MATRIZ_PERMISOS[rol]),
            es_sistema=True,
        )
        for rol in RolUsuario
    )


def _validar_rol_asignable(rol: RolUsuario | str, roles: Sequence[Rol]) -> RolUsuario | str:
    if isinstance(rol, RolUsuario):
        return rol
    codigo = _codigo_rol(rol)
    for disponible in roles:
        if disponible.codigo == codigo:
            if not disponible.activo:
                raise RolInactivoException(f"El rol {codigo} se encuentra inactivo.")
            return disponible.codigo
    raise RolInvalidoException(f"El rol {codigo} no es válido.")


@dataclass(frozen=True)
class Usuario:
    id: int
    username: str
    password_hash: str
    salt: str
    nombre_completo: str
    rol: RolUsuario | str
    estado: EstadoUsuario = EstadoUsuario.ACTIVO
    creado_en: datetime | None = None

    def __post_init__(self) -> None:
        if isinstance(self.rol, str) and not isinstance(self.rol, RolUsuario):
            object.__setattr__(self, "rol", _codigo_rol(self.rol))


@dataclass(frozen=True)
class SesionUsuario:
    token: str
    usuario_id: int
    username: str
    rol: RolUsuario | str
    fecha_inicio: datetime
    fecha_expiracion: datetime
    activa: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.rol, str) and not isinstance(self.rol, RolUsuario):
            object.__setattr__(self, "rol", _codigo_rol(self.rol))

    @property
    def rol_codigo(self) -> str:
        return _codigo_rol(self.rol)


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
        rol: RolUsuario | str,
        usuarios_existentes: list[Usuario],
        fecha_hora: datetime | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> tuple[Usuario, EventoAuditoriaUsuario]:
        """Crea una nueva cuenta de usuario (RN-01 a RN-05)."""
        ServicioGestionUsuarios.validar_admin(operador)

        rol_validado = _validar_rol_asignable(rol, roles or [])

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
            rol=rol_validado,
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
            detalle={
                "rol_asignado": _codigo_rol(rol_validado),
                "nombre": nuevo_usuario.nombre_completo,
            },
        )

        return nuevo_usuario, auditoria

    @staticmethod
    def modificar_usuario(
        operador: Usuario,
        usuario_target: Usuario,
        nuevo_nombre: str | None = None,
        nuevo_rol: RolUsuario | str | None = None,
        fecha_hora: datetime | None = None,
        roles: Sequence[Rol] | None = None,
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
            rol_validado = _validar_rol_asignable(nuevo_rol, roles or [])
            detalle["rol_anterior"] = _codigo_rol(usuario_target.rol)
            detalle["rol_nuevo"] = _codigo_rol(rol_validado)
            rol_final = rol_validado

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
        rol: RolUsuario | str | None = None,
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
            codigo = _codigo_rol(rol)
            resultados = [u for u in resultados if _codigo_rol(u.rol) == codigo]
        if estado:
            resultados = [u for u in resultados if u.estado == estado]
        return resultados


class ServicioGestionRoles:
    """Implementa el catálogo y la administración de roles del PBI-15."""

    @staticmethod
    def obtener_roles_base() -> tuple[Rol, ...]:
        """Devuelve los tres roles base inmutables del sistema."""
        return _roles_base()

    @staticmethod
    def _validar_operador(operador: Usuario, roles_existentes: Sequence[Rol]) -> None:
        if operador.estado != EstadoUsuario.ACTIVO:
            raise CuentaInactivaException("El operador no cuenta con una cuenta activa.")
        if not ServicioAutenticacionYPermisos.tiene_permiso(
            operador.rol,
            PermisoOperacion.GESTIONAR_ROLES,
            roles_existentes,
        ):
            raise AccesoDenegadoException("No tiene permiso para gestionar roles.")

    @staticmethod
    def _validar_rol_existente(rol: Rol, roles_existentes: Sequence[Rol]) -> None:
        if not any(disponible.codigo == rol.codigo for disponible in roles_existentes):
            raise RolInvalidoException(f"El rol {rol.codigo} no existe.")

    @staticmethod
    def _validar_rol_sistema(rol: Rol, accion: str) -> None:
        if rol.codigo == RolUsuario.ADMIN.value:
            raise RolInvalidoException(f"El rol ADMIN no puede {accion}.")
        if rol.es_sistema:
            raise RolInvalidoException(f"Los roles base del sistema no pueden {accion}.")

    @staticmethod
    def _auditoria(
        operador: Usuario,
        operacion: str,
        codigo: str,
        detalle: dict[str, str],
        fecha_hora: datetime | None,
    ) -> EventoAuditoriaUsuario:
        return EventoAuditoriaUsuario(
            id=f"aud-rol-{uuid.uuid4().hex[:10]}",
            admin_id=operador.id,
            admin_username=operador.username,
            fecha_hora=fecha_hora or hora_actual_utc(),
            operacion=operacion,
            usuario_afectado_id=0,
            usuario_afectado_username=codigo,
            detalle={"entidad": "ROL", "codigo": codigo, **detalle},
        )

    @staticmethod
    def _permisos_texto(permisos: frozenset[PermisoOperacion]) -> str:
        return ",".join(sorted(permiso.value for permiso in permisos))

    @staticmethod
    def crear_rol(
        operador: Usuario,
        codigo: str,
        nombre: str,
        descripcion: str,
        permisos: Iterable[PermisoOperacion | str],
        roles_existentes: Sequence[Rol],
        fecha_hora: datetime | None = None,
    ) -> tuple[Rol, EventoAuditoriaUsuario]:
        """Crea un rol personalizado con permisos válidos del catálogo."""
        ServicioGestionRoles._validar_operador(operador, roles_existentes)
        codigo_normalizado = _normalizar_codigo_rol(codigo)
        codigos_ocupados = {rol.codigo for rol in roles_existentes}
        codigos_ocupados.update(
            rol.codigo for rol in ServicioGestionRoles.obtener_roles_base()
        )
        if codigo_normalizado in codigos_ocupados:
            raise RolInvalidoException(f"El código de rol {codigo_normalizado} ya existe.")

        rol = Rol(
            codigo=codigo_normalizado,
            nombre=nombre,
            descripcion=descripcion,
            permisos=_normalizar_permisos(permisos),
        )
        auditoria = ServicioGestionRoles._auditoria(
            operador,
            "CREAR_ROL",
            rol.codigo,
            {
                "nombre": rol.nombre,
                "permisos": ServicioGestionRoles._permisos_texto(rol.permisos),
            },
            fecha_hora,
        )
        return rol, auditoria

    @staticmethod
    def actualizar_permisos_rol(
        operador: Usuario,
        rol: Rol,
        nuevos_permisos: Iterable[PermisoOperacion | str],
        roles_existentes: Sequence[Rol],
        fecha_hora: datetime | None = None,
    ) -> tuple[Rol, EventoAuditoriaUsuario]:
        """Actualiza los permisos de un rol personalizado."""
        ServicioGestionRoles._validar_operador(operador, roles_existentes)
        ServicioGestionRoles._validar_rol_existente(rol, roles_existentes)
        ServicioGestionRoles._validar_rol_sistema(rol, "modificarse")

        permisos_normalizados = _normalizar_permisos(nuevos_permisos)
        actualizado = replace(rol, permisos=permisos_normalizados)
        auditoria = ServicioGestionRoles._auditoria(
            operador,
            "MODIFICAR_ROL",
            rol.codigo,
            {
                "permisos_anteriores": ServicioGestionRoles._permisos_texto(rol.permisos),
                "permisos_nuevos": ServicioGestionRoles._permisos_texto(actualizado.permisos),
            },
            fecha_hora,
        )
        return actualizado, auditoria

    @staticmethod
    def cambiar_estado_rol(
        operador: Usuario,
        rol: Rol,
        activo: bool,
        roles_existentes: Sequence[Rol],
        fecha_hora: datetime | None = None,
    ) -> tuple[Rol, EventoAuditoriaUsuario]:
        """Activa o desactiva un rol personalizado."""
        ServicioGestionRoles._validar_operador(operador, roles_existentes)
        ServicioGestionRoles._validar_rol_existente(rol, roles_existentes)
        ServicioGestionRoles._validar_rol_sistema(rol, "cambiarse de estado")

        actualizado = replace(rol, activo=activo)
        operacion = "ACTIVAR_ROL" if activo else "DESACTIVAR_ROL"
        auditoria = ServicioGestionRoles._auditoria(
            operador,
            operacion,
            rol.codigo,
            {
                "estado_anterior": "ACTIVO" if rol.activo else "INACTIVO",
                "estado_nuevo": "ACTIVO" if actualizado.activo else "INACTIVO",
            },
            fecha_hora,
        )
        return actualizado, auditoria

    @staticmethod
    def eliminar_rol(
        operador: Usuario,
        rol: Rol,
        roles_existentes: Sequence[Rol],
        usuarios: Sequence[Usuario],
        fecha_hora: datetime | None = None,
    ) -> tuple[list[Rol], EventoAuditoriaUsuario]:
        """Elimina un rol personalizado solo si no tiene usuarios asignados."""
        ServicioGestionRoles._validar_operador(operador, roles_existentes)
        ServicioGestionRoles._validar_rol_existente(rol, roles_existentes)
        ServicioGestionRoles._validar_rol_sistema(rol, "eliminarse")

        if any(_codigo_rol(usuario.rol) == rol.codigo for usuario in usuarios):
            raise RolInvalidoException(
                f"El rol {rol.codigo} tiene usuarios asignados y no puede eliminarse."
            )

        restantes = [
            disponible
            for disponible in roles_existentes
            if disponible.codigo != rol.codigo
        ]
        auditoria = ServicioGestionRoles._auditoria(
            operador,
            "ELIMINAR_ROL",
            rol.codigo,
            {"accion": "ELIMINAR"},
            fecha_hora,
        )
        return restantes, auditoria


class ServicioAutenticacionYPermisos:
    """Implementa el control de acceso RBAC y manejo de sesiones del PBI-15."""

    @staticmethod
    def _validar_rol_para_sesion(
        rol: RolUsuario | str, roles: Sequence[Rol] | None
    ) -> None:
        if isinstance(rol, RolUsuario):
            return
        codigo = _codigo_rol(rol)
        encontrado = next(
            (disponible for disponible in (roles or []) if disponible.codigo == codigo),
            None,
        )
        if encontrado is None:
            raise RolInvalidoException(f"El rol {codigo} no es válido.")
        if not encontrado.activo:
            raise RolInactivoException(f"El rol {codigo} se encuentra inactivo.")

    @staticmethod
    def iniciar_sesion(
        username: str,
        password_plana: str,
        usuarios: list[Usuario],
        duracion_minutos: int = 480,
        fecha_hora: datetime | None = None,
        roles: Sequence[Rol] | None = None,
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

        ServicioAutenticacionYPermisos._validar_rol_para_sesion(usuario.rol, roles)

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
        return replace(sesion, activa=False)

    @staticmethod
    def revocar_sesiones_usuario(
        usuario_id: int, sesiones: Sequence[SesionUsuario]
    ) -> list[SesionUsuario]:
        """Revoca inmediatamente todas las sesiones de un usuario."""
        return [
            replace(sesion, activa=False) if sesion.usuario_id == usuario_id else sesion
            for sesion in sesiones
        ]

    @staticmethod
    def revocar_sesiones_por_rol(
        rol_codigo: str, sesiones: Sequence[SesionUsuario]
    ) -> list[SesionUsuario]:
        """Revoca las sesiones de todos los usuarios de un rol desactivado."""
        codigo = _codigo_rol(rol_codigo)
        return [
            replace(sesion, activa=False) if sesion.rol_codigo == codigo else sesion
            for sesion in sesiones
        ]

    @staticmethod
    def tiene_permiso(
        rol: RolUsuario | str | Rol,
        permiso: PermisoOperacion,
        roles: Sequence[Rol] | None = None,
    ) -> bool:
        """Evalúa un permiso en servidor; deny-by-default ante roles desconocidos."""
        if not isinstance(permiso, PermisoOperacion):
            return False
        if isinstance(rol, Rol):
            return rol.activo and permiso in rol.permisos
        if isinstance(rol, RolUsuario):
            return permiso in MATRIZ_PERMISOS.get(rol, set())
        codigo = _codigo_rol(rol)
        try:
            rol_base = RolUsuario(codigo)
        except ValueError:
            rol_base = None
        if rol_base is not None:
            return permiso in MATRIZ_PERMISOS.get(rol_base, set())
        if roles is None:
            return False
        encontrado = next(
            (disponible for disponible in roles if disponible.codigo == codigo),
            None,
        )
        return bool(encontrado and encontrado.activo and permiso in encontrado.permisos)

    @staticmethod
    def validar_permiso(
        sesion: SesionUsuario,
        permiso: PermisoOperacion,
        tiempo_actual: datetime | None = None,
        usuario_actual: Usuario | None = None,
        rol_actual: Rol | None = None,
        roles: Sequence[Rol] | None = None,
    ) -> None:
        """Valida rigurosamente la sesión, la revocación y los permisos (RN-06 a RN-08)."""
        if not sesion.activa:
            raise SesionInvalidaException("La sesión ha sido cerrada.")

        momento = tiempo_actual or hora_actual_utc()
        if momento > sesion.fecha_expiracion:
            raise SesionInvalidaException("La sesión ha expirado. Inicie sesión nuevamente.")

        if usuario_actual is not None:
            if usuario_actual.id != sesion.usuario_id:
                raise SesionInvalidaException("La sesión fue revocada.")
            if usuario_actual.estado != EstadoUsuario.ACTIVO:
                raise SesionInvalidaException("La sesión fue revocada.")
            if _codigo_rol(usuario_actual.rol) != sesion.rol_codigo:
                raise SesionInvalidaException("La sesión fue revocada.")

        if rol_actual is not None and not rol_actual.activo:
            raise AccesoDenegadoException("El rol asignado no está activo.")

        rol_efectivo: RolUsuario | str | Rol = rol_actual or sesion.rol
        if not ServicioAutenticacionYPermisos.tiene_permiso(rol_efectivo, permiso, roles):
            raise AccesoDenegadoException(
                f"El rol {sesion.rol_codigo} no tiene permiso para "
                f"la operación '{permiso.value}'."
            )
