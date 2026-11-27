"""Repositorios ORM SQLAlchemy 2.0 para seguridad, roles dinámicos y sesiones."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from src.dominio.usuarios import (
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolUsuario,
    SesionUsuario,
    Usuario,
)
from src.infraestructura.modelos import (
    PermisoModel,
    RolModel,
    RolPermisoModel,
    SesionUsuarioModel,
    UsuarioModel,
    hora_actual_utc,
)


def _normalizar_utc(fecha_hora: datetime) -> datetime:
    """Restaura o convierte una marca temporal a UTC explícito (compatible SQLite/PostgreSQL)."""
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=UTC)
    return fecha_hora.astimezone(UTC)


def _resolver_momento_utc(momento: datetime | None) -> datetime:
    if momento is None:
        return hora_actual_utc()
    return _normalizar_utc(momento)


def _codigo_rol_str(rol: RolUsuario | str) -> str:
    return rol.value if isinstance(rol, RolUsuario) else str(rol).strip().upper()


def _rol_a_dominio(codigo: str) -> RolUsuario | str:
    normalizado = codigo.strip().upper()
    try:
        return RolUsuario(normalizado)
    except ValueError:
        return normalizado


class RepositorioRoles:
    """Persistencia relacional para roles base/personalizados y sus permisos N:M (PBI-15)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: RolModel) -> Rol:
        permisos = frozenset(PermisoOperacion(rel.permiso_codigo) for rel in modelo.permisos_rel)
        return Rol(
            codigo=modelo.codigo,
            nombre=modelo.nombre,
            descripcion=modelo.descripcion,
            permisos=permisos,
            es_sistema=modelo.es_sistema,
            activo=modelo.activo,
        )

    def _asegurar_permisos(self, permisos: Iterable[PermisoOperacion]) -> None:
        codigos = {p.value for p in permisos}
        existentes = set(
            self._session.scalars(
                select(PermisoModel.codigo).where(PermisoModel.codigo.in_(codigos))
            ).all()
        )
        faltantes = codigos - existentes
        for codigo in sorted(faltantes):
            self._session.add(
                PermisoModel(
                    codigo=codigo,
                    modulo="general",
                    descripcion=codigo.replace("_", " ").capitalize(),
                )
            )
        if faltantes:
            self._session.flush()

    def guardar(self, rol: Rol) -> Rol:
        """Inserta o actualiza un rol y sincroniza su conjunto de permisos sin commit interno."""
        self._asegurar_permisos(rol.permisos)
        stmt = (
            select(RolModel)
            .options(selectinload(RolModel.permisos_rel))
            .where(RolModel.codigo == rol.codigo)
        )
        modelo = self._session.scalar(stmt)
        if modelo is None:
            modelo = RolModel(
                codigo=rol.codigo,
                nombre=rol.nombre,
                descripcion=rol.descripcion,
                es_sistema=rol.es_sistema,
                activo=rol.activo,
            )
            self._session.add(modelo)
            self._session.flush()
        else:
            modelo.nombre = rol.nombre
            modelo.descripcion = rol.descripcion
            modelo.es_sistema = rol.es_sistema
            modelo.activo = rol.activo

        codigos_deseados = {p.value for p in rol.permisos}
        actuales = {rel.permiso_codigo for rel in modelo.permisos_rel}
        modelo.permisos_rel = [
            rel for rel in modelo.permisos_rel if rel.permiso_codigo in codigos_deseados
        ]
        for codigo in sorted(codigos_deseados - actuales):
            modelo.permisos_rel.append(RolPermisoModel(rol_id=modelo.id, permiso_codigo=codigo))

        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_codigo(self, codigo: str) -> Rol | None:
        codigo_norm = codigo.strip().upper()
        stmt = (
            select(RolModel)
            .options(selectinload(RolModel.permisos_rel))
            .where(RolModel.codigo == codigo_norm)
        )
        modelo = self._session.scalar(stmt)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_id_por_codigo(self, codigo: str) -> int | None:
        codigo_norm = codigo.strip().upper()
        return self._session.scalar(select(RolModel.id).where(RolModel.codigo == codigo_norm))

    def listar(self, *, solo_activos: bool = False) -> list[Rol]:
        stmt = select(RolModel).options(selectinload(RolModel.permisos_rel)).order_by(RolModel.id)
        if solo_activos:
            stmt = stmt.where(RolModel.activo.is_(True))
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def eliminar(self, codigo: str) -> bool:
        codigo_norm = codigo.strip().upper()
        modelo = self._session.scalar(select(RolModel).where(RolModel.codigo == codigo_norm))
        if modelo is None:
            return False
        self._session.delete(modelo)
        self._session.flush()
        return True


