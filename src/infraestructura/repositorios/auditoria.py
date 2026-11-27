"""Repositorio estrictamente append-only para bitácora de auditoría SHA-256 (PBI-16)."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.dominio.auditoria import (
    HASH_GENESIS,
    ZONA_HORARIA_LIMA,
    ContextoAcademicoAuditoria,
    FiltroAuditoria,
    RegistroAuditoria,
    ResultadoAuditoria,
    TipoOperacionAuditoria,
)
from src.infraestructura.modelos import AuditoriaEventoModel


def _normalizar_lima(fecha_hora: datetime) -> datetime:
    """Normaliza una fecha al huso institucional America/Lima (UTC-5)."""
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=ZONA_HORARIA_LIMA)
    return fecha_hora.astimezone(ZONA_HORARIA_LIMA)


def _serializar_contexto(contexto: ContextoAcademicoAuditoria | None) -> str | None:
    if contexto is None:
        return None
    return json.dumps(
        {
            "nivel": contexto.nivel,
            "grado": contexto.grado,
            "seccion": contexto.seccion,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _deserializar_contexto(raw: str | None) -> ContextoAcademicoAuditoria | None:
    if not raw:
        return None
    datos = json.loads(raw)
    return ContextoAcademicoAuditoria(
        nivel=datos["nivel"],
        grado=datos["grado"],
        seccion=datos["seccion"],
    )


class RepositorioAuditoria:
    """Persistencia append-only de eventos de auditoría encadenados por SHA-256.

    No expone operaciones de actualización ni borrado (RN-16 / PBI-16).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _a_dominio(modelo: AuditoriaEventoModel) -> RegistroAuditoria:
        detalle = json.loads(modelo.detalle_json)
        return RegistroAuditoria(
            id=modelo.id,
            secuencia=modelo.secuencia,
            fecha_hora=_normalizar_lima(modelo.fecha_hora),
            usuario_id=modelo.usuario_id,
            rol_ejecutante=modelo.rol_ejecutante,
            operacion=TipoOperacionAuditoria(modelo.operacion),
            entidad=modelo.entidad,
            entidad_id=modelo.entidad_id,
            resultado=ResultadoAuditoria(modelo.resultado),
            detalle=detalle,
            alumno_id=modelo.alumno_id,
            metodo_asistencia=modelo.metodo_asistencia,
            contexto_academico=_deserializar_contexto(modelo.contexto_academico),
            estado_anterior=modelo.estado_anterior,
            estado_nuevo=modelo.estado_nuevo,
            motivo=modelo.motivo,
            hash_anterior=modelo.hash_anterior,
            hash_integridad=modelo.hash_integridad,
        )

    def registrar(self, evento: RegistroAuditoria) -> RegistroAuditoria:
        """Inserta un nuevo evento inmutable usando flush() para atomicidad UoW."""
        modelo = AuditoriaEventoModel(
            id=evento.id,
            secuencia=evento.secuencia,
            fecha_hora=_normalizar_lima(evento.fecha_hora),
            usuario_id=evento.usuario_id,
            rol_ejecutante=evento.rol_ejecutante,
            operacion=evento.operacion.value,
            entidad=evento.entidad,
            entidad_id=evento.entidad_id,
            metodo_asistencia=evento.metodo_asistencia,
            alumno_id=evento.alumno_id,
            contexto_academico=_serializar_contexto(evento.contexto_academico),
            estado_anterior=evento.estado_anterior,
            estado_nuevo=evento.estado_nuevo,
            motivo=evento.motivo,
            resultado=evento.resultado.value,
            detalle_json=json.dumps(
                dict(evento.detalle),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            hash_anterior=evento.hash_anterior,
            hash_integridad=evento.hash_integridad,
        )
        self._session.add(modelo)
        self._session.flush()
        return self._a_dominio(modelo)

    def obtener_por_id(self, evento_id: str) -> RegistroAuditoria | None:
        modelo = self._session.get(AuditoriaEventoModel, evento_id)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_ultimo(self) -> RegistroAuditoria | None:
        stmt = select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia.desc()).limit(1)
        modelo = self._session.scalar(stmt)
        return None if modelo is None else self._a_dominio(modelo)

    def obtener_ultimo_hash(self) -> str:
        """Devuelve el último hash de la cadena o HASH_GENESIS si la bitácora está vacía."""
        stmt = (
            select(AuditoriaEventoModel.hash_integridad)
            .order_by(AuditoriaEventoModel.secuencia.desc())
            .limit(1)
        )
        ultimo_hash = self._session.scalar(stmt)
        return HASH_GENESIS if ultimo_hash is None else ultimo_hash

    def siguiente_secuencia(self) -> int:
        ultima = self._session.scalar(select(func.max(AuditoriaEventoModel.secuencia)))
        return 1 if ultima is None else int(ultima) + 1

    def contar(self) -> int:
        total = self._session.scalar(select(func.count()).select_from(AuditoriaEventoModel))
        return int(total or 0)

    def listar(self, filtro: FiltroAuditoria | None = None) -> list[RegistroAuditoria]:
        """Consulta eventos ordenados por secuencia ascendente aplicando filtros opcionales."""
        stmt = select(AuditoriaEventoModel).order_by(AuditoriaEventoModel.secuencia.asc())
        if filtro is not None:
            if filtro.fecha_desde is not None:
                stmt = stmt.where(AuditoriaEventoModel.fecha_hora >= filtro.fecha_desde)
            if filtro.fecha_hasta is not None:
                stmt = stmt.where(AuditoriaEventoModel.fecha_hora <= filtro.fecha_hasta)
            if filtro.usuario_id is not None:
                stmt = stmt.where(AuditoriaEventoModel.usuario_id == filtro.usuario_id)
            if filtro.rol is not None:
                stmt = stmt.where(AuditoriaEventoModel.rol_ejecutante == filtro.rol.strip().upper())
            if filtro.operacion is not None:
                operacion_str = (
                    getattr(filtro.operacion, "value", str(filtro.operacion)).strip().upper()
                )
                stmt = stmt.where(AuditoriaEventoModel.operacion == operacion_str)
            if filtro.entidad is not None:
                stmt = stmt.where(AuditoriaEventoModel.entidad == filtro.entidad.strip().upper())
            if filtro.alumno_id is not None:
                stmt = stmt.where(AuditoriaEventoModel.alumno_id == filtro.alumno_id)
            if filtro.resultado is not None:
                stmt = stmt.where(AuditoriaEventoModel.resultado == filtro.resultado.value)
        return [self._a_dominio(m) for m in self._session.scalars(stmt).all()]
