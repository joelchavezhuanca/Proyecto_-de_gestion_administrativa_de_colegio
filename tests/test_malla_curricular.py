"""Pruebas BDD y unitarias del PBI-09: Configuración de Malla Curricular."""

from dataclasses import FrozenInstanceError

import pytest

from src.dominio.asistencia import UsuarioOperador
from src.dominio.malla_curricular import (
    GRADOS_POR_NIVEL,
    Curso,
    CursoDuplicadoException,
    CursoInvalidoException,
    EntidadEnUsoException,
    MallaCurricularException,
    NivelEducativo,
    PermisoMallaException,
    Salon,
    SalonDuplicadoException,
    SalonInvalidoException,
    ServicioMallaCurricular,
)
from src.dominio.usuarios import PermisoOperacion, Rol, RolUsuario


@pytest.fixture
def operador_admin() -> UsuarioOperador:
    return UsuarioOperador(id=1, username="admin", rol=RolUsuario.ADMIN, activo=True)


@pytest.fixture
def operador_coordinador() -> UsuarioOperador:
    return UsuarioOperador(
        id=2, username="coordinador", rol=RolUsuario.COORDINADOR, activo=True
    )


@pytest.fixture
def operador_admin_staff() -> UsuarioOperador:
    return UsuarioOperador(
        id=3, username="secretaria", rol=RolUsuario.ADMIN_STAFF, activo=True
    )


@pytest.fixture
def operador_inactivo() -> UsuarioOperador:
    return UsuarioOperador(id=4, username="admin_off", rol=RolUsuario.ADMIN, activo=False)


@pytest.fixture
def rol_academico_con_permiso() -> Rol:
    return Rol(
        codigo="COORDINADOR_ACADEMICO",
        nombre="Coordinador Académico",
        descripcion="Configura la malla curricular del colegio",
        permisos=frozenset({PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR}),
        activo=True,
    )


@pytest.fixture
def salon_4to_c() -> Salon:
    return Salon(
        id=1,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        seccion="C",
        capacidad_maxima=30,
    )


@pytest.fixture
def curso_matematica() -> Curso:
    return Curso(
        id=1,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        codigo="MAT-401",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=6,
    )


def test_enums_y_grados_oficiales() -> None:
    assert NivelEducativo.PRIMARIA == "Primaria"
    assert NivelEducativo.SECUNDARIA == "Secundaria"
    assert GRADOS_POR_NIVEL[NivelEducativo.PRIMARIA] == (
        "1ro",
        "2do",
        "3ro",
        "4to",
        "5to",
        "6to",
    )
    assert GRADOS_POR_NIVEL[NivelEducativo.SECUNDARIA] == (
        "1ro",
        "2do",
        "3ro",
        "4to",
        "5to",
    )


def test_jerarquia_excepciones() -> None:
    assert issubclass(PermisoMallaException, MallaCurricularException)
    assert issubclass(SalonInvalidoException, MallaCurricularException)
    assert issubclass(SalonDuplicadoException, MallaCurricularException)
    assert issubclass(CursoInvalidoException, MallaCurricularException)
    assert issubclass(CursoDuplicadoException, MallaCurricularException)
    assert issubclass(EntidadEnUsoException, MallaCurricularException)


def test_bdd_escenario_1_crear_salon_y_cursos_secundaria(
    operador_admin: UsuarioOperador,
) -> None:
    salon = Salon(
        id=1,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado=" 4to ",
        seccion=" c ",
        capacidad_maxima=30,
    )
    creado = ServicioMallaCurricular.crear_salon(operador_admin, salon, [])
    assert creado.anio_lectivo == 2026
    assert creado.nivel == NivelEducativo.SECUNDARIA
    assert creado.grado == "4to"
    assert creado.seccion == "C"
    assert creado.capacidad_maxima == 30
    assert creado.activo is True

    curso_mat = Curso(
        id=1,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        codigo="MAT-401",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=6,
    )
    curso_com = Curso(
        id=2,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        codigo="COM-401",
        nombre="Comunicación",
        area_curricular="Comunicación",
        horas_semanales=5,
    )

    mat_creado = ServicioMallaCurricular.crear_curso(operador_admin, curso_mat, [])
    com_creado = ServicioMallaCurricular.crear_curso(operador_admin, curso_com, [mat_creado])

    assert mat_creado.nombre == "Matemática"
    assert com_creado.nombre == "Comunicación"


