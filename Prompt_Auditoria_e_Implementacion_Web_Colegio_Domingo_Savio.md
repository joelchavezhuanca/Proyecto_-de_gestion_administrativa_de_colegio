# PROMPT MAESTRO: Auditoría e implementación de interfaces web del sistema de gestión administrativa del colegio

## 1. Rol que debes asumir

Actúa como **arquitecto de software y desarrollador full-stack senior**,
con experiencia en Python, Flask, HTML, CSS, JavaScript, diseño UX/UI,
arquitectura por capas, pruebas automatizadas y construcción de sistemas
administrativos.

Tu responsabilidad es trabajar sobre el proyecto existente, comprenderlo
antes de modificarlo y desarrollar una primera versión web funcional que
pueda presentarse como avance universitario y que, posteriormente, pueda
evolucionar hacia el producto final.

No quiero una aplicación genérica, una maqueta desconectada ni un
proyecto nuevo que ignore el trabajo ya realizado. Quiero integrar las
interfaces web con la arquitectura y la lógica de negocio que realmente
existen en el repositorio.

------------------------------------------------------------------------

## 2. Contexto del proyecto

El proyecto se denomina **Sistema de Gestión Administrativa de Colegio**
y está orientado al contexto del colegio Domingo Savio S.A.C.

Repositorio GitHub:

`https://github.com/joelchavezhuanca/Proyecto_-de_gestion_administrativa_de_colegio.git`

También se proporcionará un archivo comprimido del proyecto y el
documento técnico de especificación de interfaces gráficas y diseño
UX/UI. Debes utilizar los archivos que estén efectivamente disponibles
en el entorno de trabajo. Si el archivo comprimido no se puede extraer o
el repositorio no es accesible, informa exactamente qué recurso no
pudiste leer y solicita una alternativa. No inventes el contenido de
archivos que no hayas inspeccionado.

### Objetivo general

Implementar una **aplicación web con Flask, HTML, CSS y JavaScript**,
reutilizando la lógica, los modelos, los servicios, las excepciones y
las pruebas que ya existan en el proyecto.

La aplicación debe permitir demostrar visualmente y mediante flujos
funcionales las interfaces especificadas en el documento técnico. Debe
ejecutarse localmente desde una laptop y ser fácil de presentar ante el
profesor.

### Tecnologías elegidas

-   **Backend:** Python + Flask.
-   **Frontend:** HTML5, CSS3 y JavaScript.
-   **Plantillas:** Jinja2, integrado con Flask.
-   **Persistencia para la demostración:** SQLite, únicamente si resulta
    necesaria y compatible con la arquitectura existente.
-   **Pruebas:** conservar y utilizar el framework de pruebas ya
    presente. Si el proyecto utiliza Pytest, mantenerlo.
-   **Control de versiones:** Git, trabajando en una rama separada para
    la demostración.

No cambies estas tecnologías sin una razón técnica importante. Si
detectas una incompatibilidad real, explica el problema y plantea la
alternativa antes de sustituirlas.

------------------------------------------------------------------------

## 3. Regla fundamental: primero auditar, después implementar

**No empieces creando archivos ni programando las pantallas. Primero
realiza una auditoría real del proyecto.**

El principal riesgo que debes evitar es crear una aplicación Flask
independiente que duplique, contradiga o ignore el trabajo existente en
`src/dominio/` y en el resto del proyecto.

Debes inspeccionar el repositorio y el archivo comprimido, no limitarte
al README ni a una descripción superficial de las carpetas.

### 3.1. Inspección del proyecto

Revisa, según corresponda:

1.  La estructura completa de directorios y archivos.
2.  Los módulos y clases que existen en `src/dominio/`.
3.  Los servicios de dominio o de aplicación implementados.
4.  Los modelos, entidades, objetos de valor y DTO.
5.  Las excepciones propias del proyecto.
6.  Los repositorios y mecanismos de persistencia existentes.
7.  Las pruebas automatizadas y qué comportamiento verifican.
8.  Las dependencias y versiones declaradas en `requirements.txt`,
    `pyproject.toml` u otros archivos.
