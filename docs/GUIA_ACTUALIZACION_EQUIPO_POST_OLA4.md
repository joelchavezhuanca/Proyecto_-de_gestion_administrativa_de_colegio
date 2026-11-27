# Guía de Actualización del Proyecto para el Equipo (Post-Ola 4 → Producción v1.0)

**Proyecto:** Sistema de Control de Asistencia y Gestión Administrativa — Colegio Domingo Savio S.A.C. (Grupo Conti2000)  
**Producción en vivo (HTTPS):** https://proyecto-de-gestion-administrativa-de.onrender.com  
**Repositorio:** https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio  
**Fecha:** 27/11/2026

> Esta guía explica en lenguaje directo **todo lo que se agregó y corrigió en el repositorio después de cerrar los 5 Blueprints de la Ola 4** (donde quedó la última sincronización grupal), cómo usar y actualizar la página en producción, cómo funcionan los datos ficticios de demostración y qué debe saber cualquier integrante antes del Sprint Review final.

---

## 1. Resumen rápido: qué cambió después de la Ola 4

Cuando cerramos la Ola 4 (`PR #42` al `PR #46`), teníamos todos los 17 PBIs y los 5 Blueprints Flask funcionando en pruebas, pero faltaban piezas clave para **levantar el sistema de verdad, cumplir la rúbrica final (ATDD + Docker CI) y publicarlo en producción**. Todo eso se integró en orden mediante 6 Pull Requests en verde:

| PR | Rama / Fase | Qué se agregó exactamente |
|---|---|---|
| **#47** | `fix/ajuste-tests-inicio-seguridad` | Ajuste de aserciones en `tests/test_web_seguridad.py` tras conectar el módulo de reportes y la fábrica `app.py` completa. |
| **#48** | **Fase 1:** `feat/fase1-navegacion-y-admin-inicial` | **1) Siembra automática del usuario `admin` inicial** (`sembrar_admin_inicial` en `src/infraestructura/base_datos.py`) leyendo `ADMIN_USERNAME` y `ADMIN_PASSWORD` desde variables de entorno (idempotente: nunca duplica ni sobreescribe si ya existe un admin). **2) Barra lateral RBAC completa** en `src/presentacion/templates/base.html`: ahora el menú muestra dinámicamente los módulos según los 28 permisos del usuario logueado (Asistencia, Aforo, Justificaciones, Períodos, Alumnos/Matrícula, Carnets, Pagos, Estados, Malla, Docentes, Calificaciones, Ficha, Exportar, Boletas, Usuarios, Roles, Auditoría). |
| **#49** | **Fase 2:** `feature/fase2-atdd-ci-docs` | **1) Pruebas ATDD con `pytest-bdd`** para los **2 flujos críticos ★** exigidos por la rúbrica (`tests/acceptance/features/pbi01_registro_asistencia.feature` y `pbi10_calificaciones.feature` + sus step definitions, con historial `ATDD → RED → GREEN → REFACTOR`). **2) Rama `dev`** sincronizada con `main`. **3) CI actualizado** (`.github/workflows/ci.yml`): ahora verifica `ruff check .`, `ruff format --check .`, `pytest -v tests/acceptance` y cobertura obligatoria **`--cov-fail-under=70`** midiendo solo `src/dominio`, `src/aplicacion` y `src/infraestructura` (excluyendo `src/presentacion`). **4) Plantilla oficial de PR** (`.github/pull_request_template.md` con la DoD) y **Product Vision Board** (`docs/vision-board.md`). |
| **#51** | **Fase 3 / Instructivo N° 05:** `feature/docker-ci` | **Contenerización completa + Docker CI:** `Dockerfile` (Python 3.11-slim + Gunicorn en `0.0.0.0:$PORT`), `.dockerignore`, `docker-compose.yml` (`name: domingo-savio`, servicio **`app`** en puerto `5000` con volumen persistente `./datos_locales:/app/data` y servicio **`pruebas`** con `profiles: ["pruebas"]` aislado en memoria), `wsgi.py`, `.env.example`, endpoint `GET /health`, `ProxyFix` + `SESSION_COOKIE_SECURE` en producción, normalización automática `postgresql://` → `postgresql+psycopg://` (PostgreSQL en producción / SQLite en local), y workflow **`.github/workflows/docker-ci.yml`** que construye la imagen, corre las pruebas dentro del contenedor y verifica `http://localhost:5000/health`. |
| **#52** | `feature/ui-asistencia-qr` | **Porte quirúrgico del Registro Unificado + Escáner QR** desde `fix/mejora-ui` sobre `main` (sin perder nada de los 17 PBIs): panel de cámara web QR en `asistencia.html` + `asistencia.js` usando la librería local `html5-qrcode.min.js`, entrada unificada inteligente (auto-detecta Carnet/QR, DNI de 8 dígitos o búsqueda por nombre), nuevo endpoint protegido `GET /api/alumnos`, tabla en vivo **"Últimos registros de hoy"** y corrección condicional cuando el alumno figura `AUSENTE`. |
| **#53** | `feature/semilla-datos-demo` | **Semilla opcional realista** (`src/infraestructura/semilla_demo.py`): activada **solo** si `SEMBRAR_DATOS_DEMO=true` (apagada por defecto para no afectar tests ni producción limpia). Carga automáticamente e idempotentemente cifras estimadas reales del colegio (220 alumnos, 11 salones, 33 cursos, 1,980 notas, 440 pensiones y ~1,070 asistencias). |
| **Cierre CD** | `feature/cierre-cd-docs-v1` | Workflow **`.github/workflows/deploy-render.yml`** (despliegue continuo y botón manual en GitHub Actions hacia Render), `README.md` actualizado con producción, esta guía para el equipo y el Informe Final v1.0 actualizado. |

