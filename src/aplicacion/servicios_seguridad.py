"""Servicios de aplicación de Seguridad (PBI-02, PBI-15, PBI-16).

Casos de uso transaccionales sobre SQLAlchemy ``Session`` que reutilizan la
lógica pura de dominio (:mod:`src.dominio.usuarios`, :mod:`src.dominio.auditoria`)
y persisten con atomicidad mediante :class:`~src.aplicacion.uow.SqlAlchemyUnitOfWork`.

Incluye:

* **Login / logout / validación de sesión en servidor** con sesiones persistidas
  en ``sesiones_usuario`` (PBI-15).
* **CRUD de roles personalizados** (RBAC dinámico) con revocación de sesiones.
* **CRUD de usuarios** con revocación de sesiones al desactivar.
* **Consulta e integridad de auditoría** (PBI-16).

**Regla crítica (PBI-16):** toda operación sensible persiste su evento de
auditoría inmutable en la *misma* transacción; si falla la auditoría se hace
``rollback()`` de todo.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.aplicacion.uow import SqlAlchemyUnitOfWork
from src.dominio.asistencia import UsuarioOperador
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    ContextoAcademicoAuditoria,
    FiltroAuditoria,
    RegistroAuditoria,
    ResultadoAuditoria,
    ResultadoVerificacionIntegridad,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.usuarios import (
    CredencialesInvalidasException,
    EstadoUsuario,
    PermisoOperacion,
    Rol,
    RolInvalidoException,
    RolUsuario,
    ServicioAutenticacionYPermisos,
    ServicioGestionRoles,
    ServicioGestionUsuarios,
    SesionInvalidaException,
    SesionUsuario,
    Usuario,
    UsuarioNoEncontradoException,
    verificar_password,
)
from src.infraestructura.modelos import (
    AuditoriaEventoModel,
    RolModel,
    RolPermisoModel,
    SesionUsuarioModel,
    UsuarioModel,
)

__all__ = [
    "FabricaSesion",
    "RelojServidor",
    "ResultadoAuditoria",
    "ServicioSeguridad",
    "auditoria_model_a_dominio",
    "registrar_auditoria_pbi16",
    "rol_model_a_dominio",
    "sesion_model_a_dominio",
    "usuario_model_a_dominio",
    "usuario_model_a_operador",
]

FabricaSesion = Callable[[], Session]
RelojServidor = Callable[[], datetime]

ROL_SYSTEM = "SYSTEM"


def hora_actual_lima() -> datetime:
    """Hora del servidor normalizada a America/Lima (UTC-5)."""
    return datetime.now(ZONA_HORARIA_LIMA)


def hora_actual_utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Conversiones ORM -> dominio
# ---------------------------------------------------------------------------


def rol_codigo(rol: object) -> str:
    """Normaliza un rol (``RolUsuario``/``Rol``/``str``) a su código en mayúsculas."""
    valor = getattr(rol, "value", rol)
    if isinstance(valor, Rol):  # pragma: no cover - defensivo
        return valor.codigo
    return str(valor).strip().upper()


def usuario_model_a_dominio(modelo: UsuarioModel) -> Usuario:
    try:
        estado = EstadoUsuario(modelo.estado)
    except ValueError:
        estado = EstadoUsuario.INACTIVO
    return Usuario(
        id=modelo.id,
        username=modelo.username,
        password_hash=modelo.password_hash,
        salt=modelo.salt or "",
        nombre_completo=modelo.nombre_completo or "",
        rol=modelo.rol,
        estado=estado,
        creado_en=modelo.creado_en,
    )


def usuario_model_a_operador(modelo: UsuarioModel) -> UsuarioOperador:
    activo = bool(modelo.activo) and modelo.estado == EstadoUsuario.ACTIVO.value
    return UsuarioOperador(
        id=modelo.id,
        username=modelo.username,
        rol=modelo.rol,
        activo=activo,
    )


def rol_model_a_dominio(modelo: RolModel, session: Session | None = None) -> Rol:
    permisos: set[PermisoOperacion] = set()
    if session is not None:
        vinculos = list(session.scalars(select(RolPermisoModel).filter_by(rol_id=modelo.id)).all())
    else:
        vinculos = list(modelo.permisos_rel or [])
    for vinculo in vinculos:
        codigo = vinculo.permiso_codigo
        try:
            permisos.add(PermisoOperacion(codigo))
        except ValueError:  # permiso desconocido: se ignora (deny-by-default)
            continue
    return Rol(
        codigo=modelo.codigo,
        nombre=modelo.nombre or modelo.codigo,
        descripcion=modelo.descripcion or modelo.codigo,
        permisos=frozenset(permisos),
        es_sistema=bool(modelo.es_sistema),
        activo=bool(modelo.activo),
    )


def sesion_model_a_dominio(modelo: SesionUsuarioModel) -> SesionUsuario:
    return SesionUsuario(
        token=modelo.token,
        usuario_id=modelo.usuario_id,
        username=modelo.usuario.username if modelo.usuario is not None else "",
        rol=modelo.rol_codigo_snapshot,
        fecha_inicio=modelo.fecha_inicio,
        fecha_expiracion=modelo.fecha_expiracion,
        activa=bool(modelo.activa),
    )


def auditoria_model_a_dominio(modelo: AuditoriaEventoModel) -> RegistroAuditoria:
    detalle: dict[str, object] = {}
    if modelo.detalle_json:
        try:
            cargado = json.loads(modelo.detalle_json)
            if isinstance(cargado, dict):
                detalle = cargado
        except (ValueError, TypeError):
            detalle = {}
    contexto: ContextoAcademicoAuditoria | None = None
    if modelo.contexto_academico:
        try:
            datos = json.loads(modelo.contexto_academico)
            if isinstance(datos, dict):
                contexto = ContextoAcademicoAuditoria(
                    nivel=str(datos.get("nivel", "")),
                    grado=str(datos.get("grado", "")),
                    seccion=str(datos.get("seccion", "")),
                )
        except (ValueError, TypeError):
            contexto = None
    return RegistroAuditoria(
        id=modelo.id,
        secuencia=modelo.secuencia,
        fecha_hora=modelo.fecha_hora,
        usuario_id=modelo.usuario_id,
        rol_ejecutante=modelo.rol_ejecutante,
        operacion=TipoOperacionAuditoria(modelo.operacion),
        entidad=modelo.entidad,
        entidad_id=modelo.entidad_id,
        resultado=ResultadoAuditoria(modelo.resultado),
        detalle=detalle,
        alumno_id=modelo.alumno_id,
        metodo_asistencia=modelo.metodo_asistencia,
        contexto_academico=contexto,
        estado_anterior=modelo.estado_anterior,
        estado_nuevo=modelo.estado_nuevo,
        motivo=modelo.motivo,
        hash_anterior=modelo.hash_anterior,
        hash_integridad=modelo.hash_integridad,
    )


def _auditoria_a_model(registro: RegistroAuditoria) -> AuditoriaEventoModel:
    contexto_json: str | None = None
    if registro.contexto_academico is not None:
        contexto_json = json.dumps(
            {
                "nivel": registro.contexto_academico.nivel,
                "grado": registro.contexto_academico.grado,
                "seccion": registro.contexto_academico.seccion,
            },
            ensure_ascii=False,
        )
    detalle_json = json.dumps(
        _jsonable(registro.detalle), sort_keys=True, ensure_ascii=False, default=str
    )
    return AuditoriaEventoModel(
        id=registro.id,
        secuencia=registro.secuencia,
        fecha_hora=registro.fecha_hora.astimezone(ZONA_HORARIA_LIMA).replace(tzinfo=None),
        usuario_id=registro.usuario_id,
        rol_ejecutante=registro.rol_ejecutante,
        operacion=registro.operacion.value,
        entidad=registro.entidad,
        entidad_id=registro.entidad_id,
        metodo_asistencia=registro.metodo_asistencia,
        alumno_id=registro.alumno_id,
        contexto_academico=contexto_json,
        estado_anterior=registro.estado_anterior,
        estado_nuevo=registro.estado_nuevo,
        motivo=registro.motivo,
        resultado=registro.resultado.value,
        detalle_json=detalle_json,
        hash_anterior=registro.hash_anterior,
        hash_integridad=registro.hash_integridad,
    )


def _jsonable(valor: object) -> object:
    if isinstance(valor, ContextoAcademicoAuditoria):
        return {
            "nivel": valor.nivel,
            "grado": valor.grado,
            "seccion": valor.seccion,
        }
    if isinstance(valor, Mapping):
        return {str(clave): _jsonable(item) for clave, item in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in valor]
    if isinstance(valor, datetime):
        return valor.isoformat()
    return valor


# ---------------------------------------------------------------------------
# Auditoría PBI-16 transaccional
# ---------------------------------------------------------------------------


def _eventos_existentes(session: Session) -> list[RegistroAuditoria]:
    filas = session.scalars(
        select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia)
    ).all()
    return [auditoria_model_a_dominio(fila) for fila in filas]


def registrar_auditoria_pbi16(
    session: Session,
    *,
    usuario_id: int,
    rol_ejecutante: str,
    operacion: TipoOperacionAuditoria | str,
    entidad: str,
    entidad_id: str,
    resultado: ResultadoAuditoria = ResultadoAuditoria.CONFIRMADA,
    fecha_hora: datetime | None = None,
    detalle: dict[str, object] | None = None,
    alumno_id: int | None = None,
    metodo_asistencia: str | None = None,
    contexto_academico: ContextoAcademicoAuditoria | None = None,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
    motivo: str | None = None,
    persistir_extra: Callable[[RegistroAuditoria], None] | None = None,
) -> RegistroAuditoria:
    """Registra un evento inmutable encadenado por SHA-256 y lo persiste.

    El evento se inserta y hace ``flush`` dentro de la transacción activa. Si la
    persistencia falla, el dominio eleva ``ErrorRegistroAuditoriaException`` y
    el llamador debe hacer ``rollback()`` (ver :class:`SqlAlchemyUnitOfWork`).
    """
    eventos = _eventos_existentes(session)

    def _persistir(registro: RegistroAuditoria) -> None:
        session.add(_auditoria_a_model(registro))
        session.flush()
        if persistir_extra is not None:
            persistir_extra(registro)

    return ServicioAuditoria.registrar_evento(
        usuario_id=usuario_id,
        rol_ejecutante=rol_ejecutante,
        operacion=operacion,
        entidad=entidad,
        entidad_id=entidad_id,
        resultado=resultado,
        fecha_hora=fecha_hora or hora_actual_lima(),
        eventos_existentes=eventos,
        detalle=detalle,
        alumno_id=alumno_id,
        metodo_asistencia=metodo_asistencia,
        contexto_academico=contexto_academico,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        motivo=motivo,
        persistir=_persistir,
    )


# ---------------------------------------------------------------------------
# Servicio de seguridad
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CredencialesRegistroUsuario:
    """Datos de entrada para crear un usuario (nunca se persiste la contraseña plana)."""

    username: str
    password_plana: str
    nombre_completo: str
    rol: RolUsuario | str


class ServicioSeguridad:
    """Casos de uso transaccionales de seguridad con persistencia SQLAlchemy."""

    def __init__(
        self,
        session_factory: FabricaSesion,
        *,
        reloj: RelojServidor = hora_actual_lima,
        duracion_sesion_minutos: int = 480,
    ) -> None:
        self._session_factory = session_factory
        self._reloj = reloj
        self._duracion_sesion_minutos = duracion_sesion_minutos

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _ahora(self) -> datetime:
        return self._reloj()

    def _roles(self, session: Session) -> list[Rol]:
        return [rol_model_a_dominio(m, session) for m in session.scalars(select(RolModel)).all()]

    def _usuarios(self, session: Session) -> list[Usuario]:
        return [usuario_model_a_dominio(m) for m in session.scalars(select(UsuarioModel)).all()]

    def _usuario_operador(self, session: Session, usuario_id: int) -> Usuario:
        modelo = session.get(UsuarioModel, usuario_id)
        if modelo is None:
            raise UsuarioNoEncontradoException(f"El usuario {usuario_id} no existe.")
        return usuario_model_a_dominio(modelo)

    def _modelo_usuario(self, session: Session, usuario_id: int) -> UsuarioModel:
        modelo = session.get(UsuarioModel, usuario_id)
        if modelo is None:
            raise UsuarioNoEncontradoException(f"El usuario {usuario_id} no existe.")
        return modelo

    # ------------------------------------------------------------------
    # Login / logout / sesión en servidor (PBI-15)
    # ------------------------------------------------------------------

    def iniciar_sesion(
        self,
        username: str,
        password_plana: str,
        *,
        duracion_minutos: int | None = None,
        fecha_hora: datetime | None = None,
    ) -> SesionUsuario:
        """Autentica y crea una sesión persistida en ``sesiones_usuario`` (atómico + auditado)."""
        momento = fecha_hora or self._ahora()
        duracion = duracion_minutos or self._duracion_sesion_minutos
        username_limpio = (username or "").strip().lower()

        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            modelo = session.scalars(
                select(UsuarioModel).filter_by(username=username_limpio)
            ).first()

            # Fallo de credenciales: audita ACCESO_DENEGADO sin filtrar datos sensibles.
            if modelo is None or not verificar_password(
                password_plana, modelo.password_hash, modelo.salt or ""
            ):
                registrar_auditoria_pbi16(
                    session,
                    usuario_id=modelo.id if modelo is not None else 0,
                    rol_ejecutante=modelo.rol if modelo is not None else ROL_SYSTEM,
                    operacion=TipoOperacionAuditoria.ACCESO_DENEGADO,
                    entidad="SESION_USUARIO",
                    entidad_id=str(modelo.id if modelo is not None else username_limpio),
                    resultado=ResultadoAuditoria.FALLIDA,
                    fecha_hora=momento,
                    detalle={"motivo": "credenciales_invalidas"},
                )
                # Commit del registro de acceso denegado, luego error.
                uow.commit()
                raise CredencialesInvalidasException("Credenciales incorrectas.")

            usuario = usuario_model_a_dominio(modelo)
            if not (modelo.activo and usuario.estado == EstadoUsuario.ACTIVO):
                registrar_auditoria_pbi16(
                    session,
                    usuario_id=usuario.id,
                    rol_ejecutante=rol_codigo(usuario.rol),
                    operacion=TipoOperacionAuditoria.ACCESO_DENEGADO,
                    entidad="SESION_USUARIO",
                    entidad_id=str(usuario.id),
                    resultado=ResultadoAuditoria.FALLIDA,
                    fecha_hora=momento,
                    detalle={"motivo": "cuenta_inactiva"},
                )
                uow.commit()
                raise CredencialesInvalidasException("Credenciales incorrectas.")

            # Reutiliza la validación de rol del dominio (rol activo, roles personalizados).
            ServicioAutenticacionYPermisos._validar_rol_para_sesion(  # noqa: SLF001
                usuario.rol, self._roles(session)
            )

            token = f"tok-{secrets.token_hex(20)}"
            sesion_modelo = SesionUsuarioModel(
                token=token,
                usuario_id=usuario.id,
                rol_codigo_snapshot=rol_codigo(usuario.rol),
                fecha_inicio=momento,
                fecha_expiracion=momento + timedelta(minutes=duracion),
                activa=True,
            )
            session.add(sesion_modelo)

            registrar_auditoria_pbi16(
                session,
                usuario_id=usuario.id,
                rol_ejecutante=rol_codigo(usuario.rol),
                operacion=TipoOperacionAuditoria.INICIAR_SESION,
                entidad="SESION_USUARIO",
                entidad_id=str(usuario.id),
                fecha_hora=momento,
                detalle={"username": usuario.username},
            )
            uow.commit()

            return SesionUsuario(
                token=token,
                usuario_id=usuario.id,
                username=usuario.username,
                rol=usuario.rol,
                fecha_inicio=momento,
                fecha_expiracion=momento + timedelta(minutes=duracion),
                activa=True,
            )

    def cerrar_sesion(self, token: str, *, fecha_hora: datetime | None = None) -> SesionUsuario:
        """Invalida la sesión actual y la persiste revocada (auditado)."""
        momento = fecha_hora or self._ahora()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            modelo = session.get(SesionUsuarioModel, token)
            if modelo is None:
                raise SesionInvalidaException("La sesión no existe.")
            usuario = session.get(UsuarioModel, modelo.usuario_id)
            rol = rol_codigo(usuario.rol) if usuario is not None else modelo.rol_codigo_snapshot

            modelo.activa = False
            modelo.revocada_en = momento

            registrar_auditoria_pbi16(
                session,
                usuario_id=modelo.usuario_id,
                rol_ejecutante=rol,
                operacion=TipoOperacionAuditoria.CERRAR_SESION,
                entidad="SESION_USUARIO",
                entidad_id=str(modelo.usuario_id),
                fecha_hora=momento,
            )
            uow.commit()

            return SesionUsuario(
                token=modelo.token,
                usuario_id=modelo.usuario_id,
                username=usuario.username if usuario is not None else "",
                rol=modelo.rol_codigo_snapshot,
                fecha_inicio=modelo.fecha_inicio,
                fecha_expiracion=modelo.fecha_expiracion,
                activa=False,
            )

    def validar_sesion(
        self,
        token: str,
        *,
        permiso: PermisoOperacion | None = None,
        tiempo_actual: datetime | None = None,
    ) -> SesionUsuario:
        """Valida sesión activa, no expirada, no revocada, usuario/rol activos (+ permiso)."""
        momento = tiempo_actual or self._ahora()
        session = self._session_factory()
        try:
            modelo = session.get(SesionUsuarioModel, token)
            if modelo is None or not modelo.activa:
                raise SesionInvalidaException("La sesión ha sido cerrada o no existe.")
            if momento > _como_aware(modelo.fecha_expiracion):
                raise SesionInvalidaException("La sesión ha expirado. Inicie sesión nuevamente.")

            usuario = session.get(UsuarioModel, modelo.usuario_id)
            if usuario is None:
                raise SesionInvalidaException("La sesión fue revocada.")
            if not (usuario.activo and usuario.estado == EstadoUsuario.ACTIVO.value):
                raise SesionInvalidaException("La sesión fue revocada.")
            if rol_codigo(usuario.rol) != rol_codigo(modelo.rol_codigo_snapshot):
                raise SesionInvalidaException("La sesión fue revocada.")

            roles = self._roles(session)
            rol_actual = next((r for r in roles if r.codigo == rol_codigo(usuario.rol)), None)
            if rol_actual is not None and not rol_actual.activo:
                raise SesionInvalidaException("El rol asignado no está activo.")

            sesion_dominio = SesionUsuario(
                token=modelo.token,
                usuario_id=modelo.usuario_id,
                username=usuario.username,
                rol=modelo.rol_codigo_snapshot,
                fecha_inicio=_como_aware(modelo.fecha_inicio),
                fecha_expiracion=_como_aware(modelo.fecha_expiracion),
                activa=True,
            )

            if permiso is not None:
                ServicioAutenticacionYPermisos.validar_permiso(
                    sesion_dominio,
                    permiso,
                    tiempo_actual=momento,
                    usuario_actual=usuario_model_a_dominio(usuario),
                    rol_actual=rol_actual,
                    roles=roles,
                )
            return sesion_dominio
        finally:
            session.close()

    # ------------------------------------------------------------------
    # CRUD de roles personalizados (PBI-15) + revocación de sesiones
    # ------------------------------------------------------------------

    def listar_roles(self) -> list[Rol]:
        session = self._session_factory()
        try:
            return self._roles(session)
        finally:
            session.close()

    def crear_rol(
        self,
        operador_id: int,
        *,
        codigo: str,
        nombre: str,
        descripcion: str,
        permisos: Iterable[PermisoOperacion | str],
        fecha_hora: datetime | None = None,
    ) -> Rol:
        momento = fecha_hora or self._ahora()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            roles = self._roles(session)

            rol, auditoria = ServicioGestionRoles.crear_rol(
                operador=operador,
                codigo=codigo,
                nombre=nombre,
                descripcion=descripcion,
                permisos=list(permisos),
                roles_existentes=roles,
                fecha_hora=momento,
            )

            modelo = RolModel(
                codigo=rol.codigo,
                nombre=rol.nombre,
                descripcion=rol.descripcion,
                es_sistema=False,
                activo=True,
            )
            session.add(modelo)
            session.flush()
            for permiso in rol.permisos:
                session.add(RolPermisoModel(rol_id=modelo.id, permiso_codigo=permiso.value))

            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return rol

    def modificar_rol(
        self,
        operador_id: int,
        *,
        codigo: str,
        nombre: str | None = None,
        descripcion: str | None = None,
        permisos: Iterable[PermisoOperacion | str] | None = None,
        fecha_hora: datetime | None = None,
    ) -> Rol:
        momento = fecha_hora or self._ahora()
        codigo_norm = codigo.strip().upper()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.scalars(select(RolModel).filter_by(codigo=codigo_norm)).first()
            if modelo is None:
                raise RolInvalidoException(f"El rol {codigo_norm} no existe.")
            rol_actual = rol_model_a_dominio(modelo, session)

            rol_modificado = rol_actual
            auditoria = None
            if permisos is not None:
                rol_modificado, auditoria = ServicioGestionRoles.actualizar_permisos_rol(
                    operador=operador,
                    rol=rol_actual,
                    nuevos_permisos=list(permisos),
                    roles_existentes=roles,
                    fecha_hora=momento,
                )
                # reemplazar permisos en BD
                for vinculo in list(modelo.permisos_rel):
                    session.delete(vinculo)
                session.flush()
                for permiso in rol_modificado.permisos:
                    session.add(RolPermisoModel(rol_id=modelo.id, permiso_codigo=permiso.value))

            if nombre is not None and nombre.strip():
                modelo.nombre = nombre.strip()
            if descripcion is not None and descripcion.strip():
                modelo.descripcion = descripcion.strip()

            if auditoria is not None:
                self._persistir_auditoria_usuario(
                    session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
                )
            uow.commit()

            session.refresh(modelo)
            return rol_model_a_dominio(modelo, session)

    def activar_rol(
        self, operador_id: int, *, codigo: str, fecha_hora: datetime | None = None
    ) -> Rol:
        return self._cambiar_estado_rol(operador_id, codigo, True, fecha_hora)

    def desactivar_rol(
        self, operador_id: int, *, codigo: str, fecha_hora: datetime | None = None
    ) -> Rol:
        """Desactiva un rol personalizado y **revoca sus sesiones** en BD (regla crítica)."""
        return self._cambiar_estado_rol(operador_id, codigo, False, fecha_hora)

    def _cambiar_estado_rol(
        self, operador_id: int, codigo: str, activo: bool, fecha_hora: datetime | None
    ) -> Rol:
        momento = fecha_hora or self._ahora()
        codigo_norm = codigo.strip().upper()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.scalars(select(RolModel).filter_by(codigo=codigo_norm)).first()
            if modelo is None:
                raise RolInvalidoException(f"El rol {codigo_norm} no existe.")
            rol_actual = rol_model_a_dominio(modelo, session)

            rol_modificado, auditoria = ServicioGestionRoles.cambiar_estado_rol(
                operador=operador,
                rol=rol_actual,
                activo=activo,
                roles_existentes=roles,
                fecha_hora=momento,
            )
            modelo.activo = activo

            # Regla crítica (PBI-15/PBI-16): desactivar rol revoca sus sesiones en BD.
            if not activo:
                self._revocar_sesiones_por_rol(session, codigo_norm, momento)

            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return rol_modificado

    def eliminar_rol(
        self, operador_id: int, *, codigo: str, fecha_hora: datetime | None = None
    ) -> bool:
        momento = fecha_hora or self._ahora()
        codigo_norm = codigo.strip().upper()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            roles = self._roles(session)
            modelo = session.scalars(select(RolModel).filter_by(codigo=codigo_norm)).first()
            if modelo is None:
                raise RolInvalidoException(f"El rol {codigo_norm} no existe.")
            rol = rol_model_a_dominio(modelo, session)
            usuarios = self._usuarios(session)

            _, auditoria = ServicioGestionRoles.eliminar_rol(
                operador=operador,
                rol=rol,
                roles_existentes=roles,
                usuarios=usuarios,
                fecha_hora=momento,
            )
            # revocar sesiones del rol antes de eliminarlo
            self._revocar_sesiones_por_rol(session, codigo_norm, momento)
            session.delete(modelo)

            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return True

    # ------------------------------------------------------------------
    # CRUD de usuarios (PBI-02) + revocación de sesiones
    # ------------------------------------------------------------------

    def listar_usuarios(
        self,
        *,
        nombre: str | None = None,
        username: str | None = None,
        rol: RolUsuario | str | None = None,
        estado: EstadoUsuario | None = None,
    ) -> list[Usuario]:
        session = self._session_factory()
        try:
            usuarios = self._usuarios(session)
            return ServicioGestionUsuarios.filtrar_usuarios(
                usuarios, nombre=nombre, username=username, rol=rol, estado=estado
            )
        finally:
            session.close()

    def crear_usuario(
        self,
        operador_id: int,
        *,
        username: str,
        password_plana: str,
        nombre_completo: str,
        rol: RolUsuario | str,
        fecha_hora: datetime | None = None,
    ) -> Usuario:
        momento = fecha_hora or self._ahora()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            usuarios = self._usuarios(session)
            roles = self._roles(session)

            nuevo, auditoria = ServicioGestionUsuarios.crear_usuario(
                operador=operador,
                username=username,
                password_plana=password_plana,
                nombre_completo=nombre_completo,
                rol=rol,
                usuarios_existentes=usuarios,
                fecha_hora=momento,
                roles=roles,
            )

            modelo = UsuarioModel(
                id=nuevo.id,
                username=nuevo.username,
                nombre_completo=nuevo.nombre_completo,
                password_hash=nuevo.password_hash,
                salt=nuevo.salt,
                rol=rol_codigo(nuevo.rol),
                rol_id=self._rol_id(session, rol_codigo(nuevo.rol)),
                estado=EstadoUsuario.ACTIVO.value,
                activo=True,
                creado_en=momento,
            )
            session.add(modelo)

            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return nuevo

    def modificar_usuario(
        self,
        operador_id: int,
        usuario_id: int,
        *,
        nuevo_nombre: str | None = None,
        nuevo_rol: RolUsuario | str | None = None,
        fecha_hora: datetime | None = None,
    ) -> Usuario:
        momento = fecha_hora or self._ahora()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            usuarios = self._usuarios(session)
            roles = self._roles(session)
            modelo = self._modelo_usuario(session, usuario_id)
            target = usuario_model_a_dominio(modelo)

            modificado, auditoria = ServicioGestionUsuarios.modificar_usuario(
                operador=operador,
                usuario_target=target,
                nuevo_nombre=nuevo_nombre,
                nuevo_rol=nuevo_rol,
                fecha_hora=momento,
                roles=roles,
                usuarios_existentes=usuarios,
            )

            rol_cambio = rol_codigo(modificado.rol) != rol_codigo(target.rol)
            modelo.nombre_completo = modificado.nombre_completo
            modelo.rol = rol_codigo(modificado.rol)
            modelo.rol_id = self._rol_id(session, rol_codigo(modificado.rol))
            modelo.actualizado_en = momento

            # Si cambia el rol, las sesiones previas quedan revocadas (PBI-15).
            if rol_cambio:
                self._revocar_sesiones_usuario(session, usuario_id, momento)

            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return modificado

    def activar_usuario(
        self, operador_id: int, usuario_id: int, *, fecha_hora: datetime | None = None
    ) -> Usuario:
        return self._cambiar_estado_usuario(operador_id, usuario_id, True, fecha_hora)

    def desactivar_usuario(
        self, operador_id: int, usuario_id: int, *, fecha_hora: datetime | None = None
    ) -> Usuario:
        """Desactiva una cuenta y **revoca todas sus sesiones** en BD (regla crítica)."""
        return self._cambiar_estado_usuario(operador_id, usuario_id, False, fecha_hora)

    def _cambiar_estado_usuario(
        self, operador_id: int, usuario_id: int, activo: bool, fecha_hora: datetime | None
    ) -> Usuario:
        momento = fecha_hora or self._ahora()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            usuarios = self._usuarios(session)
            roles = self._roles(session)
            modelo = self._modelo_usuario(session, usuario_id)
            target = usuario_model_a_dominio(modelo)

            if activo:
                actualizado, auditoria = ServicioGestionUsuarios.cambiar_estado(
                    operador=operador,
                    usuario_target=target,
                    nuevo_estado=EstadoUsuario.ACTIVO,
                    fecha_hora=momento,
                    usuarios_existentes=usuarios,
                    roles=roles,
                )
                modelo.estado = EstadoUsuario.ACTIVO.value
                modelo.activo = True
            else:
                actualizado, auditoria, _sesiones = (
                    ServicioGestionUsuarios.desactivar_y_revocar_sesiones(
                        operador=operador,
                        usuario_target=target,
                        sesiones=self._sesiones_dominio(session, usuario_id),
                        fecha_hora=momento,
                        usuarios_existentes=usuarios,
                        roles=roles,
                    )
                )
                modelo.estado = EstadoUsuario.INACTIVO.value
                modelo.activo = False
                # Regla crítica (PBI-15/PBI-16): revocar sesiones en BD.
                self._revocar_sesiones_usuario(session, usuario_id, momento)

            modelo.actualizado_en = momento
            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return actualizado

    def restablecer_password(
        self,
        operador_id: int,
        usuario_id: int,
        *,
        nueva_password_plana: str,
        fecha_hora: datetime | None = None,
    ) -> Usuario:
        momento = fecha_hora or self._ahora()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            session = uow.session
            operador = self._usuario_operador(session, operador_id)
            roles = self._roles(session)
            modelo = self._modelo_usuario(session, usuario_id)
            target = usuario_model_a_dominio(modelo)

            actualizado, auditoria, _sesiones = (
                ServicioGestionUsuarios.restablecer_password_y_revocar_sesiones(
                    operador=operador,
                    usuario_target=target,
                    nueva_password_plana=nueva_password_plana,
                    sesiones=self._sesiones_dominio(session, usuario_id),
                    fecha_hora=momento,
                    roles=roles,
                )
            )
            modelo.password_hash = actualizado.password_hash
            modelo.salt = actualizado.salt
            modelo.actualizado_en = momento
            # restablecer credencial revoca sesiones vigentes (RN-09, RN-12)
            self._revocar_sesiones_usuario(session, usuario_id, momento)

            self._persistir_auditoria_usuario(
                session, auditoria, rol_ejecutante=rol_codigo(operador.rol)
            )
            uow.commit()
            return actualizado

    def obtener_usuario(self, usuario_id: int) -> Usuario:
        session = self._session_factory()
        try:
            return usuario_model_a_dominio(self._modelo_usuario(session, usuario_id))
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Auditoría (PBI-16): consulta e integridad
    # ------------------------------------------------------------------

    def consultar_auditoria(
        self, operador_id: int, filtro: FiltroAuditoria | None = None
    ) -> list[RegistroAuditoria]:
        session = self._session_factory()
        try:
            operador = usuario_model_a_dominio(self._modelo_usuario(session, operador_id))
            roles = self._roles(session)
            eventos = [
                auditoria_model_a_dominio(m)
                for m in session.scalars(
                    select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia)
                ).all()
            ]
            return ServicioAuditoria.consultar_eventos(
                eventos, filtro, operador=operador, roles=roles
            )
        finally:
            session.close()

    def verificar_integridad_auditoria(
        self, operador_id: int, *, total_esperado: int | None = None
    ) -> ResultadoVerificacionIntegridad:
        session = self._session_factory()
        try:
            operador = usuario_model_a_dominio(self._modelo_usuario(session, operador_id))
            roles = self._roles(session)
            eventos = [
                auditoria_model_a_dominio(m)
                for m in session.scalars(
                    select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia)
                ).all()
            ]
            return ServicioAuditoria.verificar_integridad(
                eventos, operador=operador, total_esperado=total_esperado, roles=roles
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Revocación de sesiones (persistencia en sesiones_usuario)
    # ------------------------------------------------------------------

    def _sesiones_dominio(self, session: Session, usuario_id: int) -> list[SesionUsuario]:
        filas = session.scalars(select(SesionUsuarioModel).filter_by(usuario_id=usuario_id)).all()
        resultado: list[SesionUsuario] = []
        for fila in filas:
            resultado.append(
                SesionUsuario(
                    token=fila.token,
                    usuario_id=fila.usuario_id,
                    username="",
                    rol=fila.rol_codigo_snapshot,
                    fecha_inicio=fila.fecha_inicio,
                    fecha_expiracion=fila.fecha_expiracion,
                    activa=bool(fila.activa),
                )
            )
        return resultado

    def _revocar_sesiones_usuario(
        self, session: Session, usuario_id: int, momento: datetime
    ) -> int:
        filas = session.scalars(
            select(SesionUsuarioModel).filter_by(usuario_id=usuario_id, activa=True)
        ).all()
        for fila in filas:
            fila.activa = False
            fila.revocada_en = momento
        session.flush()
        return len(filas)

    def _revocar_sesiones_por_rol(
        self, session: Session, rol_codigo_snapshot: str, momento: datetime
    ) -> int:
        codigo = rol_codigo(rol_codigo_snapshot)
        filas = session.scalars(select(SesionUsuarioModel).filter_by(activa=True)).all()
        revocadas = 0
        for fila in filas:
            if rol_codigo(fila.rol_codigo_snapshot) == codigo:
                fila.activa = False
                fila.revocada_en = momento
                revocadas += 1
        session.flush()
        return revocadas

    def _rol_id(self, session: Session, codigo: str) -> int | None:
        rol = session.scalars(select(RolModel).filter_by(codigo=rol_codigo(codigo))).first()
        return rol.id if rol is not None else None

    # ------------------------------------------------------------------
    # Persistencia de auditoría de eventos de usuario/rol
    # ------------------------------------------------------------------

    def _persistir_auditoria_usuario(
        self, session: Session, evento: Any, *, rol_ejecutante: str
    ) -> RegistroAuditoria:
        """Adapta ``EventoAuditoriaUsuario`` a PBI-16 y persiste en la misma transacción."""
        eventos = _eventos_existentes(session)

        def _persistir(registro: RegistroAuditoria) -> None:
            session.add(_auditoria_a_model(registro))
            session.flush()

        return ServicioAuditoria.desde_evento_usuario(
            evento,
            rol_ejecutante=rol_ejecutante,
            eventos_existentes=eventos,
            persistir=_persistir,
        )


def _como_aware(momento: datetime) -> datetime:
    """Asegura un ``datetime`` con tzinfo en America/Lima."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=ZONA_HORARIA_LIMA)
    return momento.astimezone(ZONA_HORARIA_LIMA)
