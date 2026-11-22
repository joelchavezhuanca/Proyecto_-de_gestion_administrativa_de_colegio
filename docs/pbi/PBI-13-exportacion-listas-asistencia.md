# PBI-13: Exportación de Listas de Asistencia

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-13` |
| **Rama Git a crear** | `feature/PBI-13-exportacion-listas-asistencia` *(desde `main`)* |
| **Estado actual en `main`** | Pendiente (no implementado). |
| **Dependencias** | `PBI-01` (Asistencias), `PBI-15` (RBAC), `PBI-16` (Auditoría). Independiente de `PBI-03` (el dashboard mantiene su regla de no exportación). |
| **Permisos requeridos** | `EXPORTAR_ASISTENCIAS`. |

---

## 1. Historia de Usuario
Como operador con permiso `EXPORTAR_ASISTENCIAS`, deseo exportar listados filtrados de asistencia en formatos `CSV`, `XLSX` o `PDF`, para reportes institucionales y auditorías.

---

## 2. Reglas de Negocio
- **RN-01:** Requiere permiso `EXPORTAR_ASISTENCIAS`.
- **RN-02:** Filtros: rango obligatorio de fechas (`fecha_desde <= fecha_hasta`, rango máximo `366` días), `nivel`, `grado`, `seccion`, `estado` y `alumno_id`.
- **RN-03:** Formatos soportados: `CSV` (UTF-8 con BOM `utf-8-sig` para Excel en Windows), `XLSX` y `PDF`.
- **RN-04:** Columnas mínimas: código alumno, DNI, apellidos y nombres, nivel, grado, sección (snapshot), fecha escolar, hora efectiva, estado, minutos de tardanza, método de registro y usuario responsable.
- **RN-05 (Seguridad — Formula Injection):** Sanitizar cualquier celda de texto que empiece por `=`, `+`, `-` o `@` al exportar a `CSV`/`XLSX` para prevenir inyección de fórmulas en Excel.
- **RN-06:** Toda exportación genera metadatos (usuario, fecha/hora servidor `America/Lima`, filtros aplicados, total de filas) y auditoría en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. Exportar asistencias de `Primaria - 3ro - A` en rango válido a `CSV`/`XLSX` → genera filas normalizadas con metadatos y auditoría.
2. Rechazar rango inválido (`fecha_desde > fecha_hasta` o rango `> 366` días).
3. Sanitizar textos que inicien con `=SUM(...)` o `+cmd` en exportación tabular.
4. Denegar exportación a usuario sin permiso `EXPORTAR_ASISTENCIAS`.

---

## 4. Diseño de Dominio Propuesto
- Archivo nuevo: `src/dominio/exportacion_asistencia.py` (preparación/validación/sanitización pura; los renderizadores binarios `openpyxl`/`PDF` van en `src/infraestructura/exportadores.py` en la Fase 5).
- Pruebas nuevas: `tests/test_exportacion_asistencia.py`.
- Entidades: `FormatoExportacion(CSV, XLSX, PDF)`, `FiltroExportacionAsistencia`, `FilaExportacionAsistencia`, `DocumentoExportacionAsistencia`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-13-exportacion-listas-asistencia
# 1. RED -> tests/test_exportacion_asistencia.py
# 2. GREEN -> src/dominio/exportacion_asistencia.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