class RepositorioUsuarios:
    """Persistencia relacional para cuentas de usuario del sistema (PBI-02 y PBI-15)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: UsuarioModel) -> Usuario:
        return Usuario(
            id=modelo.id,
            username=modelo.username,
            password_hash=modelo.password_hash,
            salt=modelo.salt,
            nombre_completo=modelo.nombre_completo,
            rol=_rol_a_dominio(modelo.rol),
            estado=EstadoUsuario(modelo.estado),
            creado_en=_normalizar_utc(modelo.creado_en),
        )

    def guardar(self, usuario: Usuario) -> Usuario:
        """Crea o actualiza un usuario vinculando su rol_id cuando existe en catálogo."""
        username_norm = usuario.username.strip().lower()
        rol_codigo = _codigo_rol_str(usuario.rol)
        rol_id = self._session.scalar(select(RolModel.id).where(RolModel.codigo == rol_codigo))
        activo = usuario.estado == EstadoUsuario.ACTIVO

        modelo = self._session.get(UsuarioModel, usuario.id) if usuario.id > 0 else None
        if modelo is None:
            modelo = UsuarioModel(
                username=username_norm,
                nombre_completo=usuario.nombre_completo,
                password_hash=usuario.password_hash,
                salt=usuario.salt,
                rol_id=rol_id,
                rol=rol_codigo,
                estado=usuario.estado.value,
                activo=activo,
                creado_en=_resolver_momento_utc(usuario.creado_en),
            )
            if usuario.id > 0:
                modelo.id = usuario.id
            self._session.add(modelo)
        else:
            modelo.username = username_norm
            modelo.nombre_completo = usuario.nombre_completo
            modelo.password_hash = usuario.password_hash
            modelo.salt = usuario.salt
            modelo.rol_id = rol_id
            modelo.rol = rol_codigo
            modelo.estado = usuario.estado.value
            modelo.activo = activo
            modelo.actualizado_en = hora_actual_utc()

        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, usuario_id: int) -> Usuario | None:
        modelo = self._session.get(UsuarioModel, usuario_id)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_por_username(self, username: str) -> Usuario | None:
        username_norm = username.strip().lower()
        modelo = self._session.scalar(
            select(UsuarioModel).where(UsuarioModel.username == username_norm)
        )
        return None if modelo is None else self._a_dominio(modelo)

    def listar(
        self,
        *,
        solo_activos: bool = False,
        rol: RolUsuario | str | None = None,
    ) -> list[Usuario]:
        stmt = select(UsuarioModel).order_by(UsuarioModel.id)
        if solo_activos:
            stmt = stmt.where(UsuarioModel.estado == EstadoUsuario.ACTIVO.value)
        if rol is not None:
            stmt = stmt.where(UsuarioModel.rol == _codigo_rol_str(rol))
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]


class RepositorioSesiones:
    """Persistencia de sesiones de servidor y revocación inmediata (PBI-15)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: SesionUsuarioModel) -> SesionUsuario:
        return SesionUsuario(
            token=modelo.token,
            usuario_id=modelo.usuario_id,
            username=modelo.usuario.username,
            rol=_rol_a_dominio(modelo.rol_codigo_snapshot),
            fecha_inicio=_normalizar_utc(modelo.fecha_inicio),
            fecha_expiracion=_normalizar_utc(modelo.fecha_expiracion),
            activa=modelo.activa,
        )

    def guardar(self, sesion: SesionUsuario) -> SesionUsuario:
        """Crea o actualiza una sesión de usuario sin confirmar la transacción."""
        rol_codigo = _codigo_rol_str(sesion.rol)
        fecha_inicio = _normalizar_utc(sesion.fecha_inicio)
        fecha_expiracion = _normalizar_utc(sesion.fecha_expiracion)

        modelo = self._session.get(SesionUsuarioModel, sesion.token)
        if modelo is None:
            modelo = SesionUsuarioModel(
                token=sesion.token,
                usuario_id=sesion.usuario_id,
                rol_codigo_snapshot=rol_codigo,
                fecha_inicio=fecha_inicio,
                fecha_expiracion=fecha_expiracion,
                activa=sesion.activa,
                revocada_en=None if sesion.activa else hora_actual_utc(),
            )
            self._session.add(modelo)
        else:
            modelo.rol_codigo_snapshot = rol_codigo
            modelo.fecha_inicio = fecha_inicio
            modelo.fecha_expiracion = fecha_expiracion
            if modelo.activa and not sesion.activa:
                modelo.revocada_en = hora_actual_utc()
            modelo.activa = sesion.activa

        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_token(self, token: str) -> SesionUsuario | None:
        stmt = (
            select(SesionUsuarioModel)
            .options(joinedload(SesionUsuarioModel.usuario))
            .where(SesionUsuarioModel.token == token)
        )
        modelo = self._session.scalar(stmt)
        return None if modelo is None else self._a_dominio(modelo)

    def listar_por_usuario(
        self, usuario_id: int, *, solo_activas: bool = False
    ) -> list[SesionUsuario]:
        stmt = (
            select(SesionUsuarioModel)
            .options(joinedload(SesionUsuarioModel.usuario))
            .where(SesionUsuarioModel.usuario_id == usuario_id)
            .order_by(SesionUsuarioModel.fecha_inicio)
        )
        if solo_activas:
            stmt = stmt.where(SesionUsuarioModel.activa.is_(True))
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def listar_activas(self) -> list[SesionUsuario]:
        stmt = (
            select(SesionUsuarioModel)
            .options(joinedload(SesionUsuarioModel.usuario))
            .where(SesionUsuarioModel.activa.is_(True))
            .order_by(SesionUsuarioModel.fecha_inicio)
        )
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]

    def revocar_por_token(self, token: str, *, revocada_en: datetime | None = None) -> bool:
        modelo = self._session.get(SesionUsuarioModel, token)
        if modelo is None or not modelo.activa:
            return False
        modelo.activa = False
        modelo.revocada_en = _resolver_momento_utc(revocada_en)
        self._session.flush()
        return True

    def revocar_por_usuario(self, usuario_id: int, *, revocada_en: datetime | None = None) -> int:
        momento = _resolver_momento_utc(revocada_en)
        modelos = self._session.scalars(
            select(SesionUsuarioModel).where(
                SesionUsuarioModel.usuario_id == usuario_id,
                SesionUsuarioModel.activa.is_(True),
            )
        ).all()
        for modelo in modelos:
            modelo.activa = False
            modelo.revocada_en = momento
        if modelos:
            self._session.flush()
        return len(modelos)

    def revocar_por_rol(
        self, rol_codigo: RolUsuario | str, *, revocada_en: datetime | None = None
    ) -> int:
        codigo = _codigo_rol_str(rol_codigo)
        momento = _resolver_momento_utc(revocada_en)
        modelos = self._session.scalars(
            select(SesionUsuarioModel).where(
                SesionUsuarioModel.rol_codigo_snapshot == codigo,
                SesionUsuarioModel.activa.is_(True),
            )
        ).all()
        for modelo in modelos:
            modelo.activa = False
            modelo.revocada_en = momento
        if modelos:
            self._session.flush()
        return len(modelos)
