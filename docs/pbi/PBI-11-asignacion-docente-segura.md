# PBI-11: Asignación Docente Segura

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-11` |
| **Rama Git a crear** | `feature/PBI-11-asignacion-docente-segura` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-15` (RBAC Dinámico — permite rol personalizado `DOCENTE`), `PBI-09` (Cursos y Salones), `PBI-16` (Auditoría). Consumido por `PBI-10`. |
| **Permisos requeridos** | `ASIGNAR_DOCENTES` (para asignar/revocar) y `REGISTRAR_CALIFICACIONES` (en el rol del usuario asignado). |

---

## 1. Historia de Usuario
Como administrador con permiso `ASIGNAR_DOCENTES`, deseo asignar usuarios con rol habilitado para docencia (por ejemplo, un rol personalizado `DOCENTE`) a cursos y salones específicos, para garantizar que cada docente solo acceda y califique a sus propios grupos.

---

## 2. Reglas de Negocio
- **RN-01:** Asignar o revocar docentes requiere permiso `ASIGNAR_DOCENTES`.
- **RN-02 (Integración con Roles Personalizados):** El usuario asignado debe estar `ACTIVO` y su rol (personalizado o base) debe incluir el permiso `REGISTRAR_CALIFICACIONES`.
- **RN-03:** Cada asignación vincula `(usuario_docente_id, curso_id, salon_id, anio_lectivo)` evitando duplicados activos en el mismo curso-salón.
- **RN-04 (Aislamiento de ámbito — RBAC + Scope):** Un docente solo puede crear rubros, actividades y calificaciones en los `(curso_id, salon_id)` donde posee una asignación `activa = True`. Intentar operar en otro salón lanza `AccesoDenegadoException` y se audita en `PBI-16`.
- **RN-05:** Revocar una asignación o desactivar al usuario bloquea ediciones futuras sin eliminar ni alterar las calificaciones históricas que ya registró.
- **RN-06:** Toda asignación o revocación se audita en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Asignar usuario con rol personalizado `DOCENTE` al curso `Matemática` en `Secundaria 3ro A` → asignación activa y auditada.
2. Docente autorizado valida acceso en `Secundaria 3ro A` (permitido) y en `Secundaria 3ro B` (denegado).
3. Rechazar asignación de usuario `INACTIVO` o cuyo rol no posee `REGISTRAR_CALIFICACIONES`.
4. Rechazar asignación duplicada activa para el mismo `(curso, salón, año)`.
5. Revocar asignación → el docente pierde acceso a futuras ediciones conservando historial.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/docentes.py`
- Pruebas nuevas: `tests/test_docentes.py`
- Entidades: `AsignacionDocente`, `ServicioAsignacionDocente` (`asignar_docente`, `revocar_asignacion`, `validar_ambito_docente`, `listar_asignaciones_docente`).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-11-asignacion-docente-segura
# 1. RED -> tests/test_docentes.py
# 2. GREEN -> src/dominio/docentes.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
