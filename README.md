# Sistema de Control de Asistencia y Gestión Administrativa

Proyecto integrador desarrollado para el Colegio Domingo Savio S.A.C. por el Grupo Conti2000, en la asignatura Construcción de Software. Este README resume el avance presentado en el Sprint Review parcial de la semana 12 (2026-I, Cusco).

El problema abordado es el control manual de asistencia y sus dificultades para validar estudiantes, calcular tardanzas y consultar la asistencia diaria. El repositorio implementa reglas de negocio en Python, persistencia ORM con SQLAlchemy y pruebas automatizadas. Sobre esa base se incorporó una **primera versión web funcional con Flask, Jinja2, HTML, CSS y JavaScript**, con datos ficticios de demostración. La integración activa de WhatsApp permanece pendiente.

## Integrantes y roles

- **Gari Joel Chavez Huanca:** Product Owner / Scrum Master; backlog, coordinación del flujo de trabajo y revisión de PR.
- **Yhovana Quispe Ccolqquere:** Lead Backend Engineer; dominio, asistencia, tardanzas y pruebas.
- **Eduardo Luna Lezano:** Database & ORM Specialist; modelo de datos, SQLAlchemy y fixtures.
- **Dudu Fabiano Lizarzaburu Flores:** Frontend & UX/UI Engineer; wireframes de asistencia y dashboard, e interfaz/documentación técnica.
- **Jacob Luna Basilio:** DevOps & QA Engineer; GitHub Actions, Ruff, Pytest y cobertura.

## Alcance y estado del backlog

El alcance principal del Sprint 1 comprende los PBI-01, PBI-02 y PBI-03, junto con la persistencia ORM.

| ID | Capacidad | Estado según el informe |
|---|---|---|
| PBI-01 | Registro unificado de asistencia por carnet, DNI o búsqueda asistida; puntualidad y tardanza; control de duplicados. | Completado |
| PBI-02 | Gestión de cuentas y credenciales, exclusiva para ADMIN; contraseñas protegidas con PBKDF2-HMAC-SHA256 y baja lógica. | Completado |
| PBI-03 | Dashboard de aforo global y por salón; cierre automático para registrar ausencias. | Completado |
| Persistencia ORM | Modelos SQLAlchemy y relaciones para usuarios, estudiantes, asistencias y justificaciones; pruebas con SQLite en memoria. | Incluida en Sprint 1 |
| PBI-04 | Justificaciones escolares, categorías, motivos y reversión; requiere período académico abierto. | Dominio e interfaz web implementados |
| PBI-15 | Control de acceso basado en roles y validaciones de autorización. | RBAC aplicado en servidor y navegación |
| PBI-16 | Auditoría inmutable con persistencia append-only. | Planificado para Sprint 2 |
| PBI-17 | Notificaciones a apoderados mediante un flujo desacoplado. | Planificado para Sprint 2 |

Los roles oficiales del sistema son **ADMIN**, **COORDINADOR** y **ADMIN_STAFF**. ADMIN es el único autorizado para gestionar cuentas y configurar la hora oficial de cierre.

## Calidad y verificación

El informe original registra **61 pruebas automatizadas**. La versión web añade **17 pruebas de integración Flask**, para un total actual de **78 pruebas en verde**, y `ruff check .` sin errores. El workflow de GitHub Actions ejecuta Ruff y Pytest con cobertura en Python 3.11.

## Interfaz web (demostración)

La aplicación Flask reutiliza los servicios de dominio y añade una capa de aplicación y repositorios. Incluye cinco pantallas:

1. Inicio de sesión con RBAC.
2. Registro unificado de asistencia (PBI-01).
3. Dashboard de aforo y cierre escolar (PBI-03).
4. Gestión de justificaciones (PBI-04).
5. Gestión de usuarios (PBI-02 / PBI-15).

```bash
python -m pip install -r requirements.txt
python run.py
```

Acceso local: `http://127.0.0.1:5000`

Credenciales de demostración: `admin_general` / `DemoSavio2026!` (también `coord_secundaria` y `jluna_qa`, misma contraseña).