9.  Los puntos de entrada y la forma actual de ejecutar el proyecto.
10. La documentación técnica y funcional disponible.
11. Las funcionalidades terminadas, parcialmente implementadas y
    pendientes.
12. Las convenciones de nombres, estilo de código y organización que ya
    utiliza el proyecto.

No supongas que un servicio existe porque aparezca mencionado en una
especificación. Comprueba que el archivo, clase o método exista y revisa
su implementación.

### 3.2. Informe de auditoría obligatorio

Antes de implementar, presenta un informe breve pero concreto que
incluya:

-   **Arquitectura actual:** cómo está organizado realmente el proyecto.
-   **Dominio:** módulos, entidades, modelos y reglas de negocio
    encontrados.
-   **Servicios:** nombre, ubicación y responsabilidad de cada servicio
    relevante.
-   **Excepciones:** cuáles existen y cuándo se utilizan.
-   **Persistencia:** cómo se almacenan actualmente los datos.
-   **Pruebas:** qué pruebas existen y cuál es su estado al ejecutarlas.
-   **Dependencias:** tecnologías y librerías que ya están instaladas o
    declaradas.
-   **Estado funcional:** qué está terminado, incompleto o pendiente.
-   **Integración web:** qué componentes pueden reutilizarse
    directamente y qué adaptadores hacen falta.
-   **Riesgos:** incompatibilidades, código incompleto, deuda técnica o
    información que no se pudo verificar.

Incluye rutas reales de archivos y nombres reales de clases o funciones.
Distingue claramente entre:

-   Verificado en el código.
-   Inferido a partir de la estructura o documentación.
-   Pendiente de confirmar.

No marques una funcionalidad como terminada únicamente porque exista un
archivo con ese nombre. Lee el código y, cuando sea posible, ejecuta sus
pruebas.

### 3.3. Decisión de arquitectura posterior a la auditoría

Una vez terminada la auditoría, diseña la integración de Flask con la
arquitectura existente.

Respeta estas prioridades:

1.  Reutilizar la lógica de dominio existente.
2.  Reutilizar los servicios y repositorios que ya funcionen.
3.  No duplicar reglas de negocio en rutas Flask, plantillas ni
    JavaScript.
4.  Crear servicios de aplicación o adaptadores solo cuando exista una
    necesidad concreta.
5.  Mantener separadas la presentación, la lógica de aplicación, el
    dominio y la infraestructura.
6.  Evitar reorganizaciones masivas que no sean necesarias para
    implementar las interfaces.
7.  No reemplazar tecnologías o dependencias existentes sin
    justificarlo.

**La interfaz no debe ejecutar SQL directamente ni implementar cálculos
de reglas de negocio**, como la determinación de horarios, tardanzas o
estados de asistencia. La interfaz debe solicitar esas operaciones a los
servicios correspondientes.

Si la arquitectura real no permite conectar una pantalla directamente
con un servicio existente, documenta la brecha y crea el adaptador
mínimo necesario, sin alterar el comportamiento del dominio.

------------------------------------------------------------------------

## 4. Documento técnico de interfaces: fuente principal del diseño

Lee completamente el documento proporcionado titulado **"Especificación
Técnica de Interfaces Gráficas y Diseño UX/UI"**.

Ese documento es la referencia funcional y visual principal para las
pantallas. No lo reemplaces por un diseño genérico ni ignores sus
reglas.

La especificación contempla las siguientes interfaces:

### Pantalla 1. Inicio de sesión

Debe permitir el acceso al sistema mediante las credenciales
correspondientes.

Considera: - Diseño institucional y profesional. - Campos de usuario y
contraseña. - Validaciones y mensajes claros. - Manejo de credenciales
incorrectas. - Navegación posterior al inicio de sesión según los
permisos o roles que realmente soporte el proyecto.

No inventes un sistema complejo de autenticación si el proyecto todavía
no lo contempla. Para la demostración, cualquier usuario de prueba debe
estar claramente identificado como tal.

### Pantalla 2. Registro de asistencia (PBI-01)

Debe implementar el flujo de registro de asistencia indicado en el
documento.

Considera: - Los datos y controles que especifique el documento. -
Selección de opciones predeterminadas cuando corresponda. - Validaciones
visibles y comprensibles. - Confirmación del resultado de la
operación. - Consulta o visualización del estado registrado, si está
contemplada.

