# PBI-03: Dashboard de Aforo en Tiempo Real

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-03` |
| **Rama Git a crear** | `improvement/PBI-03-calendario-detalle` *(desde `main`)* |
| **Estado actual en `main`** | Cálculo de métricas y cierre base en `src/dominio/aforo.py` y `tests/test_aforo_justificaciones.py`. |
| **Dependencias** | `PBI-01`, `PBI-15` (RBAC Dinámico), `PBI-16` (Auditoría). Consumido por `PBI-17`. |
| **Permisos requeridos** | `CONSULTAR_DASHBOARD_AFORO`, `CONSULTAR_HISTORIAL_ASISTENCIA`, `CONFIGURAR_CIERRE_ASISTENCIA`, `EJECUTAR_CIERRE_ASISTENCIA`, `ADMINISTRAR_CALENDARIO_ESCOLAR`. |

---

## 1. Historia de Usuario
Como operador con permiso `CONSULTAR_DASHBOARD_AFORO`, deseo visualizar en tiempo real los indicadores globales y por salón (`nivel`, `grado`, `seccion`), consultar el detalle individual y el historial de modificaciones, y contar con un cierre diario que respete el calendario escolar.

---

## 2. Reglas de Negocio
- **RN-01:** Acceso al dashboard validado por `CONSULTAR_DASHBOARD_AFORO`; historial por `CONSULTAR_HISTORIAL_ASISTENCIA`; hora de cierre por `CONFIGURAR_CIERRE_ASISTENCIA`; cierre manual por `EJECUTAR_CIERRE_ASISTENCIA` (o automático por `SYSTEM_CRON`).
- **RN-02:** Indicadores globales y por salón: matriculados activos, presentes (`PUNTUAL`), tardanzas (`TARDANZA`), ausentes (`AUSENTE`), justificados (`JUSTIFICADO`), pendientes (`PENDIENTE` antes del cierre), porcentaje de asistencia y aforo físico (`presentes + tardanzas`).
- **RN-03:** Filtros por `nivel`, `grado`, `seccion` y `fecha` sin confundir secciones paralelas del mismo grado.
- **RN-04:** Detalle individual por salón muestra cada alumno activo con estado actual, hora efectiva y método (`CARNET`, `MANUAL_DNI`, `MANUAL_BUSQUEDA`).
- **RN-05:** **Calendario escolar (`CalendarioEscolar`):** el cierre automático no se ejecuta en días no lectivos (fines de semana/feriados), salvo que exista una excepción habilitada expresamente para esa fecha.
- **RN-06:** **Prevención de doble cierre:** si la fecha escolar ya fue cerrada, lanzar `CierreYaEjecutadoException`.
- **RN-07:** Hora de cierre por defecto: `09:00` (`America/Lima`), configurable por `ADMIN`.
- **RN-08:** El dashboard no exporta reportes directamente (la exportación formal corresponde a `PBI-13`).

---

## 3. Escenarios BDD (Gherkin)
1. **Calcular métricas globales y por salón** filtrando por `nivel`, `grado` y `seccion`.
2. **Obtener detalle individual de un salón** mostrando estado y método de registro normalizado.
3. **Consultar historial de modificaciones** con permiso `CONSULTAR_HISTORIAL_ASISTENCIA`.
4. **Ejecutar cierre diario en día lectivo** marcando ausentes y generando `EventoCierreDiario` (para `PBI-17`).
5. **Bloquear cierre en día no lectivo** (sin excepción) y **permitirlo si existe excepción habilitada**.
6. **Lanzar `CierreYaEjecutadoException`** si se intenta cerrar una fecha ya cerrada.
7. **Permitir cierre automático por `SYSTEM_CRON`** y denegar configuración/cierre manual a usuarios sin permiso.

---

## 4. Cambios a Realizar Respecto a `main`
Archivos: `src/dominio/aforo.py`, `tests/test_aforo_justificaciones.py`.
1. Crear `CalendarioEscolar` (con `dias_no_lectivos` y `excepciones_lectivas`, método `es_dia_lectivo(fecha)`).
2. Activar validación real de `CierreYaEjecutadoException` en `ejecutar_cierre_automatico`.
3. Añadir filtros opcionales `(nivel, grado, seccion)` a `calcular_metricas`.
4. Implementar `obtener_detalle_salon(...)` y `consultar_historial_modificaciones(...)`.
5. Migrar validaciones de acceso al esquema de permisos de `PBI-15` y soportar actor `SYSTEM_CRON`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b improvement/PBI-03-calendario-detalle
# 1. RED: tests de CalendarioEscolar, doble cierre, filtros, detalle individual e historial
# 2. GREEN: implementar extensiones en src/dominio/aforo.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
