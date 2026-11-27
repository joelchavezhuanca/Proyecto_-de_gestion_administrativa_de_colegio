# Sistema de Control de Asistencia y Gestión Administrativa

Proyecto integrador desarrollado para el **Colegio Domingo Savio S.A.C.** por el **Grupo Conti2000**, en la asignatura *Construcción de Software* (2026-I, Cusco).

El sistema implementa gestión integral de asistencia, aforo, justificaciones, matrícula, carnets, pagos, estados académicos, malla curricular, calificaciones, reportes/boletas, seguridad RBAC, auditoría inmutable y notificaciones, con arquitectura en capas (`dominio`, `aplicacion`, `infraestructura`, `presentacion`), aplicación web en **Flask**, persistencia con **SQLAlchemy 2.0** (SQLite local y PostgreSQL en producción), pruebas automatizadas (**TDD + ATDD con `pytest-bdd`**) e integración continua en **GitHub Actions + Docker**.

## Integrantes y roles

- **Gari Joel Chavez Huanca (PO):** Product Owner / Scrum Master; backlog, coordinación del flujo de trabajo, README y revisión de PR.
- **Yhovana Quispe Ccolqquere (BE):** Lead Backend Engineer; dominio, servicios de aplicación, configuración y pruebas.
- **Eduardo Luna Lezano (DB):** Database & ORM Specialist; modelo de datos DER v2, SQLAlchemy, persistencia y aislamiento de pruebas.
- **Dudu Fabiano Lizarzaburu Flores (FE):** Frontend & UX/UI Engineer; interfaz web Flask/Jinja2, validación funcional y prueba de clon limpio.
- **Jacob Luna Basilio (DO):** DevOps & QA Engineer; Docker, Docker Compose, GitHub Actions, Ruff, Pytest y cobertura.

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
   - Usuario inicial creado automáticamente en Docker local: `admin` / `Admin2026!` (configurable vía variables de entorno en `.env`, ver `.env.example`).
5. Detener los contenedores:
   ```bash
   docker compose down
   ```

Los datos se guardan en la carpeta `datos_locales` (no se versiona). En producción (Render.com), el mismo `Dockerfile` se conecta a PostgreSQL inyectando `DATABASE_URL` y `SECRET_KEY` como variables de entorno.

## Estructura del proyecto

```text
Proyecto_-de_gestion_administrativa_de_colegio/
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci.yml          # Ruff + Pytest + ATDD + Cobertura ≥ 70 %
│       └── docker-ci.yml   # Build, pruebas y smoke test HTTP en Docker
├── docs/
│   └── vision-board.md
├── src/
│   ├── dominio/            # Entidades y reglas de negocio puras
│   ├── aplicacion/         # Casos de uso / servicios de aplicación
│   ├── infraestructura/    # ORM SQLAlchemy 2.0, repositorios y base_datos.py
│   └── presentacion/       # App Flask, blueprints y templates Jinja2
├── tests/
│   ├── acceptance/         # Escenarios ATDD Gherkin (pytest-bdd)
│   └── ...                 # Pruebas unitarias, ORM, aplicación y web
├── Dockerfile
├── .dockerignore
├── docker-compose.yml
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

# Ejecutar todas las pruebas (unitarias, integración, web y ATDD)
python -m pytest -v

# Ejecutar pruebas con cobertura de lógica e infraestructura
python -m pytest -v --cov=src/dominio --cov=src/aplicacion --cov=src/infraestructura --cov-report=term-missing --cov-fail-under=70

# Revisar estilo y formato con Ruff
python -m ruff check .
python -m ruff format --check .

# Iniciar servidor de desarrollo
python run.py
```
