# PBI-06: Emisión y Anulación de Carnet Escolar

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-06` |
| **Rama Git a crear** | `feature/PBI-06-emision-anulacion-carnet` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (solo existe el campo `carnet_codigo` en `Alumno`). |
| **Dependencias** | `PBI-05` (Matrícula), `PBI-08` (Estados Académicos), `PBI-15` (RBAC), `PBI-16` (Auditoría). Consumido por `PBI-01`. |
| **Permisos requeridos** | `GESTIONAR_CARNETS`. |

---

## 1. Historia de Usuario
Como operador con permiso `GESTIONAR_CARNETS`, deseo emitir carnets escolares con código QR único y anular carnets extraviados o dañados, para prevenir suplantaciones durante el ingreso diario.

---

## 2. Reglas de Negocio
- **RN-01:** Requiere permiso `GESTIONAR_CARNETS`.
- **RN-02:** Solo alumnos en estado `ACTIVO` pueden recibir emisión o reposición de carnet.
- **RN-03:** Cada estudiante puede tener como máximo **un carnet `ACTIVO`** a la vez.
- **RN-04:** Al emitir un carnet de reposición, el carnet activo previo se anula automáticamente con motivo obligatorio (`EXTRAVIO`, `DANO`, `CAMBIO_DATOS`, `OTRO`).
- **RN-05:** El `codigo_qr` debe ser único y **opaco** (ej. `DSV-2026-<token_aleatorio>`), sin exponer DNI ni datos personales del menor en texto plano. Nunca se reutiliza un código anulado.
- **RN-06:** Si `PBI-01` recibe un `codigo_qr` en estado `ANULADO` o inexistente, rechaza la asistencia inmediatamente y registra intento fallido en `PBI-16`.
- **RN-07:** Toda emisión y anulación genera auditoría en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Emitir primer carnet a alumno `ACTIVO` → genera QR único en estado `ACTIVO` y audita.
2. Reemitir carnet por `EXTRAVIO` → anula el anterior automáticamente y activa el nuevo.
3. Anular carnet manualmente con motivo → pasa a `ANULADO` y deja de ser válido para `PBI-01`.
4. Rechazar emisión de carnet a alumno `SUSPENDIDO` o `RETIRADO`.
5. Denegar operación a usuarios sin permiso `GESTIONAR_CARNETS`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/carnets.py`
- Pruebas nuevas: `tests/test_carnets.py`
- Enums/Entidades: `EstadoCarnet(ACTIVO, ANULADO)`, `MotivoAnulacionCarnet`, `CarnetEscolar`.
- Servicio: `ServicioCarnets` (`emitir_carnet`, `anular_carnet`, `validar_carnet_activo`).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-06-emision-anulacion-carnet
# 1. RED -> tests/test_carnets.py
# 2. GREEN -> src/dominio/carnets.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
