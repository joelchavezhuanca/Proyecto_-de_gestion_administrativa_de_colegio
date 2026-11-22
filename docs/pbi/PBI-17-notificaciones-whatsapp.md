# PBI-17: Notificaciones a Apoderados por WhatsApp

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-17` |
| **Rama Git a crear** | `feature/PBI-17-notificaciones-whatsapp` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no existe en `main`; en `fix/mejora-ui` hay solo un prototipo síncrono parcial de demo). |
| **Dependencias** | `PBI-01` (`EventoAsistenciaConfirmada`), `PBI-03` (`EventoCierreDiario` + `CalendarioEscolar`), `PBI-05` (contactos de apoderado), `PBI-15` (RBAC), `PBI-16` (Auditoría). |
| **Permisos requeridos** | `NOTIFICAR_AUSENCIAS_MANUAL` (`ADMIN`, `COORDINADOR`, `ADMIN_STAFF` y roles personalizados autorizados) y `CONFIGURAR_NOTIFICACIONES_WHATSAPP` (administrativo). |

---

## 1. Historia de Usuario
Como institución educativa, deseo notificar a los apoderados por WhatsApp Business sobre ingresos puntuales, tardanzas y ausencias de forma asíncrona y controlada, sin retrasar el registro de asistencia.

---

## 2. Reglas de Negocio
- **RN-01:** Canal oficial: API oficial de WhatsApp Business (desacoplada mediante puerto `PuertoNotificadorWhatsApp` + adaptador simulado para tests/local).
- **RN-02 / RN-03:** Al confirmarse `PUNTUAL` o `TARDANZA` en `PBI-01`, se encola una notificación `PENDIENTE` para procesamiento **asíncrono**; el registro de asistencia (`< 200 ms`) nunca espera al proveedor.
- **RN-04 / RN-05:** Ausencias se notifican **solo después del cierre de `PBI-03`**; nunca para alumnos en estado `PENDIENTE`.
- **RN-06 / RN-07:** Hora automática de notificación de ausencias configurable con `CONFIGURAR_NOTIFICACIONES_WHATSAPP` (por defecto **`09:00`** `America/Lima`). Respeta `CalendarioEscolar` (no notifica días no lectivos salvo excepción).
- **RN-08 / RN-09:** Acción manual **`Notificar Ausencias a Apoderados`** habilitada para usuarios con `NOTIFICAR_AUSENCIAS_MANUAL` con alcance global.
- **RN-10 (Ventana de bloqueo ±5 min):** La acción manual queda bloqueada desde 5 minutos antes hasta 5 minutos después de la hora automática (`hora_programada - 5 min <= hora_actual <= hora_programada + 5 min`).
- **RN-11 / RN-12 (Reenvío controlado):** Indicador `notificacion_ausencia_enviada` por `(alumno_id, fecha_escolar)`. Si ya es `True`, exige `confirmacion_reenvio = True`; sin confirmación lanza `ConfirmacionReenvioRequeridaException`.
- **RN-13 a RN-16:** Estados `{PENDIENTE, ENVIADO, ENTREGADO, FALLIDO}`. Conserva `referencia_proveedor`, `intentos` y `clave_idempotencia` (política de hasta **3 reintentos** sin duplicados). Los fallos de envío o falta de celular válido marcan `FALLIDO` sin alterar jamás la asistencia.
- **RN-17:** Plantillas mínimas: `PUNTUAL` (alumno, fecha, hora), `TARDANZA` (alumno, fecha, hora, minutos), `AUSENCIA` (alumno, fecha, orientación para justificar).
- **RN-18:** Webhooks actualizan estado `ENVIADO` → `ENTREGADO` o `FALLIDO` conservando referencia.

---

## 3. Escenarios BDD (Gherkin)
1. Encolar notificación `PUNTUAL` y `TARDANZA` como `PENDIENTE` sin invocar síncronamente al proveedor.
2. Fallo de WhatsApp o celular ausente/inválido → marca `FALLIDO` y deja intacta la asistencia.
3. Programar notificaciones de `AUSENTE` tras cierre de `PBI-03` en día lectivo.
4. No notificar alumnos en `PENDIENTE` antes del cierre ni en días no lectivos sin excepción.
5. Ejecutar notificación manual fuera de la ventana ±5 min (permitido) y dentro de la ventana ±5 min (bloqueado con `VentanaBloqueoActivaException`).
6. Exigir `confirmacion_reenvio = True` cuando `notificacion_ausencia_enviada == True`.
7. Actualizar estado a `ENTREGADO` con `referencia_proveedor` y controlar máximo 3 reintentos con `clave_idempotencia`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/notificaciones.py`
- Pruebas nuevas: `tests/test_notificaciones_whatsapp.py`
- Enums/Puertos/VOs: `TipoNotificacion`, `EstadoNotificacion`, `ContactoApoderado`, `NotificacionWhatsApp`, `ResultadoEnvioProveedor`, `PuertoNotificadorWhatsApp(Protocol)`.
- Servicio: `ServicioNotificacionesWhatsApp`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-17-notificaciones-whatsapp
# 1. RED -> tests/test_notificaciones_whatsapp.py
# 2. GREEN -> src/dominio/notificaciones.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
