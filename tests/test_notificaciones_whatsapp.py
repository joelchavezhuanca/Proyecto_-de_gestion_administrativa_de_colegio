"""PBI-17: pruebas BDD de notificaciones a apoderados por WhatsApp."""

from dataclasses import replace
from datetime import date, datetime, time

import pytest

from src.dominio.aforo import CalendarioEscolar, EventoCierreDiario
from src.dominio.asistencia import (
    Alumno,
    EstadoAsistencia,
    EventoAsistenciaConfirmada,
    MetodoRegistro,
    RegistroAsistencia,
    UsuarioOperador,
)
from src.dominio.notificaciones import (
    ConfirmacionReenvioRequeridaException,
    ContactoApoderado,
    EstadoNotificacion,
    NotificacionDuplicadaException,
    NotificacionException,
    NotificacionWhatsApp,
    PermisoNotificacionException,
    PuertoNotificadorWhatsApp,
    ResultadoEnvioProveedor,
    ServicioNotificacionesWhatsApp,
    TipoNotificacion,
    VentanaBloqueoActivaException,
)
from src.dominio.usuarios import PermisoOperacion, Rol, RolUsuario

Servicio = ServicioNotificacionesWhatsApp
FECHA = date(2026, 11, 2)  # lunes lectivo
AHORA = datetime(2026, 11, 2, 7, 10, 0)


# ---------------------------------------------------------------------------
# Fixtures y dobles de prueba
# ---------------------------------------------------------------------------


class ProveedorSimulado:
    """Adaptador simulado del puerto de WhatsApp: registra llamadas, no usa red."""

    def __init__(
        self,
        resultado: ResultadoEnvioProveedor | None = None,
        error: Exception | None = None,
    ) -> None:
        self.resultado = resultado or ResultadoEnvioProveedor(
            exitoso=True, estado_reportado=EstadoNotificacion.ENVIADO, referencia="wamid-001"
        )
        self.error = error
        self.enviados: list[NotificacionWhatsApp] = []

    def enviar(self, notificacion: NotificacionWhatsApp) -> ResultadoEnvioProveedor:
        self.enviados.append(notificacion)
        if self.error is not None:
            raise self.error
        return self.resultado


def _alumno(alumno_id: int = 101, nombres: str = "Eduardo") -> Alumno:
    return Alumno(
        id=alumno_id,
        codigo=f"ALU-{alumno_id}",
        dni="72945734",
        nombres=nombres,
        apellidos="Luna Lezano",
        nivel="Secundaria",
        grado="5to",
        seccion="A",
        carnet_codigo=f"CRN-{alumno_id}",
    )


def _contacto(alumno_id: int = 101, telefono: str | None = "987 654 321") -> ContactoApoderado:
    return ContactoApoderado(
        alumno_id=alumno_id, nombre_apoderado="María Lezano", telefono=telefono
    )


def _evento(
    estado: EstadoAsistencia = EstadoAsistencia.PUNTUAL,
    hora: time = time(7, 10, 0),
    minutos: int = 0,
) -> EventoAsistenciaConfirmada:
    return EventoAsistenciaConfirmada(
        id="evt-001",
        asistencia_id="ast-001",
        alumno_id=101,
        fecha_escolar=FECHA,
        hora_efectiva=hora,
        estado=estado,
        minutos_tardanza=minutos,
        metodo=MetodoRegistro.CARNET,
        usuario_id=3,
    )


def _asistencia(
    alumno_id: int,
    estado: EstadoAsistencia,
    fecha: date = FECHA,
) -> RegistroAsistencia:
    return RegistroAsistencia(
        id=f"ast-{alumno_id}",
        alumno_id=alumno_id,
        fecha_escolar=fecha,
        hora_efectiva=time(9, 0, 0),
        estado=estado,
        minutos_tardanza=0,
        metodo=MetodoRegistro.MANUAL_BUSQUEDA,
        usuario_id=0,
        rol_usuario="SYSTEM_CRON",
    )


@pytest.fixture
def staff() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="staff", rol=RolUsuario.ADMIN_STAFF)


