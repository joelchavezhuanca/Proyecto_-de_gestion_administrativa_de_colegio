# Guía de ejecución y presentación web

**Sistema de Gestión Administrativa — Colegio Domingo Savio S.A.C.**
Primera versión web construida sobre el dominio, los servicios y las pruebas existentes del repositorio.

---

## 1. Requisitos previos

- Python 3.11 o superior (probado con Python 3.14 en Windows).
- Git (opcional, solo para revisar la rama).
- Un navegador actualizado.
- Conexión a Internet opcional: solo se usa para cargar la tipografía Hanken Grotesk desde Google Fonts. Si no hay conexión, el sistema utiliza una tipografía de respaldo.

## 2. Instalación

Desde la raíz del repositorio:

```bash
python -m pip install -r requirements.txt
```

Dependencias declaradas:

| Dependencia | Uso |
|---|---|
| `Flask>=3.1.0` | Servidor web, rutas y plantillas Jinja2 |
| `SQLAlchemy>=2.0.0` | Persistencia ORM existente y SQLite de demostración |
| `pytest`, `pytest-cov` | Pruebas automatizadas |
| `ruff` | Inspección estática |
| `html5-qrcode` 2.3.8 | Lectura de QR en el navegador, incluida localmente en `src/presentacion/static/js/vendor/` (Apache 2.0) |

No se añadió SQLAlchemy: ya existía. Solo se incorporó Flask, requerido por la especificación de interfaces web. La librería QR se sirve como archivo estático local; no requiere CDN ni envía video al backend.

## 3. Iniciar la aplicación

```bash
python run.py
```

Dirección local:

```text
http://127.0.0.1:5000
```

También puede usarse:

```bash
flask --app run run --port 5000
```

Para cambiar host, puerto o depuración:

```powershell
$env:FLASK_PORT="5000"
$env:FLASK_DEBUG="0"
python run.py
```

> La depuración está desactivada por defecto. No active `FLASK_DEBUG=1` durante una presentación.

## 4. Credenciales de demostración

La base se inicializa automáticamente con cuentas ficticias:

| Usuario | Rol | Contraseña |
|---|---|---|
| `admin_general` | ADMIN | `DemoSavio2026!` |
| `coord_secundaria` | COORDINADOR | `DemoSavio2026!` |
| `jluna_qa` | ADMIN_STAFF | `DemoSavio2026!` |

Las contraseñas se almacenan con **PBKDF2-HMAC-SHA256 + salt**. Nunca se guardan en texto plano.

La pantalla de inicio de sesión muestra estas credenciales identificadas como datos de demostración.

## 5. Datos de demostración y reinicio

- La base local se crea en `instance/colegio_demo.db`.
- La carpeta `instance/` y los archivos `*.db` están excluidos de Git.
- Al iniciar con una base vacía se siembran:
  - 3 cuentas de usuario.
  - 44 alumnos ficticios distribuidos en Primaria y Secundaria.
  - Asistencias de la fecha de inicialización (puntuales, tardanzas, ausentes y justificados).
  - Una jornada anterior como historial.
  - Período académico 2026 abierto y período 2025 cerrado.
  - Hora oficial de cierre: `08:30`.
- La interfaz muestra una banda permanente que advierte que los datos son ficticios.

### Reiniciar los datos

Detenga el servidor y elimine la base local:

```powershell
Remove-Item .\instance\colegio_demo.db
python run.py
```

La base se vuelve a sembrar con la fecha actual del servidor.

> Si la base se conserva durante varios días, la fecha "hoy" puede no tener asistencias sembradas. Reinicie los datos antes de una presentación.

## 6. Las cinco pantallas

### 6.1. Inicio de sesión
- Logotipo horizontal y escudo institucionales originales, sin modificaciones.
- Usuario, contraseña, botón para mostrar/ocultar la clave.
- Validación en línea y banner de error sin borrar los campos.
- Redirección al dashboard después del login.
- Credenciales de demostración visibles y etiquetadas.