La guía completa —instalación, reinicio de datos, credenciales, pantallas, decisiones y limitaciones— está en [`docs/GUIA_EJECUCION_WEB.md`](docs/GUIA_EJECUCION_WEB.md).

## Funcionalidades implementadas

- **Asistencia (PBI-01):** registra estudiantes activos por carnet, DNI o búsqueda asistida. Considera puntual el ingreso hasta las 07:15 y calcula la tardanza a partir de ese límite; impide duplicados del mismo día y contempla corrección de ausencias con motivo.
- **Cuentas (PBI-02):** permite al ADMIN crear, modificar, desactivar, reactivar y consultar cuentas, y restablecer credenciales. Las contraseñas se protegen mediante PBKDF2-HMAC-SHA256.
- **Aforo (PBI-03):** calcula métricas globales y por salón y contempla el cierre automático de la jornada.
- **Persistencia:** SQLAlchemy 2.0 con modelos tipados, relaciones 1:N y eliminación en cascada. Las pruebas ORM usan SQLite en memoria con claves foráneas activadas.
- **Interfaz web:** Flask + Jinja2 con las cinco pantallas solicitadas, navegación por roles, validaciones en línea, datos de demostración y persistencia SQLite local.
- **Capacidades en desarrollo:** PBI-04 y PBI-15 cuentan con dominio, pruebas e interfaz web; la auditoría completa (PBI-16) y las notificaciones (PBI-17) siguen pendientes.
- **Integraciones planificadas:** el envío de notificaciones por WhatsApp está previsto para Sprint 2. El dominio genera el evento, pero no existe un adaptador de envío activo.

## Estructura del proyecto

```text
Proyecto_-de_gestion_administrativa_de_colegio/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   ├── dominio/
│   │   ├── aforo.py
│   │   ├── asistencia.py
│   │   ├── justificaciones.py
│   │   └── usuarios.py
│   ├── aplicacion/
│   │   └── casos_uso.py
│   ├── infraestructura/
│   │   ├── modelos.py
│   │   ├── repositorios.py
│   │   ├── base_datos.py
│   │   └── datos_demo.py
│   └── presentacion/
│       ├── app.py
│       ├── rutas.py
│       ├── seguridad.py
│       ├── tiempo.py
│       ├── templates/
│       └── static/
├── tests/
│   ├── conftest.py
│   ├── test_aforo_justificaciones.py
│   ├── test_asistencia_unificada.py
│   ├── test_persistencia_orm.py
│   ├── test_usuarios_rbac.py
│   └── test_web.py
├── docs/
│   └── GUIA_EJECUCION_WEB.md
├── run.py
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Capas

- `src/dominio/` contiene entidades, reglas de negocio y servicios de dominio. No depende de una base de datos ni de Flask.
- `src/aplicacion/` coordina casos de uso entre el dominio y los repositorios.
- `src/infraestructura/` define los modelos ORM, traduce entre ORM y dominio, configura SQLite y siembra datos de demostración.
- `src/presentacion/` contiene la aplicación Flask, rutas delgadas, plantillas y recursos estáticos.
- `tests/` contiene pruebas de dominio, persistencia e integración web. La fixture de base de datos utiliza SQLite en memoria y activa la verificación de claves foráneas.

## Requisitos

- Python 3.11 o superior.
- Dependencias declaradas en `requirements.txt`: Flask, SQLAlchemy, pytest, pytest-cov y Ruff.

## Instalación y ejecución

Desde la raíz del proyecto:

```bash
# Instalar dependencias
python -m pip install -r requirements.txt

# Iniciar la aplicación web
python run.py

# Ejecutar las pruebas
python -m pytest -v

# Ejecutar las pruebas con cobertura
python -m pytest -v --cov=src --cov-report=term-missing

# Revisar el estilo y errores estáticos
python -m ruff check .
```

La configuración de Ruff y pytest se encuentra en `pyproject.toml`. La integración continua de GitHub Actions ejecuta Ruff y las pruebas con cobertura en Python 3.11.

