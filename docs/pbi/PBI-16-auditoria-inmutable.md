# PBI-16: Auditoría Inmutable de Transacciones

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-16` |
| **Rama Git a crear** | `feature/PBI-16-auditoria-inmutable` *(desde `main` — **PRIMER PBI A IMPLEMENTAR**)* |
| **Estado actual en `main`** | Pendiente como módulo (solo existen DTOs locales en `asistencia.py` y `usuarios.py`). |
| **Dependencias** | Ninguna (es el servicio transversal base consumido por `PBI-01` a `PBI-17`). |
| **Permisos requeridos** | `CONSULTAR_AUDITORIA`, `VERIFICAR_INTEGRIDAD_AUDITORIA`. |

---

## 1. Historia de Usuario
Como administrador con permiso `CONSULTAR_AUDITORIA`, deseo que todas las operaciones críticas del sistema queden registradas en una bitácora inmutable y verificable criptográficamente, para garantizar trazabilidad legal y operativa sin posibilidad de manipulación posterior.

---

## 2. Reglas de Negocio
- **RN-01 / RN-02:** Todo evento tiene `id` único y registra: `fecha_hora` (servidor en `America/Lima`), `usuario_id` (o `0`/sistema), `rol_ejecutante`, `operacion`, `entidad`, `entidad_id` y `resultado` (`CONFIRMADA` o `FALLIDA`).
- **RN-03:** Actores válidos: cualquier rol activo autenticado (roles base y personalizados de `PBI-15`) + procesos automáticos `SYSTEM` y `SYSTEM_CRON`.
- **RN-04:** En eventos de asistencia incluye `metodo_asistencia`, `alumno_id`, contexto académico `(nivel, grado, seccion)` y, en correcciones, `estado_anterior`, `estado_nuevo` y `motivo`.
- **RN-05:** En eventos de usuarios/roles incluye entidad afectada y valores anteriores/nuevos.
- **RN-06 (Privacidad):** Prohibido almacenar contraseñas en texto plano, `password_hash`, `salt` o tokens de sesión completos dentro de `detalle` o `motivo` (lanzar `DatoSensibleAuditoriaException`).
- **RN-07 (Inmutabilidad — *append-only*):** Prohibido modificar o eliminar registros confirmados (`AuditoriaInmutableException`).
- **RN-08 / RN-09 (Cadena `SHA-256`):** Cada registro calcula `hash_integridad = sha256(payload_canonico + hash_anterior)` (usando `"GENESIS"` para el primero). Proveer `verificar_integridad(...)` para detectar alteraciones, reordenamientos o borrados.
- **RN-10 (Atomicidad):** Ante fallo al persistir auditoría, propagar `ErrorRegistroAuditoriaException` para que la operación de negocio ejecute rollback.
- **RN-11 / RN-12:** Consulta filtrada (rango de fechas, usuario, rol, operación, entidad, alumno, resultado) y verificación de integridad requieren `CONSULTAR_AUDITORIA` / `VERIFICAR_INTEGRIDAD_AUDITORIA`.
- **RN-13:** Retención histórica intacta aunque un usuario o alumno pase a `INACTIVO`.
- **RN-14:** Los estados de entrega de WhatsApp (`PENDIENTE`/`ENVIADO`/`ENTREGADO`/`FALLIDO`) pertenecen a `PBI-17` y no sustituyen la auditoría de `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Registrar evento de asistencia con contexto académico `(nivel, grado, seccion)` y hash encadenado desde `"GENESIS"`.
2. Registrar corrección de `AUSENTE` conservando `estado_anterior`, `estado_nuevo` y `motivo`.
3. Registrar cambio de usuario/rol personalizado con valores anteriores y nuevos.
4. Registrar cierre automático ejecutado por `SYSTEM_CRON` sin sesión humana.
5. Rechazar claves sensibles (`password`, `password_hash`, `salt`, `token`) en el detalle.
6. Lanzar `AuditoriaInmutableException` ante cualquier intento de edición o eliminación.
7. Verificar integridad de cadena válida (`integra = True`) y detectar manipulación del evento #2 (`integra = False`, reportando su ID).
8. Consultar y filtrar eventos solo con permiso `CONSULTAR_AUDITORIA`; denegar sin permiso.
9. Propagar `ErrorRegistroAuditoriaException` ante fallo del destino de persistencia.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/auditoria.py`
- Pruebas nuevas: `tests/test_auditoria.py`
- Enums/VOs: `ResultadoAuditoria`, `TipoOperacionAuditoria`, `ContextoAcademicoAuditoria`, `RegistroAuditoria`, `FiltroAuditoria`, `ResultadoVerificacionIntegridad`.
- Servicio: `ServicioAuditoria` (`registrar_evento`, `verificar_integridad`, `consultar_eventos`, `desde_evento_asistencia`, `desde_evento_usuario`, `prohibir_modificacion`, `prohibir_eliminacion`).
- **Consideración técnica:** Usar `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` para que el hash `SHA-256` sea 100% determinista entre Windows y Linux (CI).

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-16-auditoria-inmutable
# 1. RED -> tests/test_auditoria.py
# 2. GREEN -> src/dominio/auditoria.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
