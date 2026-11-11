/* Registro de asistencia: lector USB, cámara QR, búsqueda y asistente manual. */
(function () {
  "use strict";

  const segmented = document.querySelector(".segmented");
  if (!segmented) {
    return;
  }

  const paneles = document.querySelectorAll("[data-modo-panel]");
  const radios = segmented.querySelectorAll("input[name='selector-modo']");

  /* ============================ Cámara QR ============================ */
  const lectorQr = document.querySelector("[data-lector-qr]");
  const botonIniciar = document.querySelector("[data-iniciar-camara]");
  const botonDetener = document.querySelector("[data-detener-camara]");
  const selectorCamara = document.querySelector("[data-camara-select]");
  const estadoCamara = document.querySelector("[data-camara-estado]");
  const tarjetaResultado = document.querySelector("[data-resultado-qr]");
  const panelCorreccion = document.querySelector("[data-correccion-qr]");
  const motivoQr = document.querySelector("[data-motivo-qr]");
  const botonConfirmarCorreccion = document.querySelector("[data-confirmar-correccion-qr]");
  const botonCancelarCorreccion = document.querySelector("[data-cancelar-correccion-qr]");
  const botonSiguiente = document.querySelector("[data-escanear-siguiente]");
  const cuentaRegresiva = document.querySelector("[data-cuenta-regresiva]");

  let escaner = null;
  let camaraActiva = false;
  let camaraDeseada = false;
  let procesando = false;
  let codigoPendiente = "";
  let temporizadorSiguiente = null;
  let segundosRestantes = 0;

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

  function limpiarTemporizador() {
    if (temporizadorSiguiente) {
      window.clearInterval(temporizadorSiguiente);
      temporizadorSiguiente = null;
    }
    if (cuentaRegresiva) {
      cuentaRegresiva.textContent = "";
    }
  }

  function detenerCamara() {
    camaraDeseada = false;
    if (!escaner || !camaraActiva) {
      return Promise.resolve();
    }
    camaraActiva = false;
    return escaner
      .stop()
      .catch(function () {
        /* La cámara pudo haberse apagado ya. */
      })
      .then(function () {
        if (escaner) {
          try {
            escaner.clear();
          } catch (error) {
            /* Limpieza defensiva. */
          }
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
    if (!lectorQr) {
      return;
    }
    if (typeof Html5Qrcode === "undefined") {
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
    tarjetaResultado.hidden = true;
    panelCorreccion.hidden = true;
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
      escaner
        .start(
          configuracion,
          { fps: 10, qrbox: { width: 260, height: 260 }, aspectRatio: 1.0 },
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
          botonIniciar.hidden = true;
          botonDetener.hidden = false;
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
          botonIniciar.hidden = false;
          botonDetener.hidden = true;
          mostrarEstadoCamara(
            "No se pudo iniciar la cámara: " + (error && error.message ? error.message : error),
            "error"
          );
        });
    });
  }

  function construirAlumno(alumno) {
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

  function mostrarResultado(datos) {
    panelCorreccion.hidden = true;
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

    iniciarCuentaRegresiva();
  }

  function mostrarErrorQr(mensaje) {
    tarjetaResultado.hidden = false;
    panelCorreccion.hidden = true;
    tarjetaResultado.classList.remove("resultado-tardanza");
    tarjetaResultado.classList.add("resultado-error");
    tarjetaResultado.querySelector("[data-resultado-icono]").textContent = "✕";
    tarjetaResultado.querySelector("[data-resultado-eyebrow]").textContent =
      "No se pudo registrar";
    tarjetaResultado.querySelector("[data-resultado-titulo]").textContent =
      "Intente nuevamente";
    tarjetaResultado.querySelector("[data-resultado-alumno]").textContent = mensaje;
    tarjetaResultado.querySelector("[data-resultado-hora]").textContent = "—";
    tarjetaResultado.querySelector("[data-resultado-estado]").textContent = "—";
    tarjetaResultado.querySelector("[data-resultado-tardanza]").textContent = "—";
    tarjetaResultado.querySelector("[data-resultado-metodo]").textContent = "—";
    iniciarCuentaRegresiva();
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

  function actualizarCuentaRegresiva() {
    if (cuentaRegresiva) {
      cuentaRegresiva.textContent = "(" + segundosRestantes + " s)";
    }
  }

  function escanearSiguiente() {
    limpiarTemporizador();
    procesando = false;
    codigoPendiente = "";
    tarjetaResultado.hidden = true;
    tarjetaResultado.classList.remove("resultado-error", "resultado-tardanza");
    panelCorreccion.hidden = true;
    if (motivoQr) {
      motivoQr.value = "";
    }
    if (document.querySelector("[data-lector-panel='CAMARA']").hidden === false) {
      iniciarCamara();
    }
  }

  function mostrarCorreccion(datos) {
    tarjetaResultado.hidden = true;
    panelCorreccion.hidden = false;
    codigoPendiente = datos.codigoPendiente || "";
    const destino = panelCorreccion.querySelector("[data-correccion-alumno]");
    const mensaje = panelCorreccion.querySelector("[data-correccion-mensaje]");
    if (destino && datos.alumno) {
      destino.innerHTML = "";
      destino.appendChild(construirAlumno(datos.alumno));
    }
    if (mensaje) {
      const registro = datos.asistencia;
      mensaje.textContent =
        (datos.mensaje || "El alumno figura AUSENTE. Ingrese el motivo para actualizar su estado.") +
        (registro
          ? " Registro original: " +
            registro.estado +
            " a las " +
            registro.hora +
            "."
          : "");
    }
    if (motivoQr) {
      motivoQr.focus();
    }
  }

  function procesarCodigo(codigo) {
    if (procesando || !codigo) {
      return;
    }
    procesando = true;
    detenerCamara();
    limpiarTemporizador();
    mostrarEstadoCamara("Código leído. Confirmando con el servidor…");

    enviarAsistencia(codigo, "")
      .then(function (datos) {
        if (datos.ok) {
          mostrarResultado(datos);
        } else if (datos.requiere_motivo) {
          mostrarCorreccion({
            alumno: datos.alumno,
            asistencia: datos.asistencia,
            mensaje: datos.mensaje,
            codigoPendiente: codigo,
          });
        } else {
          mostrarErrorQr(datos.mensaje || "No fue posible registrar la asistencia.");
        }
      })
      .catch(function (error) {
        mostrarErrorQr(error.message || "Error de conexión con el servidor.");
      })
      .finally(function () {
        procesando = false;
      });
  }

  function enviarAsistencia(codigo, motivo) {
    const cuerpo = new URLSearchParams();
    cuerpo.set("metodo", "CARNET");
    cuerpo.set("identificador", codigo);
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
      return respuesta.json();
    });
  }

  function confirmarCorreccion() {
    const motivo = motivoQr ? motivoQr.value.trim() : "";
    if (motivo.length < 5) {
      mostrarEstadoCamara("El motivo de la corrección debe tener al menos 5 caracteres.", "error");
      if (motivoQr) {
        motivoQr.focus();
      }
      return;
    }
    if (!codigoPendiente || procesando) {
      return;
    }
    procesando = true;
    botonConfirmarCorreccion.disabled = true;
    mostrarEstadoCamara("Confirmando la corrección…");

    enviarAsistencia(codigoPendiente, motivo)
      .then(function (datos) {
        if (datos.ok) {
          mostrarResultado(datos);
        } else if (datos.requiere_motivo) {
          mostrarCorreccion({
            alumno: datos.alumno,
            asistencia: datos.asistencia,
            mensaje: datos.mensaje,
            codigoPendiente: codigoPendiente,
          });
        } else {
          mostrarErrorQr(datos.mensaje || "No fue posible confirmar la corrección.");
        }
      })
      .catch(function (error) {
        mostrarEstadoCamara(error.message || "Error de conexión con el servidor.", "error");
      })
      .finally(function () {
        procesando = false;
        botonConfirmarCorreccion.disabled = false;
      });
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

  /* ============================ Modos principales ============================ */
  function activarModo(modo, enfocar) {
    radios.forEach(function (radio) {
      radio.checked = radio.value === modo;
    });
    paneles.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-modo-panel") !== modo;
    });
    if (modo !== "CARNET") {
      detenerCamara();
    }
    if (enfocar) {
      if (modo === "CARNET") {
        const carnet = document.querySelector("#carnet");
        if (carnet) {
          carnet.focus();
        }
      } else {
        const panel = document.querySelector('[data-modo-panel="' + modo + '"]');
        const campo = panel ? panel.querySelector("input:not([type='hidden'])") : null;
        if (campo) {
          campo.focus();
        }
      }
    }
  }

  radios.forEach(function (radio) {
    radio.addEventListener("change", function () {
      activarModo(radio.value, true);
    });
  });

  activarModo(segmented.getAttribute("data-modo-inicial") || "CARNET", false);

  /* ============================ Lector USB / cámara ============================ */
  const lectorSegmentado = document.querySelector(".segmented-secundario");
  const panelesLector = document.querySelectorAll("[data-lector-panel]");

  function activarLector(modo, enfocar) {
    if (!lectorSegmentado) {
      return;
    }
    lectorSegmentado.querySelectorAll("input[name='selector-lector']").forEach(function (radio) {
      radio.checked = radio.value === modo;
    });
    panelesLector.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-lector-panel") !== modo;
    });
    if (modo !== "CAMARA") {
      limpiarTemporizador();
      detenerCamara();
    }
    if (enfocar) {
      if (modo === "USB") {
        const campo = document.querySelector("#carnet");
        if (campo) {
          campo.focus();
        }
      } else if (botonIniciar && !camaraActiva) {
        botonIniciar.focus();
      }
    }
  }

  if (lectorSegmentado) {
    lectorSegmentado.querySelectorAll("input[name='selector-lector']").forEach(function (radio) {
      radio.addEventListener("change", function () {
        activarLector(radio.value, true);
      });
    });
    activarLector(lectorSegmentado.getAttribute("data-lector-inicial") || "USB", false);
  }

  /* ============================ Utilidades ============================ */
  function escapar(texto) {
    const div = document.createElement("div");
    div.textContent = texto == null ? "" : String(texto);
    return div.innerHTML;
  }

  function construirTarjeta(alumno) {
    const contenedor = document.createElement("div");
    contenedor.innerHTML =
      "<h3>" +
      escapar(alumno.nombre) +
      "</h3>" +
      "<p class='muted small'>Estado " +
      escapar(alumno.estado) +
      " · " +
      escapar(alumno.salon) +
      "</p>" +
      "<dl>" +
      "<div><dt>Código</dt><dd>" +
      escapar(alumno.codigo) +
      "</dd></div>" +
      "<div><dt>DNI</dt><dd>" +
      escapar(alumno.dni) +
      "</dd></div>" +
      "<div><dt>Carnet</dt><dd>" +
      escapar(alumno.carnet) +
      "</dd></div>" +
      "<div><dt>Salón</dt><dd>" +
      escapar(alumno.salon) +
      "</dd></div>" +
      "</dl>";
    return contenedor;
  }

  function mostrarPaso(formulario, numero) {
    formulario.querySelectorAll("[data-paso]").forEach(function (paso) {
      paso.hidden = paso.getAttribute("data-paso") !== String(numero);
    });
    formulario.querySelectorAll("[data-paso-indicador]").forEach(function (indicador) {
      const valor = Number(indicador.getAttribute("data-paso-indicador"));
      indicador.classList.toggle("activo", valor === numero);
      indicador.classList.toggle("completado", valor < numero);
    });
  }

  /* ============================ Manual por DNI ============================ */
  const formDni = document.querySelector("[data-form-dni]");
  if (formDni) {
    const campoDni = formDni.querySelector("#dni-manual");
    const mensaje = formDni.querySelector("[data-dni-mensaje]");
    const oculto = formDni.querySelector("[data-identificador-dni]");
    const tarjeta = formDni.querySelector("[data-tarjeta-dni]");
    const boton = formDni.querySelector("[data-verificar-dni]");

    function validarDni() {
      const valor = campoDni.value.trim();
      const valido = /^\d{8}$/.test(valor);
      campoDni.setAttribute("aria-invalid", valido ? "false" : "true");
      campoDni.classList.toggle("campo-valido", valido);
      if (!valor) {
        mensaje.textContent = "El DNI es obligatorio.";
        mensaje.className = "field-message error";
      } else if (!valido) {
        mensaje.textContent = "Debe contener exactamente 8 números.";
        mensaje.className = "field-message error";
      } else {
        mensaje.textContent = "Formato válido. Consultando al servidor…";
        mensaje.className = "field-message ok";
      }
      return valido;
    }

    function verificar() {
      if (!validarDni()) {
        campoDni.focus();
        return;
      }
      const dni = campoDni.value.trim();
      boton.disabled = true;
      fetch("/api/alumnos?q=" + encodeURIComponent(dni), {
        headers: { Accept: "application/json" },
      })
        .then(function (respuesta) {
          if (!respuesta.ok) {
            throw new Error("No fue posible consultar al alumno.");
          }
          return respuesta.json();
        })
        .then(function (datos) {
          const alumno = (datos.resultados || []).find(function (item) {
            return item.dni === dni;
          });
          if (!alumno) {
            mensaje.textContent =
              "No se encontró un alumno ACTIVO con ese DNI. Verifique el número.";
            mensaje.className = "field-message error";
            campoDni.setAttribute("aria-invalid", "true");
            return;
          }
          oculto.value = dni;
          tarjeta.innerHTML = "";
          tarjeta.appendChild(construirTarjeta(alumno));
          tarjeta.hidden = false;
          mensaje.textContent = "Alumno verificado.";
          mensaje.className = "field-message ok";
          mostrarPaso(formDni, 2);
        })
        .catch(function (error) {
          mensaje.textContent = error.message;
          mensaje.className = "field-message error";
        })
        .finally(function () {
          boton.disabled = false;
        });
    }

    campoDni.addEventListener("input", function () {
      const valor = campoDni.value.replace(/\D/g, "").slice(0, 8);
      if (campoDni.value !== valor) {
        campoDni.value = valor;
      }
      if (valor.length === 8) {
        validarDni();
      } else {
        mensaje.textContent = "";
        campoDni.setAttribute("aria-invalid", "false");
        campoDni.classList.remove("campo-valido");
      }
    });

    campoDni.addEventListener("blur", validarDni);
    campoDni.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") {
        evento.preventDefault();
        verificar();
      }
    });
    boton.addEventListener("click", verificar);
  }

  /* ============================ Búsqueda asistida ============================ */
  const formBusqueda = document.querySelector("[data-form-busqueda]");
  if (formBusqueda) {
    const campo = formBusqueda.querySelector("#busqueda");
    const boton = formBusqueda.querySelector("[data-buscar-alumno]");
    const resultados = formBusqueda.querySelector("[data-resultados-busqueda]");
    const tarjeta = formBusqueda.querySelector("[data-tarjeta-busqueda]");
    const oculto = formBusqueda.querySelector("[data-alumno-id-busqueda]");

    function buscar() {
      const criterio = campo.value.trim();
      if (criterio.length < 2) {
        resultados.innerHTML =
          "<p class='field-message error'>Escriba al menos 2 caracteres para buscar.</p>";
        return;
      }
      boton.disabled = true;
      resultados.innerHTML = "<p class='muted small'>Buscando coincidencias…</p>";
      fetch("/api/alumnos?q=" + encodeURIComponent(criterio), {
        headers: { Accept: "application/json" },
      })
        .then(function (respuesta) {
          if (!respuesta.ok) {
            throw new Error("No fue posible realizar la búsqueda.");
          }
          return respuesta.json();
        })
        .then(function (datos) {
          const lista = datos.resultados || [];
          resultados.innerHTML = "";
          if (!lista.length) {
            resultados.innerHTML =
              "<p class='field-message error'>No se encontraron alumnos ACTIVO con ese criterio.</p>";
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
              oculto.value = alumno.id;
              tarjeta.innerHTML = "";
              tarjeta.appendChild(construirTarjeta(alumno));
              tarjeta.hidden = false;
              resultados.innerHTML = "";
              mostrarPaso(formBusqueda, 2);
            });
            resultados.appendChild(item);
          });
        })
        .catch(function (error) {
          resultados.innerHTML =
            "<p class='field-message error'>" + escapar(error.message) + "</p>";
        })
        .finally(function () {
          boton.disabled = false;
        });
    }

    campo.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") {
        evento.preventDefault();
        buscar();
      }
    });
    boton.addEventListener("click", buscar);
  }

  /* ============================ Navegación del wizard ============================ */
  document.querySelectorAll("[data-form-dni], [data-form-busqueda]").forEach(function (formulario) {
    formulario.querySelectorAll("[data-ir-paso]").forEach(function (boton) {
      boton.addEventListener("click", function () {
        mostrarPaso(formulario, boton.getAttribute("data-ir-paso"));
      });
    });
    formulario.querySelectorAll("[data-volver-paso]").forEach(function (boton) {
      boton.addEventListener("click", function () {
        mostrarPaso(formulario, boton.getAttribute("data-volver-paso"));
      });
    });
  });
})();