@pytest.fixture
def admin() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN)


@pytest.fixture
def cierre() -> EventoCierreDiario:
    return EventoCierreDiario(
        id="cierre-2026-11-02",
        fecha_escolar=FECHA,
        hora_cierre=time(9, 0, 0),
        total_ausentes_marcados=1,
        alumnos_ids_afectados=[201],
    )


@pytest.fixture
def notificacion_pendiente() -> NotificacionWhatsApp:
    return Servicio.encolar_notificacion_ingreso(_evento(), _alumno(), _contacto(), AHORA)


# ---------------------------------------------------------------------------
# Constantes, puerto y normalización de teléfonos
# ---------------------------------------------------------------------------


def test_constantes_por_defecto() -> None:
    assert Servicio.HORA_DEFECTO_AUSENCIAS == time(9, 0, 0)
    assert Servicio.MARGEN_BLOQUEO_MINUTOS == 5
    assert Servicio.MAX_INTENTOS_DEFECTO == 3


def test_proveedor_simulado_cumple_el_puerto() -> None:
    proveedor: PuertoNotificadorWhatsApp = ProveedorSimulado()
    assert hasattr(proveedor, "enviar")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("987654321", "+51987654321"),
        ("987 654 321", "+51987654321"),
        ("987-654-321", "+51987654321"),
        ("51987654321", "+51987654321"),
        ("+51 987 654 321", "+51987654321"),
        ("+51-987-654-321", "+51987654321"),
        ("887654321", None),
        ("98765432", None),
        ("9876543210", None),
        ("+987654321", None),
        ("+52987654321", None),
        ("98765432a", None),
        ("", None),
        (None, None),
    ],
)
def test_normalizar_telefono_peru(entrada: str | None, esperado: str | None) -> None:
    assert Servicio.normalizar_telefono_peru(entrada) == esperado


# ---------------------------------------------------------------------------
# Configuración de hora y ventana de bloqueo (RN-06, RN-07, RN-10)
# ---------------------------------------------------------------------------


def test_configurar_hora_notificacion_con_permiso(admin: UsuarioOperador) -> None:
    assert Servicio.configurar_hora_notificacion_ausencias(admin, time(9, 30)) == time(9, 30)


def test_configurar_hora_rol_personalizado_autorizado() -> None:
    rol = Rol(
        codigo="COMUNICACIONES",
        nombre="Comunicaciones",
        descripcion="Gestiona avisos a familias",
        permisos=frozenset({PermisoOperacion.CONFIGURAR_NOTIFICACIONES_WHATSAPP}),
    )
    operador = UsuarioOperador(id=8, username="comunica", rol="COMUNICACIONES")
    hora = Servicio.configurar_hora_notificacion_ausencias(operador, time(8, 45), roles=[rol])
    assert hora == time(8, 45)


def test_configurar_hora_sin_permiso_es_rechazado(staff: UsuarioOperador) -> None:
    with pytest.raises(PermisoNotificacionException):
        Servicio.configurar_hora_notificacion_ausencias(staff, time(9, 30))


def test_configurar_hora_operador_inactivo_es_rechazado() -> None:
    inactivo = UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=False)
    with pytest.raises(PermisoNotificacionException, match="activa"):
        Servicio.configurar_hora_notificacion_ausencias(inactivo, time(9, 30))


def test_configurar_hora_invalida_es_rechazada(admin: UsuarioOperador) -> None:
    with pytest.raises(NotificacionException, match="hora"):
        Servicio.configurar_hora_notificacion_ausencias(admin, "09:30")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("hora_actual", "bloqueado"),
    [
        (time(8, 54, 59), False),
        (time(8, 55, 0), True),
        (time(9, 0, 0), True),
        (time(9, 5, 0), True),
        (time(9, 5, 1), False),
        (time(7, 0, 0), False),
    ],
)
def test_ventana_bloqueo_manual_inclusiva(hora_actual: time, bloqueado: bool) -> None:
    assert Servicio.esta_en_ventana_bloqueo_manual(hora_actual, time(9, 0, 0)) is bloqueado


