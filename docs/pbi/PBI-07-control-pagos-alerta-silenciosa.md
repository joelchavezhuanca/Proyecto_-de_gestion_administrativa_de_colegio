# PBI-07: Control de Pagos e Ingreso (Alerta Silenciosa)

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-07` |
| **Rama Git a crear** | `feature/PBI-07-control-pagos-alerta-silenciosa` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-01` (consume `EventoAsistenciaConfirmada`), `PBI-05` (Matrícula), `PBI-15` (RBAC), `PBI-16` (Auditoría). |
| **Permisos requeridos** | `GESTIONAR_PAGOS` (registrar obligaciones/pagos/exoneraciones) y `VER_ALERTA_PAGOS` (consultar alertas silenciosas). |

---

## 1. Historia de Usuario
Como personal autorizado con permisos de pagos, deseo administrar el estado de pensiones y recibir una alerta silenciosa interna cuando un alumno con deuda vencida registra su asistencia, sin bloquear ni incomodar nunca su ingreso físico.

---

## 2. Reglas de Negocio
- **RN-01:** Registrar obligaciones, pagos y exoneraciones requiere `GESTIONAR_PAGOS`; consultar alertas silenciosas requiere `VER_ALERTA_PAGOS`.
- **RN-02 (No bloqueo absoluto):** Una deuda vencida **jamás** bloquea el registro de asistencia (`PBI-01`) ni el ingreso físico del estudiante, ni muestra mensajes visibles al público en la pantalla de escaneo.
- **RN-03:** Cada obligación contiene: `alumno_id`, `concepto`, `monto` (`Decimal > 0`), `fecha_vencimiento`, `estado` (`PENDIENTE`, `PAGADO`, `VENCIDO`, `EXONERADO`).
- **RN-04:** Al recibirse `EventoAsistenciaConfirmada` de `PBI-01`, si el alumno tiene al menos una obligación vencida (`estado == VENCIDO` o `estado == PENDIENTE` con `fecha_vencimiento < fecha_escolar`), se genera una `AlertaSilenciosaPago` visible solo para usuarios con `VER_ALERTA_PAGOS`.
- **RN-05:** Máximo una alerta silenciosa por `(alumno_id, fecha_escolar)`.
- **RN-06:** Si el alumno regulariza sus pagos vencidos o cuenta con exoneración, no se generan nuevas alertas en jornadas posteriores.
- **RN-07:** Todos los pagos y exoneraciones se auditan en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Alumno con pensión vencida registra asistencia → asistencia confirmada normalmente y se genera alerta silenciosa interna.
2. Alumno al día o exonerado registra asistencia → no se genera ninguna alerta.
3. Usuario sin `VER_ALERTA_PAGOS` intenta consultar alertas → acceso denegado.
4. Registrar pago de obligación vencida → pasa a `PAGADO` y deja de generar alertas.
5. Evitar duplicar alerta silenciosa para el mismo alumno en la misma fecha.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/pagos.py`
- Pruebas nuevas: `tests/test_pagos.py`
- Entidades: `EstadoObligacion`, `ObligacionPago`, `AlertaSilenciosaPago`.
- Servicio: `ServicioPagos` (`registrar_obligacion`, `registrar_pago`, `exonerar_obligacion`, `evaluar_alerta_silenciosa`, `consultar_alertas`).
- **Consideración técnica:** Usar `Decimal` para montos y desacoplar completamente de `PBI-01` por eventos; un fallo en `PBI-07` nunca debe propagarse al registro de asistencia.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-07-control-pagos-alerta-silenciosa
# 1. RED -> tests/test_pagos.py
# 2. GREEN -> src/dominio/pagos.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
