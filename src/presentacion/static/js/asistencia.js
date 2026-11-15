/* Registro de asistencia unificado: entrada única, búsqueda y cámara QR. */
(function () {
  "use strict";

  const formulario = document.querySelector("[data-form-unificado]");
  if (!formulario) {
    return;
  }

  const entrada = formulario.querySelector("[data-entrada-unificada]");
  const campoMetodo = formulario.querySelector("[data-metodo-unificado]");
  const campoAlumnoId = formulario.querySelector("[data-alumno-id-unificado]");
  const mensaje = formulario.querySelector("[data-mensaje-unificado]");
  const resultados = formulario.querySelector("[data-resultados-unificados]");
  const tarjetaAlumno = formulario.querySelector("[data-tarjeta-unificada]");
  const botonLimpiar = formulario.querySelector("[data-limpiar-unificado]");
  const botonCamara = document.querySelector("[data-abrir-camara]");
  const panelCamara = document.querySelector("[data-panel-camara]");
  const botonCerrarCamara = document.querySelector("[data-cerrar-camara]");

  const lectorQr = document.querySelector("[data-lector-qr]");
  const botonIniciar = document.querySelector("[data-iniciar-camara]");
  const botonDetener = document.querySelector("[data-detener-camara]");
  const selectorCamara = document.querySelector("[data-camara-select]");
  const estadoCamara = document.querySelector("[data-camara-estado]");
  const tarjetaResultado = document.querySelector("[data-resultado-qr]");
  const panelCorreccion = document.querySelector("[data-correccion-qr]");
  const motivoQr = document.querySelector("[data-motivo-qr]");
  const errorCorreccion = document.querySelector("[data-correccion-error]");
  const botonConfirmarCorreccion = document.querySelector("[data-confirmar-correccion-qr]");
  const botonCancelarCorreccion = document.querySelector("[data-cancelar-correccion-qr]");
  const botonSiguiente = document.querySelector("[data-escanear-siguiente]");
  const cuentaRegresiva = document.querySelector("[data-cuenta-regresiva]");

  let escaner = null;
  let camaraActiva = false;
  let camaraDeseada = false;
  let procesando = false;
  let metodoPendiente = "CARNET";
  let identificadorPendiente = "";
  let alumnoPendiente = "";
  let temporizadorSiguiente = null;
  let temporizadorBusqueda = null;
  let segundosRestantes = 0;
  let consultaActual = 0;

  /* ============================ Utilidades ============================ */
  function escapar(texto) {
    const div = document.createElement("div");
    div.textContent = texto == null ? "" : String(texto);
    return div.innerHTML;
  }

  function mostrarMensaje(texto, tipo) {
    if (!mensaje) {
      return;
    }
    mensaje.textContent = texto || "";
    mensaje.className = "field-message" + (tipo ? " " + tipo : "");
  }

  function esDni(valor) {
    return /^\d{8}$/.test(valor);
  }

  function esCarnet(valor) {
    if (/^ALU-/i.test(valor)) {
      return false;
    }
    return (
      !valor.includes(" ") &&
      /^(?=.*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$/.test(valor)
    );
  }

  function limpiarResultados() {
    consultaActual += 1;
    if (temporizadorBusqueda) {
      window.clearTimeout(temporizadorBusqueda);
      temporizadorBusqueda = null;
    }
    if (resultados) {
      resultados.innerHTML = "";
    }
  }

  function limpiarSeleccion() {
    if (campoAlumnoId) {
      campoAlumnoId.value = "";
    }
    if (campoMetodo) {
      campoMetodo.value = "CARNET";
    }
    if (tarjetaAlumno) {
      tarjetaAlumno.innerHTML = "";
      tarjetaAlumno.hidden = true;
    }
  }

  function construirTarjeta(alumno) {
    const contenedor = document.createElement("div");
    contenedor.innerHTML =
      "<h3>" +
      escapar(alumno.nombre) +
      "</h3>" +
      "<p class='muted small'>" +
      escapar(alumno.salon || "") +
      "</p>" +
      "<dl>" +
      "<div><dt>Código</dt><dd>" +
      escapar(alumno.codigo || "") +
      "</dd></div>" +
      "<div><dt>DNI</dt><dd>" +
      escapar(alumno.dni || "") +
      "</dd></div>" +
      "<div><dt>Carnet</dt><dd>" +
      escapar(alumno.carnet || "") +
      "</dd></div>" +
      "</dl>";
    return contenedor;
  }

  /* ============================ Búsqueda asistida ============================ */
  function seleccionarAlumno(alumno) {
    if (campoAlumnoId) {
      campoAlumnoId.value = alumno.id;
    }
    if (campoMetodo) {
      campoMetodo.value = "MANUAL_BUSQUEDA";
    }
    if (entrada) {
      entrada.value = alumno.nombre;
    }
    if (tarjetaAlumno) {
      tarjetaAlumno.innerHTML = "";
      tarjetaAlumno.appendChild(construirTarjeta(alumno));
      tarjetaAlumno.hidden = false;
    }
    limpiarResultados();
    mostrarMensaje("Alumno seleccionado. Presione Registrar ingreso.", "ok");
    if (entrada) {
      entrada.focus();
    }
  }

  function renderizarResultados(lista) {
    if (!resultados) {
      return;
    }
    resultados.innerHTML = "";
    if (!lista.length) {
      resultados.innerHTML =
        "<p class='field-message error'>No se encontraron alumnos ACTIVOS con ese criterio.</p>";
      mostrarMensaje("No se encontraron coincidencias.", "error");
      return;
    }
    lista.forEach(function (alumno) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "resultado-item";

      const izquierda = document.createElement("span");
      const nombre = document.createElement("strong");
      nombre.textContent = alumno.nombre;
      const detalle = document.createElement("small");
      detalle.textContent = alumno.codigo + " · DNI " + alumno.dni;
      izquierda.appendChild(nombre);
      izquierda.appendChild(detalle);

      const salon = document.createElement("span");
      salon.className = "resultado-salon";
      salon.textContent = alumno.salon;

      item.appendChild(izquierda);
      item.appendChild(salon);
      item.addEventListener("click", function () {
        seleccionarAlumno(alumno);
      });
      resultados.appendChild(item);
    });
    mostrarMensaje("Seleccione un alumno de la lista.", "ok");
  }

  function buscarAlumnos(criterio) {
    const consulta = criterio.trim();
    if (consulta.length < 2) {
      limpiarResultados();
      return;
    }
    if (temporizadorBusqueda) {
      window.clearTimeout(temporizadorBusqueda);
      temporizadorBusqueda = null;
    }
    consultaActual += 1;
    const token = consultaActual;
    if (resultados) {
      resultados.innerHTML = "<p class='muted small'>Buscando coincidencias…</p>";
    }
    fetch("/api/alumnos?q=" + encodeURIComponent(consulta), {
      headers: { Accept: "application/json" },
    })
      .then(function (respuesta) {
        if (!respuesta.ok) {
          throw new Error("No fue posible realizar la búsqueda.");
        }
        return respuesta.json();
      })
      .then(function (datos) {
        if (token !== consultaActual) {
          return;
        }
        renderizarResultados(datos.resultados || []);
      })
      .catch(function (error) {
        if (token !== consultaActual) {
          return;
        }
        if (resultados) {
          resultados.innerHTML =
            "<p class='field-message error'>" + escapar(error.message) + "</p>";
        }
        mostrarMensaje(error.message, "error");
      });
  }

  /* ============================ Registro ============================ */
  function enviarAsistencia(metodo, identificador, motivo, alumnoId) {
    const cuerpo = new URLSearchParams();
    cuerpo.set("metodo", metodo);
    if (identificador) {
      cuerpo.set("identificador", identificador);
    }
    if (alumnoId) {
      cuerpo.set("alumno_id", alumnoId);
    }
    if (motivo) {
      cuerpo.set("motivo", motivo);
    }
    return fetch("/asistencia/registrar", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-Requested-With": "fetch",
        Accept: "application/json",
      },
      body: cuerpo.toString(),
    }).then(function (respuesta) {
      return respuesta.json().catch(function () {
        throw new Error("El servidor devolvió una respuesta inesperada.");
      });
    });
  }

  function registrar(metodo, identificador, motivo, alumnoId) {
    if (procesando) {
      return Promise.resolve();
    }
    procesando = true;
    metodoPendiente = metodo;
    identificadorPendiente = identificador || "";
    alumnoPendiente = alumnoId ? String(alumnoId) : "";
    mostrarMensaje("Registrando asistencia…", "");

    return enviarAsistencia(
      metodo,
      identificadorPendiente,
      motivo,
      alumnoPendiente
    )
      .then(function (datos) {
        if (datos.ok) {
          mostrarResultado(datos);
          limpiarSeleccion();
          limpiarResultados();
          if (entrada) {
            entrada.value = "";
          }
          mostrarMensaje("", "");
        } else if (datos.requiere_motivo) {
          mostrarCorreccion(datos);
        } else {
          mostrarErrorRegistro(datos.mensaje || "No fue posible registrar la asistencia.");
        }
      })
      .catch(function (error) {
        mostrarErrorRegistro(error.message || "Error de conexión con el servidor.");
      })
      .finally(function () {
        procesando = false;
      });
  }

  /* ============================ Aviso WhatsApp al apoderado ============================ */
  const CLASE_CHIP_AVISO = {
    SIMULADO: "info",
    ENVIADO: "ok",
    ERROR: "danger",
    SIN_CONTACTO: "warn",
  };

  function mostrarAvisoWhatsapp(aviso) {
    const linea = tarjetaResultado
      ? tarjetaResultado.querySelector("[data-resultado-whatsapp]")
      : null;
    if (linea) {
      if (aviso) {
        const fallido = aviso.estado === "ERROR" || aviso.estado === "SIN_CONTACTO";
        linea.classList.toggle("aviso-fallido", fallido);
        linea.textContent =
          "WhatsApp al apoderado" +
          (aviso.apoderado ? " (" + aviso.apoderado + ", " + aviso.destino + ")" : "") +
          ": " +
          aviso.estado_texto +
          ".";
        linea.hidden = false;
      } else {
        linea.textContent = "";
        linea.hidden = true;
      }
    }
    if (aviso) {
      agregarAvisoALista(aviso);
    }
  }

  function agregarAvisoALista(aviso) {
    const lista = document.querySelector("[data-lista-avisos]");
    if (!lista) {
      return;
    }
    const vacio = document.querySelector("[data-avisos-vacio]");
    if (vacio) {
      vacio.hidden = true;
    }
    const item = document.createElement("li");
    item.className = "aviso-item";
    item.innerHTML =
      '<div class="aviso-cabecera">' +
      '<span class="mono">' + escapar(aviso.hora) + "</span>" +
      "<strong>" + escapar(aviso.alumno) + "</strong>" +
      '<span class="chip chip-' + (CLASE_CHIP_AVISO[aviso.estado] || "neutral") + '">' +
      '<span class="chip-dot" aria-hidden="true"></span>' + escapar(aviso.estado_texto) +
      "</span></div>" +
      '<p class="aviso-destino">Para: ' + escapar(aviso.apoderado || "Apoderado") +
      ' · <span class="mono">' + escapar(aviso.destino) + "</span></p>" +
      '<p class="aviso-burbuja">' + escapar(aviso.mensaje) + "</p>";
    lista.insertBefore(item, lista.firstChild);
  }

  /* ============================ Resultado y corrección ============================ */
  function mostrarResultado(datos) {
    if (!tarjetaResultado) {
      return;
    }
    if (panelCorreccion) {
      panelCorreccion.hidden = true;
    }
    tarjetaResultado.hidden = false;
    const icono = tarjetaResultado.querySelector("[data-resultado-icono]");
    const eyebrow = tarjetaResultado.querySelector("[data-resultado-eyebrow]");
    const titulo = tarjetaResultado.querySelector("[data-resultado-titulo]");
    const alumno = tarjetaResultado.querySelector("[data-resultado-alumno]");
    const hora = tarjetaResultado.querySelector("[data-resultado-hora]");
    const estado = tarjetaResultado.querySelector("[data-resultado-estado]");
    const tardanza = tarjetaResultado.querySelector("[data-resultado-tardanza]");
    const metodo = tarjetaResultado.querySelector("[data-resultado-metodo]");

    const esTardanza = datos.estado === "TARDANZA";
    tarjetaResultado.classList.remove("resultado-error");
    tarjetaResultado.classList.toggle("resultado-tardanza", esTardanza);
    if (icono) {
      icono.textContent = esTardanza ? "!" : "✓";
    }
    if (eyebrow) {
      eyebrow.textContent = esTardanza ? "Ingreso con tardanza" : "Ingreso confirmado";
    }
    if (titulo) {
      titulo.textContent = datos.estado || "Registro confirmado";
    }
    if (alumno) {
      alumno.textContent = datos.alumno
        ? datos.alumno.nombre + " · " + datos.alumno.salon
        : "Alumno registrado";
    }
    if (hora) {
      hora.textContent = datos.hora || "—";
    }
    if (estado) {
      estado.textContent = datos.estado || "—";
    }
    if (tardanza) {
      tardanza.textContent =
        datos.estado === "TARDANZA" ? datos.minutos_tardanza + " min" : "0 min";
    }
    if (metodo) {
      metodo.textContent = datos.metodo || "CARNET";
    }
    mostrarAvisoWhatsapp(datos.whatsapp);

    iniciarCuentaRegresiva();
    tarjetaResultado.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function mostrarErrorResultado(texto) {
    if (!tarjetaResultado) {
      mostrarMensaje(texto, "error");
      return;
    }
    tarjetaResultado.hidden = false;
    if (panelCorreccion) {
      panelCorreccion.hidden = true;
    }
    tarjetaResultado.classList.remove("resultado-tardanza");
    tarjetaResultado.classList.add("resultado-error");
    const icono = tarjetaResultado.querySelector("[data-resultado-icono]");
    const eyebrow = tarjetaResultado.querySelector("[data-resultado-eyebrow]");
    const titulo = tarjetaResultado.querySelector("[data-resultado-titulo]");
    const alumno = tarjetaResultado.querySelector("[data-resultado-alumno]");
    const hora = tarjetaResultado.querySelector("[data-resultado-hora]");
    const estado = tarjetaResultado.querySelector("[data-resultado-estado]");
    const tardanza = tarjetaResultado.querySelector("[data-resultado-tardanza]");
    const metodo = tarjetaResultado.querySelector("[data-resultado-metodo]");
    if (icono) {
      icono.textContent = "✕";
    }
    if (eyebrow) {
      eyebrow.textContent = "No se pudo registrar";
    }
    if (titulo) {
      titulo.textContent = "Intente nuevamente";
    }
    if (alumno) {
      alumno.textContent = texto;
    }
    if (hora) {
      hora.textContent = "—";
    }
    if (estado) {
      estado.textContent = "—";
    }
    if (tardanza) {
      tardanza.textContent = "—";
    }
    if (metodo) {
      metodo.textContent = "—";
    }
    limpiarTemporizador();
    if (cuentaRegresiva) {
      cuentaRegresiva.textContent = "";
    }
    tarjetaResultado.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function mostrarErrorRegistro(texto) {
    mostrarMensaje(texto, "error");
    if (panelCorreccion && !panelCorreccion.hidden) {
      if (errorCorreccion) {
        errorCorreccion.textContent = texto;
      }
      return;
    }
    mostrarErrorResultado(texto);
  }

  function mostrarCorreccion(datos) {
    if (!panelCorreccion) {
      return;
    }
    if (tarjetaResultado) {
      tarjetaResultado.hidden = true;
    }
    panelCorreccion.hidden = false;
    const destino = panelCorreccion.querySelector("[data-correccion-alumno]");
    const texto = panelCorreccion.querySelector("[data-correccion-mensaje]");
    if (destino && datos.alumno) {
      destino.innerHTML = "";
      destino.appendChild(construirTarjeta(datos.alumno));
    }
    if (texto) {
      const registro = datos.asistencia;
      texto.textContent =
        (datos.mensaje || "El alumno figura AUSENTE. Ingrese el motivo para actualizar su estado.") +
        (registro
          ? " Registro original: " +
            registro.estado +
            " a las " +
            registro.hora +
            "."
          : "");
    }
    if (errorCorreccion) {
      errorCorreccion.textContent = "";
    }
    if (motivoQr) {
      motivoQr.value = "";
      motivoQr.focus();
    }
    panelCorreccion.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function confirmarCorreccion() {
    const motivo = motivoQr ? motivoQr.value.trim() : "";
    if (motivo.length < 5) {
      if (errorCorreccion) {
        errorCorreccion.textContent =
          "El motivo de la corrección debe tener al menos 5 caracteres.";
      }
      if (motivoQr) {
        motivoQr.focus();
      }
      return;
    }
    if (botonConfirmarCorreccion) {
      botonConfirmarCorreccion.disabled = true;
    }
    registrar(metodoPendiente, identificadorPendiente, motivo, alumnoPendiente).finally(
      function () {
        if (botonConfirmarCorreccion) {
          botonConfirmarCorreccion.disabled = false;
        }
      }
    );
  }

  /* ============================ Cuenta regresiva ============================ */
  function limpiarTemporizador() {
    if (temporizadorSiguiente) {
      window.clearInterval(temporizadorSiguiente);
      temporizadorSiguiente = null;
    }
    if (cuentaRegresiva) {
      cuentaRegresiva.textContent = "";
    }
  }

  function actualizarCuentaRegresiva() {
    if (cuentaRegresiva) {
      cuentaRegresiva.textContent = "(" + segundosRestantes + " s)";
    }
  }

  function iniciarCuentaRegresiva() {
    limpiarTemporizador();
    segundosRestantes = 8;
    actualizarCuentaRegresiva();
    temporizadorSiguiente = window.setInterval(function () {
      segundosRestantes -= 1;
      actualizarCuentaRegresiva();
      if (segundosRestantes <= 0) {
        escanearSiguiente();
      }
    }, 1000);
  }

  function escanearSiguiente() {
    limpiarTemporizador();
    procesando = false;
    if (tarjetaResultado) {
      tarjetaResultado.hidden = true;
      tarjetaResultado.classList.remove("resultado-error", "resultado-tardanza");
    }
    if (panelCorreccion) {
      panelCorreccion.hidden = true;
    }
    if (motivoQr) {
      motivoQr.value = "";
    }
    if (errorCorreccion) {
      errorCorreccion.textContent = "";
    }
    limpiarSeleccion();
    limpiarResultados();
    mostrarMensaje("", "");
    if (entrada) {
      entrada.value = "";
      entrada.focus();
    }
    if (panelCamara && !panelCamara.hidden) {
      iniciarCamara();
    }
  }

  /* ============================ Cámara QR ============================ */
  function esDispositivoMovil() {
    return (
      window.matchMedia("(pointer: coarse)").matches ||
      /Android|iPhone|iPad|iPod|Mobile|Windows Phone/i.test(navigator.userAgent)
    );
  }

  function mostrarEstadoCamara(texto, tipo) {
    if (!estadoCamara) {
      return;
    }
    estadoCamara.textContent = texto;
    estadoCamara.className = "field-help" + (tipo ? " texto-" + tipo : "");
  }

  function detenerCamara() {
    camaraDeseada = false;
    const actual = escaner;
    if (!actual || !camaraActiva) {
      if (botonDetener) {
        botonDetener.hidden = true;
      }
      if (botonIniciar) {
        botonIniciar.hidden = false;
      }
      return Promise.resolve();
    }
    camaraActiva = false;
    return actual
      .stop()
      .catch(function () {
        /* La cámara pudo haberse apagado ya. */
      })
      .then(function () {
        try {
          actual.clear();
        } catch (error) {
          /* Limpieza defensiva. */
        }
        if (escaner === actual) {
          escaner = null;
        }
        if (botonIniciar) {
          botonIniciar.hidden = false;
        }
        if (botonDetener) {
          botonDetener.hidden = true;
        }
        mostrarEstadoCamara("Cámara detenida. Inicie nuevamente para escanear otro carnet.");
      });
  }

  function cargarCamaras(preferida) {
    if (!selectorCamara || typeof Html5Qrcode === "undefined") {
      return Promise.resolve([]);
    }
    return Html5Qrcode.getCameras()
      .then(function (camaras) {
        selectorCamara.innerHTML = "";
        if (!camaras.length) {
          const opcion = document.createElement("option");
          opcion.value = "";
          opcion.textContent = "Detección automática";
          selectorCamara.appendChild(opcion);
          selectorCamara.disabled = true;
          return [];
        }

        const movil = esDispositivoMovil();
        let predeterminada = camaras[0];
        if (movil) {
          predeterminada =
            camaras.find(function (camara) {
              return /back|rear|trasera|environment/i.test(camara.label || "");
            }) || camaras[camaras.length - 1];
        } else {
          predeterminada =
            camaras.find(function (camara) {
              return /front|user|frontal|integrada|integrated|webcam/i.test(camara.label || "");
            }) || camaras[0];
        }

        camaras.forEach(function (camara) {
          const opcion = document.createElement("option");
          opcion.value = camara.id;
          opcion.textContent = camara.label || "Cámara " + camara.id;
          if (camara.id === predeterminada.id) {
            opcion.selected = true;
          }
          selectorCamara.appendChild(opcion);
        });
        if (
          preferida &&
          camaras.some(function (camara) {
            return camara.id === preferida;
          })
        ) {
          selectorCamara.value = preferida;
        }
        selectorCamara.disabled = false;
        return camaras;
      })
      .catch(function () {
        return [];
      });
  }

  function iniciarCamara() {
    if (!panelCamara || panelCamara.hidden) {
      return;
    }
    if (!lectorQr) {
      return;
    }
    if (typeof Html5Qrcode === "undefined") {
      if (botonIniciar) {
        botonIniciar.hidden = false;
      }
      mostrarEstadoCamara(
        "No se pudo cargar la librería de lectura QR. Verifique el archivo local html5-qrcode.min.js.",
        "error"
      );
      return;
    }
    if (camaraActiva || procesando) {
      return;
    }

    limpiarTemporizador();
    if (tarjetaResultado) {
      tarjetaResultado.hidden = true;
    }
    if (panelCorreccion) {
      panelCorreccion.hidden = true;
    }
    if (botonIniciar) {
      botonIniciar.hidden = true;
    }
    if (botonDetener) {
      botonDetener.hidden = true;
    }
    camaraDeseada = true;
    mostrarEstadoCamara("Solicitando permiso y preparando la cámara…");
    const seleccionPrevia =
      selectorCamara && !selectorCamara.disabled && selectorCamara.value
        ? selectorCamara.value
        : "";

    cargarCamaras(seleccionPrevia).then(function (camaras) {
      if (!camaraDeseada) {
        return;
      }
      const movil = esDispositivoMovil();
      const dispositivo = selectorCamara && !selectorCamara.disabled ? selectorCamara.value : "";
      const configuracion = dispositivo
        ? { deviceId: { exact: dispositivo } }
        : { facingMode: movil ? "environment" : "user" };

      escaner = new Html5Qrcode("lector-qr", { verbose: false });
      const configuracionLectura = {
        fps: 10,
        qrbox: function (anchoVista, altoVista) {
          const lado = Math.floor(Math.min(anchoVista, altoVista) * 0.68);
          return { width: lado, height: lado };
        },
        aspectRatio: 1.0,
      };
      escaner
        .start(
          configuracion,
          configuracionLectura,
          function (codigo) {
            procesarCodigo(codigo);
          },
          function () {
            /* Los fallos de lectura por fotograma son normales. */
          }
        )
        .then(function () {
          if (!camaraDeseada) {
            camaraActiva = true;
            return detenerCamara();
          }
          camaraActiva = true;
          if (botonIniciar) {
            botonIniciar.hidden = true;
          }
          if (botonDetener) {
            botonDetener.hidden = false;
          }
          const cantidad = camaras.length;
          mostrarEstadoCamara(
            cantidad
              ? "Cámara activa. Apunte el carnet al recuadro para leer el QR."
              : "Cámara activa en modo automático. Apunte el carnet al recuadro."
          );
          return undefined;
        })
        .catch(function (error) {
          camaraActiva = false;
          camaraDeseada = false;
          if (botonIniciar) {
            botonIniciar.hidden = false;
          }
          if (botonDetener) {
            botonDetener.hidden = true;
          }
          mostrarEstadoCamara(
            "No se pudo iniciar la cámara: " + (error && error.message ? error.message : error),
            "error"
          );
        });
    });
  }

  function abrirCamara() {
    if (!panelCamara) {
      return;
    }
    panelCamara.hidden = false;
    if (botonCamara) {
      botonCamara.setAttribute("aria-expanded", "true");
    }
    panelCamara.scrollIntoView({ block: "nearest", behavior: "smooth" });
    iniciarCamara();
  }

  function cerrarCamara() {
    if (!panelCamara) {
      return;
    }
    limpiarTemporizador();
    detenerCamara();
    panelCamara.hidden = true;
    if (botonCamara) {
      botonCamara.setAttribute("aria-expanded", "false");
      botonCamara.focus();
    }
  }

  function procesarCodigo(codigo) {
    if (procesando || !codigo) {
      return;
    }
    detenerCamara();
    limpiarTemporizador();
    if (tarjetaResultado) {
      tarjetaResultado.hidden = true;
    }
    if (entrada) {
      entrada.value = codigo;
    }
    if (campoMetodo) {
      campoMetodo.value = "CARNET";
    }
    if (campoAlumnoId) {
      campoAlumnoId.value = "";
    }
    if (tarjetaAlumno) {
      tarjetaAlumno.innerHTML = "";
      tarjetaAlumno.hidden = true;
    }
    if (resultados) {
      resultados.innerHTML = "";
    }
    mostrarEstadoCamara("Código leído. Confirmando con el servidor…");
    registrar("CARNET", codigo, null, "");
  }

  /* ============================ Eventos de entrada ============================ */
  if (entrada) {
    entrada.addEventListener("input", function () {
      const valor = entrada.value.trim();
      if (campoAlumnoId && campoAlumnoId.value) {
        limpiarSeleccion();
      }
      if (!valor) {
        limpiarResultados();
        mostrarMensaje("", "");
        return;
      }
      if (/^\d+$/.test(valor)) {
        limpiarResultados();
        if (esDni(valor)) {
          mostrarMensaje("DNI detectado. Presione Registrar ingreso.", "ok");
        } else {
          mostrarMensaje("Escriba los 8 dígitos del DNI.", "");
        }
        return;
      }
      if (esCarnet(valor)) {
        limpiarResultados();
        mostrarMensaje("Carnet detectado. Presione Registrar ingreso.", "ok");
        return;
      }
      limpiarResultados();
      mostrarMensaje("Buscando coincidencias por nombre…", "");
      if (valor.length >= 2) {
        temporizadorBusqueda = window.setTimeout(function () {
          buscarAlumnos(valor);
        }, 350);
      } else {
        mostrarMensaje("Escriba al menos 2 caracteres para buscar por nombre.", "");
      }
    });
  }

  formulario.addEventListener("submit", function (evento) {
    evento.preventDefault();
    if (procesando) {
      return;
    }
    const valor = entrada ? entrada.value.trim() : "";
    const alumnoId = campoAlumnoId ? campoAlumnoId.value : "";

    if (!valor && !alumnoId) {
      mostrarMensaje("Ingrese un carnet, DNI o nombre de alumno.", "error");
      if (entrada) {
        entrada.focus();
      }
      return;
    }
    if (alumnoId) {
      registrar("MANUAL_BUSQUEDA", "", null, alumnoId);
      return;
    }
    if (/^\d+$/.test(valor)) {
      if (!esDni(valor)) {
        mostrarMensaje("El DNI debe tener exactamente 8 dígitos.", "error");
        if (entrada) {
          entrada.focus();
        }
        return;
      }
      registrar("MANUAL_DNI", valor, null, "");
      return;
    }
    if (esCarnet(valor)) {
      registrar("CARNET", valor, null, "");
      return;
    }
    mostrarMensaje("Buscando coincidencias por nombre…", "");
    buscarAlumnos(valor);
  });

  if (botonLimpiar) {
    botonLimpiar.addEventListener("click", function () {
      if (entrada) {
        entrada.value = "";
      }
      limpiarSeleccion();
      limpiarResultados();
      mostrarMensaje("", "");
      if (tarjetaResultado) {
        tarjetaResultado.hidden = true;
        tarjetaResultado.classList.remove("resultado-error", "resultado-tardanza");
      }
      if (panelCorreccion) {
        panelCorreccion.hidden = true;
      }
      if (motivoQr) {
        motivoQr.value = "";
      }
      if (errorCorreccion) {
        errorCorreccion.textContent = "";
      }
      if (entrada) {
        entrada.focus();
      }
    });
  }

  if (botonCamara) {
    botonCamara.addEventListener("click", function () {
      if (panelCamara && panelCamara.hidden) {
        abrirCamara();
      } else {
        cerrarCamara();
      }
    });
  }
  if (botonCerrarCamara) {
    botonCerrarCamara.addEventListener("click", cerrarCamara);
  }
  if (botonIniciar) {
    botonIniciar.addEventListener("click", iniciarCamara);
  }
  if (botonDetener) {
    botonDetener.addEventListener("click", function () {
      limpiarTemporizador();
      detenerCamara();
    });
  }
  if (botonSiguiente) {
    botonSiguiente.addEventListener("click", escanearSiguiente);
  }
  if (botonConfirmarCorreccion) {
    botonConfirmarCorreccion.addEventListener("click", confirmarCorreccion);
  }
  if (botonCancelarCorreccion) {
    botonCancelarCorreccion.addEventListener("click", escanearSiguiente);
  }
  if (selectorCamara) {
    selectorCamara.addEventListener("change", function () {
      detenerCamara().then(iniciarCamara);
    });
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      limpiarTemporizador();
      detenerCamara();
    }
  });
  window.addEventListener("pagehide", function () {
    limpiarTemporizador();
    detenerCamara();
  });

  /* El escáner se muestra abierto desde el inicio: arrancar la cámara al cargar. */
  if (panelCamara && !panelCamara.hidden) {
    iniciarCamara();
  }
})();
