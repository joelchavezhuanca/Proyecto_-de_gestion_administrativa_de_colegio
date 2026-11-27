# Sistema de Control de Asistencia y Gestión Administrativa — Colegio Domingo Savio S.A.C.

Proyecto integrador desarrollado para el **Colegio Domingo Savio S.A.C.** (Cusco, Perú) por el **Grupo 5 — Conti2000** en la asignatura *Construcción de Software* (Universidad Continental, 2026).

- **Aplicación en producción (HTTPS · Render + PostgreSQL):** https://proyecto-de-gestion-administrativa-de.onrender.com
- **Registro de Asistencia + Escáner QR:** https://proyecto-de-gestion-administrativa-de.onrender.com/asistencia
- **Estado del servicio (Healthcheck):** https://proyecto-de-gestion-administrativa-de.onrender.com/health
- **Informe Final del Proyecto por Competencias:** [`docs/INFORME_FINAL_PROYECTO_COMPETENCIAS.md`](docs/INFORME_FINAL_PROYECTO_COMPETENCIAS.md)

---

## Alcance implementado (17/17 PBIs · Clean Architecture + Flask + SQLAlchemy 2.0)

El sistema resuelve de extremo a extremo la operación administrativa y académica bajo **Clean Architecture + DDD + TDD + ATDD**:

- **Asistencia, Aforo y Justificaciones (PBI-01 ★, PBI-03, PBI-04, PBI-17):** registro unificado (< 200 ms) con **escáner QR por cámara web** (`html5-qrcode.min.js`), DNI manual o búsqueda asistida en vivo (`GET /api/alumnos`), tabla de registros del día, corrección condicional de ausencias, dashboard de aforo por salón con calendario escolar, justificaciones en períodos abiertos y notificaciones asíncronas de WhatsApp.
- **Alumnos, Carnets, Pagos y Estados (PBI-05, PBI-06, PBI-07, PBI-08):** matrícula digital con apoderados y control de vacantes, carnets QR opacos anulables, control de pensiones con **alertas silenciosas sin bloqueo en portería** y transiciones de estado académico preservando el historial.
- **Módulo Académico (PBI-09, PBI-10 ★, PBI-11):** malla curricular Primaria (`1ro–6to`) y Secundaria (`1ro–5to`), asignación docente aislada por salón/curso y libro de calificaciones de 3 niveles (`Período → Rubros 100 % → Actividades`) con precisión `Decimal`.
- **Reportes y Exportación (PBI-12, PBI-13, PBI-14):** ficha consolidada del alumno con segregación financiera, exportación CSV (UTF-8-SIG) / XLSX / PDF sanitizada contra *Formula Injection* y emisión de boletas preliminares y oficiales verificables.
- **Seguridad RBAC Dinámico y Auditoría Inmutable (PBI-02, PBI-15, PBI-16):** contraseñas `PBKDF2-HMAC-SHA256`, catálogo de 28 permisos granulares evaluados en servidor (`deny-by-default`), protección CSRF, sesiones revocables y bitácora append-only encadenada con **SHA-256**.

---

## Integrantes y roles (Grupo 5 — Conti2000)

| Rol | Responsabilidad principal | Integrante | GitHub ID |
|---|---|---|---|
| **Product Owner / Scrum Master (PO)** | Backlog, tablero, README, revisión de PRs y merges a `main`; PBIs 02, 06, 12, 13 y Blueprint Seguridad | Gari Joel Chávez Huanca | `joelchavezhuanca` |
| **Lead Backend Engineer (BE)** | Lógica de dominio TDD/ATDD; PBIs 01 ★, 10 ★, 14, 17 y Blueprint Asistencia | Yhovana Quispe Ccolqquere | `78970249-sys` |
| **Database & ORM Specialist (DB)** | DER v2 (27 tablas), SQLAlchemy 2.0, fixtures, repositorios núcleo, semilla demo; PBIs 03, 05 y Blueprint Alumnos | Eduardo Luna Lezano | `72945734-sys` |
| **Frontend & UX/UI Engineer (FE)** | Wireframes, layout institucional Flask, usabilidad, prueba de clon limpio; PBIs 09, 11, repositorios académicos y Blueprint Académico | Dudu Fabiano Lizarzaburu Flores | `Dudu123-cell` |
| **DevOps & QA Engineer (DO)** | CI/CD (GitHub Actions), Ruff, Pytest/cobertura, Docker, DoD, adaptadores, Capa Aplicación y Blueprint Reportes + E2E; PBIs 07, 08 | Jacob Luna Basilio | `71269297-source` |

---

## Calidad, pruebas y pipelines CI/CD verificados