def test_ventana_bloqueo_manual_margen_personalizado() -> None:
    assert Servicio.esta_en_ventana_bloqueo_manual(time(8, 50), time(9, 0), margen_minutos=10)
    assert not Servicio.esta_en_ventana_bloqueo_manual(time(8, 58), time(9, 0), margen_minutos=1)


# ---------------------------------------------------------------------------
# Plantillas mínimas (RN-17)
# ---------------------------------------------------------------------------


def test_plantilla_puntual() -> None:
    plantilla, texto = Servicio.construir_contenido_plantilla(
        TipoNotificacion.PUNTUAL, _alumno(), FECHA, time(7, 10, 0)
    )
    assert plantilla == "ingreso_puntual"
    assert "Eduardo Luna Lezano" in texto
    assert "02/11/2026" in texto
    assert "07:10" in texto


def test_plantilla_tardanza() -> None:
    plantilla, texto = Servicio.construir_contenido_plantilla(
        TipoNotificacion.TARDANZA, _alumno(), FECHA, time(7, 20, 0), minutos_tardanza=5
    )
    assert plantilla == "ingreso_tardanza"
    assert "Eduardo Luna Lezano" in texto
    assert "07:20" in texto
    assert "5 minuto(s)" in texto


def test_plantilla_ausencia_incluye_orientacion_justificacion() -> None:
    plantilla, texto = Servicio.construir_contenido_plantilla(
        TipoNotificacion.AUSENCIA, _alumno(), FECHA
    )
    assert plantilla == "ausencia_alumno"
    assert "02/11/2026" in texto
    assert "justificación" in texto


@pytest.mark.parametrize("tipo", [TipoNotificacion.PUNTUAL, TipoNotificacion.TARDANZA])
def test_plantilla_ingreso_exige_hora(tipo: TipoNotificacion) -> None:
    with pytest.raises(NotificacionException, match="hora"):
        Servicio.construir_contenido_plantilla(tipo, _alumno(), FECHA)


# ---------------------------------------------------------------------------
# Encolado de ingresos (RN-02, RN-03, RN-15)
# ---------------------------------------------------------------------------


def test_encolar_puntual_queda_pendiente_sin_invocar_proveedor() -> None:
    noti = Servicio.encolar_notificacion_ingreso(_evento(), _alumno(), _contacto(), AHORA)
    assert noti.estado == EstadoNotificacion.PENDIENTE
    assert noti.tipo == TipoNotificacion.PUNTUAL
    assert noti.intentos == 0
    assert noti.telefono_destino == "+51987654321"
    assert noti.apoderado_nombre == "María Lezano"
    assert noti.clave_idempotencia == "ast-001:PUNTUAL:2026-11-02"
    assert noti.evento_origen_id == "evt-001"
    assert noti.asistencia_id == "ast-001"
    assert noti.alumno_id == 101
    assert noti.fecha_escolar == FECHA
    assert noti.referencia_proveedor is None
    assert noti.detalle_error is None
    assert noti.creado_en == noti.actualizado_en == AHORA
    assert noti.plantilla == "ingreso_puntual"


def test_encolar_tardanza_queda_pendiente() -> None:
    evento = _evento(EstadoAsistencia.TARDANZA, time(7, 16, 1), 2)
    noti = Servicio.encolar_notificacion_ingreso(evento, _alumno(), _contacto(), AHORA)
    assert noti.estado == EstadoNotificacion.PENDIENTE
    assert noti.tipo == TipoNotificacion.TARDANZA
    assert noti.clave_idempotencia == "ast-001:TARDANZA:2026-11-02"
    assert "2 minuto(s)" in noti.contenido


@pytest.mark.parametrize("estado", [EstadoAsistencia.AUSENTE, EstadoAsistencia.JUSTIFICADO])
def test_encolar_ingreso_rechaza_estados_no_ingreso(estado: EstadoAsistencia) -> None:
    with pytest.raises(NotificacionException):
        Servicio.encolar_notificacion_ingreso(_evento(estado), _alumno(), _contacto(), AHORA)