### 6.2. Registro de asistencia (PBI-01)
- Tres modos con control segmentado: carnet, manual por DNI y búsqueda asistida.
- Carnet: subselector entre **Pistola / Escáner USB** y **Cámara del dispositivo**.
- Cámara: lectura de QR 100 % en el navegador con `html5-qrcode` 2.3.8 (archivo local). En móviles prioriza la cámara trasera (`environment`); en laptops, la cámara frontal (`user`). Permite elegir entre las cámaras detectadas.
- Debounce: al leer un QR se detiene la cámara de inmediato y se evita el doble envío. La tarjeta de confirmación incluye botón y cuenta regresiva de 8 segundos para "Escanear siguiente".
- La cámara se apaga al cambiar de pestaña del navegador, cambiar de modo/lector o abandonar el módulo.
- Manual por DNI: asistente DNI → alumno verificado → confirmación.
- Búsqueda: asistente buscar → seleccionar → confirmación; solo muestra alumnos `ACTIVO`.
- La puntualidad y la tardanza las calcula `registrar_asistencia_unificada()` en `src/dominio/asistencia.py` con la hora del servidor.
- El campo de motivo de corrección **no** aparece en la vista normal. Solo se despliega si el backend detecta que el alumno figura `AUSENTE` y exige el motivo para actualizar su estado.
- Errores del dominio (`RegistroDuplicadoException`, `FaltaMotivoCorreccionException`, etc.) se muestran en pantalla y no borran la entrada.
- Tabla de últimos registros confirmados.
- La interfaz no calcula estados ni tardanzas.

### 6.3. Dashboard de aforo (PBI-03)
- Filtros por fecha, nivel, grado y sección.
- Indicadores: matriculados, presentes, tardanzas, ausentes, justificados, pendientes, aforo actual y porcentaje.
- Barras de progreso y desglose por salón (nivel + grado + sección).
- Hora de cierre configurable solo por `ADMIN` (RN-17).
- Cierre escolar diario con modal defensivo y casilla obligatoria.
- El cálculo proviene de `ServicioAforo.calcular_metricas()` y `ejecutar_cierre_automatico()`.
- Estado vacío cuando no hay alumnos en el ámbito consultado.

### 6.4. Justificaciones (PBI-04)
- Listado de ausencias y tardanzas de la fecha seleccionada.
- Asistente de tres pasos: alumno → categoría/motivo → revisión.
- Tarjeta de contexto del estudiante visible en los pasos 2 y 3: nombre, código/DNI, nivel-grado-sección y estado original (`TARDANZA` con minutos o `AUSENTE` con hora).
- El botón "Justificar" de la tabla sincroniza el selector, completa la tarjeta y avanza al paso 2.
- Categorías oficiales: `MEDICA`, `PERMISO_FAMILIAR`, `OTRA`.
- Fecha limitada al día actual; motivo mínimo de 10 caracteres.
- Resumen del cambio `AUSENTE`/`TARDANZA` → `JUSTIFICADO`.
- Historial de justificaciones y anulación con restauración del estado anterior.
- Acceso restringido a `ADMIN` y `ADMIN_STAFF`, conforme a `ServicioJustificaciones`.
- `COORDINADOR` recibe una página 403 si intenta acceder.

### 6.5. Gestión de usuarios (PBI-02 / PBI-15)
- Exclusiva para `ADMIN`.
- Listado y filtros por nombre, usuario, rol y estado.
- Asistente de creación en tres pasos: identidad → rol/estado → contraseña.
- Verificación de disponibilidad del nombre de usuario.
- Solo roles oficiales: `ADMIN`, `COORDINADOR`, `ADMIN_STAFF`.
- Detalle de cuenta con edición de nombre/rol, activación/desactivación y restablecimiento de credencial.
- Validaciones y auditoría de cada operación.

## 7. Integración con el proyecto existente

```text
src/
  dominio/                  Reglas puras existentes (sin cambios de comportamiento)
  aplicacion/
    casos_uso.py            Coordina dominio + repositorios
  infraestructura/
    modelos.py              Modelos ORM existentes + columnas/tablas mínimas
    repositorios.py         Traducción ORM ↔ objetos de dominio
    base_datos.py           Motor SQLite y fábrica de sesiones
    datos_demo.py           Semilla reproducible de demostración
  presentacion/
    app.py                  Fábrica Flask, sesión, contexto y errores
    rutas.py                Rutas delgadas por PBI
    seguridad.py            Decoradores de sesión y rol
    tiempo.py               Reloj institucional UTC-5
    templates/              Jinja2
    static/                 CSS, JavaScript y recursos institucionales
```

Reglas respetadas:

- Las rutas no ejecutan SQL ni calculan tardanzas, estados o porcentajes.
- Los repositorios son la única capa que conoce SQLAlchemy.
- Los servicios de dominio existentes se invocan tal como fueron probados.
- JavaScript solo gestiona interacción, validaciones de conveniencia y consultas al backend.
- Las columnas añadidas al ORM no eliminan ni renombran las existentes.

