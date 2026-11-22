# Propuesta de Rediseño de Base de Datos — DER v2 (Fase 5)

**Rama Git prevista:** `refactor/modelo-datos-der-v2`  
**Cuándo se ejecuta:** Al concluir el dominio puro TDD de los PBIs (Camino A), antes de implementar repositorios y la capa web Flask.  
**Compatibilidad:** SQLAlchemy 2.0 + Alembic (PostgreSQL en producción / SQLite en memoria en tests).

---

## 1. Motivo del Rediseño

El DER inicial de 4 tablas (`usuarios`, `estudiantes`, `asistencias`, `justificaciones`) fue útil en el Sprint 1, pero no cubre:
- Roles personalizados (`roles`, `permisos`, `rol_permisos`) ni sesiones en servidor (`sesiones_usuario`).
- `salt` y `nombre_completo` en `usuarios`.
- `UNIQUE (estudiante_id, fecha_escolar)` y snapshot académico `(nivel, grado, seccion)` en `asistencias`.
- Tablas faltantes para `PBI-03`, `PBI-04`, `PBI-05` a `PBI-14`, `PBI-16` y `PBI-17`.

---

## 2. Bloques del Esquema Relacional (DER v2)

### Bloque 1 — Seguridad, RBAC Dinámico y Auditoría (`PBI-02`, `PBI-15`, `PBI-16`)
- `roles`: `(id PK, codigo UK, nombre, descripcion, es_sistema, activo, creado_en)`
- `permisos`: `(codigo PK, modulo, descripcion)`
- `rol_permisos`: `(rol_id PK/FK, permiso_codigo PK/FK)`
- `usuarios`: `(id PK, username UK, nombre_completo, password_hash, salt, rol_id FK, estado, creado_en, actualizado_en)`
- `sesiones_usuario`: `(token PK, usuario_id FK, rol_codigo_snapshot, fecha_inicio, fecha_expiracion, activa, revocada_en)`
- `auditoria_eventos`: `(id PK, fecha_hora, usuario_id, rol_ejecutante, operacion, entidad, entidad_id, metodo_asistencia, alumno_id, contexto_academico, estado_anterior, estado_nuevo, motivo, resultado, detalle_json, hash_anterior, hash_integridad)` — **append-only sin cascadas de borrado**.

### Bloque 2 — Estructura Académica, Alumnos y Carnets (`PBI-05`, `PBI-06`, `PBI-08`, `PBI-09`, `PBI-11`)
- `salones`: `(id PK, anio_lectivo, nivel, grado, seccion, capacidad_maxima, activo)` — `UNIQUE(anio_lectivo, nivel, grado, seccion)`
- `cursos`: `(id PK, anio_lectivo, nivel, grado, codigo, nombre, area_curricular, horas_semanales, activo)`
- `asignaciones_docentes`: `(id PK, usuario_docente_id FK, curso_id FK, salon_id FK, anio_lectivo, activa, creado_en)`
- `estudiantes`: `(id PK, codigo UK, dni UK, nombres, apellidos, fecha_nacimiento, salon_id FK, estado, creado_en)`
- `estudiante_estados_historial`: `(id PK, estudiante_id FK, estado_anterior, estado_nuevo, motivo, fecha_inicio, fecha_fin, usuario_id FK, creado_en)`
- `apoderados`: `(id PK, nombres, apellidos, documento, parentesco, telefono_whatsapp, activo)`
- `estudiante_apoderado`: `(estudiante_id PK/FK, apoderado_id PK/FK, es_principal)`
- `carnets`: `(id PK, estudiante_id FK, codigo_qr UK, estado, motivo_anulacion, emitido_por FK, emitido_en, anulado_en)`

### Bloque 3 — Asistencia, Aforo y Justificaciones (`PBI-01`, `PBI-03`, `PBI-04`)
- `asistencias`: `(id PK, estudiante_id FK, usuario_id FK, fecha_escolar, hora_efectiva, estado, minutos_tardanza, metodo, nivel_snapshot, grado_snapshot, seccion_snapshot, notificacion_ausencia_enviada, auditoria_id, creado_en)` — `UNIQUE(estudiante_id, fecha_escolar)`
- `asistencia_historial`: `(id PK, asistencia_id FK, usuario_id FK, rol_usuario, estado_anterior, estado_nuevo, motivo, metodo, auditoria_id, fecha_hora)`
- `periodos_academicos`: `(id PK, anio_lectivo, tipo_periodo, orden, nombre UK, fecha_inicio, fecha_fin, fecha_limite_notas, cerrado, creado_en)`
- `justificaciones`: `(id PK, asistencia_id FK, estudiante_id FK, periodo_id FK, usuario_id FK, fecha_solicitud, categoria, motivo, estado, minutos_tardanza_original, fecha_resolucion, creado_en)`
- `justificacion_adjuntos`: `(id PK, justificacion_id FK, nombre_archivo, extension, tamano_bytes, ruta_almacenamiento, subido_en)`
- `calendario_escolar`: `(fecha PK, es_lectivo, es_excepcion, descripcion)`
- `configuracion_sistema`: `(clave PK, valor, actualizado_por FK, actualizado_en)`
- `cierres_diarios`: `(id PK, evento_id UK, fecha_escolar UK, hora_cierre, total_ausentes_marcados, actor_ejecutante, usuario_id FK, creado_en)`

### Bloque 4 — Notificaciones y Pagos (`PBI-07`, `PBI-17`)
- `notificaciones_whatsapp`: `(id PK, clave_idempotencia UK, asistencia_id FK, estudiante_id FK, fecha_escolar, apoderado_nombre, telefono_destino, tipo, plantilla, contenido, estado, intentos, referencia_proveedor, detalle_error, creado_en, actualizado_en)`
- `obligaciones_pago`: `(id PK, estudiante_id FK, concepto, monto, fecha_vencimiento, estado, pagado_en, creado_en)`
- `alertas_pago_silenciosas`: `(id PK, estudiante_id FK, asistencia_id FK, fecha_escolar, monto_vencido_total, revisada, creado_en)` — `UNIQUE(estudiante_id, fecha_escolar)`

### Bloque 5 — Calificaciones de 3 Niveles y Boletas (`PBI-10`, `PBI-14`)
- `rubros_evaluacion`: `(id PK, asignacion_docente_id FK, periodo_id FK, nombre, peso_porcentaje, activo, creado_en)`
- `actividades_evaluables`: `(id PK, rubro_id FK, titulo, fecha, activo, creado_en)`
- `calificaciones`: `(id PK, actividad_id FK, estudiante_id FK, nota, observacion, usuario_id FK, actualizado_en)` — `UNIQUE(actividad_id, estudiante_id)`
- `boletas_emitidas`: `(id PK, codigo_verificacion UK, estudiante_id FK, periodo_id FK, anio_lectivo, es_oficial, promedio_general, resumen_asistencia_json, emitido_por FK, emitido_en)`