def test_encolar_ingreso_duplicado_es_rechazado() -> None:
    with pytest.raises(NotificacionDuplicadaException):
        Servicio.encolar_notificacion_ingreso(
            _evento(),
            _alumno(),
            _contacto(),
            AHORA,
            claves_existentes={"ast-001:PUNTUAL:2026-11-02"},
        )


@pytest.mark.parametrize("contacto", [None, _contacto(telefono="12345"), _contacto(telefono=None)])
def test_encolar_ingreso_sin_contacto_valido_marca_fallido(
    contacto: ContactoApoderado | None,
) -> None:
    noti = Servicio.encolar_notificacion_ingreso(_evento(), _alumno(), contacto, AHORA)
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert noti.detalle_error == "Contacto de apoderado inválido o ausente"
    assert noti.telefono_destino is None


# ---------------------------------------------------------------------------
# Ausencias automáticas tras el cierre de PBI-03 (RN-04 a RN-07)
# ---------------------------------------------------------------------------


def _universo_ausencias() -> tuple[list[RegistroAsistencia], dict[int, Alumno], dict]:
    asistencias = [
        _asistencia(201, EstadoAsistencia.AUSENTE),
        _asistencia(202, EstadoAsistencia.PENDIENTE),
        _asistencia(203, EstadoAsistencia.PUNTUAL),
        _asistencia(204, EstadoAsistencia.TARDANZA),
        _asistencia(205, EstadoAsistencia.JUSTIFICADO),
        _asistencia(206, EstadoAsistencia.AUSENTE),
        _asistencia(207, EstadoAsistencia.AUSENTE, fecha=date(2026, 10, 30)),
        _asistencia(208, EstadoAsistencia.AUSENTE),  # sin alumno en el padrón
    ]
    alumnos = {i: _alumno(i, f"Alumno{i}") for i in range(201, 208)}
    contactos = {201: _contacto(201), 206: _contacto(206, telefono="sin-celular")}
    return asistencias, alumnos, contactos


def test_ausencias_automaticas_solo_ausentes_tras_cierre(
    cierre: EventoCierreDiario,
) -> None:
    asistencias, alumnos, contactos = _universo_ausencias()
    notis = Servicio.encolar_notificaciones_ausencia_automatica(
        cierre,
        asistencias,
        alumnos,
        contactos,
        CalendarioEscolar(),
        hora_actual=time(9, 0, 0),
        hora_programada=time(9, 0, 0),
        ahora=datetime(2026, 11, 2, 9, 0, 0),
    )
    assert [n.alumno_id for n in notis] == [201, 206]
    assert all(n.tipo == TipoNotificacion.AUSENCIA for n in notis)
    assert notis[0].estado == EstadoNotificacion.PENDIENTE
    assert notis[0].evento_origen_id == "cierre-2026-11-02"
    assert notis[0].clave_idempotencia == "ast-201:AUSENCIA:2026-11-02"
    assert notis[0].plantilla == "ausencia_alumno"
    assert notis[1].estado == EstadoNotificacion.FALLIDO


def test_ausencias_automaticas_omite_ya_notificados(cierre: EventoCierreDiario) -> None:
    asistencias, alumnos, contactos = _universo_ausencias()
    notis = Servicio.encolar_notificaciones_ausencia_automatica(
        cierre,
        asistencias,
        alumnos,
        contactos,
        CalendarioEscolar(),
        hora_actual=time(9, 10),
        hora_programada=time(9, 0),
        ahora=datetime(2026, 11, 2, 9, 10),
        ya_notificados=frozenset({201}),
    )
    assert [n.alumno_id for n in notis] == [206]


def test_ausencias_automaticas_no_antes_de_hora_programada(
    cierre: EventoCierreDiario,
) -> None:
    asistencias, alumnos, contactos = _universo_ausencias()
    notis = Servicio.encolar_notificaciones_ausencia_automatica(
        cierre,
        asistencias,
        alumnos,
        contactos,
        CalendarioEscolar(),
        hora_actual=time(8, 59, 59),
        hora_programada=time(9, 0),
        ahora=datetime(2026, 11, 2, 8, 59, 59),
    )
    assert notis == []


