# Documentación Oficial de Ingeniería y Backlog (PBI-01 al PBI-17)

**Proyecto:** Sistema de Control de Asistencia y Gestión Administrativa — Colegio Domingo Savio S.A.C.  
**Arquitectura:** Clean Architecture + DDD + TDD (`RED -> GREEN -> REFACTOR`) + Ruff + Pytest + SQLAlchemy 2.0 + Flask.

---

## 1. Decisiones de Línea Base Cerradas

| # | Tema | Acuerdo Oficial |
| :--- | :--- | :--- |
| 1 | **Estrategia de desarrollo** | **Camino A**: completar primero la capa de dominio pura (TDD) de cada PBI → rediseño integral del DER v2 + ORM + Repositorios → capa web oficial en Flask (tomando solo el diseño UX/UI de las ramas demo). |
| 2 | **Zona horaria y reloj** | `America/Lima` (UTC-5). El servidor es la única fuente oficial de fecha y hora. |
| 3 | **Hora por defecto de cierre y avisos** | `09:00` (`America/Lima`), configurable por usuarios con permiso administrativo. |
| 4 | **Turnos** | Un solo turno escolar (máximo un registro de asistencia por alumno y fecha). |
| 5 | **Permisos de `COORDINADOR`** | Puede gestionar justificaciones (`PBI-04`), además de asistencia, dashboard y notificación manual de ausencias. |
| 6 | **RBAC Dinámico (`PBI-15`)** | 3 roles base del sistema (`ADMIN`, `COORDINADOR`, `ADMIN_STAFF`) **+ creación de roles personalizados** con permisos granulares del catálogo oficial. |
| 7 | **Calificaciones (`PBI-10`)** | Libro de 3 niveles: Período flexible (Bimestre/Trimestre/Semestre) con `fecha_limite_notas` → Rubros personalizados por docente sumando 100% → Actividades evaluables (**sin estado `EXONERADO`**). |
| 8 | **Stack final** | Python 3.11+, Flask, SQLAlchemy 2.0 (PostgreSQL en producción / SQLite en memoria en tests). |

---

## 2. Catálogo Maestro de Permisos (`PermisoOperacion`)

Todos los módulos validan **permisos en el servidor**, no nombres fijos de rol. `ADMIN` posee todos los permisos y es inmutable; `COORDINADOR` y `ADMIN_STAFF` son roles base; y `ADMIN` puede crear roles personalizados (ej. `DOCENTE`, `TESORERIA`, `AUXILIAR`) combinando permisos de esta tabla:

| Módulo | Permiso | `ADMIN` | `COORDINADOR` | `ADMIN_STAFF` |
| :--- | :--- | :---: | :---: | :---: |
| **Asistencia (PBI-01)** | `REGISTRAR_ASISTENCIA` | Sí | Sí | Sí |
| | `CORREGIR_AUSENTE` | Sí | Sí | Sí |
| | `CONSULTAR_HISTORIAL_ASISTENCIA` | Sí | Sí | Sí |
| **Aforo (PBI-03)** | `CONSULTAR_DASHBOARD_AFORO` | Sí | Sí | Sí |
| | `CONFIGURAR_CIERRE_ASISTENCIA` | Sí | No | No |
| | `EJECUTAR_CIERRE_ASISTENCIA` | Sí | No | No |
| | `ADMINISTRAR_CALENDARIO_ESCOLAR` | Sí | No | No |
| **Justificaciones (PBI-04)** | `GESTIONAR_JUSTIFICACIONES` | Sí | Sí | Sí |
| | `ADMINISTRAR_PERIODOS` | Sí | No | No |
| **Usuarios y RBAC (PBI-02 / 15)** | `GESTIONAR_USUARIOS` | Sí | No | No |
| | `GESTIONAR_ROLES` | Sí | No | No |
| | `ASIGNAR_ROLES` | Sí | No | No |
| **Auditoría (PBI-16)** | `CONSULTAR_AUDITORIA` | Sí | No | No |
| | `VERIFICAR_INTEGRIDAD_AUDITORIA` | Sí | No | No |
| **WhatsApp (PBI-17)** | `NOTIFICAR_AUSENCIAS_MANUAL` | Sí | Sí | Sí |
| | `CONFIGURAR_NOTIFICACIONES_WHATSAPP` | Sí | No | No |
| **Matrícula y Carnet (PBI-05 / 06)** | `GESTIONAR_MATRICULA` | Sí | No | Sí |
| | `GESTIONAR_CARNETS` | Sí | Sí | Sí |
| **Pagos y Estados (PBI-07 / 08)** | `GESTIONAR_PAGOS` | Sí | No | No |
| | `VER_ALERTA_PAGOS` | Sí | No | Sí |
| | `GESTIONAR_ESTADOS_ACADEMICOS` | Sí | No | No |
| **Académico (PBI-09 / 10 / 11)** | `CONFIGURAR_MALLA_CURRICULAR` | Sí | No | No |
| | `ASIGNAR_DOCENTES` | Sí | No | No |
| | `REGISTRAR_CALIFICACIONES` | Sí | No | No |
| | `CONSULTAR_CALIFICACIONES` | Sí | Sí | Sí |
| **Reportes (PBI-12 / 13 / 14)** | `CONSULTAR_FICHA_ALUMNO` | Sí | Sí | Sí |
| | `EXPORTAR_ASISTENCIAS` | Sí | Sí | Sí |
| | `EMITIR_BOLETAS` | Sí | No | Sí |

---

## 3. Índice de Documentación por PBI y Orden de Ejecución

Las ramas **NO** se crean todas vacías a la vez; cada rama se crea desde `main` actualizado justo al comenzar ese PBI, siguiendo este orden de dependencias:

| Orden | Fase | PBI | Documento | Rama Git Exacta | Estado en `main` |
| :---: | :---: | :--- | :--- | :--- | :--- |
| 1 | Fase 1 | **PBI-16** | [PBI-16-auditoria-inmutable.md](pbi/PBI-16-auditoria-inmutable.md) | `feature/PBI-16-auditoria-inmutable` | Pendiente |
| 2 | Fase 1 | **PBI-15** | [PBI-15-control-acceso-rbac.md](pbi/PBI-15-control-acceso-rbac.md) | `feature/PBI-15-control-acceso-rbac` | Parcial (roles fijos) |
| 3 | Fase 2 | **PBI-04** | [PBI-04-gestion-justificaciones.md](pbi/PBI-04-gestion-justificaciones.md) | `feature/PBI-04-gestion-justificaciones` | Parcial |
| 4 | Fase 2 | **PBI-01** | [PBI-01-registro-unificado-asistencia.md](pbi/PBI-01-registro-unificado-asistencia.md) | `improvement/PBI-01-cierre-brechas` | Dominio base completo |
| 5 | Fase 2 | **PBI-02** | [PBI-02-gestion-usuarios.md](pbi/PBI-02-gestion-usuarios.md) | `improvement/PBI-02-roles-dinamicos` | Dominio base completo |
| 6 | Fase 2 | **PBI-03** | [PBI-03-dashboard-aforo.md](pbi/PBI-03-dashboard-aforo.md) | `improvement/PBI-03-calendario-detalle` | Dominio base completo |
| 7 | Fase 2 | **PBI-17** | [PBI-17-notificaciones-whatsapp.md](pbi/PBI-17-notificaciones-whatsapp.md) | `feature/PBI-17-notificaciones-whatsapp` | Pendiente |
| 8 | Fase 3 | **PBI-09** | [PBI-09-malla-curricular.md](pbi/PBI-09-malla-curricular.md) | `feature/PBI-09-malla-curricular` | Pendiente |
| 9 | Fase 3 | **PBI-08** | [PBI-08-estados-academicos-acceso.md](pbi/PBI-08-estados-academicos-acceso.md) | `feature/PBI-08-estados-academicos-acceso` | Parcial (`ACTIVO`/`INACTIVO`) |
| 10 | Fase 3 | **PBI-05** | [PBI-05-ficha-matricula-digital.md](pbi/PBI-05-ficha-matricula-digital.md) | `feature/PBI-05-ficha-matricula-digital` | Pendiente |
| 11 | Fase 3 | **PBI-06** | [PBI-06-emision-anulacion-carnet.md](pbi/PBI-06-emision-anulacion-carnet.md) | `feature/PBI-06-emision-anulacion-carnet` | Pendiente |
| 12 | Fase 3 | **PBI-07** | [PBI-07-control-pagos-alerta-silenciosa.md](pbi/PBI-07-control-pagos-alerta-silenciosa.md) | `feature/PBI-07-control-pagos-alerta-silenciosa` | Pendiente |
| 13 | Fase 4 | **PBI-11** | [PBI-11-asignacion-docente-segura.md](pbi/PBI-11-asignacion-docente-segura.md) | `feature/PBI-11-asignacion-docente-segura` | Pendiente |
| 14 | Fase 4 | **PBI-10** | [PBI-10-calificaciones-promedios.md](pbi/PBI-10-calificaciones-promedios.md) | `feature/PBI-10-calificaciones-promedios` | Pendiente |
| 15 | Fase 4 | **PBI-12** | [PBI-12-ficha-informativa-alumno.md](pbi/PBI-12-ficha-informativa-alumno.md) | `feature/PBI-12-ficha-informativa-alumno` | Pendiente |
| 16 | Fase 4 | **PBI-13** | [PBI-13-exportacion-listas-asistencia.md](pbi/PBI-13-exportacion-listas-asistencia.md) | `feature/PBI-13-exportacion-listas-asistencia` | Pendiente |
| 17 | Fase 4 | **PBI-14** | [PBI-14-emision-boletas-calificaciones.md](pbi/PBI-14-emision-boletas-calificaciones.md) | `feature/PBI-14-emision-boletas-calificaciones` | Pendiente |
| 18 | Fase 5 | **DER v2** | [DER_V2_PROPUESTO.md](DER_V2_PROPUESTO.md) | `refactor/modelo-datos-der-v2` | Pendiente |
| 19 | Fase 6 | **Web Flask** | Diseño visual de ramas `demo/interfaces-web` y `fix/mejora-ui` | `feature/web-aplicacion-oficial` | Prototipo en ramas demo |

---

## 4. Protocolo Estándar de Trabajo por Rama (TDD + CI)

Para cualquier PBI de la tabla anterior:

```bash
# 1. Actualizar main y crear la rama exacta del PBI
git checkout main
git pull origin main
git checkout -b <nombre-de-rama-del-pbi>

# 2. Fase RED: escribir tests en tests/ y confirmar fallo inicial
python -m pytest -v
git add tests/...
git commit -m "test: (RED) pruebas BDD para <PBI-XX>"

# 3. Fase GREEN: implementar dominio mínimo en src/dominio/
python -m pytest -v
git add src/...
git commit -m "feat: (GREEN) implementar logica de <PBI-XX>"

# 4. Fase REFACTOR: tipado, inmutabilidad, Ruff y 100% cobertura
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
git add .
git commit -m "refactor: (REFACTOR) tipado estricto y validacion ruff en <PBI-XX>"

# 5. Subir rama y abrir Pull Request hacia main
git push -u origin <nombre-de-rama-del-pbi>
```
