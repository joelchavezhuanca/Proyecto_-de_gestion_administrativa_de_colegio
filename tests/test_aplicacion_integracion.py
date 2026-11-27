"""Pruebas de integración de la capa de aplicación (PBI-01/02/04/05/06/07/10/16/17).

Reglas críticas verificadas
---------------------------
1. **Auditoría atómica (PBI-16):** si falla la persistencia de la auditoría al
   registrar asistencia, la unidad de trabajo hace ``rollback()`` total y no
   queda ninguna asistencia (ni historial) huérfana en base de datos.
2. **Aislamiento de efectos externos (PBI-17 / PBI-07):** si falla WhatsApp o
   la evaluación de pagos, la asistencia **sí queda confirmada** y la
   notificación queda en estado ``FALLIDO``.
3. **Revocación inmediata de sesiones (PBI-15):** al desactivar un usuario o un
   rol personalizado, sus filas de ``sesiones_usuario`` quedan revocadas en BD.

Las pruebas usan una base SQLite en archivo temporal para que los hilos del
``ThreadPoolExecutor`` (despacho asíncrono de WhatsApp) compartan el mismo
esquema, tal como ocurre en producción.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.aplicacion.servicios_academico import ServicioAcademico
from src.aplicacion.servicios_asistencia import PagosSqlAlchemy, ServicioAsistencia
from src.aplicacion.servicios_seguridad import ServicioSeguridad
from src.aplicacion.uow import SqlAlchemyUnitOfWork, ejecutar_atomico
from src.dominio.asistencia import (
    EstadoAsistencia,
    FaltaMotivoCorreccionException,
    MetodoRegistro,
    RegistroDuplicadoException,
)
from src.dominio.auditoria import (
    ZONA_HORARIA_LIMA,
    ErrorRegistroAuditoriaException,
    FiltroAuditoria,
)
from src.dominio.calificaciones import EscalaLiteral
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.exportacion_asistencia import (
    FiltroExportacionAsistencia,
    FormatoExportacion,
)
from src.dominio.justificaciones import (
    CategoriaJustificacion,
    PeriodoAcademico,
    TipoPeriodo,
)
from src.dominio.malla_curricular import EntidadEnUsoException, NivelEducativo
from src.dominio.matricula import Apoderado
from src.dominio.notificaciones import (
    EstadoNotificacion,
    ResultadoEnvioProveedor,
)
from src.dominio.pagos import EstadoObligacion
from src.dominio.usuarios import (
    AccesoDenegadoException,
    CredencialesInvalidasException,
    PermisoOperacion,
    SesionInvalidaException,
    hashear_password,
)
from src.infraestructura.base_datos import (
    crear_motor,
    crear_session_factory,
    inicializar_bd,
)
from src.infraestructura.modelos import (
    ApoderadoModel,
    AsignacionDocenteModel,
    AsistenciaHistorialModel,
    AsistenciaModel,
    AuditoriaEventoModel,
    ConfiguracionSistemaModel,
    EstudianteApoderadoModel,
    EstudianteModel,
    JustificacionModel,
    NotificacionWhatsappModel,
    ObligacionPagoModel,
    RolModel,
    SesionUsuarioModel,
    UsuarioModel,
)

FabricaSesiones = sessionmaker[Session]

ANIO_LECTIVO = 2026
RELOJ_FIJO = datetime(2026, 11, 26, 7, 5, 0, tzinfo=ZONA_HORARIA_LIMA)
FECHA_ESCOLAR = RELOJ_FIJO.date()
PASSWORD_ADMIN = "Admin12345"
PASSWORD_USUARIO = "Usuario12345"


# ---------------------------------------------------------------------------
# Dobles de prueba para puertos externos
# ---------------------------------------------------------------------------


class NotificadorQueLanza:
    """Proveedor WhatsApp que lanza una excepción de red."""

    def __init__(self) -> None:
        self.llamadas = 0

    def enviar(self, notificacion) -> ResultadoEnvioProveedor:  # noqa: ANN001
        self.llamadas += 1
        raise RuntimeError("WhatsApp caído")


class NotificadorQueRechaza:
    """Proveedor WhatsApp que responde con un envío fallido."""

    def __init__(self) -> None:
        self.llamadas = 0

    def enviar(self, notificacion) -> ResultadoEnvioProveedor:  # noqa: ANN001
        self.llamadas += 1
        return ResultadoEnvioProveedor(
            exitoso=False,
            estado_reportado=EstadoNotificacion.FALLIDO,
            detalle_error="Rechazado por el proveedor",
        )


class NotificadorBloqueante:
    """Proveedor que bloquea el hilo hasta que la prueba lo libera."""

    def __init__(self) -> None:
        self.liberado = threading.Event()
        self.terminado = threading.Event()

    def enviar(self, notificacion) -> ResultadoEnvioProveedor:  # noqa: ANN001
        self.liberado.wait(timeout=10)
        self.terminado.set()
        return ResultadoEnvioProveedor(
            exitoso=True,
            estado_reportado=EstadoNotificacion.ENVIADO,
            referencia="ref-bloqueante",
        )


class PagosSinAlertas:
    """Puerto de pagos que no encuentra obligaciones vencidas."""

    def evaluar_alerta_silenciosa(self, evento, *, session_factory):  # noqa: ANN001
        return None


class PagosQueFalla:
    """Puerto de pagos que falla por completo (PBI-07 aislado)."""

    def evaluar_alerta_silenciosa(self, evento, *, session_factory):  # noqa: ANN001
        raise RuntimeError("Pasarela de pagos caída")


# ---------------------------------------------------------------------------
# Helpers de siembra
# ---------------------------------------------------------------------------


def _crear_usuario(
    fabrica: FabricaSesiones,
    *,
    username: str,
    password: str = PASSWORD_USUARIO,
    rol: str = "ADMIN",
    nombre_completo: str = "Usuario de Prueba",
    estado: str = "ACTIVO",
    activo: bool = True,
) -> int:
    """Inserta un usuario con credenciales reales y devuelve su id."""
    password_hash, salt = hashear_password(password)
    with fabrica() as session:
        rol_modelo = session.scalars(select(RolModel).filter_by(codigo=rol)).one()
        modelo = UsuarioModel(
            username=username,
            nombre_completo=nombre_completo,
            password_hash=password_hash,
            salt=salt,
            rol=rol,
            rol_id=rol_modelo.id,
            estado=estado,
            activo=activo,
        )
        session.add(modelo)
        session.commit()
        session.refresh(modelo)
        return modelo.id


def _crear_alumno(
    fabrica: FabricaSesiones,
    *,
    codigo: str = "ALU-2026-001",
    dni: str = "72945734",
    nombres: str = "Eduardo",
    apellidos: str = "Luna Lezano",
    carnet: str = "CRN-72945734",
    nivel: str = "Primaria",
    grado: str = "3ro",
    seccion: str = "A",
    salon_id: int | None = None,
    con_apoderado: bool = True,
    telefono: str = "+51987654321",
) -> tuple[int, str]:
    """Inserta un alumno ACTIVO (con apoderado principal opcional)."""
    with fabrica() as session:
        modelo = EstudianteModel(
            codigo=codigo,
            dni=dni,
            nombres=nombres,
            apellidos=apellidos,
            fecha_nacimiento=date(2015, 4, 12),
            nivel=nivel,
            grado=grado,
            seccion=seccion,
            carnet_codigo=carnet,
            salon_id=salon_id,
            estado="ACTIVO",
        )
        session.add(modelo)
        session.flush()
        if con_apoderado:
            apoderado = ApoderadoModel(
                nombres="Rosa",
                apellidos="Lezano",
                documento=f"DOC-{dni}",
                parentesco="MADRE",
                telefono_whatsapp=telefono,
                activo=True,
            )
            session.add(apoderado)
            session.flush()
            session.add(
                EstudianteApoderadoModel(
                    estudiante_id=modelo.id,
                    apoderado_id=apoderado.id,
                    es_principal=True,
                )
            )
        session.commit()
        session.refresh(modelo)
        return modelo.id, carnet


def _contar(fabrica: FabricaSesiones, modelo) -> int:  # noqa: ANN001
    with fabrica() as session:
        return len(session.scalars(select(modelo)).all())


def _servicio_asistencia(fabrica: FabricaSesiones) -> ServicioAsistencia:
    return ServicioAsistencia(fabrica, reloj=lambda: RELOJ_FIJO)


def _servicio_academico(fabrica: FabricaSesiones) -> ServicioAcademico:
    return ServicioAcademico(fabrica, reloj=lambda: RELOJ_FIJO)


def _apoderado_principal() -> Apoderado:
    return Apoderado(
        id=0,
        nombres="Rosa",
        apellidos="Lezano",
        documento="44556677",
        parentesco="MADRE",
        telefono_whatsapp="+51987654321",
        es_principal=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fabrica_sesiones(tmp_path) -> Iterator[FabricaSesiones]:  # noqa: ANN001
    """Base SQLite en archivo temporal compartida entre hilos + seguridad sembrada."""
    ruta = tmp_path / "integracion.db"
    motor = crear_motor(f"sqlite:///{ruta.as_posix()}")
    inicializar_bd(motor)
    fabrica = crear_session_factory(motor)
    try:
        yield fabrica
    finally:
        motor.dispose()


@pytest.fixture
def admin_id(fabrica_sesiones: FabricaSesiones) -> int:
    return _crear_usuario(
        fabrica_sesiones,
        username="admin",
        password=PASSWORD_ADMIN,
        rol="ADMIN",
        nombre_completo="Administrador",
    )


@pytest.fixture
def alumno(fabrica_sesiones: FabricaSesiones) -> tuple[int, str]:
    return _crear_alumno(fabrica_sesiones)


@pytest.fixture
def asistencia(fabrica_sesiones: FabricaSesiones) -> Iterator[ServicioAsistencia]:
    servicio = _servicio_asistencia(fabrica_sesiones)
    try:
        yield servicio
    finally:
        servicio.cerrar()


# ---------------------------------------------------------------------------
# Unit of Work: commit / rollback atómico
# ---------------------------------------------------------------------------


def test_uow_confirma_cambios_al_salir_del_contexto(fabrica_sesiones: FabricaSesiones) -> None:
    """``commit()`` explícito persiste y libera la sesión."""
    with SqlAlchemyUnitOfWork(fabrica_sesiones) as uow:
        uow.session.add(
            EstudianteModel(
                codigo="ALU-UOW-1",
                dni="71000001",
                nombres="Ana",
                apellidos="Uno",
                nivel="Primaria",
                grado="3ro",
                seccion="A",
                estado="ACTIVO",
            )
        )
        uow.commit()

    with fabrica_sesiones() as session:
        assert session.scalars(select(EstudianteModel)).one().codigo == "ALU-UOW-1"


def test_uow_revierte_automaticamente_ante_cualquier_excepcion(
    fabrica_sesiones: FabricaSesiones,
) -> None:
    """Una excepción dentro del bloque deja la base sin cambios (rollback)."""
    with pytest.raises(RuntimeError, match="fallo simulado"):
        with SqlAlchemyUnitOfWork(fabrica_sesiones) as uow:
            uow.session.add(
                EstudianteModel(
                    codigo="ALU-UOW-2",
                    dni="71000002",
                    nombres="Beto",
                    apellidos="Dos",
                    nivel="Primaria",
                    grado="3ro",
                    seccion="A",
                    estado="ACTIVO",
                )
            )
            uow.flush()
            raise RuntimeError("fallo simulado")

    assert _contar(fabrica_sesiones, EstudianteModel) == 0


def test_ejecutar_atomico_revierte_si_la_operacion_falla(
    fabrica_sesiones: FabricaSesiones,
) -> None:
    """``ejecutar_atomico`` replica la garantía commit/rollback."""

    def operacion(session: Session) -> None:
        session.add(
            EstudianteModel(
                codigo="ALU-UOW-3",
                dni="71000003",
                nombres="Carla",
                apellidos="Tres",
                nivel="Primaria",
                grado="3ro",
                seccion="A",
                estado="ACTIVO",
            )
        )
        session.flush()
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        ejecutar_atomico(fabrica_sesiones, operacion)

    assert _contar(fabrica_sesiones, EstudianteModel) == 0


# ---------------------------------------------------------------------------
# REGLA CRÍTICA 1 — Fallo de auditoría PBI-16 revierte TODO
# ---------------------------------------------------------------------------


def test_fallo_auditoria_pbi16_revierte_asistencia_sin_huerfanos(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
    asistencia: ServicioAsistencia,
) -> None:
    """Si la auditoría no se puede persistir, no queda asistencia ni historial."""
    _, carnet = alumno

    def auditoria_rota(_registro) -> None:  # noqa: ANN001
        raise RuntimeError("disco de auditoría no disponible")

    with pytest.raises(ErrorRegistroAuditoriaException):
        asistencia.registrar_asistencia(
            admin_id,
            metodo=MetodoRegistro.CARNET,
            codigo_carnet=carnet,
            persistir_auditoria=auditoria_rota,
        )

    assert _contar(fabrica_sesiones, AsistenciaModel) == 0
    assert _contar(fabrica_sesiones, AsistenciaHistorialModel) == 0
    assert _contar(fabrica_sesiones, AuditoriaEventoModel) == 0


# ---------------------------------------------------------------------------
# REGLA CRÍTICA 2 — Fallos de WhatsApp / pagos NO revierten la asistencia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "notificador",
    [NotificadorQueLanza(), NotificadorQueRechaza()],
    ids=["whatsapp-excepcion", "whatsapp-rechazo"],
)
def test_fallo_whatsapp_pbi17_confirma_asistencia_y_deja_notificacion_fallida(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
    asistencia: ServicioAsistencia,
    notificador,
) -> None:
    """La asistencia se confirma; el fallo del proveedor solo marca FALLIDO."""
    _, carnet = alumno

    resultado = asistencia.registrar_asistencia(
        admin_id,
        metodo=MetodoRegistro.CARNET,
        codigo_carnet=carnet,
        notificador=notificador,
        pagos=PagosSinAlertas(),
    )
    asistencia.esperar_despachos(resultado)

    assert resultado.asistencia.estado == EstadoAsistencia.PUNTUAL
    with fabrica_sesiones() as session:
        asistencia_db = session.scalars(select(AsistenciaModel)).one()
        assert asistencia_db.estado == EstadoAsistencia.PUNTUAL.value
        notificacion = session.scalars(select(NotificacionWhatsappModel)).one()
        assert notificacion.estado == EstadoNotificacion.FALLIDO.value
        assert notificacion.detalle_error


def test_fallo_pagos_pbi07_confirma_asistencia_y_deja_notificacion_fallida(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
    asistencia: ServicioAsistencia,
) -> None:
    """Un fallo de la evaluación de pagos jamás revierte el registro de asistencia."""
    _, carnet = alumno

    resultado = asistencia.registrar_asistencia(
        admin_id,
        metodo=MetodoRegistro.CARNET,
        codigo_carnet=carnet,
        notificador=NotificadorQueLanza(),
        pagos=PagosQueFalla(),
    )
    asistencia.esperar_despachos(resultado)

    with fabrica_sesiones() as session:
        assert session.scalars(select(AsistenciaModel)).one().estado == (
            EstadoAsistencia.PUNTUAL.value
        )
        notificacion = session.scalars(select(NotificacionWhatsappModel)).one()
        assert notificacion.estado == EstadoNotificacion.FALLIDO.value
        assert "pagos" in (notificacion.detalle_error or "").lower()
        assert session.scalars(select(AuditoriaEventoModel)).all()


# ---------------------------------------------------------------------------
# REGLA CRÍTICA 3 — Desactivar usuario / rol revoca sesiones en BD
# ---------------------------------------------------------------------------


def test_desactivar_usuario_revoca_sus_sesiones_en_bd(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    """Las filas de ``sesiones_usuario`` quedan revocadas al desactivar la cuenta."""
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    usuario_id = seguridad.crear_usuario(
        admin_id,
        username="coordinador",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Coordinador Uno",
        rol="COORDINADOR",
    ).id
    sesion = seguridad.iniciar_sesion("coordinador", PASSWORD_USUARIO)

    with fabrica_sesiones() as session:
        assert session.get(SesionUsuarioModel, sesion.token).activa is True

    seguridad.desactivar_usuario(admin_id, usuario_id)

    with fabrica_sesiones() as session:
        fila = session.get(SesionUsuarioModel, sesion.token)
        assert fila is not None
        assert fila.activa is False
        assert fila.revocada_en is not None

    with pytest.raises(SesionInvalidaException):
        seguridad.validar_sesion(sesion.token)


def test_desactivar_rol_personalizado_revoca_sesiones_de_sus_usuarios(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    """Desactivar un rol personalizado revoca todas las sesiones con ese rol."""
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    seguridad.crear_rol(
        admin_id,
        codigo="MONITOR",
        nombre="Monitor de aula",
        descripcion="Rol personalizado para monitores",
        permisos=[PermisoOperacion.CONSULTAR_DASHBOARD_AFORO],
    )
    seguridad.crear_usuario(
        admin_id,
        username="monitor",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Monitor Uno",
        rol="MONITOR",
    )
    sesion = seguridad.iniciar_sesion("monitor", PASSWORD_USUARIO)

    seguridad.desactivar_rol(admin_id, codigo="MONITOR")

    with fabrica_sesiones() as session:
        fila = session.get(SesionUsuarioModel, sesion.token)
        assert fila is not None
        assert fila.activa is False
        assert fila.revocada_en is not None

    with pytest.raises(SesionInvalidaException):
        seguridad.validar_sesion(sesion.token)


# ---------------------------------------------------------------------------
# Seguridad: login / logout / validación en servidor / auditoría
# ---------------------------------------------------------------------------


def test_login_logout_y_validacion_de_sesion_en_servidor(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)

    sesion = seguridad.iniciar_sesion("admin", PASSWORD_ADMIN)
    assert sesion.activa is True
    with fabrica_sesiones() as session:
        assert session.get(SesionUsuarioModel, sesion.token).activa is True

    validada = seguridad.validar_sesion(sesion.token)
    assert validada.usuario_id == admin_id
    assert validada.token == sesion.token

    cerrada = seguridad.cerrar_sesion(sesion.token)
    assert cerrada.activa is False
    with fabrica_sesiones() as session:
        assert session.get(SesionUsuarioModel, sesion.token).activa is False

    with pytest.raises(SesionInvalidaException):
        seguridad.validar_sesion(sesion.token)


def test_login_con_credenciales_invalidas_audita_acceso_denegado(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)

    with pytest.raises(CredencialesInvalidasException):
        seguridad.iniciar_sesion("admin", "password-incorrecta")

    with fabrica_sesiones() as session:
        eventos = session.scalars(select(AuditoriaEventoModel)).all()
        assert [e.operacion for e in eventos] == ["ACCESO_DENEGADO"]
        assert eventos[0].resultado == "FALLIDA"
        assert "password" not in eventos[0].detalle_json.lower()


def test_validar_sesion_deniega_permiso_no_concedido(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    seguridad.crear_usuario(
        admin_id,
        username="coord2",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Coordinador Dos",
        rol="COORDINADOR",
    )
    sesion = seguridad.iniciar_sesion("coord2", PASSWORD_USUARIO)

    with pytest.raises(AccesoDenegadoException):
        seguridad.validar_sesion(sesion.token, permiso=PermisoOperacion.GESTIONAR_USUARIOS)


def test_crud_de_roles_personalizados_y_eliminacion_segura(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)

    rol = seguridad.crear_rol(
        admin_id,
        codigo="AUXILIAR",
        nombre="Auxiliar",
        descripcion="Apoyo administrativo",
        permisos=[
            PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
            PermisoOperacion.EXPORTAR_ASISTENCIAS,
        ],
    )
    assert rol.codigo == "AUXILIAR"
    assert PermisoOperacion.EXPORTAR_ASISTENCIAS in rol.permisos

    modificado = seguridad.modificar_rol(
        admin_id,
        codigo="AUXILIAR",
        nombre="Auxiliar de secretaría",
        permisos=[PermisoOperacion.CONSULTAR_FICHA_ALUMNO],
    )
    assert modificado.nombre == "Auxiliar de secretaría"
    assert modificado.permisos == frozenset({PermisoOperacion.CONSULTAR_FICHA_ALUMNO})

    seguridad.eliminar_rol(admin_id, codigo="AUXILIAR")
    assert all(r.codigo != "AUXILIAR" for r in seguridad.listar_roles())


def test_consulta_e_integridad_de_auditoria_detectan_alteraciones(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    seguridad.crear_usuario(
        admin_id,
        username="auxiliar",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Auxiliar Uno",
        rol="COORDINADOR",
    )

    eventos = seguridad.consultar_auditoria(admin_id, FiltroAuditoria())
    assert eventos
    assert seguridad.verificar_integridad_auditoria(admin_id).integra is True

    with fabrica_sesiones() as session:
        fila = session.scalars(
            select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia)
        ).first()
        fila.detalle_json = '{"manipulado": true}'
        session.commit()

    resultado = seguridad.verificar_integridad_auditoria(admin_id)
    assert resultado.integra is False
    assert resultado.ids_alterados


def test_restablecer_password_revoca_sesiones_vigentes(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    usuario_id = seguridad.crear_usuario(
        admin_id,
        username="staff",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Staff Uno",
        rol="ADMIN_STAFF",
    ).id
    sesion = seguridad.iniciar_sesion("staff", PASSWORD_USUARIO)

    seguridad.restablecer_password(admin_id, usuario_id, nueva_password_plana="NuevaClave123")

    with fabrica_sesiones() as session:
        assert session.get(SesionUsuarioModel, sesion.token).activa is False

    with pytest.raises(CredencialesInvalidasException):
        seguridad.iniciar_sesion("staff", PASSWORD_USUARIO)

    nueva = seguridad.iniciar_sesion("staff", "NuevaClave123")
    assert nueva.activa is True


# ---------------------------------------------------------------------------
# Asistencia: camino feliz, duplicados, no bloqueo y cierre/ausencias
# ---------------------------------------------------------------------------


def test_registro_exitoso_persiste_asistencia_historial_auditoria_y_notificacion(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
    asistencia: ServicioAsistencia,
) -> None:
    _, carnet = alumno

    resultado = asistencia.registrar_asistencia(
        admin_id, metodo=MetodoRegistro.CARNET, codigo_carnet=carnet
    )
    asistencia.esperar_despachos(resultado)

    assert resultado.asistencia.estado == EstadoAsistencia.PUNTUAL
    assert resultado.auditoria_id
    with fabrica_sesiones() as session:
        assert session.scalars(select(AsistenciaModel)).one().estado == "PUNTUAL"
        assert session.scalars(select(AsistenciaHistorialModel)).one().estado_nuevo == "PUNTUAL"
        eventos = session.scalars(select(AuditoriaEventoModel)).all()
        assert [e.operacion for e in eventos] == ["REGISTRO_ASISTENCIA"]
        notificacion = session.scalars(select(NotificacionWhatsappModel)).one()
        assert notificacion.estado == EstadoNotificacion.ENVIADO.value
        assert notificacion.telefono_destino == "+51987654321"


def test_registro_unificado_no_bloquea_por_el_envio_de_whatsapp(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
    asistencia: ServicioAsistencia,
) -> None:
    """El hilo principal retorna mientras el proveedor sigue bloqueado (< 200 ms)."""
    _, carnet = alumno
    notificador = NotificadorBloqueante()
    try:
        resultado = asistencia.registrar_asistencia(
            admin_id,
            metodo=MetodoRegistro.CARNET,
            codigo_carnet=carnet,
            notificador=notificador,
            pagos=PagosSinAlertas(),
        )
        assert resultado.asistencia.id
        assert notificador.terminado.is_set() is False
        with fabrica_sesiones() as session:
            assert session.scalars(select(AsistenciaModel)).one().estado == "PUNTUAL"
    finally:
        notificador.liberado.set()

    asistencia.esperar_despachos(resultado)
    assert notificador.terminado.is_set() is True
    with fabrica_sesiones() as session:
        notificacion = session.scalars(select(NotificacionWhatsappModel)).one()
        assert notificacion.estado == EstadoNotificacion.ENVIADO.value
        assert notificacion.referencia_proveedor == "ref-bloqueante"


def test_registro_duplicado_es_rechazado_sin_alterar_el_existente(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
    asistencia: ServicioAsistencia,
) -> None:
    _, carnet = alumno
    asistencia.registrar_asistencia(
        admin_id, metodo=MetodoRegistro.CARNET, codigo_carnet=carnet
    )

    with pytest.raises(RegistroDuplicadoException):
        asistencia.registrar_asistencia(
            admin_id, metodo=MetodoRegistro.CARNET, codigo_carnet=carnet
        )

    assert _contar(fabrica_sesiones, AsistenciaModel) == 1


def test_cierre_diario_marca_ausentes_y_notifica_a_apoderados(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    _crear_alumno(
        fabrica_sesiones,
        codigo="ALU-AUS-1",
        dni="72000001",
        carnet="CRN-72000001",
        nombres="Luis",
        apellidos="Ausente",
    )
    asistencia = _servicio_asistencia(fabrica_sesiones)
    try:
        evento = asistencia.ejecutar_cierre_diario(
            admin_id, fecha_escolar=FECHA_ESCOLAR, hora_cierre=time(9, 0)
        )
        assert evento.total_ausentes_marcados == 1

        notificaciones = asistencia.notificar_ausencias_automaticas(
            fecha_escolar=FECHA_ESCOLAR,
            hora_actual=time(9, 5),
            hora_programada=time(9, 0),
        )
    finally:
        asistencia.cerrar()

    assert len(notificaciones) == 1
    assert notificaciones[0].tipo.value == "AUSENCIA"
    with fabrica_sesiones() as session:
        assert session.scalars(select(AsistenciaModel)).one().estado == "AUSENTE"
        fila = session.scalars(select(NotificacionWhatsappModel)).one()
        assert fila.tipo == "AUSENCIA"
        assert fila.estado == EstadoNotificacion.ENVIADO.value


def test_justificacion_aprobada_actualiza_asistencia_y_audita(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    _crear_alumno(
        fabrica_sesiones,
        codigo="ALU-JUS-1",
        dni="73000001",
        carnet="CRN-73000001",
        nombres="Marta",
        apellidos="Justifica",
    )
    asistencia = _servicio_asistencia(fabrica_sesiones)
    try:
        asistencia.crear_periodo(
            admin_id,
            PeriodoAcademico(
                id=0,
                nombre="Bimestre I 2026",
                fecha_inicio=date(2026, 8, 1),
                fecha_fin=date(2026, 12, 20),
                anio_lectivo=ANIO_LECTIVO,
                tipo_periodo=TipoPeriodo.BIMESTRE,
                orden=1,
                fecha_limite_notas=date(2026, 12, 25),
            ),
        )
        asistencia.ejecutar_cierre_diario(
            admin_id, fecha_escolar=FECHA_ESCOLAR, hora_cierre=time(9, 0)
        )
        with fabrica_sesiones() as session:
            asistencia_id = session.scalars(select(AsistenciaModel)).one().id

        resultado = asistencia.registrar_justificacion(
            admin_id,
            asistencia_id=asistencia_id,
            categoria=CategoriaJustificacion.MEDICA,
            motivo="Reposo médico",
            fecha_solicitud=FECHA_ESCOLAR,
        )
    finally:
        asistencia.cerrar()

    assert resultado.asistencia_actualizada.estado == EstadoAsistencia.JUSTIFICADO
    with fabrica_sesiones() as session:
        assert session.scalars(select(AsistenciaModel)).one().estado == "JUSTIFICADO"
        assert session.scalars(select(JustificacionModel)).one().estado == "APROBADA"
        assert any(
            e.operacion == "REGISTRO_ASISTENCIA"
            for e in session.scalars(select(AuditoriaEventoModel)).all()
        )


def test_correccion_de_ausente_exige_motivo_y_registra_tardanza(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    """Corregir un AUSENTE exige motivo y deja rastro en historial y auditoría."""
    _crear_alumno(
        fabrica_sesiones,
        codigo="ALU-COR-1",
        dni="73100001",
        carnet="CRN-73100001",
        nombres="Corrige",
        apellidos="Tarde",
    )
    servicio_cierre = _servicio_asistencia(fabrica_sesiones)
    try:
        servicio_cierre.ejecutar_cierre_diario(
            admin_id, fecha_escolar=FECHA_ESCOLAR, hora_cierre=time(9, 0)
        )
    finally:
        servicio_cierre.cerrar()

    reloj_tarde = datetime(2026, 11, 26, 7, 30, 0, tzinfo=ZONA_HORARIA_LIMA)
    servicio = ServicioAsistencia(fabrica_sesiones, reloj=lambda: reloj_tarde)
    try:
        with pytest.raises(FaltaMotivoCorreccionException):
            servicio.registrar_asistencia(
                admin_id,
                metodo=MetodoRegistro.CARNET,
                codigo_carnet="CRN-73100001",
            )

        resultado = servicio.registrar_asistencia(
            admin_id,
            metodo=MetodoRegistro.CARNET,
            codigo_carnet="CRN-73100001",
            motivo_correccion="El alumno llegó tarde por tráfico",
        )
    finally:
        servicio.cerrar()

    assert resultado.asistencia.estado == EstadoAsistencia.TARDANZA
    assert resultado.asistencia.estado_anterior == EstadoAsistencia.AUSENTE
    assert resultado.asistencia.minutos_tardanza == 15
    with fabrica_sesiones() as session:
        asistencia_db = session.scalars(select(AsistenciaModel)).one()
        assert asistencia_db.estado == "TARDANZA"
        assert asistencia_db.estado_anterior == "AUSENTE"
        historiales = session.scalars(select(AsistenciaHistorialModel)).all()
        assert [h.estado_nuevo for h in historiales] == ["AUSENTE", "TARDANZA"]
        operaciones = [
            e.operacion
            for e in session.scalars(
                select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia)
            ).all()
        ]
        assert operaciones == ["CIERRE_ESCOLAR", "CORRECCION_AUSENTE"]


def test_aforo_metricas_y_configuracion_de_hora_de_cierre(
    fabrica_sesiones: FabricaSesiones,
    admin_id: int,
    alumno: tuple[int, str],
) -> None:
    """El dashboard de aforo opera en tiempo real y refleja la hora de cierre."""
    _, carnet = alumno
    _crear_alumno(
        fabrica_sesiones,
        codigo="ALU-AFO-2",
        dni="73200002",
        carnet="CRN-73200002",
        nombres="Pendiente",
        apellidos="Aforo",
    )
    servicio = _servicio_asistencia(fabrica_sesiones)
    try:
        servicio.registrar_asistencia(
            admin_id, metodo=MetodoRegistro.CARNET, codigo_carnet=carnet
        )
        metricas = servicio.consultar_metricas_aforo(
            admin_id, fecha_escolar=FECHA_ESCOLAR, hora_consulta=time(8, 0)
        )
        nueva_hora = servicio.configurar_hora_cierre(admin_id, time(8, 30))
        actualizadas = servicio.consultar_metricas_aforo(
            admin_id, fecha_escolar=FECHA_ESCOLAR, hora_consulta=time(9, 0)
        )
    finally:
        servicio.cerrar()

    assert metricas.total_matriculados == 2
    assert metricas.presentes == 1
    assert metricas.aforo_actual_plantel == 1
    assert metricas.hora_cierre_oficial == time(9, 0)

    assert nueva_hora == time(8, 30)
    assert actualizadas.hora_cierre_oficial == time(8, 30)
    with fabrica_sesiones() as session:
        config = session.get(ConfiguracionSistemaModel, "hora_cierre_oficial")
        assert config.valor == "08:30:00"


def test_baja_logica_de_malla_y_revocacion_de_asignacion_docente(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    """La malla permite baja lógica, revocación docente y borrado seguro."""
    academico = _servicio_academico(fabrica_sesiones)
    salon = _crear_salon(academico, admin_id, seccion="B")
    curso = academico.crear_curso(
        admin_id,
        anio_lectivo=ANIO_LECTIVO,
        nivel=NivelEducativo.PRIMARIA,
        grado="3ro",
        codigo="LEN-3B",
        nombre="Lenguaje",
        area_curricular="Comunicación",
        horas_semanales=4,
    )

    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    seguridad.crear_rol(
        admin_id,
        codigo="DOCENTE2",
        nombre="Docente Dos",
        descripcion="Docente para baja de malla",
        permisos=[PermisoOperacion.REGISTRAR_CALIFICACIONES],
    )
    docente_id = seguridad.crear_usuario(
        admin_id,
        username="docente2",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Docente Dos",
        rol="DOCENTE2",
    ).id

    asignacion = academico.asignar_docente(admin_id, docente_id, curso.id, salon.id)
    revocada = academico.revocar_asignacion(admin_id, asignacion.id, motivo="Cambio de sección")
    assert revocada.activa is False
    assert academico.listar_asignaciones_docente(docente_id, solo_activas=False)[0].activa is False

    with pytest.raises(EntidadEnUsoException):
        academico.eliminar_curso(admin_id, curso.id)

    assert academico.desactivar_curso(admin_id, curso.id).activo is False
    assert academico.desactivar_salon(admin_id, salon.id).activo is False

    salon_libre = _crear_salon(academico, admin_id, seccion="C")
    curso_libre = academico.crear_curso(
        admin_id,
        anio_lectivo=ANIO_LECTIVO,
        nivel=NivelEducativo.PRIMARIA,
        grado="3ro",
        codigo="CIE-3C",
        nombre="Ciencia",
        area_curricular="Ciencia",
        horas_semanales=3,
    )
    academico.eliminar_curso(admin_id, curso_libre.id)
    academico.eliminar_salon(admin_id, salon_libre.id)

    with fabrica_sesiones() as session:
        ids = {m.id for m in session.scalars(select(AsignacionDocenteModel)).all()}
        assert asignacion.id in ids


# ---------------------------------------------------------------------------
# Académico: matrícula, carnets, pagos, calificaciones, ficha y exportación
# ---------------------------------------------------------------------------


def _crear_salon(servicio: ServicioAcademico, admin_id: int, seccion: str = "A"):
    return servicio.crear_salon(
        admin_id,
        anio_lectivo=ANIO_LECTIVO,
        nivel=NivelEducativo.PRIMARIA,
        grado="3ro",
        seccion=seccion,
        capacidad_maxima=30,
    )


def _crear_periodo(servicio: ServicioAsistencia, admin_id: int) -> PeriodoAcademico:
    servicio.crear_periodo(
        admin_id,
        PeriodoAcademico(
            id=0,
            nombre="Bimestre I 2026",
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 12, 20),
            anio_lectivo=ANIO_LECTIVO,
            tipo_periodo=TipoPeriodo.BIMESTRE,
            orden=1,
            fecha_limite_notas=date(2026, 12, 25),
        ),
    )
    return servicio.listar_periodos(anio_lectivo=ANIO_LECTIVO)[0]


def test_matricula_digital_y_emision_de_carnet(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    academico = _servicio_academico(fabrica_sesiones)
    salon = _crear_salon(academico, admin_id)

    ficha = academico.matricular(
        admin_id,
        codigo_estudiante="ALU-MAT-1",
        dni="74000001",
        nombres="Sofía",
        apellidos="Matriculada",
        fecha_nacimiento=date(2015, 2, 10),
        salon_id=salon.id,
        apoderados=[_apoderado_principal()],
    )
    assert ficha.salon_id == salon.id
    assert ficha.apoderado_principal.telefono_whatsapp == "+51987654321"

    recuperada = academico.obtener_matricula(ficha.alumno_id)
    assert recuperada is not None
    assert recuperada.codigo_estudiante == "ALU-MAT-1"

    emision = academico.emitir_carnet(admin_id, ficha.alumno_id, ANIO_LECTIVO)
    assert emision.carnet_nuevo.codigo_qr
    assert academico.validar_carnet(emision.carnet_nuevo.codigo_qr).alumno_id == ficha.alumno_id

    ficha_alumno = academico.construir_ficha_alumno(admin_id, ficha.alumno_id)
    assert ficha_alumno.estado_academico.value == "ACTIVO"
    assert ficha_alumno.carnet_codigo == emision.carnet_nuevo.codigo_qr
    assert ficha_alumno.apoderados


def test_cambio_de_estado_academico_anula_carnet_y_audita(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    academico = _servicio_academico(fabrica_sesiones)
    salon = _crear_salon(academico, admin_id)
    ficha = academico.matricular(
        admin_id,
        codigo_estudiante="ALU-EST-1",
        dni="74000002",
        nombres="Retirado",
        apellidos="Pronto",
        fecha_nacimiento=date(2014, 6, 1),
        salon_id=salon.id,
        apoderados=[_apoderado_principal()],
    )
    emision = academico.emitir_carnet(admin_id, ficha.alumno_id, ANIO_LECTIVO)

    academico.cambiar_estado_academico(
        admin_id,
        ficha.alumno_id,
        nuevo_estado=EstadoAcademico.RETIRADO,
        motivo="Retiro voluntario",
    )

    assert academico.estado_efectivo(ficha.alumno_id).value == "RETIRADO"
    with fabrica_sesiones() as session:
        from src.infraestructura.modelos import CarnetModel

        carnet = session.get(CarnetModel, emision.carnet_nuevo.id)
        assert carnet.estado == "ANULADO"


def test_pagos_alerta_silenciosa_al_registrar_asistencia_y_pago(
    fabrica_sesiones: FabricaSesiones, admin_id: int, alumno: tuple[int, str]
) -> None:
    alumno_id, carnet = alumno
    academico = _servicio_academico(fabrica_sesiones)
    obligacion = academico.registrar_obligacion(
        admin_id,
        alumno_id,
        "Pensión noviembre",
        Decimal("150.00"),
        date(2026, 11, 1),
    )
    assert obligacion.estado == EstadoObligacion.PENDIENTE

    asistencia = _servicio_asistencia(fabrica_sesiones)
    try:
        resultado = asistencia.registrar_asistencia(
            admin_id,
            metodo=MetodoRegistro.CARNET,
            codigo_carnet=carnet,
            pagos=PagosSqlAlchemy(),
        )
        asistencia.esperar_despachos(resultado)
    finally:
        asistencia.cerrar()

    alertas = academico.listar_alertas_pago()
    assert len(alertas) == 1
    assert alertas[0].monto_vencido_total == Decimal("150.00")

    pagada = academico.registrar_pago(admin_id, obligacion.id)
    assert pagada.estado == EstadoObligacion.PAGADO
    with fabrica_sesiones() as session:
        fila = session.get(ObligacionPagoModel, obligacion.id)
        assert fila.estado == "PAGADO"
        assert fila.pagado_en is not None

    resumen = academico.construir_ficha_alumno(admin_id, alumno_id)
    assert resumen.resumen_pagos is not None
    assert resumen.resumen_pagos.alertas_activas == 1


def test_flujo_de_calificaciones_tres_niveles_y_boleta(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    academico = _servicio_academico(fabrica_sesiones)
    salon = _crear_salon(academico, admin_id)
    curso = academico.crear_curso(
        admin_id,
        anio_lectivo=ANIO_LECTIVO,
        nivel=NivelEducativo.PRIMARIA,
        grado="3ro",
        codigo="MAT-3A",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=5,
    )
    ficha = academico.matricular(
        admin_id,
        codigo_estudiante="ALU-NOT-1",
        dni="75000001",
        nombres="Nota",
        apellidos="Alta",
        fecha_nacimiento=date(2015, 3, 3),
        salon_id=salon.id,
        apoderados=[_apoderado_principal()],
    )

    seguridad = ServicioSeguridad(fabrica_sesiones, reloj=lambda: RELOJ_FIJO)
    seguridad.crear_rol(
        admin_id,
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Docente con registro de calificaciones",
        permisos=[
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            PermisoOperacion.CONSULTAR_CALIFICACIONES,
        ],
    )
    docente_id = seguridad.crear_usuario(
        admin_id,
        username="docente",
        password_plana=PASSWORD_USUARIO,
        nombre_completo="Docente Uno",
        rol="DOCENTE",
    ).id

    asignacion = academico.asignar_docente(admin_id, docente_id, curso.id, salon.id)
    assert asignacion.activa is True
    assert academico.validar_ambito_docente(
        docente_id, curso.id, salon.id, ANIO_LECTIVO
    ).id == asignacion.id

    servicio_asistencia = _servicio_asistencia(fabrica_sesiones)
    try:
        periodo = _crear_periodo(servicio_asistencia, admin_id)
    finally:
        servicio_asistencia.cerrar()

    rubros = academico.configurar_rubros(
        docente_id,
        asignacion.id,
        periodo.id,
        [("Prácticas", Decimal("40")), ("Examen", Decimal("60"))],
    )
    assert sum(r.peso_porcentaje for r in rubros) == Decimal("100")

    practica = academico.crear_actividad(
        docente_id, rubros[0].id, "Práctica 1", date(2026, 11, 10)
    )
    examen = academico.crear_actividad(
        docente_id, rubros[1].id, "Examen bimestral", date(2026, 12, 1)
    )
    academico.registrar_calificacion(
        docente_id, practica.id, ficha.alumno_id, Decimal("16")
    )
    academico.registrar_calificacion(
        docente_id, examen.id, ficha.alumno_id, Decimal("18")
    )

    promedio = academico.calcular_promedio_periodo(ficha.alumno_id, curso.id, periodo.id)
    assert promedio.nota_final == Decimal("17.20")
    assert promedio.escala_literal == EscalaLiteral.A

    boleta = academico.emitir_boleta_individual(admin_id, ficha.alumno_id, periodo.id)
    assert boleta.es_oficial is False
    assert boleta.promedio_general == Decimal("17.20")
    assert len(boleta.lineas) == 1
    assert b"17.20" in academico.exportar_boleta_texto(boleta)


def test_exportacion_de_asistencias_en_csv(
    fabrica_sesiones: FabricaSesiones, admin_id: int
) -> None:
    _crear_alumno(
        fabrica_sesiones,
        codigo="ALU-EXP-1",
        dni="76000001",
        carnet="CRN-76000001",
        nombres="Export",
        apellidos="Prueba",
    )
    asistencia = _servicio_asistencia(fabrica_sesiones)
    try:
        resultado = asistencia.registrar_asistencia(
            admin_id, metodo=MetodoRegistro.CARNET, codigo_carnet="CRN-76000001"
        )
        asistencia.esperar_despachos(resultado)
    finally:
        asistencia.cerrar()

    academico = _servicio_academico(fabrica_sesiones)
    exportado = academico.exportar_asistencias(
        admin_id,
        FiltroExportacionAsistencia(
            fecha_desde=FECHA_ESCOLAR,
            fecha_hasta=FECHA_ESCOLAR,
            formato=FormatoExportacion.CSV,
        ),
    )

    assert exportado.documento.total_filas == 1
    assert exportado.contenido.startswith(b"\xef\xbb\xbf")
    assert b"ALU-EXP-1" in exportado.contenido
    assert b"PUNTUAL" in exportado.contenido
