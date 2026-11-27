Feature: Registro Unificado de Asistencia Escolar (PBI-01)
  Como operador de portería con permiso REGISTRAR_ASISTENCIA
  quiero registrar el ingreso de los estudiantes por carnet QR con hora oficial del servidor
  para clasificar puntualidad y tardanza con trazabilidad y sin duplicados

  Scenario Outline: Clasificar puntualidad y tardanza exacta con redondeo ceil
    Given un operador activo con rol "ADMIN_STAFF"
    And un alumno ACTIVO con carnet vigente "DSV-2026-A1B2C3"
    When registra el ingreso por carnet a las "<hora>" hora oficial del servidor
    Then la asistencia queda confirmada con estado "<estado>" y <minutos> minutos de tardanza

    Examples:
      | hora     | estado   | minutos |
      | 07:00:00 | PUNTUAL  | 0       |
      | 07:15:00 | PUNTUAL  | 0       |
      | 07:15:01 | TARDANZA | 1       |
      | 07:16:01 | TARDANZA | 2       |

  Scenario: Rechazar registro duplicado de un alumno ya presente
    Given un operador activo con rol "ADMIN_STAFF"
    And un alumno ACTIVO con carnet vigente "DSV-2026-A1B2C3"
    And el alumno ya tiene una asistencia previa en estado "PUNTUAL"
    When registra el ingreso por carnet a las "07:20:00" hora oficial del servidor
    Then el sistema rechaza la asistencia con error "RegistroDuplicadoException"

  Scenario: Rechazar ingreso de un alumno inactivo
    Given un operador activo con rol "ADMIN_STAFF"
    And un alumno INACTIVO con carnet "DSV-2026-INACT1"
    When registra el ingreso por carnet a las "07:05:00" hora oficial del servidor
    Then el sistema rechaza la asistencia con error "AlumnoInactivoException"

  Scenario: Corregir un estado ausente especificando un motivo obligatorio
    Given un operador activo con rol "COORDINADOR"
    And un alumno ACTIVO con carnet vigente "DSV-2026-A1B2C3"
    And el alumno ya tiene una asistencia previa en estado "AUSENTE"
    When corrige el ingreso por carnet a las "07:30:00" con motivo "Llegó tras cita médica"
    Then la asistencia queda confirmada con estado "TARDANZA" y 15 minutos de tardanza