- **Pruebas automatizadas:** **1,159 pruebas aprobadas (`0` fallos)** cubriendo dominio puro, ORM DER v2, repositorios, casos de uso, aceptación ATDD (`pytest-bdd` para PBI-01 ★ y PBI-10 ★) e integración web Flask/E2E.
- **Cobertura de código (excluyendo `src/presentacion/`):** **97.60 %** (6,846 sentencias; umbral obligatorio ≥ 70 %):
  - `src/dominio/`: **100.00 %** (3,019/3,019)
  - `src/infraestructura/`: **99.85 %** (1,938/1,941)
  - `src/aplicacion/`: **91.46 %** (1,725/1,886)
- **Análisis estático y formato:** `ruff check .` y `ruff format --check .` con **0 errores**.
- **Workflows en `.github/workflows/`:**
  - `ci.yml` (*Continuous Integration*): Ruff check + format + ATDD (`tests/acceptance`) + Pytest con cobertura ≥ 70 %.
  - `docker-ci.yml` (*Docker CI*): `docker compose --profile pruebas build`, ejecución aislada de pruebas en contenedor y smoke test HTTP contra `/health`.
  - `deploy-render.yml` (*Deploy a Producción*): disparo automático en `main` y botón manual (`workflow_dispatch`) hacia Render usando el secreto `RENDER_DEPLOY_HOOK_URL`.

---

## Cómo ejecutar con Docker

Requisito: **Docker Desktop** iniciado.

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio.git
   cd Proyecto_-de_gestion_administrativa_de_colegio
   ```
2. Ejecutar las pruebas automatizadas dentro del contenedor (aisladas en memoria, sin modificar datos reales):
   ```bash
   docker compose --profile pruebas run --rm pruebas
   ```
3. Levantar la aplicación web:
   ```bash
   docker compose up -d --build
   ```
4. Abrir `http://localhost:5000` en el navegador (el healthcheck responde en `http://localhost:5000/health`).
   - Usuario inicial creado automáticamente en Docker local: `admin` / `Admin2026!` (configurable vía `.env`, ver `.env.example`).
   - Opcional para demostración: definir `SEMBRAR_DATOS_DEMO=true` en `.env` para cargar de forma idempotente 11 salones, 220 alumnos, 33 cursos, 1,980 notas, 440 pensiones y carnets QR de prueba (`CRN-2026-0001` al `CRN-2026-0010` listos para escaneo en vivo).
5. Detener los contenedores:
   ```bash
   docker compose down
   ```

Los datos se guardan en la carpeta `datos_locales` (no se versiona). En producción (**Render.com**), el mismo `Dockerfile` se conecta a PostgreSQL inyectando `DATABASE_URL`, `SECRET_KEY`, `FLASK_ENV=production` y las credenciales iniciales por variables de entorno.

---

## Estructura del proyecto

```text
Proyecto_-de_gestion_administrativa_de_colegio/
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci.yml                  # Ruff + ATDD + Pytest + Cobertura ≥ 70 %
│       ├── docker-ci.yml           # Build, pruebas y smoke test HTTP en Docker
│       └── deploy-render.yml       # Despliegue continuo / manual a Render.com
├── docs/
│   ├── README.md                   # Índice maestro y catálogo de 28 permisos
│   ├── DER_V2_PROPUESTO.md         # Modelo relacional DER v2 (5 bloques, 27 tablas)
│   ├── vision-board.md             # Product Vision Board
│   ├── pbi/                        # 17 especificaciones BDD (PBI-01 al PBI-17)
│   └── INFORME_FINAL_PROYECTO_COMPETENCIAS.md
├── src/
│   ├── dominio/                    # 16 módulos de reglas puras (100 % cobertura)
│   ├── aplicacion/                 # Unit of Work y servicios transaccionales
│   ├── infraestructura/            # ORM DER v2, repositorios, exportadores, WhatsApp, semilla_demo
│   └── presentacion/               # App Flask, 5 Blueprints, templates Jinja2 y escáner QR
├── tests/
│   ├── acceptance/                 # Escenarios ATDD Gherkin (pytest-bdd · PBI-01 ★ y PBI-10 ★)
│   └── test_*.py                   # Unitarias, ORM, repositorios, aplicación, demo y Web/E2E
├── Dockerfile
├── .dockerignore
├── docker-compose.yml              # Servicios: app (puerto 5000 + ./datos_locales) y pruebas (perfil)
├── .env.example
├── wsgi.py
├── run.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Ejecución local sin Docker (desarrollo)

Requisitos: Python 3.11 o superior.

```bash
# Instalar dependencias
python -m pip install -r requirements.txt

# Ejecutar todas las pruebas (unitarias, integración, ATDD y web/E2E)
python -m pytest -v

# Ejecutar pruebas con cobertura obligatoria ≥ 70 % (sin capa de presentación)
python -m pytest -v --cov=src/dominio --cov=src/aplicacion --cov=src/infraestructura --cov-report=term-missing --cov-fail-under=70

# Revisar estilo y formato con Ruff
python -m ruff check .
python -m ruff format --check .

# Iniciar servidor de desarrollo
python run.py
```
