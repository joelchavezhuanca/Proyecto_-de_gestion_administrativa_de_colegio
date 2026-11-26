"""Pruebas BDD y unitarias del PBI-05: Ficha de Matrícula Digital."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from src.dominio.asistencia import (
    Alumno,
    DniInvalidoException,
    MetodoRegistro,
    RolUsuario,
    UsuarioOperador,
    registrar_asistencia_unificada,
)
from src.dominio.estados_academicos import EstadoAcademico
from src.dominio.malla_curricular import NivelEducativo, Salon
from src.dominio.matricula import (
    Apoderado,
    ApoderadoInvalidoException,
    FichaMatricula,
    MatriculaDuplicadaException,
    MatriculaException,
    PermisoMatriculaException,
    SalonInactivoException,
    SalonSinVacantesException,
    ServicioMatricula,
    normalizar_telefono_whatsapp_peru,
)
from src.dominio.usuarios import PermisoOperacion, Rol

ZONA_LIMA = timezone(timedelta(hours=-5))
FECHA_ACTUAL = date(2026, 3, 1)
FECHA_NAC_VALIDA = date(2012, 5, 14)


@pytest.fixture
def admin_op() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin_mat", rol=RolUsuario.ADMIN)


@pytest.fixture
def staff_op() -> UsuarioOperador:
    return UsuarioOperador(id=2, username="staff_mat", rol=RolUsuario.ADMIN_STAFF)


@pytest.fixture
def coord_op() -> UsuarioOperador:
    return UsuarioOperador(id=3, username="coord_mat", rol=RolUsuario.COORDINADOR)


@pytest.fixture
def salon_3a() -> Salon:
    return Salon(
        id=10,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
        capacidad_maxima=2,
        activo=True,
    )


@pytest.fixture
def salon_3b() -> Salon:
    return Salon(
        id=11,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="B",
        capacidad_maxima=2,
        activo=True,
    )


@pytest.fixture
def apoderado_principal() -> Apoderado:
    return Apoderado(
        id=1,
        nombres="  María Elena  ",
        apellidos="  Quispe Torres ",
        documento=" 40123456 ",
        parentesco=" Madre ",
        telefono_whatsapp="987 654 321",
        es_principal=True,
        activo=True,
    )


@pytest.fixture
def apoderado_secundario() -> Apoderado:
    return Apoderado(
        id=2,
        nombres="Carlos",
        apellidos="Gómez Ruiz",
        documento="41234567",
        parentesco="Padre",
        telefono_whatsapp="+51 912-345-678",
        es_principal=False,
        activo=True,
    )


def test_jerarquia_excepciones_matricula() -> None:
    assert issubclass(PermisoMatriculaException, MatriculaException)
    assert issubclass(ApoderadoInvalidoException, MatriculaException)
    assert issubclass(MatriculaDuplicadaException, MatriculaException)
    assert issubclass(SalonSinVacantesException, MatriculaException)
    assert issubclass(SalonInactivoException, MatriculaException)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("987654321", "+51987654321"),
        ("+51987654321", "+51987654321"),
        ("51987654321", "+51987654321"),
        (" 987-654-321 ", "+51987654321"),
        ("+51 (987) 654-321", "+51987654321"),
    ],
)
def test_normalizar_telefono_whatsapp_peru_validos(entrada: str, esperado: str) -> None:
    assert normalizar_telefono_whatsapp_peru(entrada) == esperado


@pytest.mark.parametrize(
    "telefono_invalido",
    [
        "",
        "   ",
        "812345678",
        "98765432",
        "9876543210",
        "+51812345678",
        "+54911223344",
        "98765abcd",
        None,
        987654321,
    ],
)
def test_normalizar_telefono_whatsapp_peru_rechaza_invalidos(
    telefono_invalido: object,
) -> None:
    with pytest.raises(ApoderadoInvalidoException):
        normalizar_telefono_whatsapp_peru(telefono_invalido)  # type: ignore[arg-type]


def test_apoderado_normaliza_campos_y_es_inmutable(apoderado_principal: Apoderado) -> None:
    assert apoderado_principal.nombres == "María Elena"
    assert apoderado_principal.apellidos == "Quispe Torres"
    assert apoderado_principal.documento == "40123456"
    assert apoderado_principal.parentesco == "Madre"
    assert apoderado_principal.telefono_whatsapp == "+51987654321"
    with pytest.raises(FrozenInstanceError):
        apoderado_principal.nombres = "Otro"  # type: ignore[misc]


@pytest.mark.parametrize(
    "cambios",
    [
        {"id": -1},
        {"id": True},
        {"nombres": ""},
        {"nombres": "   "},
        {"apellidos": ""},
        {"documento": "   "},
        {"parentesco": ""},
        {"telefono_whatsapp": "12345"},
        {"es_principal": "si"},
        {"activo": 1},
    ],
)
def test_apoderado_rechaza_datos_invalidos(cambios: dict[str, object]) -> None:
    base: dict[str, object] = {
        "id": 1,
        "nombres": "Ana",
        "apellidos": "López",
        "documento": "45678901",
        "parentesco": "Madre",
        "telefono_whatsapp": "999888777",
        "es_principal": True,
        "activo": True,
    }
    base.update(cambios)
    with pytest.raises(ApoderadoInvalidoException):
        Apoderado(**base)  # type: ignore[arg-type]


def test_ficha_matricula_valida_campos_normaliza_fecha_y_es_inmutable(
    apoderado_principal: Apoderado,
) -> None:
    creado_utc = datetime(2026, 3, 1, 15, 0, 0, tzinfo=UTC)
    ficha = FichaMatricula(
        id="  mat-001  ",
        alumno_id=100,
        codigo_estudiante="  EST-2026-001  ",
        dni="71234567",
        nombres="  Lucía  ",
        apellidos="  Pérez  ",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        anio_lectivo=2026,
        salon_id=10,
        nivel=NivelEducativo.SECUNDARIA,
        grado=" 3ro ",
        seccion=" A ",
        apoderados=(apoderado_principal,),
        estado=EstadoAcademico.ACTIVO,
        creado_en=creado_utc,
    )
    assert ficha.id == "mat-001"
    assert ficha.codigo_estudiante == "EST-2026-001"
    assert ficha.nombres == "Lucía"
    assert ficha.apellidos == "Pérez"
    assert ficha.nivel == "Secundaria"
    assert ficha.grado == "3ro"
    assert ficha.seccion == "A"
    assert ficha.creado_en == datetime(2026, 3, 1, 10, 0, 0, tzinfo=ZONA_LIMA)
    assert ficha.apoderado_principal == apoderado_principal

    ficha_naive = replace(ficha, creado_en=datetime(2026, 3, 1, 8, 30, 0))
    assert ficha_naive.creado_en == datetime(2026, 3, 1, 8, 30, 0, tzinfo=ZONA_LIMA)

    with pytest.raises(FrozenInstanceError):
        ficha.seccion = "B"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("cambios", "exc_esperada"),
    [
        ({"id": "  "}, MatriculaException),
        ({"alumno_id": 0}, MatriculaException),
        ({"alumno_id": True}, MatriculaException),
        ({"codigo_estudiante": ""}, MatriculaException),
        ({"dni": "123"}, DniInvalidoException),
        ({"nombres": ""}, MatriculaException),
        ({"apellidos": "  "}, MatriculaException),
        ({"fecha_nacimiento": datetime(2012, 5, 14, 10, 0)}, MatriculaException),
        ({"anio_lectivo": 1999}, MatriculaException),
        ({"salon_id": 0}, MatriculaException),
        ({"nivel": ""}, MatriculaException),
        ({"grado": ""}, MatriculaException),
        ({"seccion": ""}, MatriculaException),
        ({"estado": "ACTIVO"}, MatriculaException),
        ({"apoderados": "no-es-secuencia"}, ApoderadoInvalidoException),
        ({"apoderados": ("invalido",)}, ApoderadoInvalidoException),
        ({"apoderados": ()}, ApoderadoInvalidoException),
    ],
)
def test_ficha_matricula_rechaza_campos_invalidos(
    apoderado_principal: Apoderado,
    cambios: dict[str, object],
    exc_esperada: type[Exception],
) -> None:
    base: dict[str, object] = {
        "id": "mat-001",
        "alumno_id": 100,
        "codigo_estudiante": "EST-2026-001",
        "dni": "71234567",
        "nombres": "Lucía",
        "apellidos": "Pérez",
        "fecha_nacimiento": FECHA_NAC_VALIDA,
        "anio_lectivo": 2026,
        "salon_id": 10,
        "nivel": "Secundaria",
        "grado": "3ro",
        "seccion": "A",
        "apoderados": (apoderado_principal,),
        "estado": EstadoAcademico.ACTIVO,
        "creado_en": None,
    }
    base.update(cambios)
    with pytest.raises(exc_esperada):
        FichaMatricula(**base)  # type: ignore[arg-type]


def test_bdd_escenario_1_matricular_estudiante_exitoso_admin_y_staff(
    admin_op: UsuarioOperador,
    staff_op: UsuarioOperador,
    salon_3a: Salon,
    apoderado_principal: Apoderado,
    apoderado_secundario: Apoderado,
) -> None:
    ficha1 = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="  EST-2026-001 ",
        dni="71234567",
        nombres="  Mateo  ",
        apellidos="  Rojas Quispe ",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=[apoderado_principal, apoderado_secundario],
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )

    assert isinstance(ficha1, FichaMatricula)
    assert ficha1.id.startswith("mat-")
    assert ficha1.alumno_id == 101
    assert ficha1.codigo_estudiante == "EST-2026-001"
    assert ficha1.dni == "71234567"
    assert ficha1.nombres == "Mateo"
    assert ficha1.apellidos == "Rojas Quispe"
    assert ficha1.fecha_nacimiento == FECHA_NAC_VALIDA
    assert ficha1.anio_lectivo == 2026
    assert ficha1.salon_id == salon_3a.id
    assert ficha1.nivel == "Secundaria"
    assert ficha1.grado == "3ro"
    assert ficha1.seccion == "A"
    assert ficha1.estado == EstadoAcademico.ACTIVO
    assert ficha1.apoderados == (apoderado_principal, apoderado_secundario)
    assert ficha1.creado_en is not None
    assert ficha1.creado_en.tzinfo == ZONA_LIMA

    ficha2 = ServicioMatricula.matricular_estudiante(
        operador=staff_op,
        alumno_id=102,
        codigo_estudiante="EST-2026-002",
        dni="72345678",
        nombres="Sofía",
        apellidos="Vargas",
        fecha_nacimiento=date(2012, 8, 20),
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[ficha1],
        fecha_actual=FECHA_ACTUAL,
        creado_en=datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC),
    )
    assert ficha2.alumno_id == 102
    assert ficha2.salon_id == salon_3a.id
    assert ficha2.creado_en == datetime(2026, 3, 1, 9, 0, 0, tzinfo=ZONA_LIMA)


def test_matricular_mismo_estudiante_en_otro_anio_lectivo_es_permitido(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    apoderado_principal: Apoderado,
) -> None:
    ficha_2026 = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-101",
        dni="71234567",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )
    salon_4a_2027 = Salon(
        id=20,
        anio_lectivo=2027,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        seccion="A",
        capacidad_maxima=30,
    )
    ficha_2027 = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-101",
        dni="71234567",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_4a_2027,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[ficha_2026],
        fecha_actual=date(2027, 3, 1),
    )
    assert ficha_2027.anio_lectivo == 2027
    assert ficha_2027.grado == "4to"


def test_bdd_escenario_2_rechazar_dni_invalido_campos_vacios_y_fecha_invalida(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    apoderado_principal: Apoderado,
) -> None:
    for dni_malo in ("1234567", "123456789", "7123456A", ""):
        with pytest.raises(DniInvalidoException):
            ServicioMatricula.matricular_estudiante(
                operador=admin_op,
                alumno_id=101,
                codigo_estudiante="EST-001",
                dni=dni_malo,
                nombres="Mateo",
                apellidos="Rojas",
                fecha_nacimiento=FECHA_NAC_VALIDA,
                salon=salon_3a,
                apoderados=(apoderado_principal,),
                matriculas_existentes=[],
                fecha_actual=FECHA_ACTUAL,
            )

    for kwargs in (
        {"codigo_estudiante": "   "},
        {"nombres": ""},
        {"apellidos": "  "},
        {"fecha_nacimiento": FECHA_ACTUAL},
        {"fecha_nacimiento": date(2026, 3, 2)},
        {"fecha_nacimiento": datetime(2012, 5, 14, 9, 0)},
        {"alumno_id": 0},
    ):
        params: dict[str, object] = {
            "operador": admin_op,
            "alumno_id": 101,
            "codigo_estudiante": "EST-001",
            "dni": "71234567",
            "nombres": "Mateo",
            "apellidos": "Rojas",
            "fecha_nacimiento": FECHA_NAC_VALIDA,
            "salon": salon_3a,
            "apoderados": (apoderado_principal,),
            "matriculas_existentes": [],
            "fecha_actual": FECHA_ACTUAL,
        }
        params.update(kwargs)
        with pytest.raises(MatriculaException):
            ServicioMatricula.matricular_estudiante(**params)  # type: ignore[arg-type]


def test_bdd_escenario_2_rechazar_dni_alumno_y_codigo_duplicados(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    salon_3b: Salon,
    apoderado_principal: Apoderado,
) -> None:
    ficha_existente = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-2026-001",
        dni="71234567",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )

    # DNI duplicado en el mismo año lectivo
    with pytest.raises(MatriculaDuplicadaException):
        ServicioMatricula.matricular_estudiante(
            operador=admin_op,
            alumno_id=102,
            codigo_estudiante="EST-2026-002",
            dni="71234567",
            nombres="Otro",
            apellidos="Alumno",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_3b,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[ficha_existente],
            fecha_actual=FECHA_ACTUAL,
        )

    # Doble matrícula del mismo alumno_id en el mismo año lectivo
    with pytest.raises(MatriculaDuplicadaException):
        ServicioMatricula.matricular_estudiante(
            operador=admin_op,
            alumno_id=101,
            codigo_estudiante="EST-2026-999",
            dni="79999999",
            nombres="Mateo",
            apellidos="Rojas",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_3b,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[ficha_existente],
            fecha_actual=FECHA_ACTUAL,
        )

    # Código de estudiante duplicado (insensible a mayúsculas/espacios)
    with pytest.raises(MatriculaDuplicadaException):
        ServicioMatricula.matricular_estudiante(
            operador=admin_op,
            alumno_id=103,
            codigo_estudiante="  est-2026-001 ",
            dni="73333333",
            nombres="Diego",
            apellidos="Salazar",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_3b,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[ficha_existente],
            fecha_actual=FECHA_ACTUAL,
        )

    # Código de estudiante duplicado de otro alumno incluso en otro año lectivo
    salon_2027 = Salon(
        id=30,
        anio_lectivo=2027,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="A",
        capacidad_maxima=30,
    )
    with pytest.raises(MatriculaDuplicadaException):
        ServicioMatricula.matricular_estudiante(
            operador=admin_op,
            alumno_id=104,
            codigo_estudiante="EST-2026-001",
            dni="74444444",
            nombres="Camila",
            apellidos="Díaz",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_2027,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[ficha_existente],
            fecha_actual=date(2027, 3, 1),
        )


def test_bdd_escenario_3_rechazar_matricula_sin_apoderado_principal_activo(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    apoderado_principal: Apoderado,
    apoderado_secundario: Apoderado,
) -> None:
    principal_inactivo = replace(apoderado_principal, activo=False)

    for lista_invalida in (
        [],
        [apoderado_secundario],
        [principal_inactivo],
        [principal_inactivo, apoderado_secundario],
    ):
        with pytest.raises(ApoderadoInvalidoException):
            ServicioMatricula.matricular_estudiante(
                operador=admin_op,
                alumno_id=101,
                codigo_estudiante="EST-2026-001",
                dni="71234567",
                nombres="Mateo",
                apellidos="Rojas",
                fecha_nacimiento=FECHA_NAC_VALIDA,
                salon=salon_3a,
                apoderados=lista_invalida,
                matriculas_existentes=[],
                fecha_actual=FECHA_ACTUAL,
            )


def test_bdd_escenario_4_rechazar_salon_inactivo_y_sin_vacantes(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    apoderado_principal: Apoderado,
) -> None:
    salon_inactivo = replace(salon_3a, activo=False)
    with pytest.raises(SalonInactivoException):
        ServicioMatricula.matricular_estudiante(
            operador=admin_op,
            alumno_id=101,
            codigo_estudiante="EST-2026-001",
            dni="71234567",
            nombres="Mateo",
            apellidos="Rojas",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_inactivo,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[],
            fecha_actual=FECHA_ACTUAL,
        )

    f1 = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-001",
        dni="71111111",
        nombres="Uno",
        apellidos="Alumno",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )
    f2 = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=102,
        codigo_estudiante="EST-002",
        dni="72222222",
        nombres="Dos",
        apellidos="Alumno",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[f1],
        fecha_actual=FECHA_ACTUAL,
    )

    # Salón lleno (capacidad_maxima=2)
    with pytest.raises(SalonSinVacantesException):
        ServicioMatricula.matricular_estudiante(
            operador=admin_op,
            alumno_id=103,
            codigo_estudiante="EST-003",
            dni="73333333",
            nombres="Tres",
            apellidos="Alumno",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_3a,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[f1, f2],
            fecha_actual=FECHA_ACTUAL,
        )

    # Si uno de los matriculados ya fue RETIRADO, la vacante queda libre
    f2_retirado = replace(f2, estado=EstadoAcademico.RETIRADO)
    f3 = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=103,
        codigo_estudiante="EST-003",
        dni="73333333",
        nombres="Tres",
        apellidos="Alumno",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[f1, f2_retirado],
        fecha_actual=FECHA_ACTUAL,
    )
    assert f3.alumno_id == 103
    assert f3.salon_id == salon_3a.id


def test_actualizar_apoderados_exito_y_validaciones(
    staff_op: UsuarioOperador,
    salon_3a: Salon,
    apoderado_principal: Apoderado,
    apoderado_secundario: Apoderado,
) -> None:
    ficha = ServicioMatricula.matricular_estudiante(
        operador=staff_op,
        alumno_id=101,
        codigo_estudiante="EST-001",
        dni="71111111",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )

    nuevo_principal = replace(apoderado_secundario, es_principal=True)
    actualizada = ServicioMatricula.actualizar_apoderados(
        operador=staff_op,
        ficha=ficha,
        nuevos_apoderados=[nuevo_principal],
    )
    assert actualizada.apoderados == (nuevo_principal,)
    assert actualizada.apoderado_principal == nuevo_principal
    # La ficha original permanece inmutable
    assert ficha.apoderados == (apoderado_principal,)

    with pytest.raises(ApoderadoInvalidoException):
        ServicioMatricula.actualizar_apoderados(
            operador=staff_op,
            ficha=ficha,
            nuevos_apoderados=[apoderado_secundario],
        )


def test_bdd_escenario_5_cambiar_salon_y_preservar_snapshot_asistencia(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    salon_3b: Salon,
    apoderado_principal: Apoderado,
) -> None:
    ficha = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-001",
        dni="71111111",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )

    # Asistencia previa en 3ro A con snapshot académico (RN-06)
    alumno_previo = Alumno(
        id=ficha.alumno_id,
        codigo=ficha.codigo_estudiante,
        dni=ficha.dni,
        nombres=ficha.nombres,
        apellidos=ficha.apellidos,
        nivel=ficha.nivel,
        grado=ficha.grado,
        seccion=ficha.seccion,
        carnet_codigo="DSV-2026-0001",
    )
    res_asistencia = registrar_asistencia_unificada(
        operador=admin_op,
        alumno=alumno_previo,
        metodo=MetodoRegistro.CARNET,
        hora_servidor=time(7, 10, 0),
        fecha_escolar=date(2026, 3, 2),
    )

    ficha_trasladada = ServicioMatricula.cambiar_salon(
        operador=admin_op,
        ficha=ficha,
        nuevo_salon=salon_3b,
        matriculas_existentes=[ficha],
    )
    assert ficha_trasladada.salon_id == salon_3b.id
    assert ficha_trasladada.nivel == "Secundaria"
    assert ficha_trasladada.grado == "3ro"
    assert ficha_trasladada.seccion == "B"
    # El snapshot de la asistencia previa permanece intacto
    assert res_asistencia.asistencia.nivel == "Secundaria"
    assert res_asistencia.asistencia.grado == "3ro"
    assert res_asistencia.asistencia.seccion == "A"


def test_cambiar_salon_rechaza_alumno_no_activo_salon_invalido_y_sin_vacantes(
    admin_op: UsuarioOperador,
    salon_3a: Salon,
    salon_3b: Salon,
    apoderado_principal: Apoderado,
) -> None:
    ficha = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-001",
        dni="71111111",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )

    # Alumno no ACTIVO
    for estado_no_activo in (
        EstadoAcademico.SUSPENDIDO,
        EstadoAcademico.RETIRADO,
        EstadoAcademico.TRASLADADO,
        EstadoAcademico.EGRESADO,
    ):
        with pytest.raises(MatriculaException):
            ServicioMatricula.cambiar_salon(
                operador=admin_op,
                ficha=replace(ficha, estado=estado_no_activo),
                nuevo_salon=salon_3b,
                matriculas_existentes=[ficha],
            )

    # Salón destino inactivo
    with pytest.raises(SalonInactivoException):
        ServicioMatricula.cambiar_salon(
            operador=admin_op,
            ficha=ficha,
            nuevo_salon=replace(salon_3b, activo=False),
            matriculas_existentes=[ficha],
        )

    # Salón destino de otro año lectivo
    salon_otro_anio = Salon(
        id=20,
        anio_lectivo=2027,
        nivel=NivelEducativo.SECUNDARIA,
        grado="3ro",
        seccion="B",
        capacidad_maxima=30,
    )
    with pytest.raises(MatriculaException):
        ServicioMatricula.cambiar_salon(
            operador=admin_op,
            ficha=ficha,
            nuevo_salon=salon_otro_anio,
            matriculas_existentes=[ficha],
        )

    # Mismo salón actual
    with pytest.raises(MatriculaException):
        ServicioMatricula.cambiar_salon(
            operador=admin_op,
            ficha=ficha,
            nuevo_salon=salon_3a,
            matriculas_existentes=[ficha],
        )

    # Salón destino sin vacantes
    ocupante1 = replace(
        ficha,
        id="mat-o1",
        alumno_id=201,
        codigo_estudiante="EST-201",
        dni="72010001",
        salon_id=salon_3b.id,
        seccion="B",
    )
    ocupante2 = replace(
        ficha,
        id="mat-o2",
        alumno_id=202,
        codigo_estudiante="EST-202",
        dni="72020002",
        salon_id=salon_3b.id,
        seccion="B",
    )
    with pytest.raises(SalonSinVacantesException):
        ServicioMatricula.cambiar_salon(
            operador=admin_op,
            ficha=ficha,
            nuevo_salon=salon_3b,
            matriculas_existentes=[ficha, ocupante1, ocupante2],
        )

    # Si un ocupante del salón destino está RETIRADO, la vacante está disponible
    ocupante2_retirado = replace(ocupante2, estado=EstadoAcademico.RETIRADO)
    trasladada = ServicioMatricula.cambiar_salon(
        operador=admin_op,
        ficha=ficha,
        nuevo_salon=salon_3b,
        matriculas_existentes=[ficha, ocupante1, ocupante2_retirado],
    )
    assert trasladada.salon_id == salon_3b.id


def test_bdd_escenario_6_permisos_base_y_roles_dinamicos(
    admin_op: UsuarioOperador,
    coord_op: UsuarioOperador,
    salon_3a: Salon,
    salon_3b: Salon,
    apoderado_principal: Apoderado,
) -> None:
    ficha = ServicioMatricula.matricular_estudiante(
        operador=admin_op,
        alumno_id=101,
        codigo_estudiante="EST-001",
        dni="71111111",
        nombres="Mateo",
        apellidos="Rojas",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
    )

    # COORDINADOR no posee GESTIONAR_MATRICULA
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.validar_operador(coord_op)
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.matricular_estudiante(
            operador=coord_op,
            alumno_id=102,
            codigo_estudiante="EST-002",
            dni="72222222",
            nombres="Ana",
            apellidos="Cruz",
            fecha_nacimiento=FECHA_NAC_VALIDA,
            salon=salon_3a,
            apoderados=(apoderado_principal,),
            matriculas_existentes=[],
            fecha_actual=FECHA_ACTUAL,
        )
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.actualizar_apoderados(
            operador=coord_op,
            ficha=ficha,
            nuevos_apoderados=(apoderado_principal,),
        )
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.cambiar_salon(
            operador=coord_op,
            ficha=ficha,
            nuevo_salon=salon_3b,
            matriculas_existentes=[ficha],
        )

    # Operador inactivo aunque sea ADMIN
    admin_inactivo = replace(admin_op, activo=False)
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.validar_operador(admin_inactivo)

    # Roles personalizados (PBI-15)
    rol_secretaria = Rol(
        codigo="SECRETARIA_MATRICULA",
        nombre="Secretaría de Matrícula",
        descripcion="Gestiona matrículas digitales",
        permisos=frozenset({PermisoOperacion.GESTIONAR_MATRICULA}),
        activo=True,
    )
    rol_inactivo = replace(rol_secretaria, codigo="SECRETARIA_INACTIVA", activo=False)
    rol_sin_permiso = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Solo calificaciones",
        permisos=frozenset({PermisoOperacion.REGISTRAR_CALIFICACIONES}),
        activo=True,
    )
    catalogo = (rol_secretaria, rol_inactivo, rol_sin_permiso)

    op_secretaria = UsuarioOperador(id=20, username="sec_mat", rol="SECRETARIA_MATRICULA")
    op_inactiva = UsuarioOperador(id=21, username="sec_old", rol="SECRETARIA_INACTIVA")
    op_docente = UsuarioOperador(id=22, username="docente1", rol="DOCENTE")

    # Autorizado con catálogo
    ficha_sec = ServicioMatricula.matricular_estudiante(
        operador=op_secretaria,
        alumno_id=105,
        codigo_estudiante="EST-105",
        dni="75555555",
        nombres="Valeria",
        apellidos="Mendoza",
        fecha_nacimiento=FECHA_NAC_VALIDA,
        salon=salon_3a,
        apoderados=(apoderado_principal,),
        matriculas_existentes=[],
        fecha_actual=FECHA_ACTUAL,
        roles=catalogo,
    )
    assert ficha_sec.alumno_id == 105

    ficha_sec_ap = ServicioMatricula.actualizar_apoderados(
        operador=op_secretaria,
        ficha=ficha_sec,
        nuevos_apoderados=(apoderado_principal,),
        roles=catalogo,
    )
    assert ficha_sec_ap.apoderados == (apoderado_principal,)

    ficha_sec_traslado = ServicioMatricula.cambiar_salon(
        operador=op_secretaria,
        ficha=ficha_sec_ap,
        nuevo_salon=salon_3b,
        matriculas_existentes=[ficha_sec_ap],
        roles=catalogo,
    )
    assert ficha_sec_traslado.salon_id == salon_3b.id

    # Sin catálogo, rol inactivo o sin permiso → denegado
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.validar_operador(op_secretaria)
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.validar_operador(op_inactiva, roles=catalogo)
    with pytest.raises(PermisoMatriculaException):
        ServicioMatricula.validar_operador(op_docente, roles=catalogo)
