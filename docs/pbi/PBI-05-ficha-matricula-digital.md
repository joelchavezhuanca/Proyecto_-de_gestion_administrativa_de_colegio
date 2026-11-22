# PBI-05: Ficha de Matrícula Digital

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-05` |
| **Rama Git a crear** | `feature/PBI-05-ficha-matricula-digital` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-09` (Salones/Malla), `PBI-08` (Estados Académicos), `PBI-15` (RBAC), `PBI-16` (Auditoría). |
| **Permisos requeridos** | `GESTIONAR_MATRICULA`. |

---

## 1. Historia de Usuario
Como personal autorizado con permiso `GESTIONAR_MATRICULA`, deseo registrar y actualizar la matrícula digital de los estudiantes junto con sus apoderados y asignación a un salón (`anio_lectivo`, `nivel`, `grado`, `seccion`), para mantener un padrón único que alimente asistencia, notificaciones y calificaciones.

---

## 2. Reglas de Negocio
- **RN-01:** Requiere permiso `GESTIONAR_MATRICULA`.
- **RN-02:** Datos obligatorios del alumno: `codigo` único institucional, `dni` único de 8 dígitos numéricos, `nombres`, `apellidos`, `fecha_nacimiento` válida y `salon_id` activo.
- **RN-03:** Cada matrícula requiere al menos **un apoderado principal** con `nombres`, `apellidos`, `documento`, `parentesco` y `telefono_whatsapp` válido (Perú 9 dígitos o formato E.164 `+51...`).
- **RN-04:** No se permite DNI duplicado ni doble matrícula activa del mismo estudiante en el mismo año lectivo.
- **RN-05:** Validar vacantes del salón (`matriculados_actuales < salon.capacidad_maxima`).
- **RN-06:** El cambio interno de sección actualiza el salón actual del estudiante sin alterar el snapshot académico de sus asistencias pasadas (`PBI-01`).
- **RN-07:** Toda matrícula, actualización o traslado interno genera evento en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Matricular estudiante nuevo con apoderado principal en un salón con vacantes → crea alumno `ACTIVO` y audita.
2. Rechazar DNI inválido (no 8 dígitos) o DNI duplicado.
3. Rechazar matrícula sin apoderado principal o con teléfono WhatsApp inválido.
4. Rechazar matrícula cuando el salón alcanzó su `capacidad_maxima`.
5. Trasladar alumno de sección (`3ro A` → `3ro B`) verificando vacantes y auditando el cambio.
6. Denegar matrícula a usuarios sin permiso `GESTIONAR_MATRICULA`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/matricula.py`
- Pruebas nuevas: `tests/test_matricula.py`
- Entidades (`@dataclass(frozen=True)`): `Apoderado`, `FichaMatricula`, `ResultadoMatricula`.
- Servicio: `ServicioMatricula` (`matricular_estudiante`, `actualizar_apoderados`, `cambiar_salon`).
- **Consideración técnica:** Reutilizar la validación de DNI de `asistencia.py` y normalizar teléfonos a formato E.164 (`+519XXXXXXXX`) para consumo limpio en `PBI-17`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-05-ficha-matricula-digital
# 1. RED -> tests/test_matricula.py
# 2. GREEN -> src/dominio/matricula.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
