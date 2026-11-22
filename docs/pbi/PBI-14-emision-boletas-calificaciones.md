# PBI-14: Emisión de Boletas de Calificaciones

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-14` |
| **Rama Git a crear** | `feature/PBI-14-emision-boletas-calificaciones` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-10` (Calificaciones y Promedios), `PBI-04` (Períodos), `PBI-01` (Resumen de Asistencia), `PBI-05` (Matrícula), `PBI-15` (RBAC), `PBI-16` (Auditoría). |
| **Permisos requeridos** | `EMITIR_BOLETAS`. |

---

## 1. Historia de Usuario
Como personal autorizado con permiso `EMITIR_BOLETAS`, deseo emitir boletas individuales o masivas por salón para un período o año lectivo, incluyendo promedios por curso, promedio general y resumen de asistencia.

---

## 2. Reglas de Negocio
- **RN-01:** Requiere permiso `EMITIR_BOLETAS`.
- **RN-02:** Contenido obligatorio: datos institucionales (Colegio Domingo Savio S.A.C.), datos del alumno, año lectivo, salón, período académico, tabla de cursos con nota numérica (`Decimal` `[0, 20]`) y literal opcional (`AD/A/B/C`), promedio general y resumen de asistencia (`PUNTUAL`, `TARDANZA`, `AUSENTE`, `JUSTIFICADO`).
- **RN-03 (Preliminar vs. Oficial):**
  - Período abierto → boleta emitida con `es_oficial = False` y marca `"BORRADOR / PRELIMINAR"`.
  - Período cerrado → boleta emitida con `es_oficial = True` y `codigo_verificacion` único.
- **RN-04:** Soporta emisión individual (un alumno) y emisión masiva por salón `(anio_lectivo, nivel, grado, seccion)`.
- **RN-05:** No bloquea emisión por deuda (salvo política institucional explícitamente activada por `ADMIN`; por defecto no bloquea).
- **RN-06:** Toda emisión oficial se audita en `PBI-16` con código de verificación, período y usuario emisor.

---

## 3. Escenarios BDD (Gherkin)
1. Emitir boleta en período cerrado → `es_oficial = True`, incluye código verificador, promedios, resumen de asistencia y auditoría.
2. Emitir boleta en período abierto → `es_oficial = False`, etiquetada `"PRELIMINAR"`.
3. Emisión masiva por salón → genera una boleta por cada alumno matriculado en el salón.
4. Rechazar emisión oficial si el alumno no tiene calificaciones registradas para los cursos obligatorios del período.
5. Denegar emisión a usuario sin permiso `EMITIR_BOLETAS`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/boletas.py` (el renderizador PDF va en `src/infraestructura/` en la Fase 5).
- Pruebas nuevas: `tests/test_boletas.py`.
- Entidades: `LineaCursoBoleta`, `BoletaCalificaciones`, `ServicioBoletas` (`emitir_boleta_individual`, `emitir_boletas_salon`).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-14-emision-boletas-calificaciones
# 1. RED -> tests/test_boletas.py
# 2. GREEN -> src/dominio/boletas.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