---

## 2. Cómo funciona la página en Producción (Render.com)

La aplicación ya está publicada y verificada en internet con **HTTPS** y base de datos **PostgreSQL** gestionada:

- **URL principal:** https://proyecto-de-gestion-administrativa-de.onrender.com
- **Pantalla de Registro Unificado + QR:** https://proyecto-de-gestion-administrativa-de.onrender.com/asistencia
- **Verificación de estado (Healthcheck):** https://proyecto-de-gestion-administrativa-de.onrender.com/health → devuelve `{"status": "ok"}`

### Aspectos clave que todos deben saber sobre Render Free
1. **Despertar tras inactividad (~30–50 s):** En el plan gratuito de Render, si nadie entra durante 15 minutos, el contenedor se suspende automáticamente. Al abrir la URL de nuevo, tarda entre 30 y 50 segundos en despertar; luego responde rápido. **Antes de exponer al profesor, abran la URL 2 minutos antes** para que ya esté despierta.
2. **Los datos NO se pierden al dormir o re-desplegar:** La base de datos vive en un servicio PostgreSQL independiente (`domingo-savio-db`).
3. **La cámara QR funciona en celular y laptop gracias a HTTPS:** Los navegadores bloquean la cámara en sitios HTTP no locales, pero como Render sirve en **HTTPS**, el lector QR de `/asistencia` funciona directamente desde cualquier laptop o smartphone.

---

## 3. Cómo funcionan los datos ficticios (realistas) de la presentación

Para la exposición final, el sistema tiene activada en Render la variable de entorno **`SEMBRAR_DATOS_DEMO=true`**.

### Cómo opera internamente
- Al iniciar la app (`inicializar_bd` en `src/infraestructura/base_datos.py`), revisa `SEMBRAR_DATOS_DEMO`.
- Si vale **`false`** o no existe (por defecto en pruebas `pytest`, en CI y en uso real limpio): **NO inyecta nada**.
- Si vale **`true`**: ejecuta `sembrar_datos_demo()` **una sola vez** (verifica si ya hay alumnos en BD; si ya existen, no duplica nada ni borra lo que registren en vivo).
- **Para apagarlo después de la exposición:** en Render solo se borra la variable `SEMBRAR_DATOS_DEMO` (o se pone en `false`) sobre una base de datos limpia; no hay que modificar código.