def test_ausencias_automaticas_no_en_dia_no_lectivo(cierre: EventoCierreDiario) -> None:
    asistencias, alumnos, contactos = _universo_ausencias()
    calendario = CalendarioEscolar(dias_no_lectivos=frozenset({FECHA}))
    notis = Servicio.encolar_notificaciones_ausencia_automatica(
        cierre,
        asistencias,
        alumnos,
        contactos,
        calendario,
        hora_actual=time(9, 30),
        hora_programada=time(9, 0),
        ahora=datetime(2026, 11, 2, 9, 30),
    )
    assert notis == []


def test_ausencias_automaticas_en_excepcion_lectiva() -> None:
    sabado = date(2026, 11, 7)
    cierre_sabado = EventoCierreDiario(
        id="cierre-sab",
        fecha_escolar=sabado,
        hora_cierre=time(9, 0),
        total_ausentes_marcados=1,
        alumnos_ids_afectados=[201],
    )
    calendario = CalendarioEscolar(excepciones_lectivas=frozenset({sabado}))
    notis = Servicio.encolar_notificaciones_ausencia_automatica(
        cierre_sabado,
        [_asistencia(201, EstadoAsistencia.AUSENTE, fecha=sabado)],
        {201: _alumno(201)},
        {201: _contacto(201)},
        calendario,
        hora_actual=time(9, 0),
        hora_programada=time(9, 0),
        ahora=datetime(2026, 11, 7, 9, 0),
    )
    assert len(notis) == 1


# ---------------------------------------------------------------------------
# Notificación manual de ausencias (RN-08 a RN-12)
# ---------------------------------------------------------------------------


def _manual(
    operador: UsuarioOperador,
    hora_actual: time = time(10, 0),
    ya_notificados: frozenset[int] = frozenset(),
    confirmacion_reenvio: bool = False,
    roles: list[Rol] | None = None,
) -> list[NotificacionWhatsApp]:
    asistencias, alumnos, contactos = _universo_ausencias()
    return Servicio.encolar_notificaciones_ausencia_manual(
        operador,
        asistencias,
        alumnos,
        contactos,
        hora_actual=hora_actual,
        hora_programada=time(9, 0),
        ahora=datetime(2026, 11, 2, hora_actual.hour, hora_actual.minute),
        ya_notificados=ya_notificados,
        confirmacion_reenvio=confirmacion_reenvio,
        roles=roles,
    )


def test_manual_fuera_de_ventana_encola_solo_ausentes(staff: UsuarioOperador) -> None:
    notis = _manual(staff)
    assert [n.alumno_id for n in notis] == [201, 206, 207]
    assert all(n.tipo == TipoNotificacion.AUSENCIA for n in notis)
    assert notis[0].clave_idempotencia == "ast-201:AUSENCIA:2026-11-02"
    assert notis[0].evento_origen_id is None


@pytest.mark.parametrize("hora", [time(8, 55), time(9, 0), time(9, 5)])
def test_manual_dentro_de_ventana_es_bloqueado(staff: UsuarioOperador, hora: time) -> None:
    with pytest.raises(VentanaBloqueoActivaException):
        _manual(staff, hora_actual=hora)


def test_manual_sin_permiso_es_rechazado() -> None:
    rol = Rol(
        codigo="TESORERIA",
        nombre="Tesorería",
        descripcion="Pagos",
        permisos=frozenset({PermisoOperacion.GESTIONAR_PAGOS}),
    )
    operador = UsuarioOperador(id=9, username="tesorero", rol="TESORERIA")
    with pytest.raises(PermisoNotificacionException, match="NOTIFICAR_AUSENCIAS_MANUAL"):
        _manual(operador, roles=[rol])


def test_manual_operador_inactivo_es_rechazado() -> None:
    inactivo = UsuarioOperador(
        id=3, username="staff", rol=RolUsuario.ADMIN_STAFF, activo=False
    )
    with pytest.raises(PermisoNotificacionException):
        _manual(inactivo)