La UI no debe calcular por su cuenta tardanzas, horarios ni estados.
Esas responsabilidades pertenecen a la lógica de dominio o al servicio
correspondiente.

### Pantalla 3. Dashboard de aforo (PBI-03)

Debe presentar la información de aforo de manera visual y comprensible.

Considera: - Indicadores principales. - Capacidad, ocupación y
disponibilidad, si esos datos están definidos en el proyecto o
documento. - Gráficos o representaciones visuales solo cuando los datos
disponibles los permitan. - Actualización de la información según las
capacidades reales del backend. - Estados vacíos y mensajes cuando no
existan datos.

No inventes cifras ni presentes datos simulados como datos reales. Si se
utiliza información ficticia para la demostración, indícalo claramente
en la interfaz o en la documentación.

### Pantalla 4. Gestión de justificaciones (PBI-04)

Debe permitir realizar los flujos de justificación descritos en el
documento.

Considera: - Consulta de registros. - Visualización de detalles. -
Registro o envío de justificaciones, si corresponde. - Validaciones y
mensajes de resultado. - Estados y permisos definidos en las reglas de
negocio.

Respeta especialmente las reglas de negocio y permisos relacionados con
las justificaciones que ya estén definidos en el proyecto. No inventes
permisos ni estados.

### Pantalla 5. Gestión de usuarios (PBI-02 / PBI-15)

Debe implementar las operaciones de gestión de usuarios contempladas en
la especificación.

Considera: - Listado y consulta. - Registro o edición, si están
contemplados. - Asignación de roles o permisos únicamente si el proyecto
lo soporta. - Validaciones de datos. - Confirmación de las
operaciones. - Restricciones de acceso según los roles definidos
realmente.

No expongas opciones que no tengan una implementación funcional detrás.
Si una operación todavía no está desarrollada, identifica su estado y
evita simular que se guardó correctamente.

------------------------------------------------------------------------

## 5. Reglas UX/UI que debes respetar

Aplica las reglas del documento técnico. Entre ellas:

1.  **Regla de los tres clics:** procura que las operaciones frecuentes
    sean accesibles con pocos pasos.
2.  **Controles de selección:** utiliza listas, selectores o controles
    apropiados para datos predeterminados, en lugar de obligar a
    escribir valores que ya están definidos.
3.  **Wizard:** utiliza un asistente por pasos cuando el formulario
    tenga más de tres datos relevantes y el documento lo indique.
4.  **Validación inline:** muestra los errores junto al campo
    correspondiente, con mensajes claros.
5.  **Consistencia visual:** mantén una misma jerarquía visual,
    espaciados, tipografía, colores y comportamiento entre pantallas.
6.  **Accesibilidad:** utiliza etiquetas asociadas a campos, contraste
    suficiente, navegación por teclado y estados visibles de foco.
7.  **Diseño adaptable:** las pantallas deben funcionar en resoluciones
    de laptop y adaptarse razonablemente a pantallas más pequeñas.
8.  **Estados de interfaz:** contempla carga, éxito, error, ausencia de
    resultados y confirmación de acciones.
9.  **Prevención de errores:** confirma acciones importantes y evita
    envíos duplicados cuando sea necesario.
10. **Claridad:** utiliza textos en español y terminología coherente con
    el colegio y con el documento.

### Dirección visual e identidad institucional

La identidad visual debe basarse en los recursos gráficos oficiales del
**Colegio Domingo Savio** y en el archivo `DESIGN.md`, si está
disponible en el repositorio o entre los documentos proporcionados.

#### Recursos gráficos oficiales

Utiliza las imágenes institucionales originales proporcionadas:

-   **Logotipo horizontal:** `logo-domingo-savio.png`.
-   **Escudo institucional:** `escudo-domingo-savio.png`.

Primero localiza estos archivos en el proyecto. Si todavía no están
incorporados, solicita su ubicación o cópialos a la carpeta de recursos
estáticos de Flask que corresponda a la estructura real encontrada
durante la auditoría. Como ubicación orientativa, utiliza
`static/assets/branding/`, siempre que sea compatible con la
arquitectura existente. No crees una segunda carpeta de recursos si el
proyecto ya tiene una ubicación equivalente.

