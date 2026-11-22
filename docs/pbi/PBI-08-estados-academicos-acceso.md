# PBI-08: Control de Estados Académicos de Acceso

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-08` |
| **Rama Git a crear** | `feature/PBI-08-estados-academicos-acceso` *(desde `main`)* |
| **Estado actual en `main`** | Parcial: solo existe `EstadoAlumno(ACTIVO, INACTIVO)` en `src/dominio/asistencia.py`. |
| **Dependencias** | `PBI-15` (RBAC), `PBI-16` (Auditoría). Consumido por `PBI-01`, `PBI-05`, `PBI-06` y `PBI-12`. |
| **Permisos requeridos** | `GESTIONAR_ESTADOS_ACADEMICOS`. |

---

## 1. Historia de Usuario
Como usuario con permiso `GESTIONAR_ESTADOS_ACADEMICOS`, deseo gestionar los estados académicos de los alumnos (`ACTIVO`, `SUSPENDIDO`, `RETIRADO`, `TRASLADADO`, `EGRESADO`) y sus efectos sobre el ingreso y la asistencia, conservando siempre su historial.

---

## 2. Reglas de Negocio
- **RN-01:** Cambiar el estado académico requiere permiso `GESTIONAR_ESTADOS_ACADEMICOS` y `motivo` obligatorio no vacío.
- **RN-02 (Estados y efecto sobre `PBI-01`):**
  - `ACTIVO`: habilitado para asistencia, búsqueda asistida, carnet y calificaciones.
  - `SUSPENDIDO`: bloqueado temporalmente para asistencia durante `[fecha_inicio, fecha_fin]` (evaluado en `America/Lima`); al concluir o reactivarse vuelve a `ACTIVO`.
  - `RETIRADO`, `TRASLADADO`, `EGRESADO`: bloqueados permanentemente para nueva asistencia, búsqueda asistida y emisión de carnets; su carnet activo pasa a `ANULADO`.
- **RN-03:** El cambio de estado **nunca elimina** asistencias, justificaciones, pagos ni calificaciones históricas.
- **RN-04:** Validar transiciones válidas (por ejemplo, `EGRESADO` no puede pasar a `SUSPENDIDO`).
- **RN-05:** Registrar cada transición en `HistorialEstadoAlumno` y en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Suspender alumno `ACTIVO` con motivo y fechas → `PBI-01` rechaza registro indicando `SUSPENDIDO`.
2. Retirar o trasladar alumno → bloquea asistencia, señala anulación de carnet y conserva historial.
3. Reactivar alumno `SUSPENDIDO` → vuelve a `ACTIVO` y puede registrar asistencia.
4. Rechazar transición inválida (`EGRESADO` → `SUSPENDIDO`) o cambio sin motivo.
5. Denegar cambio de estado sin permiso `GESTIONAR_ESTADOS_ACADEMICOS`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/estados_academicos.py` (y alineación retrocompatible de `EstadoAlumno` en `src/dominio/asistencia.py`).
- Pruebas nuevas: `tests/test_estados_academicos.py`.
- Entidades: `EstadoAcademico`, `HistorialEstadoAlumno`, `ServicioEstadosAcademicos` (`cambiar_estado`, `puede_registrar_asistencia`).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-08-estados-academicos-acceso
# 1. RED -> tests/test_estados_academicos.py
# 2. GREEN -> src/dominio/estados_academicos.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
