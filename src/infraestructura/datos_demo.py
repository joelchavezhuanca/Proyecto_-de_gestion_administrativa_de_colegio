"""Datos ficticios de demostración, identificados explícitamente en la interfaz.

No deben utilizarse en un entorno real. Se generan de forma determinista para
que las pruebas y la presentación sean reproducibles.
"""

from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.dominio.asistencia import calcular_estado_y_tardanza
from src.dominio.usuarios import hashear_password
from src.infraestructura.modelos import (
    AsistenciaModel,
    ConfiguracionModel,
    EstudianteModel,
    JustificacionModel,
    PeriodoAcademicoModel,
    UsuarioModel,
)
from src.presentacion.tiempo import hora_institucional

PASSWORD_DEMO = "DemoSavio2026!"

CREDENCIALES_DEMO = [
    {
        "username": "admin_general",
        "rol": "ADMIN",
        "nombre": "Administrador General",
        "password": PASSWORD_DEMO,
    },
    {
        "username": "coord_secundaria",
        "rol": "COORDINADOR",
        "nombre": "Coordinación Académica",
        "password": PASSWORD_DEMO,
    },
    {
        "username": "jluna_qa",
        "rol": "ADMIN_STAFF",
        "nombre": "Personal de Portería",
        "password": PASSWORD_DEMO,
    },
]

_NOMBRES = [
    "Eduardo",
    "Yhovana",
    "Dudu",
    "Jacob",
    "Gari",
    "Ana",
    "Luis",
    "María",
    "Jorge",
    "Valeria",
    "Diego",
    "Camila",
    "Renzo",
    "Lucía",
    "Mateo",
    "Fiorella",
    "Santiago",
    "Ariana",
    "Sebastián",
    "Daniela",
    "Adrián",
    "Ximena",
    "Rodrigo",
    "Paola",
    "Álvaro",
    "Gabriela",
    "Nicolás",
    "Fernanda",
    "Bruno",
    "Antonella",
    "Cristian",
    "Micaela",
    "Piero",
    "Alessandra",
    "Fabrizio",
    "Bianca",
    "Emilio",
    "Rafaela",
    "Thiago",
    "Julieta",
    "Mauricio",
    "Rocío",
    "Iván",
    "Noelia",
]

_APELLIDOS = [
    "Luna Lezano",
    "Quispe Ccolqquere",
    "Lizarzaburu Flores",
    "Chávez Huanca",
    "Basilio",
    "Mamani",
    "Huamán",
    "Condori",
    "Flores",
    "Rojas",
    "Vargas",
    "Salazar",
    "Paredes",
    "Cárdenas",
    "Aguilar",
    "Torres",
    "Ramos",
    "Guzmán",
    "Cruz",
    "Medina",
    "Ortiz",
    "Castillo",
    "Vega",
    "Palacios",
]

_GRUPOS = [
    ("Primaria", "1ro", "A", 10),
    ("Primaria", "3ro", "A", 10),
    ("Secundaria", "4to", "A", 8),
    ("Secundaria", "5to", "A", 8),
    ("Secundaria", "5to", "B", 8),
]


def _crear_usuarios(sesion: Session) -> None:
    for indice, credencial in enumerate(CREDENCIALES_DEMO, start=1):
        password_hash, salt = hashear_password(credencial["password"])
        sesion.add(
            UsuarioModel(
                id=indice,
                username=credencial["username"],
                password_hash=password_hash,
                salt=salt,
                nombre_completo=credencial["nombre"],
                rol=credencial["rol"],
                activo=True,
            )
        )


def _crear_estudiantes(sesion: Session) -> list[EstudianteModel]:
    estudiantes: list[EstudianteModel] = []
    contador = 0
    for nivel, grado, seccion, cantidad in _GRUPOS:
        for _ in range(cantidad):
            contador += 1
            dni = f"{70000000 + contador:08d}"
            estudiante = EstudianteModel(
                codigo=f"ALU-2026-{contador:03d}",
                dni=dni,
                nombres=_NOMBRES[(contador - 1) % len(_NOMBRES)],
                apellidos=_APELLIDOS[(contador * 3) % len(_APELLIDOS)],
                nivel=nivel,
                grado=grado,
                seccion=seccion,
                carnet_codigo=f"CRN-EDU-{dni}",
                estado="ACTIVO",
            )
            sesion.add(estudiante)
            estudiantes.append(estudiante)
    sesion.flush()
    return estudiantes


