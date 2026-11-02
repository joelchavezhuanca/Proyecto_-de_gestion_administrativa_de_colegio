# Sistema de Control de Asistencia y Gestión Administrativa

Proyecto integrador desarrollado para el Colegio Domingo Savio S.A.C. por el Grupo Conti2000, en la asignatura Construcción de Software. Este README resume el avance presentado en el Sprint Review parcial de la semana 12 (2026-I, Cusco).

El problema abordado es el control manual de asistencia y sus dificultades para validar estudiantes, calcular tardanzas y consultar la asistencia diaria. El repositorio implementa reglas de negocio en Python, persistencia ORM con SQLAlchemy y pruebas automatizadas. Los wireframes del informe son prototipos: el repositorio no incluye una interfaz web ni una API. Tampoco cuenta todavía con integración activa de WhatsApp.

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
| PBI-04 | Justificaciones escolares, categorías, motivos y reversión; requiere período académico abierto. | En progreso |
| PBI-15 | Control de acceso basado en roles y validaciones de autorización. | Integrado parcialmente; en progreso |
| PBI-16 | Auditoría inmutable con persistencia append-only. | Planificado para Sprint 2 |
| PBI-17 | Notificaciones a apoderados mediante un flujo desacoplado. | Planificado para Sprint 2 |

Los roles oficiales del sistema son **ADMIN**, **COORDINADOR** y **ADMIN_STAFF**. ADMIN es el único autorizado para gestionar cuentas y configurar la hora oficial de cierre.

## Calidad y verificación

El informe registra **61 pruebas automatizadas**, **100 % de cobertura sobre 486 sentencias** y una ejecución de Ruff sin errores. Son resultados documentados para el Sprint Review y deben confirmarse con una ejecución actualizada. El workflow de GitHub Actions ejecuta Ruff y Pytest con cobertura en Python 3.11.

## Funcionalidades implementadas

- **Asistencia (PBI-01):** registra estudiantes activos por carnet, DNI o búsqueda asistida. Considera puntual el ingreso hasta las 07:15 y calcula la tardanza a partir de ese límite; impide duplicados del mismo día y contempla corrección de ausencias con motivo.
- **Cuentas (PBI-02):** permite al ADMIN crear, modificar, desactivar, reactivar y consultar cuentas, y restablecer credenciales. Las contraseñas se protegen mediante PBKDF2-HMAC-SHA256.
- **Aforo (PBI-03):** calcula métricas globales y por salón y contempla el cierre automático de la jornada.
- **Persistencia:** SQLAlchemy 2.0 con modelos tipados, relaciones 1:N y eliminación en cascada. Las pruebas ORM usan SQLite en memoria con claves foráneas activadas.
- **Capacidades en desarrollo:** el código incluye avances para justificaciones y RBAC, pero el informe clasifica PBI-04 y PBI-15 como incompletos.
- **Integraciones planificadas:** la auditoría persistente append-only y el envío de notificaciones por WhatsApp están previstos para Sprint 2; los eventos existentes no implican que esas integraciones estén desplegadas.

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
│   └── infraestructura/
│       └── modelos.py
├── tests/
│   ├── conftest.py
│   ├── test_aforo_justificaciones.py
│   ├── test_asistencia_unificada.py
│   ├── test_persistencia_orm.py
│   └── test_usuarios_rbac.py
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Capas

- `src/dominio/` contiene entidades, reglas de negocio y servicios de dominio. No depende de una base de datos.
- `src/infraestructura/modelos.py` define las entidades y relaciones ORM con SQLAlchemy 2.
- `tests/` contiene pruebas de las reglas de dominio y de persistencia. La fixture de base de datos utiliza SQLite en memoria y activa la verificación de claves foráneas.

## Requisitos

- Python 3.11 o superior.
- Dependencias declaradas en `requirements.txt`: pytest, pytest-cov, Ruff y SQLAlchemy.

## Instalación y ejecución

Desde la raíz del proyecto:

```bash
# Instalar dependencias
python -m pip install -r requirements.txt

# Ejecutar las pruebas
python -m pytest -v

# Ejecutar las pruebas con cobertura
python -m pytest -v --cov=src --cov-report=term-missing

# Revisar el estilo y errores estáticos
python -m ruff check .
```

La configuración de Ruff y pytest se encuentra en `pyproject.toml`. La integración continua de GitHub Actions ejecuta Ruff y las pruebas con cobertura en Python 3.11.
