# PBI-01: Registro Unificado de Asistencia

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-01` |
| **Rama Git a crear** | `improvement/PBI-01-cierre-brechas` *(desde `main`)* |
| **Estado actual en `main`** | Dominio base implementado al 100% en `src/dominio/asistencia.py` y `tests/test_asistencia_unificada.py`. |
| **Dependencias** | `PBI-16` (Auditoría), `PBI-15` (RBAC Dinámico), `PBI-06` (Carnet), `PBI-08` (Estados), `PBI-17` (WhatsApp), `PBI-07` (Alerta Silenciosa). |
| **Permisos requeridos** | `REGISTRAR_ASISTENCIA` (registro ordinario) y `CORREGIR_AUSENTE` (corrección de ausencias). |

---

## 1. Historia de Usuario
Como operador autenticado con permiso `REGISTRAR_ASISTENCIA`, deseo registrar el ingreso de los alumnos mediante carnet (escáner USB o cámara móvil), DNI manual o búsqueda asistida, para clasificar automáticamente la puntualidad/tardanza con la hora oficial del servidor y mantener trazabilidad completa.

---

## 2. Reglas de Negocio
- **RN-01 / RN-02:** Hora regular de ingreso `07:00:00`. Tolerancia hasta `07:15:00` inclusive.
- **RN-03 / RN-04 / RN-05:** Hasta `07:15:00` → `PUNTUAL` (`0` min). Después de `07:15:00` → `TARDANZA` con `ceil((hora_ingreso - 07:15:00) / 60)`.
- **RN-06:** La hora oficial proviene siempre del servidor (`America/Lima`, UTC-5), nunca del cliente.
- **RN-07:** Confirmación en `< 200 ms`; el envío de WhatsApp (`PBI-17`) y las alertas de pago (`PBI-07`) se ejecutan de forma asíncrona/desacoplada.
- **RN-08 a RN-12:** Sesión autenticada vigente + permiso `REGISTRAR_ASISTENCIA` (soporta roles base y personalizados). Aplica tanto para escáner USB conectado a PC como cámara móvil en web.
- **RN-13 a RN-18:** Alumno existente y en estado `ACTIVO` (`PBI-08`). Carnet en estado `ACTIVO` (`PBI-06`). DNI exacto de 8 dígitos numéricos. Búsqueda asistida busca por nombres, apellidos, DNI o código y solo retorna alumnos `ACTIVO`.
- **RN-19 a RN-24:** Un solo turno (un registro por `(alumno_id, fecha_escolar)`). Si ya existe `PUNTUAL`, `TARDANZA` o `JUSTIFICADO`, se rechaza el duplicado. Si existe `AUSENTE`, se permite corregir con permiso `CORREGIR_AUSENTE` y motivo obligatorio conservando el historial.
- **RN-25 a RN-29:** Cada registro conserva `nivel`, `grado` y `seccion` (snapshot académico del día), método normalizado (`CARNET`, `MANUAL_DNI`, `MANUAL_BUSQUEDA`), usuario/rol y auditoría atómica (`PBI-16`). Si falla la auditoría, se revierte el registro.
- **RN-30 (PBI-07):** Deudas vencidas nunca bloquean el registro de asistencia.

---

## 3. Escenarios BDD (Gherkin)
1. **Puntual por carnet (`07:10:00` y `07:15:00`):** crea `PUNTUAL`, `0` min, método `CARNET`, snapshot académico y auditoría.
2. **Tardanza por carnet (`07:15:01` → 1 min; `07:16:01` → 2 min):** aplica fórmula `ceil`.
3. **Rol personalizado autorizado:** un usuario con rol personalizado que incluye `REGISTRAR_ASISTENCIA` puede registrar asistencia; sin ese permiso se lanza `RolNoAutorizadoException`.
4. **Manual por DNI válido / inválido:** rechaza DNI distinto de 8 dígitos o sin coincidencia.
5. **Búsqueda asistida:** devuelve únicamente alumnos `ACTIVO`.
6. **Rechazo de alumno inactivo / suspendido / retirado o carnet anulado.**
7. **Corregir `AUSENTE`:** exige permiso `CORREGIR_AUSENTE` y motivo no vacío; conserva `estado_anterior = AUSENTE`.
8. **Rechazo de duplicado (`PUNTUAL`, `TARDANZA`) y protección de `JUSTIFICADO`.**
9. **Atomicidad con auditoría (`PBI-16`):** si el callback/registro de auditoría falla, lanza `ErrorRegistroAuditoriaException` y no confirma.
10. **Rendimiento `< 200 ms`.**

---

## 4. Cambios a Realizar Respecto a `main`
Archivos: `src/dominio/asistencia.py`, `tests/test_asistencia_unificada.py`.
1. Agregar campos snapshot `nivel: str | None = None`, `grado: str | None = None`, `seccion: str | None = None` a `RegistroAsistencia` (poblados desde `alumno`).
2. Evolucionar `validar_operador` para validar por permiso (`REGISTRAR_ASISTENCIA` / `CORREGIR_AUSENTE`) soportando roles personalizados de `PBI-15`, manteniendo retrocompatibilidad con `UsuarioOperador` actual.
3. Conectar contrato opcional de auditoría atómica con `ServicioAuditoria` (`PBI-16`).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b improvement/PBI-01-cierre-brechas
# 1. RED: añadir tests de snapshot académico, rol personalizado y fallo atómico de auditoría
# 2. GREEN: actualizar src/dominio/asistencia.py sin romper los tests previos
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