def _crear_asistencias(
    sesion: Session,
    estudiantes: list[EstudianteModel],
    fecha: date,
    momento,
) -> None:
    """Genera una jornada parcial: presentes, tardanzas, ausentes y justificados."""
    operadores = [1, 3, 2]
    for indice, estudiante in enumerate(estudiantes, start=1):
        operador = operadores[indice % len(operadores)]
        if indice <= 26:
            if indice % 5 == 0:
                hora = time(7, 16 + (indice % 20), 0)
            else:
                hora = time(7, 2 + (indice % 12), 0)
            estado, minutos = calcular_estado_y_tardanza(hora)
        elif indice <= 32:
            hora = time(8, 30, 0)
            estado, minutos = None, 0
            estado_valor = "AUSENTE"
        elif indice <= 36:
            hora = time(8, 30, 0)
            estado, minutos = None, 0
            estado_valor = "JUSTIFICADO"
        else:
            # Últimos alumnos sin registro: quedan PENDIENTES para la demostración.
            continue

        if estado is not None:
            estado_valor = estado.value

        asistencia = AsistenciaModel(
            id=f"ast-demo-{indice:03d}",
            estudiante_id=estudiante.id,
            usuario_id=operador,
            fecha_escolar=fecha,
            hora_efectiva=hora,
            estado=estado_valor,
            minutos_tardanza=minutos,
            metodo="CARNET" if indice % 2 == 0 else "MANUAL_BUSQUEDA",
            estado_anterior="AUSENTE" if estado_valor == "JUSTIFICADO" else None,
            motivo_correccion=(
                "Justificación médica de demostración"
                if estado_valor == "JUSTIFICADO"
                else None
            ),
            auditoria_id=f"aud-demo-{indice:03d}",
        )
        sesion.add(asistencia)
        sesion.flush()

        if estado_valor == "JUSTIFICADO":
            sesion.add(
                JustificacionModel(
                    codigo=f"just-demo-{indice:03d}",
                    asistencia_id=asistencia.id,
                    estudiante_id=estudiante.id,
                    usuario_id=operador,
                    motivo="Reposo médico certificado por pediatría (dato de demostración)",
                    categoria="MEDICA",
                    estado="APROBADA",
                    fecha_solicitud=fecha,
                    fecha_resolucion=momento,
                )
            )


def inicializar_datos_demo(sesion: Session, ahora=None) -> bool:
    """Siembra la base de demostración solo si está vacía. Devuelve True si sembró."""
    ahora = ahora or hora_institucional()
    total_usuarios = sesion.scalar(select(func.count(UsuarioModel.id))) or 0
    if total_usuarios:
        return False

    _crear_usuarios(sesion)
    sesion.add_all(
        [
            PeriodoAcademicoModel(
                id=1,
                nombre="Año escolar 2026",
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2026, 12, 20),
                cerrado=False,
            ),
            PeriodoAcademicoModel(
                id=2,
                nombre="Año escolar 2025",
                fecha_inicio=date(2025, 3, 1),
                fecha_fin=date(2025, 12, 20),
                cerrado=True,
            ),
            ConfiguracionModel(clave="hora_cierre", valor="08:30"),
        ]
    )
    sesion.flush()

    estudiantes = _crear_estudiantes(sesion)
    _crear_asistencias(sesion, estudiantes, ahora.date(), ahora)

    # Una jornada anterior para evidenciar que el sistema distingue fechas.
    ayer = ahora.date() - timedelta(days=1)
    for indice, estudiante in enumerate(estudiantes[:20], start=1):
        hora = time(7, 5 + (indice % 10), 0)
        estado, minutos = calcular_estado_y_tardanza(hora)
        sesion.add(
            AsistenciaModel(
                id=f"ast-ayer-{indice:03d}",
                estudiante_id=estudiante.id,
                usuario_id=1,
                fecha_escolar=ayer,
                hora_efectiva=hora,
                estado=estado.value,
                minutos_tardanza=minutos,
                metodo="CARNET",
            )
        )

    sesion.commit()
    return True