def test_salon_primaria_sexto_grado_valido_e_inmutabilidad(
    operador_admin: UsuarioOperador,
    salon_4to_c: Salon,
    curso_matematica: Curso,
) -> None:
    salon_primaria = Salon(
        id=2,
        anio_lectivo=2026,
        nivel=NivelEducativo.PRIMARIA,
        grado="6to",
        seccion="A1",
    )
    creado = ServicioMallaCurricular.crear_salon(operador_admin, salon_primaria, [])
    assert creado.grado == "6to"
    assert creado.capacidad_maxima == 30

    with pytest.raises(FrozenInstanceError):
        salon_4to_c.capacidad_maxima = 35  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        curso_matematica.horas_semanales = 8  # type: ignore[misc]


def test_bdd_escenario_2_rechazar_salon_duplicado(
    operador_admin: UsuarioOperador,
    salon_4to_c: Salon,
) -> None:
    duplicado = Salon(
        id=2,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4TO",
        seccion=" c ",
        capacidad_maxima=25,
    )
    with pytest.raises(SalonDuplicadoException):
        ServicioMallaCurricular.crear_salon(operador_admin, duplicado, [salon_4to_c])

    otro_anio = Salon(
        id=3,
        anio_lectivo=2027,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4to",
        seccion="C",
        capacidad_maxima=30,
    )
    assert (
        ServicioMallaCurricular.crear_salon(operador_admin, otro_anio, [salon_4to_c]) == otro_anio
    )


@pytest.mark.parametrize(
    ("kwargs"),
    [
        {"anio_lectivo": 1999},
        {"anio_lectivo": True},
        {"nivel": "Inicial"},
        {"grado": "6to", "nivel": NivelEducativo.SECUNDARIA},
        {"grado": "7mo", "nivel": NivelEducativo.PRIMARIA},
        {"grado": ""},
        {"grado": 4},
        {"seccion": ""},
        {"seccion": "   "},
        {"seccion": "ABCDEF"},
        {"seccion": "A-1"},
        {"seccion": 1},
        {"capacidad_maxima": 0},
        {"capacidad_maxima": -5},
        {"capacidad_maxima": True},
        {"activo": "si"},
    ],
)
def test_bdd_escenario_2_salon_datos_invalidos(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "id": 1,
        "anio_lectivo": 2026,
        "nivel": NivelEducativo.SECUNDARIA,
        "grado": "4to",
        "seccion": "C",
        "capacidad_maxima": 30,
        "activo": True,
    }
    base.update(kwargs)
    with pytest.raises(SalonInvalidoException):
        Salon(**base)  # type: ignore[arg-type]


def test_bdd_escenario_3_rechazar_curso_duplicado(
    operador_admin: UsuarioOperador,
    curso_matematica: Curso,
) -> None:
    duplicado = Curso(
        id=2,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="4TO",
        codigo=" mat-401 ",
        nombre="Matemática Avanzada",
        area_curricular="Matemática",
        horas_semanales=4,
    )
    with pytest.raises(CursoDuplicadoException):
        ServicioMallaCurricular.crear_curso(operador_admin, duplicado, [curso_matematica])

    otro_grado = Curso(
        id=3,
        anio_lectivo=2026,
        nivel=NivelEducativo.SECUNDARIA,
        grado="5to",
        codigo="MAT-401",
        nombre="Matemática",
        area_curricular="Matemática",
        horas_semanales=6,
    )
    assert (
        ServicioMallaCurricular.crear_curso(operador_admin, otro_grado, [curso_matematica])
        == otro_grado
    )