### Cifras realistas cargadas automáticamente
- **11 salones (año 2026):** Primaria `1ro–6to A` (6 aulas) y Secundaria `1ro–5to A` (5 aulas), capacidad 30 vacantes por aula.
- **220 alumnos con apoderados y carnets QR** (`ALU-2026-0001` al `ALU-2026-0220`, DNIs `72100001` al `72100220`, carnets `CRN-2026-0001` al `CRN-2026-0220`):
  - **216 `ACTIVO`**, **2 `SUSPENDIDO`** (`CRN-2026-0217`, `CRN-2026-0218`), **2 `RETIRADO`** (`CRN-2026-0219`, `CRN-2026-0220`, carnet anulado).
- **33 cursos + 33 asignaciones docentes** (Matemática, Comunicación y Ciencia y Tecnología en los 11 grados), **2 períodos** (`Bimestre III` cerrado + `Bimestre IV` abierto) y **1,980 notas vigesimales** (`10.5` a `19.5`) listas para consultar **Calificaciones**, **Boletas** y **Ficha del alumno**.
- **440 obligaciones de pago** (`S/ 320.00` Primaria / `S/ 360.00` Secundaria) con ~12 % de morosidad y **alertas silenciosas** visibles en Pagos.
- **~1,070 registros de asistencia** (últimos 4 días lectivos + hoy, ~90 % asistencia en el Dashboard de Aforo + 6 justificaciones aprobadas).

### Cuentas listas para demostrar RBAC en la exposición
| Usuario | Contraseña | Rol | Qué demuestra en vivo |
|---|---|---|---|
| `admin` | `DomingoSavio2026!` *(en Render)* / `Admin2026!` *(en Docker local)* | `ADMIN` | Acceso total a los 17 módulos, roles, auditoría SHA-256 y configuración. |
| `coordinador_demo` | `Demo2026!` | `COORDINADOR` | Asistencia, aforo, justificaciones, reportes y ficha (sin gestión de usuarios). |
| `staff_demo` | `Demo2026!` | `ADMIN_STAFF` | Matrícula, carnets, pagos (con alertas silenciosas) y asistencia. |
| `auxiliar_puerta` | `Demo2026!` | `AUXILIAR` *(personalizado)* | Solo portería QR (`/asistencia`) y consulta de aforo (`/aforo`). |
| `docente_mat` / `docente_com` / `docente_cyt` | `Demo2026!` | `DOCENTE` *(personalizado)* | Calificaciones solo en su área/salón asignado (403 en cursos ajenos). |

### Carnets QR preparados para escanear EN VIVO frente al docente
Pueden generar un código QR en cualquier generador online (ej. con el texto exacto `CRN-2026-0001`) y mostrarlo desde un celular a la cámara web en `/asistencia`:

- **`CRN-2026-0001` al `CRN-2026-0008`:** alumnos activos **pendientes hoy** → escaneo normal que registra ingreso al instante y actualiza la tabla del día y el aforo.
- **`CRN-2026-0009`:** figura **`AUSENTE`** hoy → al escanearlo abre automáticamente el panel de **corrección condicional con motivo**.
- **`CRN-2026-0010`:** alumno activo **con pensión vencida** → ingresa **sin bloqueo** en portería y genera una **alerta silenciosa** visible solo en el módulo de Pagos (PBI-07).
- **`CRN-2026-0217`:** alumno **`SUSPENDIDO`** → el sistema **bloquea el ingreso** (PBI-08).

---

## 4. Cómo actualizar el código y publicar cambios en Producción

### Paso A — Flujo obligatorio en GitHub (para cualquier cambio)
1. **Sincroniza primero tu PC:**
   ```bash
   git fetch --all --prune
   git switch main
   git pull origin main
   ```
2. **Crea una rama desde `main`** (nunca subas commits directos a `main`):
   ```bash
   git switch -c fix/mi-cambio
   ```
3. **Edita, formatea y valida localmente antes de subir:**
   ```bash
   python -m ruff check .
   python -m ruff format --check .
   python -m pytest -v
   ```
