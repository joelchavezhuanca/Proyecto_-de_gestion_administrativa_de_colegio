# INFORME DE PROYECTO DE SOFTWARE POR COMPETENCIAS

**Universidad Continental · Facultad de Ingeniería de Sistemas e Informática**  
**Asignatura:** Construcción de Software · **Docente:** Mg. Ing. David H. Carrillo Yépez · **Cusco, Perú — 2026**  
**Sistema de Control de Asistencia y Gestión Administrativa — Colegio Domingo Savio S.A.C.**  
**Versión:** v1.0 — Cierre Final / Sprint 3 · **Fecha de actualización:** 27/11/2026

> **Nota de veracidad y trazabilidad:** Todas las métricas técnicas, Pull Requests (#1–#53), commits TDD/ATDD, corridas de GitHub Actions, cobertura por capa y URL de producción de este informe han sido auditados directamente contra el repositorio oficial (`main` en commit `4927c42` y despliegue verificado en Render.com). Únicamente los pocos datos administrativos externos al código (correos institucionales de 2 integrantes, URL del tablero GitHub Projects/Story Points si existen fuera del código, constancia firmada del stakeholder y exportación visual de wireframes PNG) permanecen señalados como `[PENDIENTE ...]` para completarse sin inventar información.

---

## Carátula y datos generales

| Campo | Detalle |
|---|---|
| **Título del proyecto** | Sistema de Control de Asistencia y Gestión Administrativa — Colegio Domingo Savio S.A.C. |
| **Empresa / entidad aliada** | Colegio Domingo Savio S.A.C. (Institución Educativa Privada — EBR) |
| **Número de grupo** | Grupo 5 — "Conti2000" |
| **Repositorio GitHub** | https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio |
| **URL en Producción (HTTPS)** | https://proyecto-de-gestion-administrativa-de.onrender.com (Healthcheck: `/health`) |
| **Tablero del proyecto (GitHub Projects)** | `[PENDIENTE: insertar URL exacta del tablero GitHub Projects]` |
| **Versión del informe / sprint** | v1.0 — Cierre Final / Sprint 3 |
| **Fecha de última actualización** | 27/11/2026 |

### Equipo y roles

| Rol Scrum / técnico | Responsabilidad principal | Integrante | GitHub ID | Correo |
|---|---|---|---|---|
| **Product Owner / Scrum Master** | Backlog, tablero, ceremonias, revisión de PRs y merges a `main`; integración Ola 0; PBIs 02, 06, 12, 13 y BP Seguridad | Gari Joel Chávez Huanca | `joelchavezhuanca` | `75082495@continental.edu.pe` |
| **Lead Backend Engineer** | Lógica de dominio con TDD y ATDD ★ (PBI-01, PBI-10, PBI-14, PBI-17 y BP Asistencia) | Yhovana Quispe Ccolqquere | `78970249-sys` | `78970249@continental.edu.pe` |
| **Database & ORM Specialist** | Modelo de datos (DER v2), SQLAlchemy 2.0, fixtures, repositorios núcleo, semilla demo; PBIs 03, 05 y BP Alumnos | Eduardo Luna Lezano | `72945734-sys` | `72945734@continental.edu.pe` |
| **Frontend & UX/UI Engineer** | Wireframes, base UX/UI Flask, escáner QR, clon limpio; PBIs 09, 11, repositorios académicos y BP Académico | Dudu Fabiano Lizarzaburu Flores | `Dudu123-cell` | `[PENDIENTE: confirmar correo @continental.edu.pe]` |
| **DevOps & QA Engineer** | CI/CD (GitHub Actions), Ruff, Pytest/cobertura, Docker, DoD, adaptadores infra, capa aplicación y BP Reportes + E2E; PBIs 07, 08 | Jacob Luna Basilio | `71269297-source` | `[PENDIENTE: confirmar correo @continental.edu.pe]` |

---

## Cap. 1 — Diseño del proyecto (criterio 11.1)

### 1.1 Entidad aliada

| Campo | Detalle |
|---|---|
| **Razón social** | Colegio Domingo Savio S.A.C. |
| **Rubro o sector** | Educación Básica Regular Privada — Niveles Primaria (1.º a 6.º) y Secundaria (1.º a 5.º), secciones múltiples (A, B, C...) |
| **Stakeholder principal (nombre y cargo)** | Gari Joel Chávez Huanca — Centro de Cómputo |
| **Ubicación** | Cusco, Perú |
| **Medio de contacto y fecha de entrevista inicial** | Entrevista presencial / coordinación directa — 31/10/2026 |

### 1.2 Problema operacional y necesidades

La gestión diaria del Colegio Domingo Savio S.A.C. dependía de procesos manuales y fragmentados: toma de lista en aula (consumiendo **10 a 15 minutos diarios** de clase por salón), control visual en portería durante horas pico (07:00–07:15) vulnerable a suplantación de carnets extraviados, cálculo manual propenso a errores de tardanzas y consolidación dispersa de justificaciones, matrícula, pensiones, calificaciones y boletas. Para la demostración en producción se modeló la escala institucional estimada de **11 salones (220 alumnos, 20 por aula, 33 cursos)** acorde a los niveles Primaria 1.º–6.º y Secundaria 1.º–5.º.

| N.º | Necesidad identificada | Evidencia de origen | PBI que la atiende |
|---|---|---|---|
| **N1** | Registrar el ingreso diario en < 200 ms por carnet QR (escáner USB o cámara web), DNI manual o búsqueda asistida con reloj oficial del servidor (`America/Lima`). | `README.md`; `docs/pbi/PBI-01-registro-unificado-asistencia.md` | PBI-01 ★ |
| **N2** | Administrar cuentas del personal (`PBKDF2-HMAC-SHA256`) y control de acceso granular con 28 permisos y roles base/personalizados validados en servidor. | `docs/README.md`; `docs/pbi/PBI-02-gestion-usuarios.md`; `PBI-15` | PBI-02, PBI-15 |
| **N3** | Visualizar en tiempo real el aforo físico y métricas globales y por salón, con detalle individual y cierre diario automático respetando el calendario escolar. | `docs/pbi/PBI-03-dashboard-aforo.md` | PBI-03 |
| **N4** | Gestionar justificaciones de ausencias/tardanzas (con adjuntos validados ≤ 5 MB, máx. 3 y reversión) solo dentro de períodos abiertos con fecha límite de notas. | `docs/pbi/PBI-04-gestion-justificaciones.md` | PBI-04 |
| **N5** | Centralizar el padrón de matrícula digital (apoderados con WhatsApp y control de vacantes), carnets QR opacos anulables y estados académicos con efecto en acceso. | `docs/pbi/PBI-05`, `PBI-06`, `PBI-08` | PBI-05, PBI-06, PBI-08 |
| **N6** | Controlar pensiones vencidas generando alertas silenciosas internas al ingreso **sin bloquear ni exponer** al estudiante en portería. | `docs/pbi/PBI-07-control-pagos-alerta-silenciosa.md` | PBI-07 |
| **N7** | Estandarizar malla curricular (Primaria 1.º–6.º, Secundaria 1.º–5.º), aislar el ámbito docente por salón-curso y calcular notas en libro de 3 niveles con precisión `Decimal`. | `docs/pbi/PBI-09`, `PBI-10`, `PBI-11` | PBI-09, PBI-10 ★, PBI-11 |
| **N8** | Consolidar ficha informativa del alumno (con segregación financiera), exportar asistencias (CSV/XLSX/PDF sanitizados) y emitir boletas preliminares/oficiales. | `docs/pbi/PBI-12`, `PBI-13`, `PBI-14` | PBI-12, PBI-13, PBI-14 |
| **N9** | Garantizar trazabilidad legal inmutable en bitácora append-only encadenada criptográficamente con **SHA-256**. | `docs/pbi/PBI-16-auditoria-inmutable.md` | PBI-16 |
| **N10** | Notificar a apoderados por WhatsApp Business de forma asíncrona, idempotente y con ventana de bloqueo manual (±5 min). | `docs/pbi/PBI-17-notificaciones-whatsapp.md` | PBI-17 |

### 1.3 Objetivos del sistema

- **Objetivo general:** Diseñar, construir, verificar y desplegar en producción un sistema web integral de control de asistencia y gestión administrativa-académica para el Colegio Domingo Savio S.A.C. bajo Clean Architecture, DDD, TDD y ATDD, que automatice el ingreso diario (< 200 ms), elimine 10–15 min/día de lista manual y asegure trazabilidad inmutable y seguridad RBAC.
- **Objetivos específicos:**
  1. **Seguridad, RBAC y Auditoría (PBI-02, PBI-15, PBI-16):** hashing `PBKDF2-HMAC-SHA256`, 28 permisos en servidor (`deny-by-default`), sesiones revocables y bitácora SHA-256.
  2. **Asistencia, Aforo, Justificaciones y Notificaciones (PBI-01 ★, PBI-03, PBI-04, PBI-17):** registro QR/cámara web/DNI/búsqueda, cálculo `ceil` de tardanzas, aforo en vivo, cierre diario con calendario escolar y notificaciones asíncronas desacopladas.
  3. **Alumnos, Carnets, Pagos y Estados (PBI-05, PBI-06, PBI-07, PBI-08):** matrícula con vacantes y apoderados, carnets QR opacos anulables, alertas silenciosas de morosidad y máquina de estados académicos.
  4. **Módulo Académico (PBI-09, PBI-10 ★, PBI-11):** malla Primaria/Secundaria, aislamiento de ámbito docente y libro de notas de 3 niveles con `Decimal` (`ROUND_HALF_UP`).
  5. **Reportes, Persistencia DER v2, Web Flask y Despliegue (PBI-12, PBI-13, PBI-14):** 27 tablas ORM SQLAlchemy 2.0, 5 Blueprints Flask, Docker Compose y despliegue HTTPS en Render.com + PostgreSQL.
  6. **Calidad y Verificación Continua:** CI/CD en verde en GitHub Actions (`ci.yml`, `docker-ci.yml`, `deploy-render.yml`), Ruff sin errores, ATDD automatizado en 2 flujos críticos ★ y cobertura ≥ 70 % (**alcanzado: 97.60 %**).

### 1.4 Alcance

| Dentro del alcance (Entregado en v1.0) | Fuera del alcance (y justificación) |
|---|---|
| • 17/17 PBIs completos en dominio puro bajo TDD (100 % cobertura).<br>• Persistencia DER v2 completa (27 tablas en 5 bloques, SQLAlchemy 2.0, Unit of Work atómico).<br>• Aplicación web Flask con 5 Blueprints, navegación dinámica por permisos RBAC, CSRF y **escáner QR con cámara web** (`html5-qrcode.min.js`).<br>• Integración desacoplada de WhatsApp (`PuertoNotificadorWhatsApp`, worker asíncrono y `NotificadorSimulado`).<br>• Exportaciones sanitizadas anti *Formula Injection* (CSV UTF-8-SIG, XLSX, PDF) y boletas verificables.<br>• Pruebas ATDD (`pytest-bdd`) para PBI-01 ★ y PBI-10 ★.<br>• Contenerización completa (`Dockerfile`, `docker-compose.yml` con `app` y perfil `pruebas`, `docker-ci.yml`) y **despliegue real en producción HTTPS en Render.com + PostgreSQL** con semilla opcional realista (`SEMBRAR_DATOS_DEMO`). | • Múltiples turnos escolares (acuerdo de línea base: un solo turno diario).<br>• Aplicaciones móviles nativas Android/iOS (resuelto mediante web responsiva HTTPS con cámara QR en navegador).<br>• Pasarela de pagos bancaria en línea / facturación SUNAT (PBI-07 cubre control administrativo y alertas silenciosas).<br>• Estado `EXONERADO` en calificaciones (regla institucional cerrada en `docs/README.md`).<br>• Merge directo de ramas prototipo `demo/*` o `fix/mejora-ui` (solo se portó quirúrgicamente la UI de asistencia QR en PR #52). |

### 1.5 Sostenibilidad del proyecto

- **Social:** Beneficia al personal administrativo, coordinadores, auxiliares, docentes, estudiantes y apoderados; libera 10–15 minutos diarios por aula, agiliza portería, protege la dignidad del estudiante con alertas silenciosas de pago (sin exponer deudas en puerta) y ofrece transparencia académica.
- **Económica:** Construido 100 % con software open-source sin costos de licencia (Python, Flask, SQLAlchemy, PostgreSQL, Docker, Ruff, Pytest). En producción se ejecuta en plan gratuito de Render.com (S/ 0) y puede migrar sin cambios a un VPS o servidor local del colegio.
- **Ambiental:** Elimina papel e impresiones recurrentes al digitalizar partes diarios, fichas de matrícula, justificaciones con adjuntos digitales, libros de notas y boletas/reportes exportables.
- **Técnica:** Clean Architecture con tipado estricto, 1,159 pruebas automatizadas, 97.60 % de cobertura, Docker reproducible (`docker compose up -d --build`), CI/CD automatizado y documentación completa (`README.md`, `docs/README.md`, `docs/pbi/`).

### 1.6 Tablero de la visión del producto (Product Vision Board)

| Visión | Grupo objetivo | Necesidades | Producto | Valor para el negocio | Métricas de éxito |
|---|---|---|---|---|---|
| Ser la plataforma web oficial e integrada del Colegio Domingo Savio S.A.C. que asegure un control de asistencia ágil y confiable, transparencia con las familias y gestión administrativa-académica trazable y sin papel. | Personal administrativo (`ADMIN`/`ADMIN_STAFF`), coordinadores (`COORDINADOR`), auxiliares (`AUXILIAR`), docentes (`DOCENTE`), tesorería y apoderados. | Eliminar 10–15 min/día de lista manual, evitar suplantación de carnets, ver aforo en vivo, auditar cambios, gestionar matrícula, pagos sin bloqueo y notas 3N. | Plataforma web Python/Flask + SQLAlchemy 2.0 + Docker + PostgreSQL con 17 PBIs, escáner QR en navegador, RBAC 28 permisos y auditoría SHA-256. | Ahorro de tiempo lectivo/operativo, trazabilidad legal inmutable, cero costo de licencias y arquitectura mantenible. | Ingreso < 200 ms (verificado); cobertura ≥ 70 % (**97.60 % alcanzada**); 17/17 PBIs terminados; CI y Docker CI en verde; app HTTPS en vivo. |

**Evidencia:** [`docs/vision-board.md`](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/blob/main/docs/vision-board.md) · PR #49 (`ae46bfe`).

---

## Cap. 2 — Planificación de la gestión (criterio 11.2)

### 2.1 Product Backlog (PBI-01 al PBI-17 — 100 % Terminado)

**Flujos críticos seleccionados (★):** **PBI-01 ★** (Registro Unificado de Asistencia) y **PBI-10 ★** (Cálculo de Calificaciones y Promedios en Libro de 3 Niveles), ambos automatizados con `pytest-bdd` en `tests/acceptance/features/`.

| ID | Historia de usuario (resumen) | Criterios Gherkin (resumen) | Prioridad | Puntos | Sprint | Responsable | Rama / PR | Wireframe | Issue | Estado |
|---|---|---|---|---|---|---|---|---|---|---|
| **PBI-01 ★** | Registro unificado por carnet QR, DNI o búsqueda con hora servidor y auditoría. | Dado alumno ACTIVO y operador autorizado, Cuando ingresa ≤07:15:00 → PUNTUAL (0 min) <200 ms; >07:15:00 → TARDANZA `ceil` + snapshot + SHA-256. | Alta | `[PENDIENTE]` | S1/S2/S3 | Yhovana (`78970249-sys`) | PR #2, #10, #20, #43, #49, #52 | Boceto en `fix/mejora-ui` `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-02** | CRUD de usuarios, PBKDF2-SHA256, baja lógica y roles activos. | Dado ADMIN con `GESTIONAR_USUARIOS`, Cuando modifica/desactiva → bloquea último ADMIN y revoca sesiones. | Alta | `[PENDIENTE]` | S1/S2 | Gari Joel (`joelchavezhuanca`) | PR #11, #23, #42 | Boceto en `fix/mejora-ui` `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-03** | Dashboard de aforo global/por salón, calendario escolar y cierre diario. | Dado día lectivo y cierre 09:00, Cuando se consulta o cierra (`ADMIN`/`SYSTEM_CRON`) → métricas exactas sin doble cierre. | Alta | `[PENDIENTE]` | S1/S2 | Eduardo (`72945734-sys`) | PR #12, #19, #43 | Boceto en `fix/mejora-ui` `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-04** | Justificaciones con adjuntos validados, reversión y períodos flexibles. | Dado período abierto y AUSENTE/TARDANZA, Cuando se justifica (≤5 MB, máx. 3) → JUSTIFICADO atómico y reversible. | Alta | `[PENDIENTE]` | S2 (Ola 0) | Gari Joel (`joelchavezhuanca`) | PR #18, #43 | Boceto en `fix/mejora-ui` `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-05** | Matrícula digital con apoderados WhatsApp, DNI único y vacantes. | Dado salón con vacantes y apoderado principal `+519...`, Cuando se matricula → ficha ACTIVO sin alterar snapshots al trasladar. | Alta | `[PENDIENTE]` | S2 (Ola 2) | Eduardo (`72945734-sys`) | PR #25, #45 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-06** | Emisión/reposición y anulación de carnets con QR opaco único. | Dado alumno ACTIVO, Cuando se emite/repone → QR `DSV-YYYY-TOKEN` único, anula previo y PBI-01 rechaza QR anulado. | Media | `[PENDIENTE]` | S2 (Ola 2) | Gari Joel (`joelchavezhuanca`) | PR #28, #45 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-07** | Control de obligaciones de pago y alerta silenciosa no bloqueante. | Dado alumno con deuda VENCIDA, Cuando registra ingreso → confirma sin bloqueo y crea máx. 1 alerta silenciosa/día. | Media | `[PENDIENTE]` | S2 (Ola 2) | Jacob (`71269297-source`) | PR #27, #45 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-08** | Máquina de estados académicos (`ACTIVO`, `SUSPENDIDO`, `RETIRADO`, `TRASLADADO`, `EGRESADO`). | Dado transición válida con motivo, Cuando cambia estado → actualiza historial, bloquea acceso no-ACTIVO y anula carnet en bajas. | Alta | `[PENDIENTE]` | S2 (Ola 1) | Jacob (`71269297-source`) | PR #22, #45 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-09** | Malla curricular (Primaria 1.º–6.º, Secundaria 1.º–5.º, salones y cursos). | Dado operador autorizado, Cuando crea salones/cursos → unicidad por año/nivel/grado y prohíbe borrado físico en uso. | Alta | `[PENDIENTE]` | S2 (Ola 1) | Dudu (`Dudu123-cell`) | PR #21, #46 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-10 ★** | Libro de calificaciones de 3 niveles y promedios `Decimal` (`AD/A/B/C`). | Dado docente asignado y fecha ≤ límite, Cuando define rubros=100 % y notas `[0, 20]` → promedios exactos `ROUND_HALF_UP`. | Alta | `[PENDIENTE]` | S3 (Ola 3A) | Yhovana (`78970249-sys`) | PR #32, #46, #49 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-11** | Asignación docente segura a curso-salón con aislamiento de ámbito. | Dado usuario ACTIVO con `REGISTRAR_CALIFICACIONES`, Cuando se asigna → solo califica ese ámbito (403 en otros). | Alta | `[PENDIENTE]` | S2 (Ola 2) | Dudu (`Dudu123-cell`) | PR #26, #46 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-12** | Ficha informativa consolidada del alumno con segregación financiera. | Dado alumno activo/histórico, Cuando consulta ficha → devuelve DTO consolidado y oculta pagos sin permiso. | Media | `[PENDIENTE]` | S3 (Ola 3B) | Gari Joel (`joelchavezhuanca`) | PR #36, #44 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-13** | Exportación de asistencias (CSV UTF-8-SIG, XLSX, PDF) sanitizada. | Dado rango ≤ 366 días, Cuando exporta → 12 columnas con snapshot, sanitiza `=,+,-,@` anti Formula Injection y audita. | Media | `[PENDIENTE]` | S3 (Ola 3A) | Gari Joel (`joelchavezhuanca`) | PR #30, #34, #44 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-14** | Emisión de boletas preliminares (abierto) y oficiales verificables (cerrado). | Dado período cerrado y cursos completos, Cuando emite → boleta OFICIAL con código único; si abierto → BORRADOR. | Media | `[PENDIENTE]` | S3 (Ola 3B) | Yhovana (`78970249-sys`) | PR #35, #44 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-15** | RBAC dinámico (28 permisos), roles personalizados y sesiones en servidor. | Dado ADMIN, Cuando administra roles → evaluación `deny-by-default`, blindaje ADMIN y revocación inmediata. | Alta | `[PENDIENTE]` | S1/S2 (Ola 0) | Gari Joel (`joelchavezhuanca`) | PR #16, #18, #42 | Boceto en `fix/mejora-ui` `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-16** | Auditoría inmutable append-only encadenada criptográficamente por SHA-256. | Dado evento crítico, Cuando registra → hash SHA-256 desde `GENESIS`, bloquea claves sensibles y valida integridad. | Alta | `[PENDIENTE]` | S2 (Ola 0) | Gari Joel (`joelchavezhuanca`) | PR #15, #18, #42 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |
| **PBI-17** | Notificaciones WhatsApp asíncronas, idempotentes y con ventana ±5 min. | Dado ingreso/cierre en día lectivo, Cuando encola → nunca bloquea PBI-01, máx. 3 reintentos y bloqueo manual ±5 min. | Alta | `[PENDIENTE]` | S2 (Ola 2) | Yhovana (`78970249-sys`) | PR #24, #34, #40 | `[PENDIENTE PNG]` | `[PENDIENTE #]` | **Terminado** |

### 2.2 Plan de sprints (ejecutado y verificado)

| Sprint | Fechas verificadas en Git | Objetivo del sprint | PBIs y entregables cumplidos | Evidencia verificable |
|---|---|---|---|---|
| **Sprint 1 (Línea base)** | 26/10/2026 – 22/11/2026 | Núcleo base PBI-01/02/03, ORM inicial (4 tablas), CI y especificación maestra v2 (17 PBIs + DER v2). | PBI-01/02/03 base, ORM v1, `docs/pbi/PBI-01..17`, `docs/DER_V2_PROPUESTO.md`. | PRs #1–#14 (`fac4109`..`699cf8d`) |
| **Sprint 2 (Olas 0, 1 y 2)** | 26/11/2026 – 27/11/2026 | Integración Ola 0 (PBI-16, 15, 04) + cierre de brechas y 9 PBIs nuevos de dominio en paralelo (0 conflictos). | PBI-01, 02, 03, 04, 05, 06, 07, 08, 09, 11, 15, 16, 17 + estabilización pre-Ola 3. | PRs #15, #16, #18–#29 (`8fb7fe0`..`7a387bb`) |
| **Sprint 3 (Olas 3A, 3B, 4 + Cierre Producción)** | 27/11/2026 | PBIs académicos/reportes, DER v2 (27 tablas), Repositorios, Capa Aplicación, 5 Blueprints Flask, ATDD ★, Docker CI, QR cámara, semilla realista (220 alumnos) y despliegue HTTPS Render. | PBI-10 ★, 12, 13, 14, DER v2, Repositorios A/B, UoW/Aplicación, 5 Blueprints, ATDD, Docker CI, QR cámara, Semilla Demo, Render HTTPS + CD. | PRs #30–#37, #39, #40, #42–#49, #51–#53 (`46d1914`..`4927c42`) |

### 2.3 Recursos categorizados

| Categoría | Recurso | Para qué actividad o PBI | Responsable | Costo / disponibilidad |
|---|---|---|---|---|
| **Humanos** | Equipo de 5 estudiantes de Ingeniería de Sistemas (PO/SM, Lead Backend, DB/ORM, Frontend UX/UI, DevOps/QA) | Desarrollo TDD/ATDD de PBI-01 a PBI-17, DER v2, Web Flask, Docker y Render | Todos (5 integrantes) | Dedicación académica semanal |
| **Software de desarrollo** | Python 3.11+, Flask ≥ 3.1.0, SQLAlchemy ≥ 2.0.0, Gunicorn ≥ 22, psycopg[binary] ≥ 3.2, openpyxl, `html5-qrcode.min.js`, VS Code, Git | Implementación de las 4 capas de Clean Architecture y escáner QR en navegador | Backend / DB / Frontend | Software libre (S/ 0) |
| **Calidad y pruebas** | `pytest` ≥ 8.0, `pytest-cov` ≥ 5.0, `pytest-bdd` ≥ 7.0, `Ruff` ≥ 0.8, `unittest.mock` | 1,159 pruebas automatizadas, cobertura 97.60 %, ATDD ★ y linteo/formato | DevOps & QA + equipo | Software libre (S/ 0) |
| **Infraestructura** | GitHub, GitHub Actions (`ubuntu-latest`), Docker Desktop + Docker Compose, Render.com (Web Service Docker + PostgreSQL) | CI/CD (`ci.yml`, `docker-ci.yml`, `deploy-render.yml`), contenedores y hosting HTTPS | DevOps & QA / DB / PO | Plan gratuito (S/ 0) |
| **Diseño** | Guía `docs/DESIGN.md`, `docs/ESPECIFICACION_INTERFACES_GRAFICAS_UX_UI.md`, CSS institucional verde Domingo Savio | Diseño UX/UI (regla de 3 clics, escáner QR, dashboards) | Frontend & UX/UI (`Dudu123-cell`) | Libre (S/ 0) |
| **Información del cliente** | Reglas escolares (07:00/07:15/09:00), escala vigesimal/literal, estructura Primaria/Secundaria y datos ficticios estimados (220 alumnos) | Especificaciones BDD en `docs/pbi/` y `semilla_demo.py` | PO (`joelchavezhuanca`) y equipo | Suministrado por entidad aliada |

### 2.4 Riesgos gestionados

| Riesgo | Probabilidad | Impacto | Respuesta aplicada | Responsable |
|---|---|---|---|---|
| Conflictos Git al desarrollar 5 módulos por Ola | Media | Alto | Aislamiento estricto por archivo en Olas 0–4, prohibición de merge directo de ramas `demo/*`, sincronización continua `main`/`dev`. | PO (`joelchavezhuanca`) y DB (`72945734-sys`) |
| Latencia o caída de WhatsApp API afectando ingreso < 200 ms | Alta | Alto | Desacoplamiento con `PuertoNotificadorWhatsApp` + `ThreadPoolExecutor` post-commit y `NotificadorSimulado` en pruebas. | Lead Backend (`78970249-sys`) |
| Rechazo de etiquetas Docker por el carácter `_-` en el nombre del repo | Alta (ocurrió) | Medio | Solucionado fijando `name: domingo-savio` en `docker-compose.yml` (commit `480f4dc`). | DevOps/DB (`72945734-sys`) |
| Bloqueo de cámara web en navegadores sin HTTPS | Alta | Alto | Despliegue en producción con TLS/HTTPS automático en Render.com (`https://proyecto-de-gestion-administrativa-de.onrender.com`). | DB/DevOps (`72945734-sys`) |
| Indisponibilidad del administrador de Render para futuros despliegues | Media | Medio | Workflow `.github/workflows/deploy-render.yml` con botón manual `workflow_dispatch` y disparo en `main` mediante `RENDER_DEPLOY_HOOK_URL`. | DevOps / PO |

### 2.5 Definición de Terminado (DoD)

Publicada oficialmente como plantilla en [`.github/pull_request_template.md`](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/blob/main/.github/pull_request_template.md) (PR #49):
- [x] Criterios de aceptación escritos en Gherkin (`Dado… Cuando… Entonces…`) en `docs/pbi/` y/o Issue.
- [x] Escenarios ATDD (`.feature` con `pytest-bdd`) en verde para los 2 flujos críticos ★ (`PBI-01` y `PBI-10`).
- [x] Ciclo TDD visible en historial (`test: (RED)` → `feat: (GREEN)` → `refactor: (REFACTOR)`).
- [x] `ruff check .` y `ruff format --check .` con 0 errores.
- [x] Cobertura ≥ 70 % en `src/dominio`, `src/aplicacion` y `src/infraestructura` (**97.60 % real**); `src/presentacion` excluida del umbral.
- [x] Pull Request revisado con `Continuous Integration` y `Docker CI` en verde.
- [x] Documentación actualizada (`README.md`, `docs/vision-board.md`, `docs/INFORME_FINAL_PROYECTO_COMPETENCIAS.md`).

---

## Cap. 3 — Ejecución y coordinación del proyecto (criterio 11.3)

### 3.1 Matriz de responsabilidades (R = realiza · A = aprueba · C = consultado)

| Entregable / PBI | PO/SM (`joelchavezhuanca`) | Backend (`78970249-sys`) | DB/ORM (`72945734-sys`) | Frontend (`Dudu123-cell`) | DevOps/QA (`71269297-source`) |
|---|---|---|---|---|---|
| Ola 0 (PBI-16, PBI-15, PBI-04) | **R / A** | C | C | C | C |
| PBI-01 ★, PBI-10 ★, PBI-14, PBI-17 | A | **R** | C | C | C |
| PBI-02, PBI-06, PBI-12, PBI-13 | **R** | C | C | C | **A** |
| PBI-03, PBI-05, DER v2 ORM, Repos A/B | A | C | **R** | C | C |
| PBI-09, PBI-11, Base Web UX/UI | A | C | C | **R** | C |
| PBI-07, PBI-08, Adaptadores, Capa App | A | C | C | C | **R** |
| Ola 4 — 5 Blueprints Flask + E2E | **R** (Seguridad) / A | **R** (Asistencia) | **R** (Alumnos, Académico) | C | **R** (Reportes + E2E) |
| Cierre: Admin+Nav, ATDD, Docker CI, QR, Semilla Demo, Render | A | C | **R** | C | C |

### 3.2 Registro por sprint

| Sprint | PRs fusionados verificados | Qué se entregó y demostró | Mejora acordada en retrospectiva |
|---|---|---|---|
| **Sprint 1** | #1–#5, #7–#14 (12 PRs) | Núcleo base PBI-01/02/03, ORM v1 (4 tablas), 61 tests al 100 %, guías maestras v2 (17 PBIs + DER v2). | Trabajar por Olas anti-conflictos con archivos separados por integrante. |
| **Sprint 2** | #15, #16, #18–#29 (14 PRs) | Integración Ola 0 (PBI-16 SHA-256, PBI-15 RBAC 28 permisos, PBI-04) + cierre de PBI-01/02/03 + 9 PBIs nuevos (05–09, 11, 17). | Estabilizar contratos entre módulos (PR #29) antes de iniciar persistencia v2. |
| **Sprint 3** | #30–#37, #39, #40, #42–#49, #51–#53 (22 PRs) | PBI-10 ★, 12, 13, 14, DER v2 (27 tablas), Repositorios, UoW/Aplicación, 5 Blueprints Flask, ATDD `pytest-bdd`, Docker CI, cámara QR, semilla 220 alumnos y despliegue Render HTTPS. | Automatizar el despliegue a Render mediante Deploy Hook en GitHub Actions y entregar guía de onboarding post-Ola 4. |

### 3.3 Integración y revisión de código (48 Pull Requests verificados en `main`)

| Bloque / Ola | PRs fusionados | Autores verificados | Merge commits de evidencia | CI |
|---|---|---|---|---|
| **Sprint 1 (Base + Docs v2)** | #1–#5, #7–#14 | `joelchavezhuanca`, `72945734-sys`, `78970249-sys` | `fac4109`..`699cf8d` | Verde |
| **Ola 0 (Seguridad + Auditoría + Justif.)** | #15, #16, #18 | `joelchavezhuanca` | `8fb7fe0` | Verde |
| **Ola 1 (Cierre brechas + PBI-08, 09)** | #19, #20, #21, #22, #23 | `72945734-sys`, `78970249-sys`, `Dudu123-cell`, `71269297-source`, `joelchavezhuanca` | `a1d616a`, `96d49cb`, `878908e`, `9902ef0`, `6bf7da4` | Verde |
| **Ola 2 (PBI-05, 06, 07, 11, 17 + Fix)** | #24, #25, #26, #27, #28, #29 | Los 5 integrantes | `a5b60bd`, `f9d32fa`, `4b6bfc9`, `47912bb`, `e42096e`, `7a387bb` | Verde |
| **Ola 3A (PBI-10 ★, 13, DER v2, UX, Adapt.)** | #30, #31, #32, #33, #34 | `72945734-sys`, `78970249-sys`, `Dudu123-cell`, `71269297-source` | `46d1914`, `952d5b5`, `81a7150`, `01de947`, `98cf6e0` | Verde |
| **Ola 3B (PBI-12, 14, Repos A/B, App)** | #35, #36, #37, #39, #40 | `78970249-sys`, `joelchavezhuanca`, `72945734-sys`, `71269297-source` | `ed4d92a`, `36156fb`, `462b62e`, `3e45804`, `22577cf` | Verde |
| **Ola 4 (5 Blueprints Web Flask + E2E)** | #42, #43, #44, #45, #46, #47 | `joelchavezhuanca`, `78970249-sys`, `71269297-source`, `72945734-sys` | `a83d149`, `efcb9e4`, `e32a26c`, `c3a5445`, `ec82b06`, `a0e5a06` | Verde |
| **Cierre: Fases 1–3, QR, Semilla Demo** | #48, #49, #51, #52, #53 | `72945734-sys` (revisado/fusionado en `main`) | `dcd35e7`, `ae46bfe`, `1a0f5bf`, `11e387c`, `4927c42` | Verde (CI + Docker CI) |

**Evidencia completa:** https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/pulls?q=is%3Apr+is%3Amerged

---

## Cap. 4 — Técnicas y metodologías (criterio 14.1)

### 4.1 Registro de decisiones técnicas

| Decisión | Opción elegida | Alternativas comparadas | Criterios | Justificación para Colegio Domingo Savio S.A.C. |
|---|---|---|---|---|
| **Marco de gestión** | Scrum con ejecución paralela en Olas anti-conflictos | Kanban puro, Cascada | Incertidumbre de reglas, entregas incrementales, equipo de 5 personas | Permitió incorporar el rediseño de 17 PBIs y escalar en paralelo sin conflictos entre los 5 roles. |
| **Estrategia de pruebas** | TDD (`RED → GREEN → REFACTOR`) + ATDD (`pytest-bdd` en 2 flujos ★) | Test-last, pruebas manuales | Detección temprana de defectos, precisión en reglas críticas | Garantizó 0 errores en fronteras de tardanza (`07:15:00`), SHA-256, alertas no bloqueantes y promedios `Decimal`. |
| **Arquitectura** | Clean Architecture + DDD (`dominio → aplicacion → infraestructura → presentacion`) | MVC acoplado en rutas Flask | Testabilidad sin BD/framework, velocidad (< 200 ms), mantenibilidad | Logró **100 % de cobertura en dominio** (3,019 sentencias) y permitió pasar de 4 a 27 tablas y de SQLite a PostgreSQL sin tocar reglas de negocio. |
| **Estrategia de ramas** | Ramas por tarea (`feature/`, `improvement/`, `fix/`, `refactor/`) + `dev` + `main` con tags | Push directo a `main`, Trunk-Based sin PR | Estabilidad del release y trazabilidad por PBI | Protege la rama desplegada en Render y deja trazabilidad auditable de los 48 PRs. |
| **Diseño de casos de prueba** | Valores límite + Particiones de equivalencia + Tablas de decisión | Casos ad hoc | Cobertura de fronteras reales del negocio | Validó límites exactos (`07:15:00` vs `07:15:01`, notas `-0.01`/`0`/`20`/`20.01`, rubros `99`/`100`/`101`, adjuntos `5_242_880 B`). |
| **Diseño UX/UI** | Especificación previa (Regla de 3 clics) + lector QR en navegador | Codificación directa sin diseño | Ergonomía en portería bajo horas pico | Redujo el registro diario a un solo campo unificado + cámara QR automática sin recargar la página. |

### 4.2 Estrategia de ramas y estándar de commits

- **Ramas activas:** `main` y `dev` sincronizadas (commit `4927c42`), más ramas temáticas por entregable (`feature/*`, `improvement/*`, `fix/*`, `refactor/*`).
- **Conventional Commits con trazabilidad TDD/ATDD:** verificable en `https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/commits/main`, incluyendo prefijos `test: (RED)`, `feat: (GREEN)`, `refactor: (REFACTOR)`, `test: (ATDD)`, `build(docker):`, `ci(docker):` y etiquetas de rol `(DO)`, `(DB)`, `(PO)` conforme al Instructivo N° 05.

---

## Cap. 5 — Herramientas (criterio 14.2)

### 5.1 Comparación de herramientas (Stack Python 3.11+)

| Necesidad | Herramienta usada | Alternativa comparada | Criterios | Por qué se eligió | Evidencia en el repositorio |
|---|---|---|---|---|---|
| **Pruebas unitarias e integración** | `pytest` ≥ 8.0 | `unittest` | Fixtures componibles, parametrización, claridad | Escala a **1,159 pruebas** con fixtures herméticos y parametrizaciones exactas. | `tests/`, `pyproject.toml` |
| **Pruebas de aceptación (ATDD ★)** | `pytest-bdd` ≥ 7.0 | `behave` | Un solo runner en CI, reutilización de fixtures pytest | Ejecuta `.feature` de PBI-01 ★ y PBI-10 ★ dentro de `pytest` sin framework separado. | `tests/acceptance/features/*.feature` |
| **Análisis estático y formato** | `Ruff` ≥ 0.8 | `Flake8 + Black + isort` | Velocidad (Rust), configuración única, costo 0 | Unifica linteo (`E, F, I, UP`) y formato en `pyproject.toml`; 0 errores en 103 archivos. | `pyproject.toml`, `.github/workflows/ci.yml` |
| **Cobertura** | `pytest-cov` ≥ 5.0 | `coverage.py` CLI | Integración directa, `--cov-fail-under=70` | Mide dominio, aplicación e infraestructura excluyendo presentación (**97.60 %**). | `.github/workflows/ci.yml` |
| **Persistencia (ORM)** | `SQLAlchemy 2.0` | SQL crudo / Peewee | Tipado `Mapped`, portabilidad SQLite ↔ PostgreSQL | Pruebas en `sqlite:///:memory:` (`PRAGMA foreign_keys=ON`) y producción en PostgreSQL (Render) con 0 cambios de código. | `src/infraestructura/modelos.py`, `base_datos.py` |
| **Interfaz web + QR** | `Flask 3.1` + Jinja2 + `html5-qrcode.min.js` | Django, Streamlit, Tkinter | Ligereza, Clean Architecture, cámara QR en celular/PC | Permite 5 Blueprints paralelos sin acoplar dominio y escaneo QR nativo en navegador HTTPS. | `src/presentacion/` |
| **Integración y despliegue continuo** | GitHub Actions | GitLab CI, Jenkins | Integración nativa con PRs, plan gratuito | 3 workflows: `ci.yml`, `docker-ci.yml` y `deploy-render.yml` (CD a Render). | `.github/workflows/*.yml` |
| **Contenerización y hosting** | Docker + Docker Compose + Render.com (PostgreSQL) | Instalación manual local / Heroku | Reproducibilidad total, volumen persistente, HTTPS gratis | Cualquier integrante o docente levanta pruebas y app en 1 comando; producción HTTPS viva. | `Dockerfile`, `docker-compose.yml`, `wsgi.py` |

### 5.2 Pipeline de Integración y Despliegue Continuo (CI/CD)

1. **[`.github/workflows/ci.yml`](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/blob/main/.github/workflows/ci.yml):** corre en `push` y `pull_request` hacia `main`/`dev` sobre `ubuntu-latest` (Python 3.11); ejecuta `ruff check .`, `ruff format --check .`, `pytest -v tests/acceptance` y `pytest -v --cov=src/dominio --cov=src/aplicacion --cov=src/infraestructura --cov-fail-under=70`.
   - **Evidencia Run verde en `main`:** [Run #45984537313](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537313)
2. **[`.github/workflows/docker-ci.yml`](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/blob/main/.github/workflows/docker-ci.yml):** construye la imagen (`docker compose --profile pruebas build`), corre las pruebas aisladas en el contenedor (`docker compose --profile pruebas run --rm pruebas`) y levanta la web verificando `http://localhost:5000/health`.
   - **Evidencia Run verde en `main`:** [Run #45984537455](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537455)
3. **[`.github/workflows/deploy-render.yml`](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/blob/main/.github/workflows/deploy-render.yml):** permite despliegue automático al fusionar a `main` y disparo manual (`workflow_dispatch`) mediante el secreto `RENDER_DEPLOY_HOOK_URL`.

### 5.3 Contenerización y Despliegue en Producción

- **Servicios de `docker-compose.yml` (`name: domingo-savio`):**
  1. `app`: imagen `python:3.11-slim` + Gunicorn (`0.0.0.0:5000`), puerto `5000:5000`, volumen persistente `./datos_locales:/app/data` (`colegio.db`) y siembra automática del admin inicial.
  2. `pruebas` (`profiles: ["pruebas"]`): ejecuta `pytest` completamente aislado en memoria sin montar `./datos_locales`.
- **Comandos reproducibles en equipo limpio (verificados con prueba de clon limpio en `C:\proyectos\prueba_clon`):**
  `git clone ...` → `docker compose --profile pruebas run --rm pruebas` → `docker compose up -d --build` → `http://localhost:5000` → `docker compose down`.
- **Producción en vivo:** desplegado en Render.com usando el mismo `Dockerfile` conectado a PostgreSQL (`domingo-savio-db`) en https://proyecto-de-gestion-administrativa-de.onrender.com (verificado `GET /health` → `200 {"status": "ok"}`).

---

## Cap. 6 — Desarrollo de experimentos y pruebas (criterio 8.1)

### 6.1 Plan de pruebas consolidado (PBI-01 al PBI-17)

Todos los 17 PBIs siguieron el procedimiento estándar **TDD (`RED → GREEN → REFACTOR`)** con valores límite, particiones de equivalencia, tablas de decisión y dobles de prueba (`NotificadorSimulado` y mocks HTTP), ejecutados en `pytest` + `SQLite :memory:` (`PRAGMA foreign_keys=ON`) y validados en GitHub Actions (`ci.yml` y `docker-ci.yml`).

### 6.2 Evidencia real del ciclo TDD (commits verificados en `main`)

| PBI / Módulo | RED (`test:`) | GREEN (`feat:`) | REFACTOR (`refactor:`) | PR |
|---|---|---|---|---|
| **PBI-01 ★** (Unif. + Brechas) | `d415b19` / `0abd9f0` | `911dcc2` / `8e0ad47` | `464be30` / `24c18fd` | #10, #20 |
| **PBI-02** (Usuarios + RBAC) | `63d98d9` / `6b5523d` | `55e2688` / `8a4807d` | `8cb30cb` / `87bd7d5` | #11, #23 |
| **PBI-03** (Aforo + Calendario) | `bd2b760` / `32a145a` | `37c5850` / `a96e923` | `99dcbcf` / `3031f49` | #12, #19 |
| **PBI-04** (Justificaciones/Períodos) | `5f8fb9c` | `c078d67` | `c66ae99` | #18 |
| **PBI-05** (Matrícula Digital) | `1e0480e` | `a612750` | `0ee241b` | #25 |
| **PBI-06** (Carnets QR Opacos) | `2204804` | `dcbac26` | `8bcecb2` | #28 |
| **PBI-07** (Pagos + Alerta Silenciosa) | `d44a739` | `215a720` | `72f4552` | #27 |
| **PBI-08** (Estados Académicos) | `0d06b05` | `c557dcb` | `2d65a69` | #22 |
| **PBI-09** (Malla Curricular) | `63ed1ac` | `1dc03fa` | `31ef153` | #21 |
| **PBI-10 ★** (Calificaciones 3N) | `cbc9c02` | `28d2e58` | `9cc7d7f` | #32 |
| **PBI-11** (Asignación Docente) | `fff6762` | `74eb527` | `bff455f` | #26 |
| **PBI-12** (Ficha del Alumno) | `59bb505` | `b60a297` | `5d286c4` | #36 |
| **PBI-13** (Exportación Asistencias) | `f4d27e4` | `cbf19e3` | `76572fe` | #30 |
| **PBI-14** (Emisión de Boletas) | `5867b8b` | `ef235d8` | `7b3b51f` | #35 |
| **PBI-15** (RBAC Dinámico 28 perm.) | `122576e` | `01ca478` | `1c2cff5` | #16, #18 |
| **PBI-16** (Auditoría SHA-256) | `bf324ca` | `167ad21` | `731f7be` | #15, #18 |
| **PBI-17** (Notificaciones WhatsApp) | `7db8b69` | `77f3cc3` | `108a16f` | #24 |
| **DER v2 + Repositorios A/B** | `42526fd`, `d4df966`, `ab1a348` | `e5c1aa3`, `d7d97ba`, `51ea349` | `baec106`, `110478f`, `168a7f1` | #31, #37, #39 |
| **Web Base + Blueprints Ola 4** | `7feda6f`, `31a2ffa`, `29c4725`, `9f00a7c` | `551a500`, `3ebcbfb`, `d7bacff`, `fa74d34` | `4aec589`, `bc454ca`, `53c8199`, `862a10b` | #33, #42–#46 |

### 6.3 Evidencia ATDD (pruebas de aceptación — 2 flujos críticos ★)

| Flujo crítico | PBI | Archivo `.feature` y steps | Escenarios cubiertos | Resultado | Cadena de commits ATDD |
|---|---|---|---|---|---|
| **★ Flujo crítico 1** | PBI-01 ★ | `tests/acceptance/features/pbi01_registro_asistencia.feature` + `tests/acceptance/test_pbi01_registro_asistencia.py` | Puntualidad, tardanza exacta (`ceil`), duplicado, corrección de `AUSENTE` con motivo, rechazo de carnet anulado, bloqueo a alumno inactivo y rendimiento < 200 ms. | **7 passed** | `5b26091` (ATDD) → `e4f3787` (RED) → `f9c8437` (GREEN) → `0756238` (REFACTOR) · PR #49 |
| **★ Flujo crítico 2** | PBI-10 ★ | `tests/acceptance/features/pbi10_calificaciones.feature` + `tests/acceptance/test_pbi10_calificaciones.py` | Rubros = 100 %, rechazo suma ≠ 100 %, promedio ponderado 3 niveles `Decimal` (`AD/A/B/C`), rechazo nota fuera de `[0, 20]`, bloqueo post fecha límite y denegación de ámbito docente ajeno. | **7 passed** | `5b26091` (ATDD) → `e4f3787` (RED) → `f9c8437` (GREEN) → `0756238` (REFACTOR) · PR #49 |

### 6.4 Interfaz web implementada (5 Blueprints Flask)

Los 17 PBIs están desplegados en 5 Blueprints con pruebas automatizadas Flask:
- `bp_seguridad` (`login.html`, `usuarios.html`, `usuarios_form.html`, `roles.html`, `roles_form.html`, `auditoria.html`) → `tests/test_web_seguridad.py` (64 casos).
- `bp_asistencia` (`asistencia.html` con **escáner QR + búsqueda en vivo + tabla del día**, `aforo.html`, `justificaciones.html`, `periodos.html`) → `tests/test_web_asistencia.py` (97 casos).
- `bp_alumnos` (`matricula.html`, `carnets.html`, `pagos.html`, `estados.html`) → `tests/test_web_alumnos.py` (8 funciones / múltiples escenarios).
- `bp_academico` (`malla.html`, `docentes.html`, `calificaciones.html`) → `tests/test_web_academico.py` (3 flujos integrales).
- `bp_reportes` (`ficha_alumno.html`, `exportar_asistencia.html`, `boletas.html`) → `tests/test_web_e2e.py` (43 casos E2E).
- *(Nota: `[PENDIENTE]` adjuntar capturas finales de las pantallas desplegadas en Render y exportar wireframes PNG si el docente lo requiere en `docs/wireframes/`).*

### 6.5 Pruebas de integración (ORM y dobles de prueba)

- **Persistencia aislada:** [`tests/conftest.py`](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/blob/main/tests/conftest.py) crea y destruye el esquema DER v2 (27 tablas) en `sqlite:///:memory:` con `PRAGMA foreign_keys=ON` por prueba; validado en `test_persistencia_orm.py`, `test_repositorios_nucleo.py`, `test_repositorios_academico.py`, `test_aplicacion_integracion.py` (rollback atómico si falla auditoría PBI-16) y `test_semilla_demo.py`.
- **Dobles de prueba:** `NotificadorSimulado` y mocks HTTP en `tests/test_notificaciones_whatsapp.py` y `tests/test_infra_adaptadores.py` garantizan 0 llamadas externas en CI.

---

## Cap. 7 — Análisis e interpretación de resultados (criterio 8.2)

### 7.1 Resultados clasificados por tipo de prueba (medidos en `main` `4927c42`)

| Tipo de prueba | N.º de pruebas | Pasan | Fallan | Módulos cubiertos | Evidencia (Actions) |
|---|---|---|---|---|---|
| **Unitarias (dominio)** | **772** | **772** | **0** | Los 16 módulos de `src/dominio/` (17 PBIs completos) | [Run #45984537313](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537313) |
| **Integración (ORM, Repos, Adapt., UoW, Demo)** | **135** | **135** | **0** | `modelos.py` (27 tablas), `base_datos.py`, 6 repositorios, `exportadores.py`, `whatsapp.py`, `uow.py`, servicios de aplicación y `semilla_demo.py` | [Run #45984537313](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537313) |
| **Aceptación (ATDD ★ `pytest-bdd`)** | **14** | **14** | **0** | `pbi01_registro_asistencia.feature` (7) y `pbi10_calificaciones.feature` (7) | [Run #45984537313](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537313) |
| **Integración Web Flask y E2E** | **238** | **238** | **0** | `app.py`, `seguridad.py` (CSRF/RBAC) y los 5 Blueprints (`bp_seguridad`, `bp_asistencia`, `bp_alumnos`, `bp_academico`, `bp_reportes`) | [Run #45984537455 (Docker CI)](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537455) |
| **TOTAL CONSOLIDADO** | **1,159** | **1,159** | **0** | **Sistema completo verificado local y en contenedor Docker** | **100 % en verde** |

### 7.2 Cobertura por capa (umbral obligatorio ≥ 70 %, sin `src/presentacion/`)

Medición real con `python -m pytest --cov=src/dominio --cov=src/aplicacion --cov=src/infraestructura --cov-report=term --cov-fail-under=70`:

| Módulo / capa | Sentencias | Sin cubrir | Cobertura | Interpretación técnica |
|---|---|---|---|---|
| **Dominio (`src/dominio/`)** | **3,019** | **0** | **100.00 %** | Reglas de negocio puras de los 17 PBIs sin ninguna línea sin cubrir (riesgo mínimo de regresión lógica). |
| **Casos de uso (`src/aplicacion/`)** | **1,886** | **161** | **91.46 %** | Orquestación transaccional UoW y despacho asíncrono; las líneas no cubiertas corresponden principalmente a ramas defensivas ante fallos extremos de E/S o excepciones redundantes en workers post-commit. |
| **Infraestructura / ORM (`src/infraestructura/`)** | **1,941** | **3** | **99.85 %** | 100 % en ORM (27 tablas), `base_datos.py`, `exportadores.py` y los 6 repositorios; solo 3 líneas defensivas sin cubrir (`whatsapp.py`: 2, `semilla_demo.py`: 1). |
| **TOTAL MEDIDO** | **6,846** | **164** | **97.60 %** | **Supera ampliamente el umbral exigido (≥ 70 %) en +27.60 puntos porcentuales.** |
| **Presentación (`src/presentacion/`)** | — | — | **Excluida** | Excluida del umbral conforme a la rúbrica; igualmente validada con **238 pruebas Flask/E2E** y pruebas en vivo en Docker y Render. |

### 7.3 Defectos reales detectados y corregidos por pruebas y CI

| N.º | Defecto detectado | Qué lo detectó | Causa raíz | Corrección verificada |
|---|---|---|---|---|
| **D1** | Error tipográfico en `sqlalchemy` en `requirements.txt`. | CI en PR #5 | Error manual al declarar dependencia. | Commit `4d72c9e` |
| **D2** | Incompatibilidad de PBI-16 (`auditoria.py`) con roles personalizados `str` de PBI-15. | Auditoría Ola 0 + test `AUDITOR_INTERNO` | `auditoria.py` asumía solo enum `RolUsuario`. | PR #18 (`8fb7fe0`) |
| **D3** | `PeriodoAcademico` prohibía `fecha_limite_notas > fecha_fin`. | Revisión cruzada PBI-04 / PBI-10 | Validación excesivamente restrictiva para regularización docente. | Commit `5eefd2e` (PR #18) |
| **D4** | Doble registro de Blueprints (`ValueError`) al integrar `bp_alumnos`/`bp_asistencia` con `app.py`. | Pruebas integrales Ola 4 | `app.py` auto-registraba Blueprints ya registrados manualmente. | Commits `1761753`, `09a16f3` (PRs #43, #45) |
| **D5** | `docker compose up` falló con `invalid tag "...proyecto_-de_gestion..."`. | Ejecución en Docker Desktop (Instructivo 05) | El nombre de la carpeta en GitHub contiene `_-` (inválido en etiquetas OCI). | Commit `480f4dc` (`name: domingo-savio`, PR #51) |
| **D6** | Smoke test HTTP en `docker-ci.yml` falló en Ubuntu Linux (`curl` error 56). | GitHub Actions `Docker CI` (Run `45977807443`) | `docker-proxy` aceptaba TCP antes de terminar de arrancar Gunicorn y `--retry-connrefused` no reintenta reset. | Commit `67164f1` (`--retry-all-errors` + espera, PR #51) |
| **D7** | Orden invertido de parámetros en `buscar_alumnos_activos(consulta, alumnos)`. | Nueva prueba `test_api_buscar_alumnos_filtra_y_protege_acceso` | Al portar `GET /api/alumnos` se invirtió el orden de argumentos. | Commit `2a77098` (PR #52) |

### 7.4 Validación con la entidad aliada

| Fecha | Participante (cargo) | Qué se validó | Observación recibida | Ajuste realizado |
|---|---|---|---|---|
| 31/10/2026 | Gari Joel Chávez Huanca (Centro de Cómputo) | Reglas de asistencia (07:00/07:15/09:00), roles, 17 PBIs y DER v2. | Formalizar 17 especificaciones BDD y separar exportación de aforo. | PR #14 (`699cf8d`) |
| `[PENDIENTE]` | Representante Colegio Domingo Savio S.A.C. | Validación final del sistema en producción HTTPS (17 PBIs + QR cámara + datos realistas). | `[PENDIENTE: registrar observaciones de la demo final]` | `[PENDIENTE]` |

### 7.5 Interpretación

La combinación de **772 pruebas unitarias de dominio (100 % de cobertura)**, **135 pruebas de integración ORM/UoW/demo (99.85 % en infraestructura y 91.46 % en aplicación)**, **14 escenarios ATDD (`pytest-bdd`)** y **238 pruebas web Flask/E2E** —sumando **1,159 pruebas en verde (97.60 % de cobertura total)**— confirma que el sistema satisface las 10 necesidades del Cap. 1: marcación < 200 ms, RBAC de 28 permisos, bitácora SHA-256 atómica, alerta silenciosa no bloqueante, libro de notas `Decimal`, escáner QR en navegador y persistencia verificada tanto en Docker local (SQLite) como en producción HTTPS (PostgreSQL en Render.com). Los únicos riesgos fuera del alcance del CI automatizado son el envío real a números productivos de Meta WhatsApp Cloud API (aislado mediante adaptador/simulador) y pruebas de estrés concurrente en red escolar física.

---

## Cap. 8 — Sprint Review final y cierre

### 8.1 Incremento entregado (Release v1.0)

- **Estado de los 17 PBIs:** **17/17 Terminados**, cumpliendo DoD, integrados en `dev` y `main`, verificados en `ci.yml` y `docker-ci.yml`, y desplegados en producción en https://proyecto-de-gestion-administrativa-de.onrender.com (con 220 alumnos realistas en 11 salones mediante `SEMBRAR_DATOS_DEMO=true`).
- **Release / Tag:** `v1.0` sobre `main`.

### 8.2 Guion del Sprint Review (≈ 15 minutos)

1. **Visión, problema y alcance (2 min):** Colegio Domingo Savio S.A.C., eliminación de 10–15 min/día de lista manual, 17 PBIs, sostenibilidad y `docs/vision-board.md`.
2. **Backlog, Olas y coordinación (3 min):** 48 PRs fusionados (#1–#53), reparto por los 5 roles (`joelchavezhuanca`, `78970249-sys`, `72945734-sys`, `Dudu123-cell`, `71269297-source`) y revisión cruzada.
3. **Demo en vivo (5 min):**
   - **Local Docker (persistencia):** `docker compose up -d --build` → crear registro en `http://localhost:5000` → `docker compose down` → `docker compose up -d` → demostrar persistencia en `./datos_locales/colegio.db` y aislamiento con `docker compose --profile pruebas run --rm pruebas`.
   - **Producción HTTPS (escáner QR + 220 alumnos):** abrir https://proyecto-de-gestion-administrativa-de.onrender.com/asistencia, escanear en vivo `CRN-2026-0001` (puntual), `CRN-2026-0009` (corrección con motivo), `CRN-2026-0010` (alerta silenciosa sin bloqueo) y `CRN-2026-0217` (bloqueo por `SUSPENDIDO`), más recorrido por Aforo, Calificaciones 3N, Boletas y Auditoría SHA-256.
   - **Trazabilidad:** rama → `.feature` (`tests/acceptance/`) → commits `RED/GREEN/REFACTOR` → PR verde → `main` (`v1.0`).
4. **Pruebas y cobertura (2 min):** mostrar Runs verdes `#45984537313` y `#45984537455`, 1,159 pruebas y **97.60 %** de cobertura (100 % dominio).
5. **Decisiones técnicas y herramientas (2 min):** Clean Architecture, SQLAlchemy 2.0, Ruff, Flask + `html5-qrcode`, Docker y Render HTTPS.
6. **Preguntas y verificación Git (1 min):** `git fetch && git status` sincronizado con `origin/main`.

### 8.3 Retrospectiva del equipo

| Qué funcionó bien | Qué se puede mejorar | Lecciones aprendidas |
|---|---|---|
| Clean Architecture permitió 100 % de cobertura en dominio y cambiar de 4 a 27 tablas y de SQLite a PostgreSQL sin fricción. | Configurar `dev`, Branch Protection, ATDD y Docker desde el Sprint 1 en lugar de consolidarlos al cierre. | **Técnica:** probar en Docker y en Linux CI temprano detecta detalles reales (`name: domingo-savio`, `curl --retry-all-errors`) imposibles de ver solo en Windows. |
| La división en 5 Olas redujo conflictos a casi cero entre 5 integrantes. | Exportar wireframes formales en PNG desde el primer sprint y registrar Story Points en GitHub Issues desde el inicio. | **Organizacional:** una guía de sincronización post-Ola 4 y el despliegue continuo vía GitHub Actions aseguran que todo el equipo pueda operar y sustentar el sistema sin cuellos de botella. |

### 8.4 Conformidad de la entidad aliada

`[PENDIENTE: adjuntar aquí constancia firmada o captura del correo de conformidad del representante del Colegio Domingo Savio S.A.C. tras la demostración final.]`

---

## Anexo A — Matriz de trazabilidad rúbrica → evidencia

| Criterio | Evidencia mínima en GitHub | Sección | Enlaces verificados del equipo | Nivel autoevaluado (0–3) |
|---|---|---|---|---|
| **8.1 Desarrollo de experimentos** | Commits RED/GREEN/REFACTOR; `.feature` de 2 flujos ★; BD prueba aislada | 6.1–6.5 | `tests/conftest.py` · `tests/acceptance/features/` · PR #49 (`ae46bfe`) · historial `commits/main` | **3 (Sobresaliente)** |
| **8.2 Análisis e interpretación** | Run verde con cobertura dominio/app/infra; defectos reales | 7.1–7.5 | [Run #45984537313](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/actions/runs/45984537313) (1,159 pruebas, **97.60 %**) · defectos D1–D7 | **3 (Sobresaliente)** |
| **11.1 Diseño del proyecto** | `docs/vision-board.md`; `README.md` con problema y alcance | 1.1–1.6 | `docs/vision-board.md` · `README.md` · `docs/README.md` | **3 (Sobresaliente)** |
| **11.2 Planificación de la gestión** | 17 especificaciones BDD, DoD en PR template, recursos y riesgos | 2.1–2.5 | `docs/pbi/` (17 guías) · `.github/pull_request_template.md` (`[PENDIENTE: enlazar Issues/Milestones en GitHub]`) | **3** *(al enlazar Issues/Milestones)* |
| **11.3 Ejecución del proyecto** | Matriz R/A/C, 48 PRs fusionados de los 5 integrantes | 3.1–3.3 | [PRs fusionados (#1–#53)](https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio/pulls?q=is%3Apr+is%3Amerged) | **3 (Sobresaliente)** |
| **14.1 Técnicas y metodologías** | Comparación formal + ramas `feature` → `dev`/`main` + Conventional Commits | 4.1–4.3 | Ramas `dev` y `main` sincronizadas · `commits/main` (`[PENDIENTE: activar Branch Protection en Settings → Branches]`) | **3** *(al activar protección de `main`)* |
| **14.2 Herramientas** | `ci.yml`, `docker-ci.yml`, `deploy-render.yml`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml` | 5.1–5.3 | `.github/workflows/ci.yml` · `.github/workflows/docker-ci.yml` · `Dockerfile` · `docker-compose.yml` · Producción HTTPS en Render | **3 (Sobresaliente)** |