@pytest.mark.parametrize(
    ("kwargs"),
    [
        {"anio_lectivo": 1999},
        {"nivel": "Inicial"},
        {"grado": "6to", "nivel": NivelEducativo.SECUNDARIA},
        {"codigo": ""},
        {"codigo": "   "},
        {"codigo": 123},
        {"nombre": ""},
        {"nombre": "   "},
        {"nombre": None},
        {"area_curricular": ""},
        {"area_curricular": "   "},
        {"area_curricular": 10},
        {"horas_semanales": 0},
        {"horas_semanales": -2},
        {"horas_semanales": False},
        {"activo": 1},
    ],
)
def test_bdd_escenario_3_curso_datos_invalidos(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "id": 1,
        "anio_lectivo": 2026,
        "nivel": NivelEducativo.SECUNDARIA,
        "grado": "4to",
        "codigo": "MAT-401",
        "nombre": "Matemática",
        "area_curricular": "Matemática",
        "horas_semanales": 6,
        "activo": True,
    }
    base.update(kwargs)
    with pytest.raises(CursoInvalidoException):
        Curso(**base)  # type: ignore[arg-type]


def test_actualizar_capacidad_salon(
    operador_admin: UsuarioOperador,
    salon_4to_c: Salon,
) -> None:
    actualizado = ServicioMallaCurricular.actualizar_capacidad_salon(
        operador_admin,
        salon_4to_c,
        nueva_capacidad=35,
        matriculados_actuales=28,
    )
    assert actualizado.capacidad_maxima == 35
    assert salon_4to_c.capacidad_maxima == 30

    with pytest.raises(SalonInvalidoException):
        ServicioMallaCurricular.actualizar_capacidad_salon(
            operador_admin, salon_4to_c, nueva_capacidad=0
        )

    with pytest.raises(SalonInvalidoException):
        ServicioMallaCurricular.actualizar_capacidad_salon(
            operador_admin, salon_4to_c, nueva_capacidad=True
        )

    with pytest.raises(SalonInvalidoException):
        ServicioMallaCurricular.actualizar_capacidad_salon(
            operador_admin, salon_4to_c, nueva_capacidad=20, matriculados_actuales=-1
        )

    with pytest.raises(SalonInvalidoException):
        ServicioMallaCurricular.actualizar_capacidad_salon(
            operador_admin, salon_4to_c, nueva_capacidad=20, matriculados_actuales=25
        )


def test_bdd_escenario_4_baja_logica_vs_eliminacion_en_uso(
    operador_admin: UsuarioOperador,
    salon_4to_c: Salon,
    curso_matematica: Curso,
) -> None:
    salon_inactivo = ServicioMallaCurricular.desactivar_salon(
        operador_admin,
        salon_4to_c,
        tiene_alumnos_activos=True,
    )
    assert salon_inactivo.activo is False
    assert salon_4to_c.activo is True

    with pytest.raises(EntidadEnUsoException):
        ServicioMallaCurricular.eliminar_salon(
            operador_admin,
            salon_4to_c,
            tiene_alumnos_asociados=True,
        )

    ServicioMallaCurricular.eliminar_salon(
        operador_admin,
        salon_4to_c,
        tiene_alumnos_asociados=False,
    )

    curso_inactivo = ServicioMallaCurricular.desactivar_curso(operador_admin, curso_matematica)
    assert curso_inactivo.activo is False
    assert curso_matematica.activo is True

    with pytest.raises(EntidadEnUsoException):
        ServicioMallaCurricular.eliminar_curso(
            operador_admin,
            curso_matematica,
            tiene_calificaciones=True,
        )

    ServicioMallaCurricular.eliminar_curso(
        operador_admin,
        curso_matematica,
        tiene_calificaciones=False,
    )


def test_bdd_escenario_5_denegar_operaciones_sin_permiso(
    operador_coordinador: UsuarioOperador,
    operador_admin_staff: UsuarioOperador,
    operador_inactivo: UsuarioOperador,
    salon_4to_c: Salon,
    curso_matematica: Curso,
) -> None:
    for operador in (operador_coordinador, operador_admin_staff, operador_inactivo):
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.crear_salon(operador, salon_4to_c, [])
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.actualizar_capacidad_salon(operador, salon_4to_c, 32)
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.desactivar_salon(operador, salon_4to_c)
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.eliminar_salon(operador, salon_4to_c)
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.crear_curso(operador, curso_matematica, [])
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.desactivar_curso(operador, curso_matematica)
        with pytest.raises(PermisoMallaException):
            ServicioMallaCurricular.eliminar_curso(operador, curso_matematica)