4. **Sube tu rama y abre un Pull Request hacia `main`** completando el checklist de la DoD.
5. **Espera a que los dos workflows queden en verde:**
   - `Continuous Integration - Domingo Savio S.A.C.` (Ruff + ATDD + Pytest + Cobertura ≥ 70 %)
   - `Docker CI` (build + pruebas dentro del contenedor + smoke test `/health`)
6. El Product Owner aprueba y hace **Merge pull request** a `main`.

### Paso B — Cómo se actualiza la página en Render.com
Existen dos caminos (sin compartir contraseñas de Render):

1. **Despliegue automático y botón manual desde GitHub Actions (Recomendado — configurar 1 sola vez por el dueño del repo `joelchavezhuanca`):**
   - El workflow `.github/workflows/deploy-render.yml` ya está en el repositorio.
   - El dueño del repo (`joelchavezhuanca`) solo entra a GitHub → **Settings → Secrets and variables → Actions → New repository secret**:
     - **Name:** `RENDER_DEPLOY_HOOK_URL`
     - **Secret:** *(el enlace secreto del Deploy Hook que Eduardo pasó por privado — nunca se guarda en el código)*
   - A partir de ese momento:
     - **Cada merge a `main` actualiza Render automáticamente.**
     - Además, **cualquier integrante** puede ir a **Actions → Deploy a Producción (Render) → Run workflow** para forzar un despliegue manual cuando Eduardo no esté disponible.
2. **Manual desde el panel de Render** (si Eduardo está conectado):
   - En Render → Web Service → arriba a la derecha: **`Manual Deploy` → `Deploy latest commit`**.

> **Precaución importante sobre cambios de base de datos:** Los cambios en vistas HTML, CSS, JS, rutas Flask y lógica Python se publican sin problema y conservan todos los datos de PostgreSQL. Si algún día se agregan **columnas nuevas** a tablas ya existentes en `src/infraestructura/modelos.py`, recuerden que `Base.metadata.create_all()` crea tablas nuevas pero no altera columnas existentes (en ese caso habría que aplicar un `ALTER TABLE` o recrear la BD de pruebas).

---

## 5. Cómo levantar el proyecto en tu propia PC (para ensayar o para el Sprint Review)

### Opción 1 — Con Docker Desktop *(forma oficial del Sprint Review)*
Requisito: Docker Desktop abierto y en ejecución (*Engine running*). Clonar siempre en una ruta local fuera de OneDrive (ej. `C:\proyectos`).

```bash
git clone https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio.git
cd Proyecto_-de_gestion_administrativa_de_colegio

# 1. Ejecutar todas las pruebas aisladas dentro del contenedor (sin tocar datos reales)
docker compose --profile pruebas run --rm pruebas

# 2. Levantar la aplicación web en http://localhost:5000 (usuario admin / Admin2026!)
docker compose up -d --build

# 3. Apagar cuando termines (los datos persisten en ./datos_locales/colegio.db)
docker compose down
```
*(Si además quieres ensayar con los 220 alumnos demo en tu Docker local, crea un archivo `.env` en la raíz con `SEMBRAR_DATOS_DEMO=true` antes de levantar `docker compose up -d --build`).*

### Opción 2 — En Python local sin Docker
```bash
python -m pip install -r requirements.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -v --cov=src/dominio --cov=src/aplicacion --cov=src/infraestructura --cov-fail-under=70
```

---

## 6. Checklist rápido para cada integrante antes de la sustentación
- [ ] Ejecutar `git fetch --all --prune && git switch main && git pull` en tu PC y comprobar con `git status` que estás limpio y sincronizado con `origin/main`.
- [ ] Probar al menos una vez `docker compose up -d --build` → entrar a `http://localhost:5000` → `docker compose down` → `docker compose up -d` para dominar la demo de persistencia del Cap. 8.2.
- [ ] Probar el enlace de producción https://proyecto-de-gestion-administrativa-de.onrender.com (login con `admin` y con un rol limitado como `auxiliar_puerta` o `docente_mat`).
- [ ] Repasar los flujos críticos ★ (**PBI-01 Asistencia QR** y **PBI-10 Calificaciones 3 niveles**) porque el docente selecciona el orden de sustentación al azar.
