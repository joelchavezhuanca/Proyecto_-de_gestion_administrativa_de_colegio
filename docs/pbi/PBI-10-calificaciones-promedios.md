# PBI-10: Cálculo de Calificaciones y Promedios (Libro de 3 Niveles)

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-10` |
| **Rama Git a crear** | `feature/PBI-10-calificaciones-promedios` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-04` (`PeriodoAcademico` con `fecha_limite_notas`), `PBI-09` (Cursos/Salones), `PBI-11` (Asignación Docente), `PBI-15` (RBAC), `PBI-16` (Auditoría). |
| **Permisos requeridos** | `REGISTRAR_CALIFICACIONES` (docentes asignados / autorizados) y `CONSULTAR_CALIFICACIONES`. |

---

## 1. Historia de Usuario
Como docente con permiso `REGISTRAR_CALIFICACIONES`, deseo definir mis propios rubros de evaluación (sumando 100%) y registrar actividades evaluables y notas dentro de la fecha límite del período, para calcular automáticamente promedios de período y anuales con precisión.

---

## 2. Arquitectura de 3 Niveles (Estándar de la Industria)
1. **Nivel 1 — Período Institucional (`ADMIN`):** Períodos flexibles (`BIMESTRE`, `TRIMESTRE`, `SEMESTRE`) con `fecha_inicio`, `fecha_fin` y **`fecha_limite_notas`**.
2. **Nivel 2 — Rubros / Categorías del Docente:** Por cada `(curso, salón, período)`, el docente define sus rubros personalizados (ej. *Exámenes 50%*, *Prácticas 30%*, *Tareas 20%*) o parte de una plantilla sugerida opcional. La suma de pesos de los rubros activos debe ser exactamente **100%**.
3. **Nivel 3 — Actividades Evaluables:** Dentro de cada rubro, el docente crea libremente sus tareas, prácticas, proyectos o exámenes sin alterar la suma del 100%.

---

## 3. Reglas de Negocio
- **RN-01:** Registrar/modificar rubros, actividades y calificaciones requiere `REGISTRAR_CALIFICACIONES` y asignación docente activa sobre ese `(curso, salón)` según `PBI-11`.
- **RN-02:** Escala vigesimal oficial `[0, 20]` calculada exclusivamente con **`Decimal` y `ROUND_HALF_UP`** (nunca `float`). Conversión opcional a escala literal (`AD: 18–20`, `A: 14–17`, `B: 11–13`, `C: 0–10`) configurable por nivel.
- **RN-03 (Fecha límite de notas):** Solo se permite crear/editar rubros, actividades y notas cuando el período está **abierto** (`cerrado = False`) **y** `ahora <= periodo.fecha_limite_notas` (`America/Lima`). Vencida la fecha límite, se lanza `FechaLimiteNotasVencidaException`; solo un usuario con `ADMINISTRAR_PERIODOS` puede prorrogarla o reabrir el período (auditado en `PBI-16`).
- **RN-04 (Sin estado `EXONERADO`):** Todas las actividades evaluables del rubro entran en el cálculo. Si un alumno faltó, el docente coordina su regularización antes de `fecha_limite_notas`; si al cierre no presentó, queda con su nota real (`0`).
- **RN-05 (Fórmulas):**
  - `Promedio_Rubro` = promedio aritmético de las actividades del rubro.
  - `Nota_Periodo` = sumatoria de `Promedio_Rubro * (Peso_Rubro / 100)`.
  - `Promedio_Anual_Curso` = promedio de las notas de los períodos oficiales del año lectivo.
- **RN-06:** Toda modificación de nota conserva valor anterior, valor nuevo, motivo y auditoría en `PBI-16`.

---

## 4. Escenarios BDD (Gherkin)
1. Docente configura rubros `Exámenes 50%`, `Prácticas 30%`, `Tareas 20%`, agrega 3 tareas y 2 exámenes dentro de `fecha_limite_notas` → calcula promedio exacto por rubro y nota del período con `Decimal`.
2. Rechazar configuración de rubros cuya suma de pesos sea distinta de `100%` (ej. 90% o 110%).
3. Rechazar nota fuera de `[0, 20]` (`-1` o `21`).
4. Bloquear registro o modificación si `ahora > fecha_limite_notas` o si el período está cerrado.
5. `ADMIN` prorroga `fecha_limite_notas` → docente regulariza la nota pendiente y se audita.
6. Docente intenta calificar un salón no asignado (`PBI-11`) → acceso denegado.

---

## 5. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/calificaciones.py`
- Pruebas nuevas: `tests/test_calificaciones.py`
- Entidades (`@dataclass(frozen=True)`): `RubroEvaluacion`, `ActividadEvaluable`, `Calificacion`, `PromedioPeriodo`, `PromedioAnualCurso`.
- Servicio: `ServicioCalificaciones` (`configurar_rubros`, `crear_actividad`, `registrar_calificacion`, `calcular_promedio_periodo`, `calcular_promedio_anual`, `convertir_a_literal`).

---

## 6. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-10-calificaciones-promedios
# 1. RED -> tests/test_calificaciones.py
# 2. GREEN -> src/dominio/calificaciones.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