def test_permisos_dinamicos_rol_personalizado(
    rol_academico_con_permiso: Rol,
    salon_4to_c: Salon,
) -> None:
    operador_custom = UsuarioOperador(
        id=10,
        username="acad_custom",
        rol="COORDINADOR_ACADEMICO",  # type: ignore[arg-type]
        activo=True,
    )

    creado = ServicioMallaCurricular.crear_salon(
        operador_custom,
        salon_4to_c,
        [],
        roles=[rol_academico_con_permiso],
    )
    assert creado == salon_4to_c

    # Sin pasar catálogo de roles: deny-by-default
    with pytest.raises(PermisoMallaException):
        ServicioMallaCurricular.crear_salon(operador_custom, salon_4to_c, [])

    # Rol personalizado inactivo
    rol_inactivo = Rol(
        codigo="COORDINADOR_ACADEMICO",
        nombre="Coordinador Académico",
        descripcion="Rol suspendido",
        permisos=frozenset({PermisoOperacion.CONFIGURAR_MALLA_CURRICULAR}),
        activo=False,
    )
    with pytest.raises(PermisoMallaException):
        ServicioMallaCurricular.crear_salon(
            operador_custom,
            salon_4to_c,
            [],
            roles=[rol_inactivo],
        )

    # Rol personalizado sin el permiso CONFIGURAR_MALLA_CURRICULAR
    rol_sin_permiso = Rol(
        codigo="DOCENTE",
        nombre="Docente",
        descripcion="Solo consulta notas",
        permisos=frozenset({PermisoOperacion.CONSULTAR_CALIFICACIONES}),
        activo=True,
    )
    operador_docente = UsuarioOperador(
        id=11,
        username="docente",
        rol="DOCENTE",  # type: ignore[arg-type]
        activo=True,
    )
    with pytest.raises(PermisoMallaException):
        ServicioMallaCurricular.crear_salon(
            operador_docente,
            salon_4to_c,
            [],
            roles=[rol_sin_permiso],
        )


def test_listar_salones_y_cursos_con_filtros() -> None:
    salones = [
        Salon(1, 2026, NivelEducativo.PRIMARIA, "1ro", "A", 28, True),
        Salon(2, 2026, NivelEducativo.SECUNDARIA, "4to", "C", 30, True),
        Salon(3, 2026, NivelEducativo.SECUNDARIA, "4to", "D", 30, False),
        Salon(4, 2025, NivelEducativo.SECUNDARIA, "4to", "C", 30, True),
    ]

    assert [s.id for s in ServicioMallaCurricular.listar_salones(salones)] == [1, 2, 4]
    assert [
        s.id
        for s in ServicioMallaCurricular.listar_salones(
            salones,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado=" 4TO ",
            solo_activos=True,
        )
    ] == [2]
    assert [
        s.id
        for s in ServicioMallaCurricular.listar_salones(
            salones,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="4to",
            solo_activos=False,
        )
    ] == [2, 3]

    cursos = [
        Curso(1, 2026, NivelEducativo.PRIMARIA, "1ro", "MAT-101", "Matemática", "Mat", 6, True),
        Curso(2, 2026, NivelEducativo.SECUNDARIA, "4to", "MAT-401", "Matemática", "Mat", 6, True),
        Curso(
            3, 2026, NivelEducativo.SECUNDARIA, "4to", "COM-401", "Comunicación", "Com", 5, False
        ),
        Curso(4, 2025, NivelEducativo.SECUNDARIA, "4to", "MAT-401", "Matemática", "Mat", 6, True),
    ]

    assert [c.id for c in ServicioMallaCurricular.listar_cursos(cursos)] == [1, 2, 4]
    assert [
        c.id
        for c in ServicioMallaCurricular.listar_cursos(
            cursos,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="4to",
            solo_activos=True,
        )
    ] == [2]
    assert [
        c.id
        for c in ServicioMallaCurricular.listar_cursos(
            cursos,
            anio_lectivo=2026,
            nivel=NivelEducativo.SECUNDARIA,
            grado="4to",
            solo_activos=False,
        )
    ] == [2, 3]
