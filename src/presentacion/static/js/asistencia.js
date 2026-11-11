/* Registro de asistencia: modos, búsqueda asistida y asistente manual. */
(function () {
  "use strict";

  const segmented = document.querySelector(".segmented");
  if (!segmented) {
    return;
  }

  const paneles = document.querySelectorAll("[data-modo-panel]");
  const radios = segmented.querySelectorAll("input[name='selector-modo']");

  function activarModo(modo, enfocar) {
    radios.forEach(function (radio) {
      radio.checked = radio.value === modo;
    });
    paneles.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-modo-panel") !== modo;
    });
    if (enfocar) {
      const panel = document.querySelector('[data-modo-panel="' + modo + '"]');
      const campo = panel ? panel.querySelector("input:not([type='hidden'])") : null;
      if (campo) {
        campo.focus();
      }
    }
  }

  radios.forEach(function (radio) {
    radio.addEventListener("change", function () {
      activarModo(radio.value, true);
    });
  });

  activarModo(segmented.getAttribute("data-modo-inicial") || "CARNET", false);

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

  /* ----------------------------- Manual por DNI ----------------------------- */
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

  /* ----------------------------- Búsqueda asistida ----------------------------- */
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

  /* ----------------------------- Navegación del wizard ----------------------------- */
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