def test_manual_rol_personalizado_autorizado() -> None:
    rol = Rol(
        codigo="AUXILIAR",
        nombre="Auxiliar",
        descripcion="Avisos de inasistencia",
        permisos=frozenset({PermisoOperacion.NOTIFICAR_AUSENCIAS_MANUAL}),
    )
    operador = UsuarioOperador(id=10, username="aux", rol="AUXILIAR")
    assert len(_manual(operador, roles=[rol])) == 3


def test_manual_reenvio_sin_confirmacion_es_rechazado(staff: UsuarioOperador) -> None:
    with pytest.raises(ConfirmacionReenvioRequeridaException):
        _manual(staff, ya_notificados=frozenset({201}))


def test_manual_reenvio_con_confirmacion_usa_clave_de_reenvio(staff: UsuarioOperador) -> None:
    notis = _manual(staff, ya_notificados=frozenset({201}), confirmacion_reenvio=True)
    por_alumno = {n.alumno_id: n for n in notis}
    assert por_alumno[201].clave_idempotencia.startswith("ast-201:AUSENCIA:2026-11-02:REENVIO:")
    assert por_alumno[206].clave_idempotencia == "ast-206:AUSENCIA:2026-11-02"


# ---------------------------------------------------------------------------
# Procesamiento asíncrono, reintentos y aislamiento de fallos (RN-13 a RN-16)
# ---------------------------------------------------------------------------


def test_procesar_envio_exitoso_marca_enviado(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado()
    ahora = datetime(2026, 11, 2, 7, 11)
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, ahora)
    assert noti.estado == EstadoNotificacion.ENVIADO
    assert noti.intentos == 1
    assert noti.referencia_proveedor == "wamid-001"
    assert noti.actualizado_en == ahora
    assert noti.creado_en == AHORA
    assert len(proveedor.enviados) == 1


def test_procesar_envio_estado_reportado_entregado(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado(
        ResultadoEnvioProveedor(True, EstadoNotificacion.ENTREGADO, referencia="wamid-9")
    )
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, AHORA)
    assert noti.estado == EstadoNotificacion.ENTREGADO


def test_procesar_envio_exitoso_con_estado_reportado_ambiguo_queda_enviado(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado(ResultadoEnvioProveedor(True, EstadoNotificacion.PENDIENTE))
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, AHORA)
    assert noti.estado == EstadoNotificacion.ENVIADO


@pytest.mark.parametrize("estado", [EstadoNotificacion.ENVIADO, EstadoNotificacion.ENTREGADO])
def test_procesar_envio_es_idempotente(
    notificacion_pendiente: NotificacionWhatsApp, estado: EstadoNotificacion
) -> None:
    ya_enviada = replace(notificacion_pendiente, estado=estado, intentos=1)
    proveedor = ProveedorSimulado()
    assert Servicio.procesar_envio(ya_enviada, proveedor, AHORA) is ya_enviada
    assert proveedor.enviados == []


def test_procesar_envio_excepcion_del_proveedor_marca_fallido(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado(error=ConnectionError("timeout WhatsApp"))
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, AHORA)
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert noti.intentos == 1
    assert "timeout WhatsApp" in (noti.detalle_error or "")


def test_procesar_envio_rechazado_por_proveedor_marca_fallido(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado(
        ResultadoEnvioProveedor(
            False, EstadoNotificacion.FALLIDO, referencia="wamid-x", detalle_error="número no WA"
        )
    )
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, AHORA)
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert noti.detalle_error == "número no WA"
    assert noti.referencia_proveedor == "wamid-x"


def test_procesar_envio_rechazo_sin_detalle_usa_mensaje_por_defecto(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado(ResultadoEnvioProveedor(False, EstadoNotificacion.FALLIDO))
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, AHORA)
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert noti.detalle_error == "El proveedor rechazó el envío."


