# PBI-04: Gestión de Justificaciones de Inasistencia y Períodos Académicos

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-04` |
| **Rama Git a crear** | `feature/PBI-04-gestion-justificaciones` *(desde `main`)* |
| **Estado actual en `main`** | Parcial en `src/dominio/justificaciones.py` (solo registrar/aprobar y anular; excluye a `COORDINADOR`, sin edición, sin adjuntos validados ni gestión de períodos). |
| **Dependencias** | `PBI-01`, `PBI-15` (RBAC Dinámico), `PBI-16` (Auditoría). Consumido por `PBI-10` y `PBI-14`. |
| **Permisos requeridos** | `GESTIONAR_JUSTIFICACIONES` (`ADMIN`, `COORDINADOR`, `ADMIN_STAFF` y roles personalizados autorizados) y `ADMINISTRAR_PERIODOS` (exclusivo `ADMIN` / roles con permiso). |

---

## 1. Historia de Usuario
Como operador con permiso `GESTIONAR_JUSTIFICACIONES`, deseo registrar, consultar, modificar y anular justificaciones de inasistencias o tardanzas dentro de períodos académicos abiertos; y como administrador con `ADMINISTRAR_PERIODOS`, gestionar los períodos escolares (Bimestres/Trimestres/Semestres) y sus fechas límite de notas.

---

## 2. Reglas de Negocio
- **RN-01 / RN-02:** Gestionar justificaciones requiere `GESTIONAR_JUSTIFICACIONES` (habilitado por defecto para `ADMIN`, `COORDINADOR` y `ADMIN_STAFF`). Administrar períodos académicos requiere `ADMINISTRAR_PERIODOS`.
- **RN-03:** El alumno debe existir (`alumno is not None`) y estar `ACTIVO`.
- **RN-04:** Solo se justifican asistencias en estado `AUSENTE` o `TARDANZA`.
- **RN-05:** Prohibido justificar fechas futuras respecto a la fecha oficial del servidor (`America/Lima`).
- **RN-06:** La fecha de la asistencia debe pertenecer a un período académico **abierto** (`cerrado = False`). Si está cerrado, se bloquea crear, modificar y anular.
- **RN-07 / RN-08:** Motivo obligatorio no vacío. Categorías: `MEDICA`, `PERMISO_FAMILIAR`, `OTRA`.
- **RN-09 / RN-10:** Registro atómico cambia asistencia a `JUSTIFICADO` (`minutos_tardanza = 0`, guarda `estado_anterior` y `minutos_tardanza_original`). La anulación (en período abierto) restaura el estado y los minutos originales.
- **RN-11:** Modificación permitida sobre justificaciones vigentes dentro de período abierto (actualiza categoría/motivo y permite anexar nuevos adjuntos).
- **RN-12 / RN-13 (Adjuntos):** Opcionales; extensiones permitidas `pdf`, `jpg`, `jpeg`, `png`; tamaño `<= 5 MB` (`5_242_880` bytes); máximo `3` adjuntos por justificación; **inmutables** (no se eliminan ni sobrescriben al modificar).
- **RN-14 a RN-16 (Períodos Académicos):** Períodos flexibles (`BIMESTRE`, `TRIMESTRE`, `SEMESTRE`) con `anio_lectivo`, `orden`, `nombre` único, `fecha_inicio <= fecha_fin` y `fecha_limite_notas` (usada por `PBI-10`), la cual debe ser `>= fecha_inicio` y **puede ser posterior a `fecha_fin`** para que los docentes regularicen calificaciones al cierre del período. Sin solapamiento de fechas y sin borrado si tienen justificaciones o calificaciones asociadas.
- **RN-17 / RN-18:** Historial filtrable por `nivel`, `grado`, `seccion`, `alumno_id`, `categoria`, `estado` y fechas; todo auditado en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. `COORDINADOR` registra y aprueba justificación de `AUSENTE` → asistencia pasa a `JUSTIFICADO` atómicamente.
2. Justificar `TARDANZA` (12 min) y anularla en período abierto → restaura `TARDANZA` con 12 min.
3. Rechazar alumno inexistente (`None`) o inactivo.
4. Validar adjuntos: rechazar `.exe`, tamaño `> 5 MB` o más de 3 archivos.
5. Modificar justificación conservando los adjuntos previos intactos.
6. Bloquear creación, modificación y anulación en período cerrado.
7. Solo usuarios con `ADMINISTRAR_PERIODOS` crean, modifican, cierran/reabren o eliminan períodos (con `fecha_limite_notas`).
8. Impedir solapamiento de períodos y borrado de períodos con uso.
9. Filtrar historial de justificaciones por `(nivel, grado, seccion)`.

---

## 4. Diseño de Dominio y Cambios Respecto a `main`
Archivos: `src/dominio/justificaciones.py`, `tests/test_aforo_justificaciones.py` (o `tests/test_justificaciones.py`).
- Agregar `TipoPeriodo(StrEnum)` (`BIMESTRE`, `TRIMESTRE`, `SEMESTRE`), `AdjuntoJustificacion`, `FiltroJustificaciones`.
- Extender `PeriodoAcademico` con `anio_lectivo`, `tipo_periodo`, `orden`, `fecha_limite_notas` (con defaults retrocompatibles).
- Extender `Justificacion` con `adjuntos: tuple[AdjuntoJustificacion, ...] = ()` y `minutos_tardanza_original: int = 0`.
- Agregar `modificar_justificacion`, `consultar_justificaciones` y `ServicioPeriodosAcademicos`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-04-gestion-justificaciones
# 1. RED: tests para COORDINADOR, adjuntos, modificación, consulta filtrada y ServicioPeriodosAcademicos
# 2. GREEN: implementar en src/dominio/justificaciones.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
