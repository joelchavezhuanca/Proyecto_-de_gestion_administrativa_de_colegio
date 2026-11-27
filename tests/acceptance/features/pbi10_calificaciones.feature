Feature: Libro de Calificaciones de 3 Niveles y Promedios (PBI-10)
  Como docente asignado con permiso REGISTRAR_CALIFICACIONES
  quiero configurar rubros ponderados al 100 por ciento y registrar notas vigesimales exactas
  para calcular promedios con precisión Decimal dentro de la fecha límite del período

  Scenario Outline: Clasificar escala literal vigesimal con precisión Decimal
    Given un docente asignado al curso "Matemática" en "Secundaria 3ro A"
    And un período académico abierto con fecha límite "2026-05-22"
    And rubros ponderados configurados con pesos 40 y 60 por ciento
    When registra la nota "<nota>" en la actividad del rubro único el día "2026-05-10"
    Then la nota queda registrada con valor exacto "<nota>" y escala literal "<escala>"

    Examples:
      | nota  | escala |
      | 19.00 | AD     |
      | 15.50 | A      |
      | 12.00 | B      |
      | 9.50  | C      |

  Scenario: Rechazar una nota fuera del rango vigesimal 0 a 20
    Given un docente asignado al curso "Matemática" en "Secundaria 3ro A"
    And un período académico abierto con fecha límite "2026-05-22"
    And rubros ponderados configurados con pesos 40 y 60 por ciento
    When registra la nota "21.00" en la actividad del rubro único el día "2026-05-10"
    Then el sistema rechaza la calificación con error "NotaFueraDeRangoException"

  Scenario: Rechazar configuración de rubros cuyos pesos no suman 100 por ciento
    Given un docente asignado al curso "Matemática" en "Secundaria 3ro A"
    And un período académico abierto con fecha límite "2026-05-22"
    When intenta configurar rubros con pesos 40 y 50 por ciento el día "2026-05-10"
    Then el sistema rechaza la calificación con error "PesosRubrosInvalidosException"

  Scenario: Rechazar calificación cuando el período superó la fecha límite de notas
    Given un docente asignado al curso "Matemática" en "Secundaria 3ro A"
    And un período académico abierto con fecha límite "2026-05-22"
    And rubros ponderados configurados con pesos 40 y 60 por ciento
    When registra la nota "16.00" en la actividad del rubro único el día "2026-05-25"
    Then el sistema rechaza la calificación con error "FechaLimiteNotasVencidaException"
