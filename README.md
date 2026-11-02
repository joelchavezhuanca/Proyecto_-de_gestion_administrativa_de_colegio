# Sistema de Control de Asistencia en Tiempo Real
## Entidad Aliada: Domingo Savio S.A.C.
**Asignatura:** Construcción de Software | **Equipo de Desarrollo:** Conti2000  

---

### Integrantes y Roles Técnicos:
- **Product Owner / Scrum Master:** Gari Joel Chavez Huanca (75082495)
- **Git Master & Lead Backend / Database:** Eduardo Luna Lezano (72945734)
- **Frontend & UX/UI Engineer:** Dudú Fabiano Lizarzaburu Flores (73299606)
- **DevOps & QA Engineer:** Rodrigo Huarancca Ccori (72229789)

---

### Estructura del Proyecto (Clean Architecture / Fase 2):
```text
mi-proyecto-software/
│
├── .github/
│   └── workflows/
│       └── ci.yml                 <-- Workflow de GitHub Actions (Ruff + Pytest)
│
├── src/                           <-- Código fuente de la aplicación
│   ├── __init__.py
│   └── dominio/                   <-- Capa de Reglas de Negocio Puras
│       └── __init__.py
│
├── tests/                         <-- Suite de Pruebas Automatizadas
│   └── __init__.py
│
├── .gitignore                     <-- Exclusión de temporales
├── pyproject.toml                 <-- Configuración de Ruff y Pytest
├── requirements.txt               <-- pytest, ruff, pytest-cov
└── README.md
```

---

### Comandos Rápidos de Terminal:
```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Inspección estática de código con Ruff (0 errores)
python -m ruff check .

# 3. Ejecución de pruebas con Pytest
python -m pytest -v
```
