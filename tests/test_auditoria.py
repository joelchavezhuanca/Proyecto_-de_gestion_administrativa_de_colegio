"""Pruebas BDD/unitarias del PBI-16: Auditoría Inmutable de Transacciones."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.dominio.asistencia import (
    EstadoAsistencia,
    EventoAuditoria,
    MetodoRegistro,
)
from src.dominio.asistencia import (
    RolUsuario as RolAsistencia,
)
from src.dominio.auditoria import (
    HASH_GENESIS,
    ZONA_HORARIA_LIMA,
    AuditoriaException,
    ContextoAcademicoAuditoria,
    DatoSensibleAuditoriaException,
    ErrorRegistroAuditoriaException,
    FiltroAuditoria,
    PermisoAuditoriaException,
    RegistroAuditoria,
    ResultadoAuditoria,
    ResultadoVerificacionIntegridad,
    ServicioAuditoria,
    TipoOperacionAuditoria,
)
from src.dominio.usuarios import (
    EstadoUsuario,
    EventoAuditoriaUsuario,
    RolUsuario,
    Usuario,
)

FECHA = datetime(2026, 11, 23, 7, 10, 0, tzinfo=ZONA_HORARIA_LIMA)


@pytest.fixture
def admin_user() -> Usuario:
    return Usuario(
        id=1,
        username="admin_auditoria",
        password_hash="hash-admin",
        salt="salt-admin",
        nombre_completo="Administrador de Auditoría",
        rol=RolUsuario.ADMIN,
        estado=EstadoUsuario.ACTIVO,
    )


@pytest.fixture
def staff_user() -> Usuario:
    return Usuario(
        id=2,
        username="staff_auditoria",
        password_hash="hash-staff",
        salt="salt-staff",
        nombre_completo="Personal de Auditoría",
        rol=RolUsuario.ADMIN_STAFF,
        estado=EstadoUsuario.ACTIVO,
    )


def _evento(**cambios) -> RegistroAuditoria:
    datos = {
        "usuario_id": 1,
        "rol_ejecutante": "ADMIN",
        "operacion": TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
        "entidad": "ASISTENCIA",
        "entidad_id": "ast-001",
        "resultado": ResultadoAuditoria.CONFIRMADA,
        "fecha_hora": FECHA,
        "eventos_existentes": [],
        "detalle": {"alumno_id": 10},
    }
    datos.update(cambios)
    return ServicioAuditoria.registrar_evento(**datos)


def _registro_invalido(**cambios) -> RegistroAuditoria:
    datos = {
        "id": "aud-invalido",
        "secuencia": 1,
        "fecha_hora": FECHA,
        "usuario_id": 1,
        "rol_ejecutante": "ADMIN",
        "operacion": TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
        "entidad": "ASISTENCIA",
        "entidad_id": "ast-001",
        "resultado": ResultadoAuditoria.CONFIRMADA,
        "detalle": {},
    }
    datos.update(cambios)
    return RegistroAuditoria(**datos)


# ----------------------------------------------------------------------
# Registro de eventos y cadena de integridad
# ----------------------------------------------------------------------
def test_registrar_evento_asistencia_con_contexto_y_hash_genesis() -> None:
    evento = ServicioAuditoria.registrar_evento(
        usuario_id=1,
        rol_ejecutante="ADMIN",
        operacion=TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
        entidad="ASISTENCIA",
        entidad_id="ast-001",
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=FECHA,
        eventos_existentes=[],
        alumno_id=10,
        metodo_asistencia="CARNET",
        contexto_academico=ContextoAcademicoAuditoria("Secundaria", "3ro", "A"),
        detalle={"alumno_id": 10, "metodo": "CARNET"},
    )

    assert evento.hash_anterior == HASH_GENESIS
    assert len(evento.hash_integridad) == 64
    assert evento.secuencia == 1
    assert evento.contexto_academico == ContextoAcademicoAuditoria("Secundaria", "3ro", "A")
    assert evento.metodo_asistencia == "CARNET"
    assert evento.alumno_id == 10
    assert evento.resultado == ResultadoAuditoria.CONFIRMADA


def test_cadena_hash_encadena_eventos_consecutivos() -> None:
    primero = _evento(id_evento="aud-001")
    segundo = _evento(id_evento="aud-002", eventos_existentes=[primero])
    tercero = _evento(id_evento="aud-003", eventos_existentes=[primero, segundo])

    assert segundo.hash_anterior == primero.hash_integridad
    assert tercero.hash_anterior == segundo.hash_integridad
    assert (primero.secuencia, segundo.secuencia, tercero.secuencia) == (1, 2, 3)


def test_hash_determinista_para_mismo_payload_y_orden_distinto() -> None:
    primero = _evento(id_evento="aud-fijo", detalle={"b": 2, "a": 1})
    segundo = _evento(id_evento="aud-fijo", detalle={"a": 1, "b": 2})

    assert primero.hash_integridad == segundo.hash_integridad


def test_evento_de_correccion_conserva_estado_anterior_y_motivo() -> None:
    evento = _evento(
        operacion=TipoOperacionAuditoria.CORRECCION_AUSENTE,
        estado_anterior="AUSENTE",
        estado_nuevo="PUNTUAL",
        motivo="Olvido de carnet al ingresar",
    )

    assert evento.estado_anterior == "AUSENTE"
    assert evento.estado_nuevo == "PUNTUAL"
    assert evento.motivo == "Olvido de carnet al ingresar"


def test_evento_de_usuario_registra_valores_anteriores_y_nuevos() -> None:
    evento = _evento(
        operacion=TipoOperacionAuditoria.MODIFICAR_USUARIO,
        entidad="USUARIO",
        entidad_id="7",
        detalle={"nombre_anterior": "Ana", "nombre_nuevo": "Ana María"},
    )

    assert evento.entidad == "USUARIO"
    assert evento.entidad_id == "7"
    assert dict(evento.detalle) == {
        "nombre_anterior": "Ana",
        "nombre_nuevo": "Ana María",
    }


def test_evento_de_sistema_sin_sesion_humana_es_valido() -> None:
    evento = _evento(usuario_id=0, rol_ejecutante="SYSTEM_CRON")

    assert evento.usuario_id == 0
    assert evento.rol_ejecutante == "SYSTEM_CRON"


def test_actor_invalido_es_rechazado() -> None:
    with pytest.raises(Exception, match="actor"):
        _evento(usuario_id=0, rol_ejecutante="ADMIN")

    with pytest.raises(Exception, match="rol"):
        _evento(rol_ejecutante="")


# ----------------------------------------------------------------------
# Privacidad y append-only
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "clave",
    ["password", "password_hash", "salt", "token", "contraseña", "secret"],
)
def test_rechaza_claves_sensibles_en_detalle(clave: str) -> None:
    with pytest.raises(DatoSensibleAuditoriaException):
        _evento(detalle={clave: "valor-prohibido"})


def test_rechaza_claves_sensibles_anidadas() -> None:
    with pytest.raises(DatoSensibleAuditoriaException):
        _evento(detalle={"usuario": {"password": "secreto"}})


def test_prohibe_modificacion_y_eliminacion_de_eventos() -> None:
    with pytest.raises(Exception, match="modificar"):
        ServicioAuditoria.prohibir_modificacion("aud-001")

    with pytest.raises(Exception, match="eliminar"):
        ServicioAuditoria.prohibir_eliminacion("aud-001")


# ----------------------------------------------------------------------
# Verificación de integridad
# ----------------------------------------------------------------------
def test_verificar_cadena_valida(admin_user: Usuario) -> None:
    primero = _evento(id_evento="aud-001")
    segundo = _evento(id_evento="aud-002", eventos_existentes=[primero])
    tercero = _evento(id_evento="aud-003", eventos_existentes=[primero, segundo])

    resultado = ServicioAuditoria.verificar_integridad(
        [primero, segundo, tercero], operador=admin_user
    )

    assert isinstance(resultado, ResultadoVerificacionIntegridad)
    assert resultado.integra is True
    assert resultado.ids_alterados == ()


def test_detectar_manipulacion_de_un_evento(admin_user: Usuario) -> None:
    primero = _evento(id_evento="aud-001")
    segundo = _evento(id_evento="aud-002", eventos_existentes=[primero])
    tercero = _evento(id_evento="aud-003", eventos_existentes=[primero, segundo])
    alterado = replace(segundo, motivo="manipulado")

    resultado = ServicioAuditoria.verificar_integridad(
        [primero, alterado, tercero], operador=admin_user
    )

    assert resultado.integra is False
    assert "aud-002" in resultado.ids_alterados


def test_detectar_reordenamiento_de_eventos(admin_user: Usuario) -> None:
    primero = _evento(id_evento="aud-001")
    segundo = _evento(id_evento="aud-002", eventos_existentes=[primero])

    resultado = ServicioAuditoria.verificar_integridad(
        [segundo, primero], operador=admin_user
    )

    assert resultado.integra is False
    assert resultado.ids_alterados


def test_detectar_borrado_de_evento_intermedio(admin_user: Usuario) -> None:
    primero = _evento(id_evento="aud-001")
    segundo = _evento(id_evento="aud-002", eventos_existentes=[primero])
    tercero = _evento(id_evento="aud-003", eventos_existentes=[primero, segundo])

    resultado = ServicioAuditoria.verificar_integridad(
        [primero, tercero], operador=admin_user
    )

    assert resultado.integra is False
    assert resultado.ids_alterados


def test_detectar_borrado_del_ultimo_evento_con_total_esperado(
    admin_user: Usuario,
) -> None:
    primero = _evento(id_evento="aud-001")
    segundo = _evento(id_evento="aud-002", eventos_existentes=[primero])

    resultado = ServicioAuditoria.verificar_integridad(
        [primero, segundo], operador=admin_user, total_esperado=3
    )

    assert resultado.integra is False
    assert resultado.eventos_faltantes == (3,)


def test_cadena_vacia_es_integra(admin_user: Usuario) -> None:
    resultado = ServicioAuditoria.verificar_integridad([], operador=admin_user)

    assert resultado.integra is True


def test_verificar_integridad_requiere_permiso(staff_user: Usuario) -> None:
    evento = _evento()

    with pytest.raises(PermisoAuditoriaException):
        ServicioAuditoria.verificar_integridad([evento], operador=staff_user)


# ----------------------------------------------------------------------
# Consulta y filtros
# ----------------------------------------------------------------------
def _tres_eventos() -> list[RegistroAuditoria]:
    primero = _evento(
        id_evento="aud-001",
        usuario_id=1,
        rol_ejecutante="ADMIN",
        operacion=TipoOperacionAuditoria.REGISTRO_ASISTENCIA,
        entidad="ASISTENCIA",
        entidad_id="ast-001",
        alumno_id=10,
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=datetime(2026, 11, 23, 7, 0, tzinfo=ZONA_HORARIA_LIMA),
    )
    segundo = _evento(
        id_evento="aud-002",
        usuario_id=2,
        rol_ejecutante="ADMIN_STAFF",
        operacion=TipoOperacionAuditoria.CORRECCION_AUSENTE,
        entidad="ASISTENCIA",
        entidad_id="ast-002",
        alumno_id=20,
        resultado=ResultadoAuditoria.FALLIDA,
        fecha_hora=datetime(2026, 11, 23, 8, 0, tzinfo=ZONA_HORARIA_LIMA),
        eventos_existentes=[primero],
    )
    tercero = _evento(
        id_evento="aud-003",
        usuario_id=1,
        rol_ejecutante="ADMIN",
        operacion=TipoOperacionAuditoria.CREAR_USUARIO,
        entidad="USUARIO",
        entidad_id="7",
        resultado=ResultadoAuditoria.CONFIRMADA,
        fecha_hora=datetime(2026, 11, 23, 9, 0, tzinfo=ZONA_HORARIA_LIMA),
        eventos_existentes=[primero, segundo],
    )
    return [primero, segundo, tercero]


def test_consultar_eventos_sin_filtro(admin_user: Usuario) -> None:
    eventos = _tres_eventos()

    resultado = ServicioAuditoria.consultar_eventos(eventos, operador=admin_user)

    assert [evento.id for evento in resultado] == ["aud-001", "aud-002", "aud-003"]


def test_consultar_eventos_filtra_por_cada_criterio(admin_user: Usuario) -> None:
    eventos = _tres_eventos()

    por_rango = ServicioAuditoria.consultar_eventos(
        eventos,
        FiltroAuditoria(
            fecha_desde=datetime(2026, 11, 23, 7, 30, tzinfo=ZONA_HORARIA_LIMA),
            fecha_hasta=datetime(2026, 11, 23, 10, 0, tzinfo=ZONA_HORARIA_LIMA),
        ),
        operador=admin_user,
    )
    por_usuario = ServicioAuditoria.consultar_eventos(
        eventos, FiltroAuditoria(usuario_id=2), operador=admin_user
    )
    por_operacion = ServicioAuditoria.consultar_eventos(
        eventos,
        FiltroAuditoria(operacion=TipoOperacionAuditoria.CREAR_USUARIO),
        operador=admin_user,
    )
    por_entidad = ServicioAuditoria.consultar_eventos(
        eventos, FiltroAuditoria(entidad="USUARIO"), operador=admin_user
    )
    por_alumno = ServicioAuditoria.consultar_eventos(
        eventos, FiltroAuditoria(alumno_id=20), operador=admin_user
    )
    por_resultado = ServicioAuditoria.consultar_eventos(
        eventos,
        FiltroAuditoria(resultado=ResultadoAuditoria.FALLIDA),
        operador=admin_user,
    )

    assert [evento.id for evento in por_rango] == ["aud-002", "aud-003"]
    assert [evento.id for evento in por_usuario] == ["aud-002"]
    assert [evento.id for evento in por_operacion] == ["aud-003"]
    assert [evento.id for evento in por_entidad] == ["aud-003"]
    assert [evento.id for evento in por_alumno] == ["aud-002"]
    assert [evento.id for evento in por_resultado] == ["aud-002"]


def test_filtro_con_rango_invertido_es_rechazado() -> None:
    with pytest.raises(Exception, match="rango"):
        FiltroAuditoria(
            fecha_desde=datetime(2026, 11, 24, tzinfo=ZONA_HORARIA_LIMA),
            fecha_hasta=datetime(2026, 11, 23, tzinfo=ZONA_HORARIA_LIMA),
        )


def test_consultar_eventos_requiere_permiso(staff_user: Usuario) -> None:
    with pytest.raises(PermisoAuditoriaException):
        ServicioAuditoria.consultar_eventos(_tres_eventos(), operador=staff_user)


# ----------------------------------------------------------------------
# Atomicidad y adaptadores desde DTO existentes
# ----------------------------------------------------------------------
def test_error_de_persistencia_propaga_excepcion_para_rollback() -> None:
    def persistir_fallido(evento: RegistroAuditoria) -> None:
        raise RuntimeError("destino no disponible")

    with pytest.raises(ErrorRegistroAuditoriaException):
        _evento(persistir=persistir_fallido)


def test_desde_evento_asistencia_mapea_contexto_y_estados() -> None:
    evento_dominio = EventoAuditoria(
        id="aud-ast-001",
        evento_tipo="ASISTENCIA_REGISTRADA",
        usuario_id=1,
        rol=RolAsistencia.ADMIN,
        fecha_hora=FECHA,
        operacion="REGISTRO_ASISTENCIA",
        metodo=MetodoRegistro.CARNET,
        alumno_id=10,
        estado_anterior=None,
        estado_nuevo=EstadoAsistencia.TARDANZA,
        motivo=None,
    )

    registro = ServicioAuditoria.desde_evento_asistencia(
        evento_dominio,
        asistencia_id="ast-001",
        contexto=ContextoAcademicoAuditoria("Secundaria", "3ro", "A"),
        eventos_existentes=[],
    )

    assert registro.entidad == "ASISTENCIA"
    assert registro.entidad_id == "ast-001"
    assert registro.alumno_id == 10
    assert registro.metodo_asistencia == "CARNET"
    assert registro.estado_nuevo == "TARDANZA"
    assert registro.contexto_academico == ContextoAcademicoAuditoria("Secundaria", "3ro", "A")
    assert registro.rol_ejecutante == "ADMIN"


def test_desde_evento_usuario_mapea_entidad_y_detalle() -> None:
    evento_dominio = EventoAuditoriaUsuario(
        id="aud-usr-001",
        admin_id=1,
        admin_username="admin_auditoria",
        fecha_hora=FECHA,
        operacion="CREAR_USUARIO",
        usuario_afectado_id=7,
        usuario_afectado_username="nuevo_usuario",
        detalle={"rol_asignado": "ADMIN_STAFF"},
    )

    registro = ServicioAuditoria.desde_evento_usuario(
        evento_dominio,
        rol_ejecutante="ADMIN",
        eventos_existentes=[],
    )

    assert registro.entidad == "USUARIO"
    assert registro.entidad_id == "7"
    assert registro.operacion == TipoOperacionAuditoria.CREAR_USUARIO
    assert dict(registro.detalle)["rol_asignado"] == "ADMIN_STAFF"


# ----------------------------------------------------------------------
# Reloj institucional
# ----------------------------------------------------------------------
def test_fecha_naive_se_normaliza_a_zona_lima() -> None:
    evento = _evento(fecha_hora=datetime(2026, 11, 23, 7, 0, 0))

    assert evento.fecha_hora.utcoffset() == timedelta(hours=-5)


def test_fecha_utc_se_convierte_a_zona_lima() -> None:
    evento = _evento(fecha_hora=datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC))

    assert evento.fecha_hora.hour == 7
    assert evento.fecha_hora.utcoffset() == timedelta(hours=-5)


# ----------------------------------------------------------------------
# Cobertura de validaciones defensivas y caminos alternativos (REFACTOR)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("campo", ["nivel", "grado", "seccion"])
def test_contexto_academico_rechaza_campos_vacios(campo: str) -> None:
    valores = {"nivel": "Secundaria", "grado": "3ro", "seccion": "A"}
    valores[campo] = " "

    with pytest.raises(AuditoriaException, match="contexto"):
        ContextoAcademicoAuditoria(**valores)


@pytest.mark.parametrize(
    "cambios",
    [
        {"id": ""},
        {"secuencia": 0},
        {"fecha_hora": None},
        {"usuario_id": -1},
        {"rol_ejecutante": ""},
        {"operacion": "NO_EXISTE"},
        {"resultado": "NO_EXISTE"},
        {"entidad": ""},
        {"entidad_id": ""},
        {"hash_integridad": "corto"},
        {"detalle": ["no-mapa"]},
    ],
)
def test_registro_rechaza_campos_invalidos(cambios: dict[str, object]) -> None:
    with pytest.raises(AuditoriaException):
        _registro_invalido(**cambios)


def test_registro_acepta_operacion_y_resultado_como_texto() -> None:
    registro = _registro_invalido(operacion="registro_asistencia", resultado="confirmada")

    assert registro.operacion == TipoOperacionAuditoria.REGISTRO_ASISTENCIA
    assert registro.resultado == ResultadoAuditoria.CONFIRMADA


@pytest.mark.parametrize("cambios", [{"usuario_id": -1}, {"alumno_id": 0}])
def test_filtro_rechaza_identificadores_invalidos(cambios: dict[str, int]) -> None:
    with pytest.raises(AuditoriaException):
        FiltroAuditoria(**cambios)


def test_detalle_con_tipos_compuestos_genera_hash_estable() -> None:
    evento = _evento(
        detalle={
            "lista": [1, 2],
            "tupla": (3, 4),
            "conjunto": {5},
            "operacion": TipoOperacionAuditoria.CREAR_USUARIO,
            "fecha": FECHA,
        }
    )

    assert len(evento.hash_integridad) == 64


def test_rechaza_claves_sensibles_dentro_de_listas() -> None:
    with pytest.raises(DatoSensibleAuditoriaException):
        _evento(detalle={"eventos": [{"token": "x"}]})


def test_rechaza_evento_anterior_sin_hash() -> None:
    evento = _evento()
    sin_hash = replace(evento, hash_integridad="")

    with pytest.raises(AuditoriaException, match="hash"):
        _evento(eventos_existentes=[sin_hash])


def test_consultar_eventos_filtra_por_rol_y_fecha_hasta(admin_user: Usuario) -> None:
    eventos = _tres_eventos()

    por_rol = ServicioAuditoria.consultar_eventos(
        eventos, FiltroAuditoria(rol="admin_staff"), operador=admin_user
    )
    por_hasta = ServicioAuditoria.consultar_eventos(
        eventos,
        FiltroAuditoria(
            fecha_hasta=datetime(2026, 11, 23, 7, 30, tzinfo=ZONA_HORARIA_LIMA)
        ),
        operador=admin_user,
    )

    assert [evento.id for evento in por_rol] == ["aud-002"]
    assert [evento.id for evento in por_hasta] == ["aud-001"]


def test_operador_inactivo_no_puede_consultar(admin_user: Usuario) -> None:
    inactivo = replace(admin_user, estado=EstadoUsuario.INACTIVO)

    with pytest.raises(PermisoAuditoriaException, match="activa"):
        ServicioAuditoria.consultar_eventos([], operador=inactivo)