def test_procesar_envio_reintenta_hasta_max_intentos(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado(error=RuntimeError("caído"))
    noti = notificacion_pendiente
    for _ in range(5):
        noti = Servicio.procesar_envio(noti, proveedor, AHORA)
    assert len(proveedor.enviados) == 3
    assert noti.intentos == 3
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert "máximo de 3 intentos" in (noti.detalle_error or "")
    assert {n.clave_idempotencia for n in proveedor.enviados} == {
        "ast-001:PUNTUAL:2026-11-02"
    }


def test_procesar_envio_reintento_exitoso_tras_fallo(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    fallida = Servicio.procesar_envio(
        notificacion_pendiente, ProveedorSimulado(error=RuntimeError("x")), AHORA
    )
    noti = Servicio.procesar_envio(fallida, ProveedorSimulado(), AHORA)
    assert noti.estado == EstadoNotificacion.ENVIADO
    assert noti.intentos == 2
    assert noti.detalle_error is None


def test_procesar_envio_respeta_max_intentos_personalizado(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    proveedor = ProveedorSimulado()
    noti = Servicio.procesar_envio(notificacion_pendiente, proveedor, AHORA, max_intentos=0)
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert proveedor.enviados == []


def test_procesar_envio_sin_telefono_no_invoca_proveedor() -> None:
    sin_contacto = Servicio.encolar_notificacion_ingreso(_evento(), _alumno(), None, AHORA)
    proveedor = ProveedorSimulado()
    noti = Servicio.procesar_envio(sin_contacto, proveedor, AHORA)
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert noti.intentos == 0
    assert noti.detalle_error == "Contacto de apoderado inválido o ausente"
    assert proveedor.enviados == []


# ---------------------------------------------------------------------------
# Webhooks del proveedor (RN-18)
# ---------------------------------------------------------------------------


@pytest.fixture
def notificacion_enviada(notificacion_pendiente: NotificacionWhatsApp) -> NotificacionWhatsApp:
    return Servicio.procesar_envio(notificacion_pendiente, ProveedorSimulado(), AHORA)


def test_webhook_entregado_conserva_referencia(
    notificacion_enviada: NotificacionWhatsApp,
) -> None:
    ahora = datetime(2026, 11, 2, 7, 12)
    noti = Servicio.actualizar_estado_proveedor(
        notificacion_enviada, EstadoNotificacion.ENTREGADO, ahora
    )
    assert noti.estado == EstadoNotificacion.ENTREGADO
    assert noti.referencia_proveedor == "wamid-001"
    assert noti.actualizado_en == ahora


def test_webhook_fallido_registra_detalle_y_nueva_referencia(
    notificacion_enviada: NotificacionWhatsApp,
) -> None:
    noti = Servicio.actualizar_estado_proveedor(
        notificacion_enviada,
        EstadoNotificacion.FALLIDO,
        AHORA,
        referencia="wamid-002",
        detalle_error="no entregado",
    )
    assert noti.estado == EstadoNotificacion.FALLIDO
    assert noti.referencia_proveedor == "wamid-002"
    assert noti.detalle_error == "no entregado"


def test_webhook_repetido_es_idempotente(notificacion_enviada: NotificacionWhatsApp) -> None:
    entregada = Servicio.actualizar_estado_proveedor(
        notificacion_enviada, EstadoNotificacion.ENTREGADO, AHORA
    )
    repetida = Servicio.actualizar_estado_proveedor(
        entregada, EstadoNotificacion.ENTREGADO, datetime(2026, 11, 2, 8, 0)
    )
    assert repetida is entregada


@pytest.mark.parametrize("estado", [EstadoNotificacion.PENDIENTE, EstadoNotificacion.ENVIADO])
def test_webhook_estado_destino_invalido(
    notificacion_enviada: NotificacionWhatsApp, estado: EstadoNotificacion
) -> None:
    with pytest.raises(NotificacionException, match="ENTREGADO o FALLIDO"):
        Servicio.actualizar_estado_proveedor(notificacion_enviada, estado, AHORA)


def test_webhook_sobre_notificacion_no_enviada_es_rechazado(
    notificacion_pendiente: NotificacionWhatsApp,
) -> None:
    with pytest.raises(NotificacionException, match="ENVIADO"):
        Servicio.actualizar_estado_proveedor(
            notificacion_pendiente, EstadoNotificacion.ENTREGADO, AHORA
        )
