# PBI-12: Ficha Informativa del Alumno

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-12` |
| **Rama Git a crear** | `feature/PBI-12-ficha-informativa-alumno` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-01`, `PBI-04`, `PBI-05`, `PBI-06`, `PBI-07`, `PBI-08`, `PBI-10`, `PBI-15`. |
| **Permisos requeridos** | `CONSULTAR_FICHA_ALUMNO` (y opcionalmente `VER_ALERTA_PAGOS` para ver el bloque financiero). |

---

## 1. Historia de Usuario
Como usuario con permiso `CONSULTAR_FICHA_ALUMNO`, deseo consultar una vista consolidada del alumno con su perfil de matrícula, salón, apoderados, estado académico, carnet, resumen de asistencia y rendimiento académico.

---

## 2. Reglas de Negocio
- **RN-01:** Requiere permiso `CONSULTAR_FICHA_ALUMNO`.
- **RN-02:** Ensambla en un DTO estructurado: datos de matrícula (`PBI-05`), estado académico (`PBI-08`), estado del carnet activo (`PBI-06`), apoderados, resumen de asistencia (`PUNTUAL`, `TARDANZA`, `AUSENTE`, `JUSTIFICADO`, % asistencia) y resumen de promedios por curso (`PBI-10`).
- **RN-03 (Segregación financiera):** El resumen de pagos/deudas solo se incluye si el operador también posee `VER_ALERTA_PAGOS` o `GESTIONAR_PAGOS`; de lo contrario ese bloque se devuelve como `None` (no se expone).
- **RN-04:** Permite consultar tanto alumnos `ACTIVO` como históricos (`RETIRADO`, `TRASLADADO`, `EGRESADO`).
- **RN-05:** Si el alumno no existe, lanza `AlumnoNoEncontradoException`.

---

## 3. Escenarios BDD (Gherkin)
1. Usuario con `CONSULTAR_FICHA_ALUMNO` + `VER_ALERTA_PAGOS` consulta ficha → recibe perfil completo incluyendo resumen de pagos.
2. Usuario con `CONSULTAR_FICHA_ALUMNO` (sin `VER_ALERTA_PAGOS`) consulta ficha → recibe ficha completa con `resumen_pagos = None`.
3. Consultar ficha de alumno `RETIRADO` → devuelve su información histórica intacta.
4. Rechazar consulta de alumno inexistente o sin permiso `CONSULTAR_FICHA_ALUMNO`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/ficha_alumno.py`
- Pruebas nuevas: `tests/test_ficha_alumno.py`
- Entidades (`@dataclass(frozen=True)`): `ResumenAsistenciaAlumno`, `ResumenPagosAlumno`, `FichaInformativaAlumno`.
- Servicio: `ServicioFichaAlumno` (`construir_ficha`).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-12-ficha-informativa-alumno
# 1. RED -> tests/test_ficha_alumno.py
# 2. GREEN -> src/dominio/ficha_alumno.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
