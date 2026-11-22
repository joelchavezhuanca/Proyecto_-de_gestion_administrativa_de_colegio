# PBI-15: Control de Acceso Basado en Roles Dinámico (RBAC) y Sesiones

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-15` |
| **Rama Git a crear** | `feature/PBI-15-control-acceso-rbac` *(desde `main` — ejecutar justo después de `PBI-16`)* |
| **Estado actual en `main`** | Parcial en `src/dominio/usuarios.py` (solo 3 roles fijos en `RolUsuario` y 8 permisos). |
| **Dependencias** | `PBI-16` (Auditoría Inmutable). Base de seguridad para **todos los demás PBIs (01 al 17)**. |
| **Permisos requeridos** | `GESTIONAR_ROLES`, `ASIGNAR_ROLES`. |

---

## 1. Historia de Usuario
Como administrador con permiso `GESTIONAR_ROLES`, deseo crear y administrar **roles personalizados** asignándoles permisos específicos del catálogo oficial, y asegurar que el servidor valide sesiones vigentes y permisos en cada operación protegida.

---

## 2. Reglas de Negocio
- **RN-01 (Roles base del sistema):** Existen 3 roles predefinidos (`es_sistema = True`): `ADMIN`, `COORDINADOR`, `ADMIN_STAFF`. El rol `ADMIN` posee todos los permisos y **no puede eliminarse, desactivarse ni reducirse en permisos**.
- **RN-02 (Roles personalizados):** Un usuario con `GESTIONAR_ROLES` puede crear roles personalizados (`codigo` único normalizado en mayúsculas, `nombre`, `descripcion`, conjunto no vacío de permisos válidos de `PermisoOperacion`), modificar sus permisos, activar/desactivar y eliminar (solo si no tiene usuarios asignados).
- **RN-03 (Catálogo cerrado de permisos):** Solo se aceptan permisos declarados en `PermisoOperacion` (~28 permisos definidos en `docs/README.md`). Cualquier permiso desconocido se rechaza (*deny-by-default*).
- **RN-04 (Evaluación por permiso en servidor):** Todos los módulos validan `tiene_permiso(rol, permiso)` en el servidor, no nombres rígidos de rol. Ocultar botones en UI no sustituye la validación en servidor.
- **RN-05 (Login y estado activo):** Iniciar sesión valida credenciales (`PBKDF2-HMAC-SHA256`), que la cuenta esté `ACTIVO` **y** que su rol asignado esté `activo = True`.
- **RN-06 (Sesiones en servidor):** Cada sesión tiene `token`, `usuario_id`, `rol_codigo`, `fecha_inicio`, `fecha_expiracion` (`America/Lima`) y `activa`. Una sesión expirada, cerrada o revocada no puede ejecutar operaciones.
- **RN-07 (Revocación inmediata):** Cerrar sesión, desactivar usuario, cambiarle de rol, desactivar su rol personalizado o restablecer contraseña revoca de inmediato sus sesiones activas.
- **RN-08 (Sin fuga de datos):** Mensajes de error genéricos en 401/403; nunca exponer información protegida.
- **RN-09 (Auditoría):** Creación/modificación/desactivación de roles, cambios de permisos, inicios/cierres de sesión y accesos denegados se auditan en `PBI-16`.

---

## 3. Escenarios BDD (Gherkin)
1. `ADMIN` crea rol personalizado `DOCENTE` con `{REGISTRAR_CALIFICACIONES, CONSULTAR_CALIFICACIONES}` y lo asigna a un usuario.
2. Usuario con rol personalizado `DOCENTE` ejecuta operaciones permitidas y recibe `AccesoDenegadoException` en operaciones fuera de sus permisos.
3. `ADMIN` modifica permisos de un rol personalizado y el cambio surte efecto inmediato en servidor.
4. Impedir modificar permisos, desactivar o eliminar el rol base `ADMIN`.
5. Impedir eliminar un rol personalizado que todavía tiene usuarios asignados.
6. Rechazar creación de rol con permisos vacíos o permiso inexistente.
7. Desactivar un rol personalizado impide iniciar sesión y revoca el acceso de sus usuarios.
8. Validar expiración de sesión, cierre de sesión y revocación tras desactivar cuenta.
9. Mantener 100% de compatibilidad con los tests existentes en `tests/test_usuarios_rbac.py`.

---

## 4. Diseño de Dominio y Cambios Respecto a `main`
Archivos: `src/dominio/usuarios.py` (y opcionalmente `src/dominio/roles.py` reexportado), `tests/test_usuarios_rbac.py`.
- Ampliar `PermisoOperacion` al catálogo maestro de `docs/README.md` y actualizar `MATRIZ_PERMISOS` (incluyendo `GESTIONAR_JUSTIFICACIONES` para `COORDINADOR`).
- Crear `Rol(frozen=True)`: `codigo`, `nombre`, `descripcion`, `permisos: frozenset[PermisoOperacion]`, `es_sistema: bool = False`, `activo: bool = True`.
- Crear `ServicioGestionRoles`: `crear_rol`, `actualizar_permisos_rol`, `cambiar_estado_rol`, `eliminar_rol`, `obtener_roles_base`.
- Extender `ServicioAutenticacionYPermisos`: `validar_permiso(..., usuario_actual=None, rol_actual=None)`, `revocar_sesiones_usuario`, `tiene_permiso`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b feature/PBI-15-control-acceso-rbac
# 1. RED: tests de roles personalizados, blindaje de ADMIN, revocación y catálogo completo
# 2. GREEN: implementar Rol, ServicioGestionRoles y extensiones RBAC sin romper los 61 tests previos
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
