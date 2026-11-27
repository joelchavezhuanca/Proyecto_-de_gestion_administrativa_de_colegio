"""Semilla opcional e idempotente de datos realistas para demostración (Colegio Domingo Savio).

Se activa únicamente cuando la variable de entorno ``SEMBRAR_DATOS_DEMO`` vale
``true`` / ``1`` / ``si`` / ``yes`` (apagada por defecto para no afectar pruebas
ni despliegues productivos limpios).

Escala estimada realista (EBR privada en Cusco):
- 11 salones oficiales (Primaria 1ro–6to A y Secundaria 1ro–5to A, capacidad 30 c/u).
- 220 estudiantes (20 por salón: 216 activos, 2 suspendidos y 2 retirados).
- 220 apoderados principales con contacto WhatsApp normalizado (+519...).
- 33 cursos (MAT, COM, CYT por grado), 33 asignaciones docentes, 2 períodos,
  rubros 30 % / 30 % / 40 %, actividades y calificaciones vigesimales realistas.
- Obligaciones de pago mensuales (S/ 320 Primaria, S/ 360 Secundaria) con ~12 %
  de morosidad realista y alertas silenciosas para deudores que ingresaron hoy.
- Asistencias de los últimos 4 días lectivos + jornada actual (~90 % asistencia),
  dejando los carnets ``CRN-2026-0001`` al ``CRN-2026-0008`` y ``CRN-2026-0010``
  pendientes hoy para escaneo QR en vivo, y ``CRN-2026-0009`` como AUSENTE hoy
  para demostrar corrección condicional con motivo.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.dominio.auditoria import ZONA_HORARIA_LIMA
from src.dominio.malla_curricular import GRADOS_POR_NIVEL, NivelEducativo
from src.dominio.usuarios import EstadoUsuario, PermisoOperacion, RolUsuario, hashear_password
from src.infraestructura.modelos import (
    ActividadEvaluableModel,
    AlertaPagoSilenciosaModel,
    ApoderadoModel,
    AsignacionDocenteModel,
    AsistenciaModel,
    CalificacionModel,
    CarnetModel,
    ConfiguracionSistemaModel,
    CursoModel,
    EstudianteApoderadoModel,
    EstudianteModel,
    JustificacionModel,
    ObligacionPagoModel,
    PeriodoAcademicoModel,
    RolModel,
    RolPermisoModel,
    RubroEvaluacionModel,
    SalonModel,
    UsuarioModel,
)

CLAVE_DEMO_DEFECTO: Final[str] = "Demo2026!"
CODIGO_CENTINELA_DEMO: Final[str] = "ALU-2026-0001"
ALUMNOS_POR_SALON: Final[int] = 20

_NOMBRES_ESTUDIANTES: Final[tuple[str, ...]] = (
    "Mateo",
    "Valentina",
    "Santiago",
    "Camila",
    "Sebastián",
    "Lucía",
    "Diego",
    "Sofía",
    "Nicolás",
    "Mariana",
    "Gabriel",
    "Antonella",
    "Joaquín",
    "Renata",
    "Adrián",
    "Valeria",
    "Emiliano",
    "Fernanda",
    "Thiago",
    "Ximena",
    "Lucas",
    "Ariana",
    "Samuel",
    "Paula",
    "Rodrigo",
    "Daniela",
    "Fabrizio",
    "Isabella",
    "Leonardo",
    "Abril",
)

_NOMBRES_APODERADOS: Final[tuple[str, ...]] = (
    "Carlos",
    "Rosa",
    "Jorge",
    "María",
    "Luis",
    "Patricia",
    "Miguel",
    "Carmen",
    "Juan",
    "Elena",
    "Fernando",
    "Claudia",
    "Ricardo",
    "Sonia",
    "Raúl",
    "Verónica",
    "Héctor",
    "Silvia",
    "Óscar",
    "Gladys",
)

_APELLIDOS_CUSCO: Final[tuple[str, ...]] = (
    "Quispe",
    "Huamán",
    "Chávez",
    "Luna",
    "Mendoza",
    "Flores",
    "Torres",
    "Rojas",
    "Paredes",
    "Vargas",
    "Ccahuana",
    "Condori",
    "Salazar",
    "Delgado",
    "Castillo",
    "Ramos",
    "Cárdenas",
    "Gutiérrez",
    "Pacheco",
    "Medina",
    "Sánchez",
    "Romero",
    "Aguilar",
    "Palomino",
    "Farfán",
    "Loayza",
    "Bellido",
    "Arias",
    "Peña",
    "Valdivia",
)

_AREAS_CURRICULARES: Final[tuple[tuple[str, str, str, int, str], ...]] = (
    ("MAT", "Matemática", "Matemática", 6, "docente_mat"),
    ("COM", "Comunicación", "Comunicación", 5, "docente_com"),
    ("CYT", "Ciencia y Tecnología", "Ciencia y Tecnología", 4, "docente_cyt"),
)

_RUBROS_BASE: Final[tuple[tuple[str, str, Decimal, str], ...]] = (
    ("pra", "Prácticas calificadas", Decimal("30.00"), "Práctica calificada N° 1"),
    ("tra", "Trabajos y proyectos", Decimal("30.00"), "Proyecto integrador de unidad"),
    ("exa", "Examen bimestral", Decimal("40.00"), "Evaluación bimestral"),
)


@dataclass(frozen=True)
class ResumenSemillaDemo:
    """Resumen cuantitativo de la siembra demo ejecutada."""

    ejecutada: bool
    salones: int = 0
    estudiantes: int = 0
    cursos: int = 0
    asistencias: int = 0
    calificaciones: int = 0
    obligaciones_pago: int = 0


def debe_sembrar_demo() -> bool:
    """Indica si ``SEMBRAR_DATOS_DEMO`` está habilitada en el entorno."""
    valor = (os.environ.get("SEMBRAR_DATOS_DEMO") or "").strip().lower()
    return valor in {"1", "true", "si", "sí", "yes", "on"}


def _ultimos_dias_lectivos(fecha_hoy: date, cantidad: int) -> list[date]:
    dias: list[date] = []
    cursor = fecha_hoy - timedelta(days=1)
    while len(dias) < cantidad:
        if cursor.weekday() < 5:
            dias.append(cursor)
        cursor -= timedelta(days=1)
    dias.reverse()
    return dias


def _asegurar_rol_personalizado(
    session: Session,
    *,
    codigo: str,
    nombre: str,
    descripcion: str,
    permisos: tuple[PermisoOperacion, ...],
) -> RolModel:
    rol = session.scalars(select(RolModel).filter_by(codigo=codigo)).first()
    if rol is None:
        rol = RolModel(
            codigo=codigo,
            nombre=nombre,
            descripcion=descripcion,
            es_sistema=False,
            activo=True,
        )
        session.add(rol)
        session.flush()
    asignados = set(
        session.scalars(select(RolPermisoModel.permiso_codigo).filter_by(rol_id=rol.id)).all()
    )
    for permiso in permisos:
        if permiso.value not in asignados:
            session.add(RolPermisoModel(rol_id=rol.id, permiso_codigo=permiso.value))
    session.flush()
    return rol


def _asegurar_usuario_demo(
    session: Session,
    *,
    username: str,
    nombre_completo: str,
    rol_codigo: str,
    pwd_hash: str,
    salt: str,
) -> UsuarioModel:
    existente = session.scalars(select(UsuarioModel).filter_by(username=username)).first()
    if existente is not None:
        return existente
    rol_id = session.scalar(select(RolModel.id).where(RolModel.codigo == rol_codigo))
    usuario = UsuarioModel(
        username=username,
        nombre_completo=nombre_completo,
        password_hash=pwd_hash,
        salt=salt,
        rol_id=rol_id,
        rol=rol_codigo,
        estado=EstadoUsuario.ACTIVO.value,
        activo=True,
    )
    session.add(usuario)
    session.flush()
    return usuario


def _asegurar_usuarios_y_roles(session: Session) -> dict[str, UsuarioModel]:
    _asegurar_rol_personalizado(
        session,
        codigo="DOCENTE",
        nombre="Docente de aula",
        descripcion="Registra y consulta calificaciones en sus cursos asignados",
        permisos=(
            PermisoOperacion.REGISTRAR_CALIFICACIONES,
            PermisoOperacion.CONSULTAR_CALIFICACIONES,
            PermisoOperacion.CONSULTAR_FICHA_ALUMNO,
        ),
    )
    _asegurar_rol_personalizado(
        session,
        codigo="AUXILIAR",
        nombre="Auxiliar de portería",
        descripcion="Registra asistencia diaria por carnet QR, DNI o búsqueda",
        permisos=(
            PermisoOperacion.REGISTRAR_ASISTENCIA,
            PermisoOperacion.CONSULTAR_DASHBOARD_AFORO,
        ),
    )

    clave_demo = os.environ.get("DEMO_PASSWORD") or CLAVE_DEMO_DEFECTO
    pwd_hash, salt = hashear_password(clave_demo)

    admin = session.scalars(
        select(UsuarioModel).where(
            UsuarioModel.rol == RolUsuario.ADMIN.value, UsuarioModel.activo.is_(True)
        )
    ).first()
    if admin is None:
        admin = _asegurar_usuario_demo(
            session,
            username="admin_demo",
            nombre_completo="Administrador Demo Domingo Savio",
            rol_codigo=RolUsuario.ADMIN.value,
            pwd_hash=pwd_hash,
            salt=salt,
        )

    cuentas = {
        "admin": admin,
        "coordinador_demo": _asegurar_usuario_demo(
            session,
            username="coordinador_demo",
            nombre_completo="Lic. Patricia Quispe Mendoza",
            rol_codigo=RolUsuario.COORDINADOR.value,
            pwd_hash=pwd_hash,
            salt=salt,
        ),
        "staff_demo": _asegurar_usuario_demo(
            session,
            username="staff_demo",
            nombre_completo="Sr. Eduardo Luna Lezano",
            rol_codigo=RolUsuario.ADMIN_STAFF.value,
            pwd_hash=pwd_hash,
            salt=salt,
        ),
        "auxiliar_puerta": _asegurar_usuario_demo(
            session,
            username="auxiliar_puerta",
            nombre_completo="Sr. Marco Huamán Paredes",
            rol_codigo="AUXILIAR",
            pwd_hash=pwd_hash,
            salt=salt,
        ),
        "docente_mat": _asegurar_usuario_demo(
            session,
            username="docente_mat",
            nombre_completo="Prof. Jorge Chávez Vargas",
            rol_codigo="DOCENTE",
            pwd_hash=pwd_hash,
            salt=salt,
        ),
        "docente_com": _asegurar_usuario_demo(
            session,
            username="docente_com",
            nombre_completo="Prof. Yhovana Quispe Flores",
            rol_codigo="DOCENTE",
            pwd_hash=pwd_hash,
            salt=salt,
        ),
        "docente_cyt": _asegurar_usuario_demo(
            session,
            username="docente_cyt",
            nombre_completo="Prof. Dudu Lizarzaburu Torres",
            rol_codigo="DOCENTE",
            pwd_hash=pwd_hash,
            salt=salt,
        ),
    }
    return cuentas


def _crear_periodos(
    session: Session, fecha_hoy: date
) -> tuple[PeriodoAcademicoModel, PeriodoAcademicoModel]:
    anio = fecha_hoy.year
    inicio_b4 = min(date(anio, 10, 1), fecha_hoy - timedelta(days=20))
    fin_b4 = max(date(anio, 12, 20), fecha_hoy + timedelta(days=20))
    limite_b4 = fin_b4 + timedelta(days=7)

    inicio_b3 = inicio_b4 - timedelta(days=75)
    fin_b3 = inicio_b4 - timedelta(days=1)

    p3 = PeriodoAcademicoModel(
        anio_lectivo=anio,
        tipo_periodo="BIMESTRE",
        orden=3,
        nombre=f"Bimestre III {anio}",
        fecha_inicio=inicio_b3,
        fecha_fin=fin_b3,
        fecha_limite_notas=fin_b3,
        cerrado=True,
    )
    p4 = PeriodoAcademicoModel(
        anio_lectivo=anio,
        tipo_periodo="BIMESTRE",
        orden=4,
        nombre=f"Bimestre IV {anio}",
        fecha_inicio=inicio_b4,
        fecha_fin=fin_b4,
        fecha_limite_notas=limite_b4,
        cerrado=False,
    )
    session.add_all([p3, p4])
    session.flush()
    return p3, p4


def sembrar_datos_demo(
    session: Session, *, fecha_referencia: date | None = None
) -> ResumenSemillaDemo:
    """Puebla la base de datos de forma idempotente con cifras realistas del colegio.

    Si ya existen estudiantes en la base de datos (o el registro centinela demo),
    retorna sin duplicar ni modificar datos existentes.
    """
    total_estudiantes = session.scalar(select(func.count(EstudianteModel.id))) or 0
    if total_estudiantes > 0:
        return ResumenSemillaDemo(ejecutada=False)

    rng = random.Random(2026)
    fecha_hoy = fecha_referencia or datetime.now(ZONA_HORARIA_LIMA).date()
    anio = fecha_hoy.year

    cuentas = _asegurar_usuarios_y_roles(session)
    admin = cuentas["admin"]
    coordinador = cuentas["coordinador_demo"]
    auxiliar = cuentas["auxiliar_puerta"]

    if session.get(ConfiguracionSistemaModel, "hora_cierre_oficial") is None:
        session.add(
            ConfiguracionSistemaModel(
                clave="hora_cierre_oficial",
                valor="09:00:00",
                actualizado_por=admin.id,
            )
        )

    _p3, periodo_activo = _crear_periodos(session, fecha_hoy)

    # 1. Salones (11 aulas: Primaria 1ro–6to A y Secundaria 1ro–5to A)
    salones: list[SalonModel] = []
    for nivel in (NivelEducativo.PRIMARIA, NivelEducativo.SECUNDARIA):
        for grado in GRADOS_POR_NIVEL[nivel]:
            salones.append(
                SalonModel(
                    anio_lectivo=anio,
                    nivel=nivel.value,
                    grado=grado,
                    seccion="A",
                    capacidad_maxima=30,
                    activo=True,
                )
            )
    session.add_all(salones)
    session.flush()

    # 2. Cursos, asignaciones docentes, rubros y actividades (33 cursos)
    cursos: list[CursoModel] = []
    actividades_por_salon: dict[int, list[tuple[ActividadEvaluableModel, int]]] = {
        s.id: [] for s in salones
    }
    asignaciones: list[AsignacionDocenteModel] = []
    rubros: list[RubroEvaluacionModel] = []
    actividades: list[ActividadEvaluableModel] = []

    for idx_salon, salon in enumerate(salones, start=1):
        prefijo_nivel = "PRI" if salon.nivel == "Primaria" else "SEC"
        for cod_area, nombre_curso, area, horas, clave_doc in _AREAS_CURRICULARES:
            curso = CursoModel(
                anio_lectivo=anio,
                nivel=salon.nivel,
                grado=salon.grado,
                codigo=f"{cod_area}-{prefijo_nivel}-{salon.grado.upper()}",
                nombre=nombre_curso,
                area_curricular=area,
                horas_semanales=horas,
                activo=True,
            )
            cursos.append(curso)
            session.add(curso)
            session.flush()

            docente = cuentas[clave_doc]
            asig_id = f"asig-demo-{idx_salon:02d}-{cod_area.lower()}"
            asignaciones.append(
                AsignacionDocenteModel(
                    id=asig_id,
                    usuario_docente_id=docente.id,
                    curso_id=curso.id,
                    salon_id=salon.id,
                    anio_lectivo=anio,
                    activa=True,
                    asignado_por=admin.id,
                )
            )
            for idx_r, (r_slug, r_nombre, r_peso, act_titulo) in enumerate(_RUBROS_BASE, start=1):
                rubro_id = f"rub-demo-{idx_salon:02d}-{cod_area.lower()}-{r_slug}"
                rubros.append(
                    RubroEvaluacionModel(
                        id=rubro_id,
                        asignacion_docente_id=asig_id,
                        periodo_id=periodo_activo.id,
                        nombre=r_nombre,
                        peso_porcentaje=r_peso,
                        activo=True,
                    )
                )
                act = ActividadEvaluableModel(
                    id=f"act-demo-{idx_salon:02d}-{cod_area.lower()}-{idx_r}",
                    rubro_id=rubro_id,
                    titulo=act_titulo,
                    fecha=fecha_hoy - timedelta(days=12 - idx_r * 3),
                    activo=True,
                )
                actividades.append(act)
                actividades_por_salon[salon.id].append((act, docente.id))

    session.add_all(asignaciones)
    session.flush()
    session.add_all(rubros)
    session.flush()
    session.add_all(actividades)
    session.flush()

    # 3. 220 Estudiantes + Apoderados + Carnets QR
    estudiantes: list[EstudianteModel] = []
    apoderados: list[ApoderadoModel] = []
    contador = 0

    for idx_salon, salon in enumerate(salones):
        edad_base = 6 + idx_salon
        for _ in range(ALUMNOS_POR_SALON):
            contador += 1
            ap1 = _APELLIDOS_CUSCO[(contador * 3 + idx_salon) % len(_APELLIDOS_CUSCO)]
            ap2 = _APELLIDOS_CUSCO[(contador * 7 + 5) % len(_APELLIDOS_CUSCO)]
            nombre = _NOMBRES_ESTUDIANTES[(contador - 1) % len(_NOMBRES_ESTUDIANTES)]
            codigo_est = f"ALU-2026-{contador:04d}"
            dni_est = f"{72100000 + contador:08d}"
            carnet_cod = f"CRN-2026-{contador:04d}"

            estado_est = "ACTIVO"
            if contador in (217, 218):
                estado_est = "SUSPENDIDO"
            elif contador in (219, 220):
                estado_est = "RETIRADO"

            est = EstudianteModel(
                codigo=codigo_est,
                dni=dni_est,
                nombres=nombre,
                apellidos=f"{ap1} {ap2}",
                fecha_nacimiento=date(
                    anio - edad_base,
                    ((contador - 1) % 12) + 1,
                    ((contador * 3) % 27) + 1,
                ),
                salon_id=salon.id,
                nivel=salon.nivel,
                grado=salon.grado,
                seccion=salon.seccion,
                carnet_codigo=carnet_cod,
                estado=estado_est,
            )
            estudiantes.append(est)

            apoderado = ApoderadoModel(
                nombres=_NOMBRES_APODERADOS[(contador - 1) % len(_NOMBRES_APODERADOS)],
                apellidos=f"{ap1} {ap2}",
                documento=f"{42100000 + contador:08d}",
                parentesco="MADRE" if contador % 2 == 0 else "PADRE",
                telefono_whatsapp=f"+51984{100000 + contador:06d}",
                activo=True,
            )
            apoderados.append(apoderado)

    session.add_all(estudiantes)
    session.add_all(apoderados)
    session.flush()

    vinculos: list[EstudianteApoderadoModel] = []
    carnets: list[CarnetModel] = []
    for idx, (est, apo) in enumerate(zip(estudiantes, apoderados, strict=True), start=1):
        vinculos.append(
            EstudianteApoderadoModel(
                estudiante_id=est.id,
                apoderado_id=apo.id,
                es_principal=True,
            )
        )
        retirado = est.estado == "RETIRADO"
        carnets.append(
            CarnetModel(
                id=f"crn-demo-{idx:04d}",
                estudiante_id=est.id,
                codigo_qr=est.carnet_codigo or f"CRN-2026-{idx:04d}",
                estado="ANULADO" if retirado else "ACTIVO",
                motivo_anulacion="CAMBIO_ESTADO" if retirado else None,
                detalle_anulacion="Retiro definitivo del año lectivo" if retirado else None,
                emitido_por=admin.id,
                anulado_en=datetime.now(ZONA_HORARIA_LIMA) if retirado else None,
            )
        )
    session.add_all(vinculos)
    session.add_all(carnets)
    session.flush()

    # 4. Obligaciones de pago (~12 % morosidad realista; incluye CRN-2026-0010 para demo en vivo)
    obligaciones: list[ObligacionPagoModel] = []
    deudores_vencidos: dict[int, tuple[int, Decimal]] = {}
    venc_oct = fecha_hoy - timedelta(days=25)
    venc_nov = fecha_hoy - timedelta(days=5)
    ahora_utc = datetime.now(ZONA_HORARIA_LIMA)

    for idx, est in enumerate(estudiantes, start=1):
        monto = Decimal("320.00") if est.nivel == "Primaria" else Decimal("360.00")
        es_deudor_fuerte = idx == 10 or (idx > 12 and idx % 9 == 0)
        es_deudor_nov = idx % 5 == 0 and not es_deudor_fuerte

        estado_oct = "VENCIDO" if es_deudor_fuerte else "PAGADO"
        estado_nov = "VENCIDO" if (es_deudor_fuerte or es_deudor_nov) else "PAGADO"

        obligaciones.append(
            ObligacionPagoModel(
                id=f"obl-demo-{idx:04d}-oct",
                estudiante_id=est.id,
                concepto=f"Pensión Octubre {anio}",
                monto=monto,
                fecha_vencimiento=venc_oct,
                estado=estado_oct,
                pagado_en=None if estado_oct == "VENCIDO" else ahora_utc - timedelta(days=27),
            )
        )
        obligaciones.append(
            ObligacionPagoModel(
                id=f"obl-demo-{idx:04d}-nov",
                estudiante_id=est.id,
                concepto=f"Pensión Noviembre {anio}",
                monto=monto,
                fecha_vencimiento=venc_nov,
                estado=estado_nov,
                pagado_en=None if estado_nov == "VENCIDO" else ahora_utc - timedelta(days=7),
            )
        )
        vencidas = (1 if estado_oct == "VENCIDO" else 0) + (1 if estado_nov == "VENCIDO" else 0)
        if vencidas > 0:
            deudores_vencidos[est.id] = (vencidas, monto * vencidas)

    session.add_all(obligaciones)
    session.flush()

    # 5. Calificaciones vigesimales realistas [11.00, 19.50] (1,980 notas)
    calificaciones: list[CalificacionModel] = []
    for idx, est in enumerate(estudiantes, start=1):
        base_rendimiento = rng.uniform(12.0, 18.0)
        for idx_act, (act, docente_id) in enumerate(
            actividades_por_salon[est.salon_id or salones[0].id], start=1
        ):
            valor = max(10.5, min(19.5, base_rendimiento + rng.uniform(-1.8, 1.8)))
            nota_dec = Decimal(f"{round(valor * 2) / 2:.2f}")
            calificaciones.append(
                CalificacionModel(
                    id=f"cal-demo-{idx:04d}-{idx_act:02d}",
                    actividad_id=act.id,
                    estudiante_id=est.id,
                    nota=nota_dec,
                    usuario_id=docente_id,
                )
            )
    session.add_all(calificaciones)
    session.flush()

    # 6. Asistencias: últimos 4 días lectivos + hoy (~90 % asistencia) + justificaciones + alertas
    dias_previos = _ultimos_dias_lectivos(fecha_hoy, 4)
    asistencias: list[AsistenciaModel] = []
    justificaciones: list[JustificacionModel] = []
    alertas_pago: list[AlertaPagoSilenciosaModel] = []

    for dia_idx, dia in enumerate(dias_previos, start=1):
        for idx, est in enumerate(estudiantes, start=1):
            if est.estado != "ACTIVO":
                continue
            tirada = rng.random()
            if tirada < 0.87:
                estado_as = "PUNTUAL"
                hora_as = time(7, rng.randint(0, 14), rng.randint(0, 59))
                tardanza = 0
                metodo = "CARNET" if idx % 7 != 0 else "MANUAL_DNI"
            elif tirada < 0.95:
                estado_as = "TARDANZA"
                min_t = rng.randint(16, 36)
                hora_as = time(7, min_t, rng.randint(0, 59))
                tardanza = min_t - 15
                metodo = "CARNET"
            else:
                estado_as = "AUSENTE"
                hora_as = time(9, 0, 0)
                tardanza = 0
                metodo = "CARNET"

            as_id = f"as-demo-d{dia_idx}-{idx:04d}"
            es_justificada = estado_as == "AUSENTE" and len(justificaciones) < 6
            if es_justificada:
                estado_final = "JUSTIFICADO"
                estado_ant = "AUSENTE"
            else:
                estado_final = estado_as
                estado_ant = None

            asistencias.append(
                AsistenciaModel(
                    id=as_id,
                    estudiante_id=est.id,
                    usuario_id=auxiliar.id,
                    fecha_escolar=dia,
                    hora_efectiva=hora_as,
                    estado=estado_final,
                    minutos_tardanza=tardanza,
                    metodo=metodo,
                    rol_usuario=auxiliar.rol,
                    estado_anterior=estado_ant,
                    nivel_snapshot=est.nivel,
                    grado_snapshot=est.grado,
                    seccion_snapshot=est.seccion,
                )
            )
            if es_justificada:
                justificaciones.append(
                    JustificacionModel(
                        id=f"just-demo-{len(justificaciones) + 1:03d}",
                        asistencia_id=as_id,
                        estudiante_id=est.id,
                        periodo_id=periodo_activo.id,
                        usuario_id=coordinador.id,
                        rol_usuario=coordinador.rol,
                        fecha_solicitud=dia,
                        categoria="MEDICA" if len(justificaciones) % 2 == 0 else "PERMISO_FAMILIAR",
                        motivo="Descanso médico presentado por apoderado"
                        if len(justificaciones) % 2 == 0
                        else "Permiso familiar autorizado por coordinación",
                        estado="APROBADA",
                        minutos_tardanza_original=0,
                        nivel=est.nivel,
                        grado=est.grado,
                        seccion=est.seccion,
                        fecha_resolucion=ahora_utc - timedelta(days=1),
                    )
                )

    # Jornada de HOY:
    # - CRN-2026-0001..0008 y CRN-2026-0010 quedan PENDIENTES para escaneo QR EN VIVO
    # - CRN-2026-0009 queda AUSENTE para demostrar corrección condicional con motivo
    # - CRN-2026-0011..0216 ya ingresaron (~90 % puntual, ~10 % tardanza)
    for idx, est in enumerate(estudiantes, start=1):
        if est.estado != "ACTIVO":
            continue
        if idx in (1, 2, 3, 4, 5, 6, 7, 8, 10):
            continue

        as_id = f"as-demo-hoy-{idx:04d}"
        if idx == 9:
            asistencias.append(
                AsistenciaModel(
                    id=as_id,
                    estudiante_id=est.id,
                    usuario_id=admin.id,
                    fecha_escolar=fecha_hoy,
                    hora_efectiva=time(9, 0, 0),
                    estado="AUSENTE",
                    minutos_tardanza=0,
                    metodo="CARNET",
                    rol_usuario=admin.rol,
                    nivel_snapshot=est.nivel,
                    grado_snapshot=est.grado,
                    seccion_snapshot=est.seccion,
                )
            )
            continue

        es_tardanza = idx % 11 == 0
        if es_tardanza:
            minuto = 16 + (idx % 22)
            hora_as = time(7, minuto, idx % 60)
            tardanza = minuto - 15
            estado_as = "TARDANZA"
        else:
            minuto = idx % 15
            hora_as = time(7, minuto, (idx * 7) % 60)
            tardanza = 0
            estado_as = "PUNTUAL"

        asistencias.append(
            AsistenciaModel(
                id=as_id,
                estudiante_id=est.id,
                usuario_id=auxiliar.id,
                fecha_escolar=fecha_hoy,
                hora_efectiva=hora_as,
                estado=estado_as,
                minutos_tardanza=tardanza,
                metodo="CARNET" if idx % 6 != 0 else "MANUAL_DNI",
                rol_usuario=auxiliar.rol,
                nivel_snapshot=est.nivel,
                grado_snapshot=est.grado,
                seccion_snapshot=est.seccion,
            )
        )

        if est.id in deudores_vencidos:
            cant_v, monto_v = deudores_vencidos[est.id]
            alertas_pago.append(
                AlertaPagoSilenciosaModel(
                    id=f"alerta-demo-hoy-{idx:04d}",
                    estudiante_id=est.id,
                    asistencia_id=as_id,
                    fecha_escolar=fecha_hoy,
                    cantidad_obligaciones_vencidas=cant_v,
                    monto_vencido_total=monto_v,
                    revisada=False,
                )
            )

    session.add_all(asistencias)
    session.flush()
    session.add_all(justificaciones)
    session.add_all(alertas_pago)
    session.flush()

    return ResumenSemillaDemo(
        ejecutada=True,
        salones=len(salones),
        estudiantes=len(estudiantes),
        cursos=len(cursos),
        asistencias=len(asistencias),
        calificaciones=len(calificaciones),
        obligaciones_pago=len(obligaciones),
    )


if __name__ == "__main__":  # pragma: no cover - ejecución CLI manual opcional
    from src.infraestructura.base_datos import crear_motor, crear_session_factory, inicializar_bd

    motor = crear_motor()
    inicializar_bd(motor)
    fabrica = crear_session_factory(motor)
    with fabrica() as sesion:
        resumen = sembrar_datos_demo(sesion)
        sesion.commit()
    print(f"Semilla demo: {resumen}")