Reglas obligatorias para los logotipos:

-   Utiliza los archivos originales proporcionados; no los vuelvas a
    generar con IA.
-   No redibujes, vectorices automáticamente, estilices, deformes ni
    alteres los logotipos.
-   No cambies sus colores, tipografía, composición ni proporciones.
-   No apliques filtros, tintes, efectos 3D, sombras añadidas ni
    transparencias que alteren su apariencia original.
-   Mantén su relación de aspecto y utiliza `object-fit: contain` cuando
    corresponda.
-   No recortes partes del logotipo ni lo estires para llenar un
    contenedor.
-   Comprueba que los archivos carguen correctamente en todas las
    pantallas donde se utilicen.
-   No sustituyas los recursos oficiales por texto escrito con una
    fuente parecida ni por versiones inventadas.

Uso recomendado:

-   **Logotipo horizontal:** úsalo principalmente en la pantalla de
    inicio de sesión y en encabezados o zonas institucionales donde
    exista espacio horizontal suficiente.
-   **Escudo institucional:** úsalo como elemento complementario en la
    pantalla de inicio de sesión, bienvenida o identificación
    institucional. En la navegación lateral puede utilizarse si encaja
    mejor que el logotipo horizontal.
-   No muestres ambos logotipos repetidamente en cada tarjeta o sección.
    Su uso debe ser equilibrado y mantener una jerarquía visual clara.
-   En pantallas internas, conserva una identificación institucional
    discreta; prioriza el espacio destinado al trabajo administrativo.

#### Paleta cromática institucional

La paleta debe derivarse de los colores visibles en los logotipos
oficiales y de las especificaciones de `DESIGN.md`. Para evitar
inconsistencias, utiliza los siguientes valores como paleta canónica de
la interfaz:

  -----------------------------------------------------------------------
  Uso                     Color                   Aplicación
  ----------------------- ----------------------- -----------------------
  Verde institucional     `#004000`               Botones principales,
  principal                                       enlaces activos y
                                                  elementos de identidad

  Verde institucional     `#002800`               Sidebar, encabezados
  profundo                                        institucionales y
                                                  superficies oscuras
                                                  puntuales

  Verde lima de acento    `#00F900`               Indicadores activos,
                                                  pequeños detalles,
                                                  bordes de énfasis y
                                                  estados positivos

  Fondo general           `#F7FAF4`               Fondo principal de las
                                                  páginas

  Superficie de tarjetas  `#FFFFFF`               Tarjetas, formularios,
                                                  tablas y paneles

  Texto principal         `#191D19`               Títulos y contenido
                                                  principal

  Texto secundario        `#41493D`               Descripciones,
                                                  etiquetas secundarias y
                                                  metadatos

  Bordes y divisores      `#C1C9BA`               Contornos, separadores
                                                  y límites de
                                                  componentes

  Superficie oscura       `#1E2220`               Elementos oscuros
                                                  puntuales cuando el
                                                  contraste lo justifique
  -----------------------------------------------------------------------

Si `DESIGN.md` contiene tokens con valores diferentes para estos mismos
usos, toma esta tabla como la definición canónica para las interfaces de
esta implementación y evita mezclar valores contradictorios. No
introduzcas azules como color institucional principal.

El verde lima es muy intenso: úsalo con moderación y verifica siempre el
contraste del texto. No coloques texto blanco pequeño sobre verde lima
ni grandes superficies de verde lima como fondo. Para botones y acciones
principales, prioriza el verde institucional principal con texto blanco.

Los colores semánticos pueden utilizarse únicamente para comunicar
estados y no como parte de la identidad de marca:

-   Éxito: `#2E7D32`.
-   Advertencia: `#FBC02D`.
-   Error: `#D32F2F`.
-   Información: `#0288D1`.

Asegura contraste suficiente y no dependas únicamente del color para
comunicar un estado; acompaña los indicadores con texto o iconografía.

#### Tipografía

