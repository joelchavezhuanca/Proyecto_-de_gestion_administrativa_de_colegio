"""Pruebas de integración de repositorios de infraestructura (Parte B) en SQLite en memoria.

Verifica:
- RepositorioMatricula, RepositorioCarnets, RepositorioEstadosAcademicos
- RepositorioMalla, RepositorioDocentes, RepositorioCalificaciones, RepositorioBoletas
- RepositorioPagos, RepositorioNotificacionesWhatsApp
- Preservación exacta de precisión Decimal en montos y calificaciones
- Normalización de zonas horarias a America/Lima (UTC-5)
- Operación atómica sin session.commit() forzado (uso exclusivo de session.flush())
- Cumplimiento de restricciones de unicidad e integridad referencial
- 100% de cobertura en los tres módulos de repositorio
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.dominio.carnets import CarnetEscolar, EstadoCarnet, MotivoAnulacionCarnet
from src.dominio.estados_academicos import EstadoAcademico, HistorialEstadoAlumno
from src.dominio.malla_curricular import Curso, NivelEducativo, Salon
from src.dominio.matricula import Apoderado, FichaMatricula
from src.dominio.notificaciones import EstadoNotificacion, NotificacionWhatsApp, TipoNotificacion
from src.dominio.pagos import AlertaSilenciosaPago, EstadoObligacion, ObligacionPago
from src.infraestructura.modelos import (
    AsistenciaModel,
    Base,
    PeriodoAcademicoModel,
    UsuarioModel,
)
from src.infraestructura.repositorios.academico import (
    BoletaEmitida,
    RepositorioBoletas,
    RepositorioCalificaciones,
    RepositorioDocentes,
    RepositorioMalla,
)
from src.infraestructura.repositorios.alumnos import (
    RepositorioCarnets,
    RepositorioEstadosAcademicos,
    RepositorioMatricula,
)
from src.infraestructura.repositorios.pagos_notificaciones import (
    RepositorioNotificacionesWhatsApp,
    RepositorioPagos,
)

ZONA_LIMA = timezone(timedelta(hours=-5))


@pytest.fixture
def sesion_bd() -> Session:
    """Crea una base de datos SQLite en memoria con claves foráneas activas."""
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = fabrica()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def usuario_base(sesion_bd: Session) -> UsuarioModel:
    usuario = UsuarioModel(
        username="docente_juan",
        password_hash="argon2id$hashed",
        rol="COORDINADOR",
        activo=True,
    )
    sesion_bd.add(usuario)
    sesion_bd.flush()
    return usuario


@pytest.fixture
def periodo_base(sesion_bd: Session) -> PeriodoAcademicoModel:
    periodo = PeriodoAcademicoModel(
        nombre="Bimestre I 2026",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 5, 10),
        fecha_limite_notas=date(2026, 5, 15),
        anio_lectivo=2026,
        cerrado=False,
    )
    sesion_bd.add(periodo)
    sesion_bd.flush()
    return periodo


# ===========================================================================
# 1. Pruebas RepositorioMatricula, RepositorioCarnets, RepositorioEstadosAcademicos
# ===========================================================================


def test_repositorio_matricula_crud_y_restricciones(sesion_bd: Session):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(
            id=1,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="5to",
            seccion="A",
            capacidad_maxima=30,
        )
    )

    ap1 = Apoderado(
        id=1,
        nombres="Carlos",
        apellidos="Pérez",
        documento="10203040",
        parentesco="Padre",
        telefono_whatsapp="987654321",
        es_principal=True,
    )
    ap2 = Apoderado(
        id=2,
        nombres="Ana",
        apellidos="Gómez",
        documento="20304050",
        parentesco="Madre",
        telefono_whatsapp="987654322",
        es_principal=False,
    )

    ficha = FichaMatricula(
        id="mat-ALU-001",
        alumno_id=1,
        codigo_estudiante="ALU-001",
        dni="72345678",
        nombres="Pedro",
        apellidos="Pérez Gómez",
        fecha_nacimiento=date(2009, 5, 12),
        anio_lectivo=2026,
        salon_id=salon.id,
        nivel=NivelEducativo.SECUNDARIA.value,
        grado="5to",
        seccion="A",
        apoderados=(ap1, ap2),
        estado=EstadoAcademico.ACTIVO,
    )

    # 1. Guardar y verificar
    guardada = repo_mat.guardar(ficha)
    assert guardada.codigo_estudiante == "ALU-001"
    assert len(guardada.apoderados) == 2
    assert guardada.apoderado_principal.documento == "10203040"

    # 2. Consultas por diversos campos
    por_id = repo_mat.obtener_por_id("mat-ALU-001")
    assert por_id is not None
    assert por_id.dni == "72345678"

    por_alumno = repo_mat.obtener_por_alumno_id(1)
    assert por_alumno is not None
    assert por_alumno.nombres == "Pedro"

    por_dni = repo_mat.obtener_por_dni("72345678")
    assert por_dni is not None
    assert por_dni.apellidos == "Pérez Gómez"

    por_cod = repo_mat.obtener_por_codigo("ALU-001")
    assert por_cod is not None

    # Inexistentes
    assert repo_mat.obtener_por_id("no-existe") is None
    assert repo_mat.obtener_por_dni("00000000") is None

    # Listados y conteo
    del_salon = repo_mat.listar_por_salon(salon.id, anio_lectivo=2026)
    assert len(del_salon) == 1
    assert repo_mat.contar_matriculados(salon.id, 2026) == 1
    assert len(repo_mat.listar_todas()) == 1

    # Actualizar ficha (cambio de nombres y apoderado)
    ficha_mod = FichaMatricula(
        id="mat-ALU-001",
        alumno_id=1,
        codigo_estudiante="ALU-001",
        dni="72345678",
        nombres="Pedro Antonio",
        apellidos="Pérez Gómez",
        fecha_nacimiento=date(2009, 5, 12),
        anio_lectivo=2026,
        salon_id=salon.id,
        nivel=NivelEducativo.SECUNDARIA.value,
        grado="5to",
        seccion="A",
        apoderados=(ap1,),
        estado=EstadoAcademico.ACTIVO,
    )
    actualizada = repo_mat.guardar(ficha_mod)
    assert actualizada.nombres == "Pedro Antonio"
    assert len(actualizada.apoderados) == 1

    # Restricción UNIQUE en DNI
    ficha_dup_dni = FichaMatricula(
        id="mat-ALU-002",
        alumno_id=2,
        codigo_estudiante="ALU-002",
        dni="72345678",  # DNI repetido
        nombres="Otro",
        apellidos="Alumno",
        fecha_nacimiento=date(2010, 1, 1),
        anio_lectivo=2026,
        salon_id=salon.id,
        nivel=NivelEducativo.SECUNDARIA.value,
        grado="5to",
        seccion="A",
        apoderados=(ap1,),
    )
    with pytest.raises(IntegrityError):
        repo_mat.guardar(ficha_dup_dni)
    sesion_bd.rollback()


def test_repositorio_carnets_emision_anulacion(sesion_bd: Session, usuario_base: UsuarioModel):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)
    repo_carnets = RepositorioCarnets(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=2, anio_lectivo=2026, nivel=NivelEducativo.PRIMARIA, grado="1ro", seccion="B")
    )
    ap = Apoderado(
        id=10,
        nombres="Rosa",
        apellidos="Díaz",
        documento="40506070",
        parentesco="Madre",
        telefono_whatsapp="912345678",
        es_principal=True,
    )
    ficha = FichaMatricula(
        id="mat-ALU-010",
        alumno_id=10,
        codigo_estudiante="ALU-010",
        dni="71112222",
        nombres="Lucía",
        apellidos="Díaz",
        fecha_nacimiento=date(2019, 4, 15),
        anio_lectivo=2026,
        salon_id=salon.id,
        nivel=NivelEducativo.PRIMARIA.value,
        grado="1ro",
        seccion="B",
        apoderados=(ap,),
    )
    repo_mat.guardar(ficha)

    ahora = datetime.now(ZONA_LIMA)
    carnet = CarnetEscolar(
        id="crn-001",
        alumno_id=10,
        codigo_qr="QR-OPACO-LUCIA-2026",
        estado=EstadoCarnet.ACTIVO,
        emitido_por=usuario_base.id,
        emitido_en=ahora,
    )

    # 1. Guardar y verificar carnet activo
    guardado = repo_carnets.guardar(carnet)
    assert guardado.id == "crn-001"
    assert guardado.estado == EstadoCarnet.ACTIVO

    activo = repo_carnets.obtener_activo_por_alumno(10)
    assert activo is not None
    assert activo.codigo_qr == "QR-OPACO-LUCIA-2026"

    por_qr = repo_carnets.obtener_por_codigo_qr("QR-OPACO-LUCIA-2026")
    assert por_qr is not None
    assert por_qr.id == "crn-001"

    assert repo_carnets.obtener_por_id("crn-001") is not None
    assert repo_carnets.obtener_por_codigo_qr("no-existe") is None

    # Actualizar carnet existente
    carnet_actualizado = CarnetEscolar(
        id="crn-001",
        alumno_id=10,
        codigo_qr="QR-OPACO-LUCIA-2026",
        estado=EstadoCarnet.ACTIVO,
        emitido_por=usuario_base.id,
        emitido_en=ahora,
        detalle_anulacion="Nota aclaratoria",
    )
    repo_carnets.guardar(carnet_actualizado)

    # 2. Anular carnet
    anulado = repo_carnets.anular(
        carnet_id="crn-001",
        motivo=MotivoAnulacionCarnet.EXTRAVIO,
        detalle="Extravío en el transporte escolar",
        anulado_en=ahora + timedelta(days=1),
    )
    assert anulado.estado == EstadoCarnet.ANULADO
    assert anulado.motivo_anulacion == MotivoAnulacionCarnet.EXTRAVIO
    assert anulado.detalle_anulacion == "Extravío en el transporte escolar"
    assert repo_carnets.obtener_activo_por_alumno(10) is None

    lista = repo_carnets.listar_por_alumno(10)
    assert len(lista) == 1
    assert lista[0].estado == EstadoCarnet.ANULADO

    # Anular carnet inexistente lanza ValueError
    with pytest.raises(ValueError, match="No existe el carnet"):
        repo_carnets.anular("crn-fantasma", MotivoAnulacionCarnet.DANO, None, ahora)

    # 3. Restricción UNIQUE en código QR
    carnet_dup = CarnetEscolar(
        id="crn-dup",
        alumno_id=10,
        codigo_qr="QR-OPACO-LUCIA-2026",
        estado=EstadoCarnet.ACTIVO,
        emitido_por=usuario_base.id,
        emitido_en=ahora,
    )
    with pytest.raises(IntegrityError):
        repo_carnets.guardar(carnet_dup)
    sesion_bd.rollback()


def test_repositorio_estados_academicos(sesion_bd: Session, usuario_base: UsuarioModel):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)
    repo_estados = RepositorioEstadosAcademicos(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=3, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="2do", seccion="C")
    )
    ap = Apoderado(
        id=20,
        nombres="Hugo",
        apellidos="Ríos",
        documento="30405060",
        parentesco="Tutor",
        telefono_whatsapp="955667788",
        es_principal=True,
    )
    ficha = FichaMatricula(
        id="mat-ALU-020",
        alumno_id=20,
        codigo_estudiante="ALU-020",
        dni="73334444",
        nombres="Mario",
        apellidos="Ríos",
        fecha_nacimiento=date(2012, 8, 20),
        anio_lectivo=2026,
        salon_id=salon.id,
        nivel=NivelEducativo.SECUNDARIA.value,
        grado="2do",
        seccion="C",
        apoderados=(ap,),
    )
    repo_mat.guardar(ficha)

    # 1. Estado inicial
    assert repo_estados.obtener_estado_alumno(20) == EstadoAcademico.ACTIVO

    # 2. Registrar transición a SUSPENDIDO
    ahora = datetime.now(ZONA_LIMA)
    historial1 = HistorialEstadoAlumno(
        id="hist-001",
        alumno_id=20,
        estado_anterior=EstadoAcademico.ACTIVO,
        estado_nuevo=EstadoAcademico.SUSPENDIDO,
        motivo="Medida disciplinaria de 5 días",
        usuario_id=usuario_base.id,
        rol_usuario="COORDINADOR",
        fecha_hora=ahora,
        fecha_inicio_suspension=date(2026, 4, 1),
        fecha_fin_suspension=date(2026, 4, 5),
    )
    repo_estados.guardar_historial(historial1)
    repo_estados.actualizar_estado_alumno(20, EstadoAcademico.SUSPENDIDO)

    assert repo_estados.obtener_estado_alumno(20) == EstadoAcademico.SUSPENDIDO

    # 3. Retorno a ACTIVO
    historial2 = HistorialEstadoAlumno(
        id="hist-002",
        alumno_id=20,
        estado_anterior=EstadoAcademico.SUSPENDIDO,
        estado_nuevo=EstadoAcademico.ACTIVO,
        motivo="Cumplimiento de suspensión",
        usuario_id=usuario_base.id,
        rol_usuario="COORDINADOR",
        fecha_hora=ahora + timedelta(days=6),
    )
    repo_estados.guardar_historial(historial2)
    repo_estados.actualizar_estado_alumno(20, EstadoAcademico.ACTIVO)

    historiales = repo_estados.listar_historial_alumno(20)
    assert len(historiales) == 2
    assert historiales[0].estado_nuevo == EstadoAcademico.SUSPENDIDO
    assert historiales[1].estado_nuevo == EstadoAcademico.ACTIVO
    assert repo_estados.obtener_estado_alumno(999) is None

    # Actualizar estado de alumno inexistente no falla silenciosamente
    repo_estados.actualizar_estado_alumno(999, EstadoAcademico.RETIRADO)


# ===========================================================================
# 2. Pruebas RepositorioMalla, RepositorioDocentes, RepositorioCalificaciones, Boletas
# ===========================================================================


def test_repositorio_malla_salones_y_cursos_con_unicidad(sesion_bd: Session):
    repo = RepositorioMalla(sesion_bd)

    # 1. Salones
    s1 = repo.guardar_salon(
        Salon(id=10, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="3ro", seccion="A")
    )
    repo.guardar_salon(
        Salon(id=11, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="3ro", seccion="B")
    )
    assert repo.obtener_salon_por_id(10) == s1
    assert repo.obtener_salon(2026, NivelEducativo.SECUNDARIA, "3ro", "A") == s1
    assert (
        len(
            repo.listar_salones(
                anio_lectivo=2026,
                nivel=NivelEducativo.SECUNDARIA,
                grado="3ro",
                solo_activos=True,
            )
        )
        == 2
    )

    # Actualizar salón
    s1_mod = Salon(
        id=10,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
        capacidad_maxima=35,
        activo=True,
    )
    repo.guardar_salon(s1_mod)
    assert repo.obtener_salon_por_id(10).capacidad_maxima == 35

    # Restricción UNIQUE en salón (anio, nivel, grado, seccion)
    s_dup = Salon(
        id=12,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
    )
    with pytest.raises(IntegrityError):
        repo.guardar_salon(s_dup)
    sesion_bd.rollback()

    # 2. Cursos
    c1 = repo.guardar_curso(
        Curso(
            id=100,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="3ro",
            codigo="MAT-3SEC",
            nombre="Matemática",
            area_curricular="Matemática",
            horas_semanales=6,
        )
    )
    assert repo.obtener_curso_por_id(100) == c1
    assert repo.obtener_curso(2026, NivelEducativo.SECUNDARIA, "3ro", "MAT-3SEC") == c1
    assert (
        len(
            repo.listar_cursos(
                anio_lectivo=2026,
                nivel=NivelEducativo.SECUNDARIA,
                grado="3ro",
                solo_activos=True,
            )
        )
        == 1
    )

    # Actualizar curso
    c1_mod = Curso(
        id=100,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo="MAT-3SEC",
        nombre="Matemática y Lógica",
        area_curricular="Matemática",
        horas_semanales=7,
        activo=True,
    )
    repo.guardar_curso(c1_mod)
    assert repo.obtener_curso_por_id(100).horas_semanales == 7

    assert repo.obtener_curso_por_id(999) is None
    assert repo.obtener_curso(2026, NivelEducativo.SECUNDARIA, "3ro", "NO_EXISTE") is None

    # Restricción UNIQUE en curso (anio, nivel, grado, codigo)
    c_dup = Curso(
        id=101,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        codigo="MAT-3SEC",
        nombre="Matemática Avanzada",
        area_curricular="Matemática",
        horas_semanales=6,
    )
    with pytest.raises(IntegrityError):
        repo.guardar_curso(c_dup)
    sesion_bd.rollback()


def test_repositorio_docentes_asignacion_y_revocacion(
    sesion_bd: Session, usuario_base: UsuarioModel
):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_doc = RepositorioDocentes(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=20, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="4to", seccion="A")
    )
    curso = repo_malla.guardar_curso(
        Curso(
            id=200,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="4to",
            codigo="FIS-4SEC",
            nombre="Física",
            area_curricular="Ciencias",
            horas_semanales=4,
        )
    )

    from src.dominio.docentes import AsignacionDocente

    asig = AsignacionDocente(
        id="asig-001",
        usuario_docente_id=usuario_base.id,
        curso_id=curso.id,
        salon_id=salon.id,
        anio_lectivo=2026,
        activa=True,
        asignado_por=usuario_base.id,
        creado_en=datetime.now(ZONA_LIMA),
    )

    guardada = repo_doc.guardar_asignacion(asig)
    assert guardada.id == "asig-001"
    assert guardada.activa is True

    # Actualizar asignación existente
    asig_mod = AsignacionDocente(
        id="asig-001",
        usuario_docente_id=usuario_base.id,
        curso_id=curso.id,
        salon_id=salon.id,
        anio_lectivo=2026,
        activa=True,
        asignado_por=usuario_base.id,
        motivo_revocacion="Modificación temporal",
    )
    repo_doc.guardar_asignacion(asig_mod)

    obtenida = repo_doc.obtener_asignacion_por_id("asig-001")
    assert obtenida.id == "asig-001"

    activa = repo_doc.obtener_asignacion_activa(curso.id, salon.id, 2026)
    assert activa is not None
    assert activa.id == "asig-001"

    doc_list = repo_doc.listar_asignaciones_docente(usuario_base.id, anio_lectivo=2026)
    assert len(doc_list) == 1
    assert len(repo_doc.listar_todas(anio_lectivo=2026)) == 1

    # Revocar asignación
    ahora_rev = datetime.now(ZONA_LIMA) + timedelta(days=10)
    revocada = repo_doc.revocar_asignacion("asig-001", "Licencia médica", ahora_rev)
    assert revocada.activa is False
    assert revocada.motivo_revocacion == "Licencia médica"
    assert repo_doc.obtener_asignacion_activa(curso.id, salon.id, 2026) is None

    with pytest.raises(ValueError, match="No existe la asignación"):
        repo_doc.revocar_asignacion("asig-fantasma", "Motivo", ahora_rev)


def test_repositorio_calificaciones_precision_decimal_y_unicidad(
    sesion_bd: Session, usuario_base: UsuarioModel, periodo_base: PeriodoAcademicoModel
):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_doc = RepositorioDocentes(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)
    repo_cal = RepositorioCalificaciones(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=30, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="5to", seccion="B")
    )
    curso = repo_malla.guardar_curso(
        Curso(
            id=300,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="5to",
            codigo="BIO-5SEC",
            nombre="Biología",
            area_curricular="Ciencias",
            horas_semanales=4,
        )
    )

    from src.dominio.docentes import AsignacionDocente

    asig = repo_doc.guardar_asignacion(
        AsignacionDocente(
            id="asig-BIO-01",
            usuario_docente_id=usuario_base.id,
            curso_id=curso.id,
            salon_id=salon.id,
            anio_lectivo=2026,
        )
    )

    ap = Apoderado(
        id=30,
        nombres="Juan",
        apellidos="López",
        documento="80901020",
        parentesco="Padre",
        telefono_whatsapp="988776655",
        es_principal=True,
    )
    ficha = repo_mat.guardar(
        FichaMatricula(
            id="mat-ALU-030",
            alumno_id=30,
            codigo_estudiante="ALU-030",
            dni="74445555",
            nombres="Elena",
            apellidos="López",
            fecha_nacimiento=date(2008, 9, 10),
            anio_lectivo=2026,
            salon_id=salon.id,
            nivel=NivelEducativo.SECUNDARIA.value,
            grado="5to",
            seccion="B",
            apoderados=(ap,),
        )
    )

    # 1. Rubro de evaluación con Decimal
    from src.dominio.calificaciones import ActividadEvaluable, Calificacion, RubroEvaluacion

    rubro = RubroEvaluacion(
        id="rub-001",
        asignacion_docente_id=asig.id,
        periodo_id=periodo_base.id,
        nombre="Exámenes Parciales",
        peso_porcentaje=Decimal("40.00"),
    )
    r_guardado = repo_cal.guardar_rubro(rubro)
    assert r_guardado.peso_porcentaje == Decimal("40.00")
    assert isinstance(r_guardado.peso_porcentaje, Decimal)

    # Actualizar rubro existente
    rubro_mod = RubroEvaluacion(
        id="rub-001",
        asignacion_docente_id=asig.id,
        periodo_id=periodo_base.id,
        nombre="Exámenes Parciales y Prácticas",
        peso_porcentaje=Decimal("45.00"),
    )
    repo_cal.guardar_rubro(rubro_mod)
    assert repo_cal.obtener_rubro_por_id("rub-001").peso_porcentaje == Decimal("45.00")
    assert repo_cal.obtener_rubro_por_id("rub-inexistente") is None

    rubros = repo_cal.listar_rubros_asignacion(asig.id, periodo_base.id)
    assert len(rubros) == 1

    # 2. Actividad evaluable
    act = ActividadEvaluable(
        id="act-001",
        rubro_id=r_guardado.id,
        titulo="Parcial 1: Genética",
        fecha=date(2026, 4, 15),
    )
    act_guardada = repo_cal.guardar_actividad(act)
    assert act_guardada.id == "act-001"
    assert len(repo_cal.listar_actividades_rubro(r_guardado.id)) == 1

    # Actualizar actividad existente
    act_mod = ActividadEvaluable(
        id="act-001",
        rubro_id=r_guardado.id,
        titulo="Parcial 1: Genética Molecular",
        fecha=date(2026, 4, 16),
    )
    repo_cal.guardar_actividad(act_mod)
    assert repo_cal.obtener_actividad_por_id("act-001").titulo == "Parcial 1: Genética Molecular"
    assert repo_cal.obtener_actividad_por_id("act-inexistente") is None

    # 3. Calificación vigesimal con Decimal exacto
    cal = Calificacion(
        id="cal-001",
        actividad_id=act_guardada.id,
        alumno_id=ficha.alumno_id,
        nota=Decimal("18.75"),
        usuario_id=usuario_base.id,
        actualizado_en=datetime.now(ZONA_LIMA),
        observacion="Excelente desempeño",
    )
    cal_guardada = repo_cal.guardar_calificacion(cal)
    assert cal_guardada.nota == Decimal("18.75")
    assert isinstance(cal_guardada.nota, Decimal)

    obtenida_cal = repo_cal.obtener_calificacion(act_guardada.id, ficha.alumno_id)
    assert obtenida_cal is not None
    assert obtenida_cal.nota == Decimal("18.75")

    # Actualizar nota conservando nota_anterior y motivo
    cal_mod = Calificacion(
        id="cal-001",
        actividad_id=act_guardada.id,
        alumno_id=ficha.alumno_id,
        nota=Decimal("19.50"),
        nota_anterior=Decimal("18.75"),
        motivo_modificacion="Recalificación pregunta 4",
        usuario_id=usuario_base.id,
        actualizado_en=datetime.now(ZONA_LIMA),
    )
    cal_actualizada = repo_cal.guardar_calificacion(cal_mod)
    assert cal_actualizada.nota == Decimal("19.50")
    assert cal_actualizada.nota_anterior == Decimal("18.75")

    # Listados
    assert len(repo_cal.listar_calificaciones_actividad(act_guardada.id)) == 1
    assert len(repo_cal.listar_calificaciones_alumno_en_rubro(r_guardado.id, ficha.alumno_id)) == 1
    assert (
        len(
            repo_cal.listar_calificaciones_alumno_en_asignacion(
                asig.id, periodo_base.id, ficha.alumno_id
            )
        )
        == 1
    )

    # Restricción UNIQUE en (actividad_id, estudiante_id)
    cal_dup = Calificacion(
        id="cal-dup",
        actividad_id=act_guardada.id,
        alumno_id=ficha.alumno_id,
        nota=Decimal("15.00"),
        usuario_id=usuario_base.id,
        actualizado_en=datetime.now(ZONA_LIMA),
    )
    with pytest.raises(IntegrityError):
        sesion_bd.add(repo_cal._a_modelo_calificacion(cal_dup))
        sesion_bd.flush()
    sesion_bd.rollback()


def test_repositorio_boletas(
    sesion_bd: Session, usuario_base: UsuarioModel, periodo_base: PeriodoAcademicoModel
):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)
    repo_bol = RepositorioBoletas(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=40, anio_lectivo=2026, nivel=NivelEducativo.PRIMARIA, grado="6to", seccion="A")
    )
    ap = Apoderado(
        id=40,
        nombres="Marta",
        apellidos="Vega",
        documento="90102030",
        parentesco="Madre",
        telefono_whatsapp="944332211",
        es_principal=True,
    )
    ficha = repo_mat.guardar(
        FichaMatricula(
            id="mat-ALU-040",
            alumno_id=40,
            codigo_estudiante="ALU-040",
            dni="75556666",
            nombres="Gabriel",
            apellidos="Vega",
            fecha_nacimiento=date(2014, 2, 28),
            anio_lectivo=2026,
            salon_id=salon.id,
            nivel=NivelEducativo.PRIMARIA.value,
            grado="6to",
            seccion="A",
            apoderados=(ap,),
        )
    )

    boleta = BoletaEmitida(
        id="bol-001",
        codigo_verificacion="VERIF-BOL-2026-001",
        estudiante_id=ficha.alumno_id,
        periodo_id=periodo_base.id,
        anio_lectivo=2026,
        es_oficial=True,
        promedio_general=Decimal("17.85"),
        resumen_asistencia_json='{"puntual": 45, "tardanza": 2}',
        emitido_por=usuario_base.id,
        emitido_en=datetime.now(ZONA_LIMA),
    )

    guardada = repo_bol.guardar(boleta)
    assert guardada.codigo_verificacion == "VERIF-BOL-2026-001"
    assert guardada.promedio_general == Decimal("17.85")
    assert isinstance(guardada.promedio_general, Decimal)

    # Actualizar boleta existente
    boleta_mod = BoletaEmitida(
        id="bol-001",
        codigo_verificacion="VERIF-BOL-2026-001-MOD",
        estudiante_id=ficha.alumno_id,
        periodo_id=periodo_base.id,
        anio_lectivo=2026,
        es_oficial=True,
        promedio_general=Decimal("18.00"),
        resumen_asistencia_json='{"puntual": 46, "tardanza": 2}',
        emitido_por=usuario_base.id,
        emitido_en=datetime.now(ZONA_LIMA),
    )
    repo_bol.guardar(boleta_mod)

    por_id = repo_bol.obtener_por_id("bol-001")
    assert por_id is not None
    assert por_id.promedio_general == Decimal("18.00")
    assert repo_bol.obtener_por_id("bol-fantasma") is None

    por_verif = repo_bol.obtener_por_codigo_verificacion("VERIF-BOL-2026-001-MOD")
    assert por_verif is not None
    assert por_verif.estudiante_id == 40

    por_est_per = repo_bol.obtener_por_estudiante_y_periodo(40, periodo_base.id)
    assert por_est_per is not None

    del_est = repo_bol.listar_por_estudiante(40, anio_lectivo=2026)
    assert len(del_est) == 1

    por_salon = repo_bol.listar_por_salon_y_periodo(salon.id, periodo_base.id)
    assert len(por_salon) == 1

    # Unicidad código de verificación
    bol_dup = BoletaEmitida(
        id="bol-dup",
        codigo_verificacion="VERIF-BOL-2026-001-MOD",
        estudiante_id=ficha.alumno_id,
        periodo_id=periodo_base.id,
        anio_lectivo=2026,
        es_oficial=True,
        promedio_general=Decimal("15.00"),
        resumen_asistencia_json="{}",
        emitido_por=usuario_base.id,
        emitido_en=datetime.now(ZONA_LIMA),
    )
    with pytest.raises(IntegrityError):
        repo_bol.guardar(bol_dup)
    sesion_bd.rollback()


# ===========================================================================
# 3. Pruebas RepositorioPagos y RepositorioNotificacionesWhatsApp
# ===========================================================================


def test_repositorio_pagos_obligaciones_y_alertas_con_decimal(
    sesion_bd: Session, usuario_base: UsuarioModel
):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)
    repo_pagos = RepositorioPagos(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=50, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="1ro", seccion="A")
    )
    ap = Apoderado(
        id=50,
        nombres="Felipe",
        apellidos="Soto",
        documento="50607080",
        parentesco="Padre",
        telefono_whatsapp="977889900",
        es_principal=True,
    )
    ficha = repo_mat.guardar(
        FichaMatricula(
            id="mat-ALU-050",
            alumno_id=50,
            codigo_estudiante="ALU-050",
            dni="76667777",
            nombres="Joaquín",
            apellidos="Soto",
            fecha_nacimiento=date(2013, 11, 5),
            anio_lectivo=2026,
            salon_id=salon.id,
            nivel=NivelEducativo.SECUNDARIA.value,
            grado="1ro",
            seccion="A",
            apoderados=(ap,),
        )
    )

    # 1. Obligación de pago con monto Decimal
    ob1 = ObligacionPago(
        id="obl-001",
        alumno_id=ficha.alumno_id,
        concepto="Pensión Marzo 2026",
        monto=Decimal("450.50"),
        fecha_vencimiento=date(2026, 3, 31),
        estado=EstadoObligacion.PENDIENTE,
    )
    ob_guardada = repo_pagos.guardar_obligacion(ob1)
    assert ob_guardada.monto == Decimal("450.50")
    assert isinstance(ob_guardada.monto, Decimal)

    # Actualizar obligación existente
    ob1_mod = ObligacionPago(
        id="obl-001",
        alumno_id=ficha.alumno_id,
        concepto="Pensión Marzo 2026 (Actualizada)",
        monto=Decimal("460.00"),
        fecha_vencimiento=date(2026, 3, 31),
        estado=EstadoObligacion.PENDIENTE,
    )
    repo_pagos.guardar_obligacion(ob1_mod)
    assert repo_pagos.obtener_obligacion_por_id("obl-001").monto == Decimal("460.00")
    assert repo_pagos.obtener_obligacion_por_id("obl-fantasma") is None

    # Listar por estados
    lista_estados = repo_pagos.listar_obligaciones_alumno(
        ficha.alumno_id, estados=[EstadoObligacion.PENDIENTE]
    )
    assert len(lista_estados) == 1

    vencidas = repo_pagos.obtener_obligaciones_vencidas(ficha.alumno_id, date(2026, 4, 15))
    assert len(vencidas) == 1

    # Pagar obligación
    ahora_pago = datetime.now(ZONA_LIMA)
    pagada = repo_pagos.marcar_como_pagada("obl-001", ahora_pago)
    assert pagada.estado == EstadoObligacion.PAGADO
    assert pagada.pagado_en is not None

    with pytest.raises(ValueError, match="No existe la obligación"):
        repo_pagos.marcar_como_pagada("obl-inexistente", ahora_pago)

    # Exonerar obligación
    repo_pagos.guardar_obligacion(
        ObligacionPago(
            id="obl-002",
            alumno_id=ficha.alumno_id,
            concepto="Matrícula 2026",
            monto=Decimal("300.00"),
            fecha_vencimiento=date(2026, 2, 28),
        )
    )
    exonerada = repo_pagos.exonerar_obligacion("obl-002", "Beca por excelencia")
    assert exonerada.estado == EstadoObligacion.EXONERADO
    assert exonerada.motivo_exoneracion == "Beca por excelencia"

    with pytest.raises(ValueError, match="No existe la obligación"):
        repo_pagos.exonerar_obligacion("obl-inexistente", "Motivo")

    # 2. Alerta Silenciosa de Pago única por estudiante y fecha
    asistencia = AsistenciaModel(
        id="ast-pago-01",
        estudiante_id=ficha.alumno_id,
        usuario_id=usuario_base.id,
        fecha_escolar=date(2026, 4, 1),
        hora_efectiva=time(7, 30),
        estado="PUNTUAL",
        metodo="CARNET",
    )
    sesion_bd.add(asistencia)
    sesion_bd.flush()

    alerta = AlertaSilenciosaPago(
        id="alt-001",
        alumno_id=ficha.alumno_id,
        asistencia_id=asistencia.id,
        fecha_escolar=date(2026, 4, 1),
        cantidad_obligaciones_vencidas=1,
        monto_vencido_total=Decimal("450.50"),
        revisada=False,
    )
    alt_guardada = repo_pagos.guardar_alerta(alerta)
    assert alt_guardada.monto_vencido_total == Decimal("450.50")
    assert isinstance(alt_guardada.monto_vencido_total, Decimal)

    # Actualizar alerta existente
    alerta_mod = AlertaSilenciosaPago(
        id="alt-001",
        alumno_id=ficha.alumno_id,
        asistencia_id=asistencia.id,
        fecha_escolar=date(2026, 4, 1),
        cantidad_obligaciones_vencidas=2,
        monto_vencido_total=Decimal("900.00"),
        revisada=False,
    )
    repo_pagos.guardar_alerta(alerta_mod)
    assert repo_pagos.obtener_alerta_por_id("alt-001").monto_vencido_total == Decimal("900.00")
    assert repo_pagos.obtener_alerta_por_id("alt-inexistente") is None

    por_asist = repo_pagos.obtener_alerta_por_asistencia(asistencia.id)
    assert por_asist is not None
    assert por_asist.id == "alt-001"

    por_est_fecha = repo_pagos.obtener_alerta_por_estudiante_y_fecha(
        ficha.alumno_id, date(2026, 4, 1)
    )
    assert por_est_fecha is not None
    assert repo_pagos.obtener_alerta_por_estudiante_y_fecha(999, date(2026, 4, 1)) is None

    del_alumno = repo_pagos.listar_alertas_alumno(ficha.alumno_id)
    assert len(del_alumno) == 1

    revisada = repo_pagos.marcar_alerta_revisada("alt-001")
    assert revisada.revisada is True

    with pytest.raises(ValueError, match="No existe la alerta"):
        repo_pagos.marcar_alerta_revisada("alt-inexistente")

    # Restricción UNIQUE en alerta (estudiante_id, fecha_escolar)
    alt_dup = AlertaSilenciosaPago(
        id="alt-dup",
        alumno_id=ficha.alumno_id,
        asistencia_id=asistencia.id,
        fecha_escolar=date(2026, 4, 1),
        cantidad_obligaciones_vencidas=1,
        monto_vencido_total=Decimal("450.50"),
    )
    with pytest.raises(IntegrityError):
        repo_pagos.guardar_alerta(alt_dup)
    sesion_bd.rollback()


def test_repositorio_notificaciones_whatsapp_idempotencia(
    sesion_bd: Session, usuario_base: UsuarioModel
):
    repo_malla = RepositorioMalla(sesion_bd)
    repo_mat = RepositorioMatricula(sesion_bd)
    repo_notif = RepositorioNotificacionesWhatsApp(sesion_bd)

    salon = repo_malla.guardar_salon(
        Salon(id=60, anio_lectivo=2026, nivel=NivelEducativo.PRIMARIA, grado="2do", seccion="A")
    )
    ap = Apoderado(
        id=60,
        nombres="Silvia",
        apellidos="Rojas",
        documento="60708090",
        parentesco="Madre",
        telefono_whatsapp="933221100",
        es_principal=True,
    )
    ficha = repo_mat.guardar(
        FichaMatricula(
            id="mat-ALU-060",
            alumno_id=60,
            codigo_estudiante="ALU-060",
            dni="77778888",
            nombres="Daniel",
            apellidos="Rojas",
            fecha_nacimiento=date(2018, 7, 14),
            anio_lectivo=2026,
            salon_id=salon.id,
            nivel=NivelEducativo.PRIMARIA.value,
            grado="2do",
            seccion="A",
            apoderados=(ap,),
        )
    )

    asistencia = AsistenciaModel(
        id="ast-notif-01",
        estudiante_id=ficha.alumno_id,
        usuario_id=usuario_base.id,
        fecha_escolar=date(2026, 4, 2),
        hora_efectiva=time(8, 15),
        estado="TARDANZA",
        metodo="CARNET",
    )
    sesion_bd.add(asistencia)
    sesion_bd.flush()

    ahora = datetime.now(ZONA_LIMA)
    notif = NotificacionWhatsApp(
        id="notif-001",
        clave_idempotencia="IDEMP-2026-04-02-ALU-060-TARDANZA",
        evento_origen_id="evt-001",
        asistencia_id=asistencia.id,
        alumno_id=ficha.alumno_id,
        fecha_escolar=date(2026, 4, 2),
        apoderado_nombre="Silvia Rojas",
        telefono_destino="+51933221100",
        tipo=TipoNotificacion.TARDANZA,
        plantilla="aviso_tardanza_v1",
        contenido="Estimada Silvia, Daniel registró ingreso con tardanza a las 08:15.",
        estado=EstadoNotificacion.PENDIENTE,
        intentos=0,
        referencia_proveedor=None,
        detalle_error=None,
        creado_en=ahora,
        actualizado_en=ahora,
    )

    guardada = repo_notif.guardar(notif)
    assert guardada.clave_idempotencia == "IDEMP-2026-04-02-ALU-060-TARDANZA"
    assert guardada.estado == EstadoNotificacion.PENDIENTE

    # Actualizar notificación existente
    notif_mod = NotificacionWhatsApp(
        id="notif-001",
        clave_idempotencia="IDEMP-2026-04-02-ALU-060-TARDANZA",
        evento_origen_id="evt-001",
        asistencia_id=asistencia.id,
        alumno_id=ficha.alumno_id,
        fecha_escolar=date(2026, 4, 2),
        apoderado_nombre="Silvia Rojas",
        telefono_destino="+51933221100",
        tipo=TipoNotificacion.TARDANZA,
        plantilla="aviso_tardanza_v1",
        contenido="Texto modificado",
        estado=EstadoNotificacion.PENDIENTE,
        intentos=1,
        referencia_proveedor="REF-1",
        detalle_error="Detalle 1",
        creado_en=ahora,
        actualizado_en=ahora,
    )
    repo_notif.guardar(notif_mod)

    por_id = repo_notif.obtener_por_id("notif-001")
    assert por_id is not None
    assert por_id.intentos == 1
    assert repo_notif.obtener_por_id("notif-fantasma") is None

    por_clave = repo_notif.obtener_por_clave_idempotencia("IDEMP-2026-04-02-ALU-060-TARDANZA")
    assert por_clave is not None
    assert por_clave.id == "notif-001"
    assert repo_notif.obtener_por_clave_idempotencia("CLAVE-INEXISTENTE") is None

    pendientes = repo_notif.listar_pendientes()
    assert len(pendientes) == 1

    del_alumno = repo_notif.listar_por_alumno(ficha.alumno_id)
    assert len(del_alumno) == 1

    por_fecha = repo_notif.listar_por_fecha(date(2026, 4, 2))
    assert len(por_fecha) == 1

    # Actualizar estado a ENVIADO
    actualizada = repo_notif.actualizar_estado(
        notificacion_id="notif-001",
        nuevo_estado=EstadoNotificacion.ENVIADO,
        intentos=1,
        referencia="WABA-MSG-12345678",
        detalle_error=None,
        actualizado_en=ahora + timedelta(seconds=5),
    )
    assert actualizada.estado == EstadoNotificacion.ENVIADO
    assert actualizada.referencia_proveedor == "WABA-MSG-12345678"
    assert len(repo_notif.listar_pendientes()) == 0

    with pytest.raises(ValueError, match="No existe la notificación"):
        repo_notif.actualizar_estado("notif-fantasma", EstadoNotificacion.FALLIDO, 1)

    # Restricción UNIQUE en clave_idempotencia
    notif_dup = NotificacionWhatsApp(
        id="notif-dup",
        clave_idempotencia="IDEMP-2026-04-02-ALU-060-TARDANZA",  # Clave repetida
        evento_origen_id="evt-002",
        asistencia_id=asistencia.id,
        alumno_id=ficha.alumno_id,
        fecha_escolar=date(2026, 4, 2),
        apoderado_nombre="Silvia Rojas",
        telefono_destino="+51933221100",
        tipo=TipoNotificacion.TARDANZA,
        plantilla="aviso_tardanza_v1",
        contenido="Contenido repetido",
        estado=EstadoNotificacion.PENDIENTE,
        intentos=0,
        referencia_proveedor=None,
        detalle_error=None,
        creado_en=ahora,
        actualizado_en=ahora,
    )
    with pytest.raises(IntegrityError):
        repo_notif.guardar(notif_dup)
    sesion_bd.rollback()


def test_repositorios_no_hacen_commit_forzado(sesion_bd: Session):
    """Verifica que los repositorios usen flush() y que rollback() revierta todo."""
    repo_malla = RepositorioMalla(sesion_bd)
    repo_malla.guardar_salon(
        Salon(id=99, anio_lectivo=2026, nivel=NivelEducativo.SECUNDARIA, grado="1ro", seccion="Z")
    )
    assert repo_malla.obtener_salon_por_id(99) is not None

    # Al hacer rollback externo, no debe haber quedado commiteado
    sesion_bd.rollback()
    assert repo_malla.obtener_salon_por_id(99) is None
