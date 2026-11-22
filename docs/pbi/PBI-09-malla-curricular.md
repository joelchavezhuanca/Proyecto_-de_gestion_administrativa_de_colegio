# PBI-09: Configuración de Malla Curricular

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-09` |
| **Rama Git a crear** | `feature/PBI-09-malla-curricular` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-15` (RBAC), `PBI-16` (Auditoría). Base estructural para `PBI-03`, `PBI-05`, `PBI-10` y `PBI-11`. |
| **Permisos requeridos** | `CONFIGURAR_MALLA_CURRICULAR`. |

---

## 1. Historia de Usuario
Como administrador con permiso `CONFIGURAR_MALLA_CURRICULAR`, deseo definir la estructura académica del colegio (niveles Primaria y Secundaria, grados, secciones/salones y cursos por año lectivo), para estandarizar matrícula, asistencia y evaluaciones.

---

## 2. Reglas de Negocio
- **RN-01:** Requiere permiso `CONFIGURAR_MALLA_CURRICULAR`.
- **RN-02:** Soporta `Primaria` (`1ro` a `6to`) y `Secundaria` (`1ro` a `5to`), con una o más secciones (`A`, `B`, `C`, ...) por grado y año lectivo.
- **RN-03:** Unicidad estricta de salón por `(anio_lectivo, nivel, grado, seccion)`. Cada salón tiene `capacidad_maxima > 0`.
- **RN-04:** Cada curso tiene `codigo` único por `(anio_lectivo, nivel, grado)`, `nombre`, `area_curricular`, `horas_semanales > 0` y estado `activo`.
- **RN-05:** No se permite eliminación física de un salón con alumnos matriculados ni de un curso con calificaciones registradas (solo baja lógica `activo = False`).
- **RN-06:** Toda creación o modificación se audita en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Crear salón `2026 - Secundaria - 4to - C` con capacidad 30 y crear cursos `Matemática` y `Comunicación`.
2. Rechazar salón duplicado en el mismo año lectivo o grado inválido para el nivel (ej. `6to` de Secundaria).
3. Rechazar curso con código duplicado en el mismo grado/año o con `horas_semanales <= 0`.
4. Impedir baja/eliminación destructiva de salón o curso en uso; permitir desactivación lógica.
5. Denegar operación sin permiso `CONFIGURAR_MALLA_CURRICULAR`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/malla_curricular.py`
- Pruebas nuevas: `tests/test_malla_curricular.py`
- Entidades: `NivelEducativo(PRIMARIA, SECUNDARIA)`, `Salon`, `Curso`, `ServicioMallaCurricular`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-09-malla-curricular
# 1. RED -> tests/test_malla_curricular.py
# 2. GREEN -> src/dominio/malla_curricular.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