Utiliza **Hanken Grotesk** como tipografía principal, de acuerdo con
`DESIGN.md`. Si no está disponible localmente, incorpora una alternativa
compatible sin alterar la jerarquía visual. Mantén buena legibilidad en
español, incluidos los caracteres `ñ`, `á`, `é`, `í`, `ó` y `ú`.

#### Estilo de las interfaces

Construye una interfaz administrativa **Corporate / Modern**,
profesional, académica, sobria y eficiente:

-   Sidebar lateral en verde institucional profundo, con textos e iconos
    claros. Los elementos inactivos deben tener menor énfasis visual y
    el elemento activo debe identificarse con un indicador verde lima
    discreto.
-   Barra superior clara, con nombre de la sección, usuario autenticado
    y acciones pertinentes.
-   Fondo general claro con un matiz ligeramente verdoso.
-   Tarjetas y paneles blancos con bordes sutiles.
-   Botones principales en verde institucional, con texto blanco.
-   Botones secundarios con fondo transparente o blanco y borde verde
    institucional.
-   Formularios con etiquetas visibles, campos claros y estados de foco
    accesibles.
-   Tablas ordenadas, legibles y con acciones claramente identificadas.
-   Bordes moderadamente redondeados y sombras muy discretas, reservadas
    para elementos flotantes cuando sean necesarias.
-   Iconografía consistente y funcional.

Evita:

-   Azul como color principal o sustituto de la identidad institucional.
-   Gradientes decorativos que no estén presentes en el lenguaje visual
    de la marca.
-   Sombras exageradas, glassmorphism y efectos 3D en los componentes de
    interfaz.
-   Grandes bloques de verde lima.
-   Repetir los logotipos en exceso.
-   Plantillas genéricas que no reflejen la identidad del Colegio
    Domingo Savio.

La identidad institucional debe reconocerse por el uso consistente de
sus logotipos, verdes y tipografía, pero la prioridad de cada pantalla
sigue siendo la claridad, accesibilidad y eficiencia de las tareas
administrativas.

No agregues elementos decorativos que dificulten el uso ni sacrifiques
claridad por apariencia.

------------------------------------------------------------------------

## 6. Arquitectura web esperada

La estructura final debe adaptarse a lo que descubras en la auditoría.
No fuerces esta estructura si el proyecto ya tiene una organización
equivalente.

Como orientación, la integración puede contemplar responsabilidades
similares a las siguientes:

-   **Presentación web:** aplicación Flask, rutas, controladores,
    plantillas y recursos estáticos.
-   **Aplicación:** coordinación de casos de uso, DTO y servicios de
    aplicación, si son necesarios.
-   **Dominio:** entidades, reglas de negocio, servicios y excepciones
    existentes.
-   **Infraestructura:** repositorios, persistencia y adaptadores.
-   **Pruebas:** pruebas existentes y nuevas pruebas de integración web.

Las rutas Flask deben ser delgadas: recibir la solicitud, validar
aspectos propios de la entrada web, invocar el caso de uso
correspondiente y devolver una respuesta o renderizar una plantilla.

No coloques reglas de negocio dentro de las rutas Flask.

No coloques consultas SQL dentro de plantillas o archivos JavaScript.

No hagas que JavaScript sea responsable de determinar resultados que
corresponden al dominio. JavaScript puede encargarse de interacciones
visuales, validaciones de conveniencia y solicitudes al backend.

### SQLite y datos de demostración

Evalúa primero la persistencia existente.

-   Si el proyecto ya dispone de una base de datos o repositorios
    funcionales, prioriza su reutilización.
-   Si no existe persistencia adecuada para la demostración, puedes
    incorporar SQLite mediante una capa de infraestructura.
-   Mantén la base de datos de demostración separada de cualquier dato
    real o entorno de producción.
-   No migres ni reemplaces la persistencia existente sin una razón
    técnica documentada.
-   Utiliza datos ficticios identificados como datos de demostración.
-   Incluye un mecanismo reproducible para inicializar o reiniciar los
    datos de demostración.
-   No guardes contraseñas en texto plano si se implementa
    autenticación.

No agregues SQLAlchemy u otra librería por costumbre. Primero comprueba
las dependencias y el diseño de persistencia actuales; incorpora una
nueva dependencia solo si aporta una solución necesaria y justificada.

------------------------------------------------------------------------

