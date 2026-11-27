## PBI
Cierra #<número del Issue>

¿Es uno de los 2 flujos críticos (★: PBI-01 o PBI-10)?
- [ ] Sí
- [ ] No

## Definición de Terminado (DoD)
- [ ] Criterios de aceptación en Gherkin registrados en el Issue
- [ ] Escenarios ATDD (`.feature`) en verde (obligatorio solo si es flujo crítico ★)
- [ ] Commits `RED → GREEN → REFACTOR` visibles en la rama
- [ ] Linter y formato Ruff sin errores (`ruff check .` y `ruff format --check .`)
- [ ] Cobertura ≥ 70 % en `src/dominio`, `src/aplicacion` y `src/infraestructura` (sin presentación)
- [ ] Interfaz Flask coincide con el wireframe aprobado (si aplica)
- [ ] Documentación actualizada (`README.md` / `docs/`)
- [ ] Validado por el Product Owner