### Ajustes mínimos de persistencia

Se añadieron a `src/infraestructura/modelos.py`:

- `UsuarioModel.salt` y `UsuarioModel.nombre_completo` (necesarios para autenticar con el dominio).
- `JustificacionModel.codigo`, `fecha_solicitud`, `fecha_resolucion` y `documento_adjunto`.
- Tablas `periodos_academicos`, `configuracion`, `cierres_diarios` y `auditoria_eventos`.
- Restricción única por estudiante y fecha en asistencias.

Estos cambios son compatibles con las pruebas ORM existentes.

## 8. Pruebas y calidad

```bash
# Todas las pruebas
python -m pytest -v

# Cobertura
python -m pytest --cov=src --cov-report=term-missing

# Estilo
python -m ruff check .
```

Resultado de la implementación:

- `84 passed` (61 pruebas previas + 23 pruebas de integración web).
- `ruff check .` sin errores.

Las pruebas web están en `tests/test_web.py` y verifican login, protección de rutas, registro por carnet, duplicados, RBAC, justificaciones, alta y edición de usuarios, restablecimiento de credencial, cierre diario, rechazo de fechas futuras, respuesta JSON del flujo QR, exigencia de motivo para corregir `AUSENTE`, ausencia del campo de motivo en la vista normal y tarjeta de contexto del wizard.

## 9. Decisiones y limitaciones conocidas

1. **Cierre diario reservado a ADMIN.** La especificación reserva la configuración de la hora al ADMIN, pero no detalla el rol del botón de cierre. Se optó por la opción conservadora: una acción irreversible que marca ausencias solo la ejecuta `ADMIN`. La interfaz lo informa.
2. **Lectura por cámara sujeta a permisos y hardware.** El modo cámara requiere que el navegador permita el acceso al dispositivo y que el equipo tenga una cámara disponible. La lectura de QR trabaja en el cliente; si la librería local no carga, se informa en pantalla. El escáner USB sigue disponible como alternativa.
3. **Notificaciones WhatsApp no implementadas.** El dominio genera `EventoAsistenciaConfirmada`, pero no se envía nada. PBI-17 sigue pendiente.
4. **Auditoría mínima.** Se persiste una bitácora append-only básica en `auditoria_eventos`; no sustituye la implementación completa de PBI-16.
5. **Sin CSRF explícito.** La aplicación está pensada para ejecución local de demostración. Antes de un despliegue real debe añadirse protección CSRF, cookies seguras y una `SECRET_KEY` propia.
6. **SQLite de demostración.** No se migra ni reemplaza una persistencia productiva. La base es local y desechable.
7. **Datos ficticios.** Toda la información sembrada está identificada como demostración en la interfaz y en esta guía.
8. **Zona horaria fija UTC-5.** Corresponde a America/Lima, sin horario de verano. El servidor es la fuente oficial de hora.
9. **Edición de contraseña.** La política web exige mínimo 8 caracteres y combinación de letras/números; el dominio conserva su validación mínima de 6 para no alterar sus pruebas.

## 10. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: flask` | Dependencias no instaladas | `python -m pip install -r requirements.txt` |
| La base no tiene datos de hoy | Se conserva una base de días anteriores | Elimine `instance/colegio_demo.db` y reinicie |
| Error de columna faltante | Base creada con una versión anterior | Elimine `instance/colegio_demo.db` y reinicie |
| La tipografía se ve distinta | Sin conexión a Google Fonts | Es normal; se usa una fuente de respaldo |
| El cierre no aparece | El usuario no es ADMIN | Ingrese con `admin_general` |
| Justificaciones da 403 | El usuario es COORDINADOR | Use `admin_general` o `jluna_qa` |

## 11. Presentación sugerida (5 minutos)

1. Iniciar sesión con `admin_general`.
2. Mostrar el dashboard con indicadores y filtros.
3. Ir a Asistencia y registrar un alumno sugerido en el panel "Ayuda para la demostración".
4. Intentar registrar el mismo carnet para evidenciar el rechazo por duplicado.
5. Ir a Justificaciones, seleccionar una ausencia, completar el asistente y mostrar el cambio a `JUSTIFICADO`.
6. Ir a Usuarios, crear una cuenta y mostrar la disponibilidad de username y la fortaleza de contraseña.
7. Volver al dashboard y mostrar el modal de cierre (sin ejecutarlo si no desea modificar los datos).