## 7. Estrategia Git y protección del trabajo existente

Antes de modificar archivos:

1.  Comprueba el estado de Git.
2.  Identifica la rama actual.
3.  Revisa si existen cambios locales sin confirmar.
4.  No sobrescribas ni descartes cambios del usuario.
5.  No hagas commits destructivos ni operaciones de limpieza que puedan
    eliminar trabajo.

La implementación debe desarrollarse en una rama separada llamada:

`demo/interfaces-web`

Si la rama ya existe, inspecciónala antes de utilizarla. Si no existe,
créala desde la base adecuada después de comprobar el estado del
repositorio.

No trabajes directamente sobre `main` salvo que exista una instrucción
explícita.

No hagas `reset --hard`, no elimines archivos desconocidos, no fuerces
pushes y no reescribas el historial.

Si no tienes acceso a Git o no puedes crear la rama desde el entorno
disponible, indícalo y proporciona los comandos necesarios. No afirmes
que creaste una rama si no lo hiciste.

------------------------------------------------------------------------

## 8. Plan de implementación

Después de presentar la auditoría y definir la arquitectura de
integración, implementa el sistema por etapas.

### Fase 1. Preparación

-   Preparar la rama de trabajo.
-   Definir la estructura web adaptada al repositorio.
-   Configurar Flask.
-   Verificar que la aplicación pueda iniciarse.
-   Mantener intacta la lógica existente.

### Fase 2. Estructura visual común

-   Crear la plantilla base.
-   Implementar navegación y distribución general.
-   Crear componentes reutilizables.
-   Definir estilos globales.
-   Implementar mensajes, alertas, estados vacíos y elementos comunes.

### Fase 3. Inicio de sesión

-   Implementar la pantalla.
-   Integrarla con la autenticación existente, si existe.
-   Si no existe, definir un mecanismo de demostración seguro y
    claramente documentado.
-   Proteger las rutas que requieran autenticación, según el alcance
    real del proyecto.

### Fase 4. Registro de asistencia (PBI-01)

-   Identificar el servicio real que debe atender el caso de uso.
-   Implementar la pantalla.
-   Conectar el formulario con el backend.
-   Mostrar resultados y errores provenientes de la lógica
    correspondiente.
-   Probar el flujo completo.

### Fase 5. Dashboard de aforo (PBI-03)

-   Identificar la fuente real de los datos.
-   Implementar indicadores y visualizaciones.
-   Diferenciar datos reales de datos de demostración.
-   Probar estados con y sin información.

### Fase 6. Justificaciones (PBI-04)

-   Identificar servicios, reglas y permisos existentes.
-   Implementar los flujos contemplados.
-   Respetar las reglas de negocio.
-   Probar los escenarios principales y los errores.

### Fase 7. Gestión de usuarios (PBI-02 / PBI-15)

-   Identificar los modelos, servicios y permisos existentes.
-   Implementar las operaciones que realmente estén soportadas.
-   Validar entradas y permisos.
-   Probar los flujos principales.

### Fase 8. Persistencia de demostración

Solo si la auditoría determina que es necesaria:

-   Implementar SQLite en infraestructura.
-   Crear inicialización de base de datos.
-   Preparar datos ficticios.
-   Evitar duplicar repositorios o modelos existentes.
-   Documentar cómo reiniciar los datos.

### Fase 9. Pruebas y revisión

-   Ejecutar las pruebas existentes.
-   Añadir pruebas para las rutas y casos de uso web.
-   Probar validaciones y manejo de excepciones.
-   Comprobar navegación entre pantallas.
-   Comprobar que las operaciones persistan cuando corresponda.
-   Verificar que no se hayan roto funcionalidades previas.
-   Revisar errores de consola del navegador y del servidor.
-   Verificar el diseño en resoluciones habituales de laptop.

### Fase 10. Documentación y presentación

Actualizar o crear la documentación necesaria para que otra persona
pueda ejecutar y presentar el sistema.

Incluye: - Requisitos previos. - Instalación de dependencias. -
Configuración. - Inicialización de datos de demostración, si aplica. -
Comando para iniciar Flask. - Dirección local de acceso. - Credenciales
de demostración, solo si se implementaron. - Descripción de las cinco
pantallas. - Funcionalidades implementadas y limitaciones conocidas. -
Comandos para ejecutar pruebas.

