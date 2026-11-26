# PBI-02: Gestión de Usuarios

| Propiedad | Detalle |
| :--- | :--- |
| **ID** | `PBI-02` |
| **Rama Git a crear** | `improvement/PBI-02-roles-dinamicos` *(desde `main`)* |
| **Estado actual en `main`** | Implementado en `improvement/PBI-02-roles-dinamicos`: RBAC por permisos, roles personalizados activos, protección del último `ADMIN` y revocación de sesiones. |
| **Dependencias** | `PBI-16` (Auditoría), `PBI-15` (RBAC Dinámico con Roles Personalizados). |
| **Permisos requeridos** | `GESTIONAR_USUARIOS` y `ASIGNAR_ROLES`. |

---

## 1. Historia de Usuario
Como administrador con permiso `GESTIONAR_USUARIOS`, deseo crear, modificar, consultar, activar/desactivar cuentas y restablecer credenciales asignando roles base o personalizados activos, para controlar quién accede a la aplicación web.

---

## 2. Reglas de Negocio
- **RN-01:** Solo usuarios activos con permiso `GESTIONAR_USUARIOS` administran cuentas; asignar o cambiar roles requiere `ASIGNAR_ROLES`.
- **RN-02:** Se puede asignar cualquier rol **activo** (roles base `ADMIN`, `COORDINADOR`, `ADMIN_STAFF` o roles personalizados creados en `PBI-15`). Se rechaza asignar roles inexistentes o inactivos.
- **RN-03:** Cada cuenta tiene `id` único y `username` único (normalizado a minúsculas, sin espacios).
- **RN-04:** Campos mínimos obligatorios: `nombre_completo`, `username`, credencial inicial y `rol`.
- **RN-05:** Contraseñas almacenadas únicamente con `PBKDF2-HMAC-SHA256` + `salt` criptográfico único; nunca en texto plano. Política mínima unificada de **8 caracteres** (manteniendo compatibilidad explícita si se ajusta en tests).
- **RN-06 / RN-07 / RN-08:** Baja lógica (`INACTIVO`) sin eliminar historial. Una cuenta `INACTIVO` no puede iniciar sesión ni ejecutar operaciones protegidas.
- **RN-09:** Al desactivar una cuenta o restablecer su contraseña, el sistema revoca inmediatamente todas sus sesiones activas (`PBI-15`).
- **RN-10 (Protección anti-bloqueo):** No se permite desactivar ni quitar el rol `ADMIN` al último usuario `ADMIN` activo del sistema.
- **RN-11:** Consulta y filtrado por `nombre`, `username`, `rol` y `estado`.
- **RN-12:** Restablecimiento de credencial sin consultar ni mostrar la contraseña anterior.
- **RN-13:** Todas las operaciones generan evento de auditoría en `PBI-16` sin exponer contraseñas, hashes ni salts.

---

## 3. Escenarios BDD (Gherkin)
1. **Crear usuario con rol base o personalizado activo:** cuenta creada con hash+salt y evento en `PBI-16`.
2. **Rechazar creación con rol inactivo o inexistente.**
3. **Denegar operaciones a usuarios sin `GESTIONAR_USUARIOS`.**
4. **Rechazar `username` duplicado (insensible a mayúsculas).**
5. **Modificar datos y cambiar rol** registrando valores anteriores y nuevos en auditoría.
6. **Impedir desactivar o degradar al último `ADMIN` activo.**
7. **Desactivar cuenta y revocar sesiones activas** conservando historial.
8. **Reactivar cuenta inactiva y restablecer contraseña** sin revelar la anterior.
9. **Filtrar cuentas por nombre, username, rol y estado.**

---

## 4. Cambios a Realizar Respecto a `main`
Archivos: `src/dominio/usuarios.py`, `tests/test_usuarios_rbac.py`.
1. Permitir que `Usuario` y `ServicioGestionUsuarios` trabajen con roles personalizados activos de `PBI-15`.
2. Reemplazar validación rígida `operador.rol == ADMIN` por verificación de permisos `GESTIONAR_USUARIOS` / `ASIGNAR_ROLES`.
3. Añadir validación para no desactivar ni cambiar de rol al último `ADMIN` activo.
4. Unificar eventos de auditoría con `ServicioAuditoria` (`PBI-16`).

> **Nota de implementación:** la política de credenciales es de 8 caracteres por defecto
> (`longitud_minima` configurable) y la protección del último `ADMIN` se aplica cuando
> el servicio recibe la lista `usuarios_existentes`.

---

## 5. Cómo Trabajar esta Rama
```bash
git checkout main && git pull origin main
git checkout -b improvement/PBI-02-roles-dinamicos
# 1. RED: agregar tests de rol personalizado, último ADMIN y revocación de sesiones
# 2. GREEN: actualizar ServicioGestionUsuarios en src/dominio/usuarios.py
# 3. REFACTOR:
python -m ruff check .
python -m pytest -v --cov=src --cov-report=term-missing
```