------------------------------------------------------------------------

## 9. Criterios de calidad y aceptación

La implementación se considerará satisfactoria cuando se cumpla lo
siguiente:

### Arquitectura

-   Flask está integrado con el proyecto existente.
-   La lógica de negocio permanece fuera de las rutas y de la interfaz.
-   Se reutilizan los servicios y modelos existentes cuando corresponde.
-   No hay duplicación innecesaria de reglas de negocio.
-   La persistencia está aislada de la presentación.

### Funcionalidad

-   Las cinco pantallas especificadas están implementadas o su estado
    pendiente está documentado con precisión.
-   Los formularios realizan validaciones.
-   Las acciones muestran resultados reales del backend.
-   Los errores se comunican claramente.
-   Los permisos se respetan cuando están definidos.
-   No se presentan operaciones simuladas como si fueran operaciones
    persistentes reales.

### Presentación

-   La interfaz es coherente y profesional.
-   La navegación es clara.
-   El diseño es adaptable.
-   Los textos están en español.
-   La aplicación puede demostrarse desde una laptop.

### Calidad técnica

-   Las pruebas existentes siguen funcionando.
-   Se incorporan pruebas para las funcionalidades web relevantes.
-   Las dependencias están justificadas.
-   La instalación y ejecución están documentadas.
-   No se han eliminado ni sobrescrito componentes existentes sin
    justificación.

------------------------------------------------------------------------

## 10. Forma de trabajo y comunicación

Trabaja de manera ordenada, verificable y transparente.

### Antes de implementar

Entrega primero:

1.  Resultado de la inspección del repositorio.
2.  Informe de auditoría con rutas reales.
3.  Tabla de estado de las cinco funcionalidades.
4.  Arquitectura de integración propuesta.
5.  Lista de archivos que planeas crear o modificar.
6.  Riesgos o decisiones que requieran mi aprobación.

No presentes una propuesta como si ya estuviera implementada.

### Durante la implementación

-   Trabaja por fases y verifica cada una.
-   Explica brevemente qué archivos creaste o modificaste y por qué.
-   Ejecuta las pruebas pertinentes después de cambios importantes.
-   Si una prueba falla, investiga la causa en lugar de ocultarla.
-   Si encuentras una decisión funcional ambigua, consulta antes de
    inventar una regla de negocio.
-   Si falta una función de dominio, no la simules silenciosamente:
    documenta la ausencia y propone el adaptador o implementación mínima
    necesaria.
-   No te detengas en recomendaciones generales: el objetivo final es
    implementar el sistema, no limitarte a diseñarlo.
-   No afirmes que una fase está terminada sin haber comprobado su
    resultado.

### Al finalizar

Entrega un informe final con:

-   Resumen de lo implementado.
-   Pantallas funcionales.
-   Integraciones realizadas con los servicios existentes.
-   Archivos creados y modificados.
-   Dependencias añadidas y justificación.
-   Pruebas ejecutadas y resultados.
-   Instrucciones exactas para ejecutar la aplicación.
-   Datos o credenciales de demostración, si corresponde.
-   Limitaciones conocidas y funcionalidades pendientes.
-   Estado de la rama Git y commits realizados, únicamente si realmente
    se realizaron.

------------------------------------------------------------------------

## 11. Instrucción final prioritaria

Quiero una **primera versión web funcional, visualmente cuidada y
presentable**, construida sobre el proyecto real.

No quiero que empieces desde cero por comodidad. No quiero que inventes
la arquitectura ni los servicios. No quiero una maqueta que solo parezca
funcionar.

**Primero comprende el código existente, después decide cómo integrarlo
y finalmente implementa las interfaces.**

La prioridad es preservar el trabajo existente, respetar el documento
técnico y conseguir una aplicación Flask que demuestre de manera clara
el avance del sistema de gestión administrativa del colegio.

Si no puedes acceder a un archivo o verificar una funcionalidad, dilo
explícitamente. La precisión y la integridad del proyecto tienen
prioridad sobre aparentar que todo está terminado.
