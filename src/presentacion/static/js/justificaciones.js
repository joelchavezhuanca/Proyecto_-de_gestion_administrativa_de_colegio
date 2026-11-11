/* Justificaciones: asistente de tres pasos y validaciones en línea. */
(function () {
  "use strict";

  const contenedor = document.querySelector("[data-contenedor-wizard]");
  if (!contenedor) {
    return;
  }

  const formulario = contenedor.querySelector("[data-form-justificacion]");
  if (!formulario) {
    return;
  }

  const botonesSiguiente = formulario.querySelectorAll("[data-ir-paso]");
  const botonesVolver = formulario.querySelectorAll("[data-volver-paso]");
  const selector = formulario.querySelector("#asistencia_id");
  const motivo = formulario.querySelector("#motivo");
  const contador = formulario.querySelector("[data-contador-texto]");
  const fecha = formulario.querySelector("#fecha_solicitud");
  const botonGuardar = formulario.querySelector("[data-boton-guardar-justificacion]");
  const resumenAlumno = formulario.querySelector("[data-resumen-alumno]");
  const resumenCategoria = formulario.querySelector("[data-resumen-categoria]");
  const resumenFecha = formulario.querySelector("[data-resumen-fecha]");

  function mostrarPaso(numero) {
    formulario.querySelectorAll("[data-paso]").forEach(function (paso) {
      paso.hidden = paso.getAttribute("data-paso") !== String(numero);
    });
    contenedor.querySelectorAll("[data-paso-indicador]").forEach(function (indicador) {
      const valor = Number(indicador.getAttribute("data-paso-indicador"));
      indicador.classList.toggle("activo", valor === numero);
      indicador.classList.toggle("completado", valor < numero);
    });
    if (numero === 3) {
      actualizarResumen();
    }
  }

  function categoriaSeleccionada() {
    const elegido = formulario.querySelector("input[name='categoria']:checked");
    if (!elegido) {
      return "Sin categoría";
    }
    const etiqueta = elegido.closest(".radio-card").querySelector("strong");
    return etiqueta ? etiqueta.textContent : elegido.value;
  }

  function textoSeleccionado() {
    if (!selector || !selector.value) {
      return "Sin registro seleccionado";
    }
    const opcion = selector.options[selector.selectedIndex];
    return opcion ? opcion.textContent.trim() : "Registro seleccionado";
  }

  function formatearFecha(valor) {
    if (!valor) {
      return "—";
    }
    const partes = valor.split("-");
    return partes.length === 3 ? partes[2] + "/" + partes[1] + "/" + partes[0] : valor;
  }

  function actualizarResumen() {
    if (resumenAlumno) {
      resumenAlumno.textContent = textoSeleccionado();
    }
    if (resumenCategoria) {
      resumenCategoria.textContent = categoriaSeleccionada();
    }
    if (resumenFecha) {
      resumenFecha.textContent = formatearFecha(fecha ? fecha.value : "");
    }
  }

  function validarPaso1() {
    if (!selector || !selector.value) {
      if (selector) {
        selector.focus();
        selector.setAttribute("aria-invalid", "true");
      }
      return false;
    }
    selector.setAttribute("aria-invalid", "false");
    return true;
  }

  function validarPaso2() {
    let valido = true;
    if (motivo) {
      const limpio = motivo.value.trim();
      const largo = limpio.length >= 10;
      motivo.setAttribute("aria-invalid", largo ? "false" : "true");
      if (!largo) {
        valido = false;
        motivo.focus();
      }
    }
    if (fecha && !fecha.value) {
      fecha.setAttribute("aria-invalid", "true");
      valido = false;
    } else if (fecha) {
      fecha.setAttribute("aria-invalid", "false");
    }
    return valido;
  }

  function actualizarContador() {
    if (!motivo || !contador) {
      return;
    }
    contador.textContent = motivo.value.length;
  }

  botonesSiguiente.forEach(function (boton) {
    boton.addEventListener("click", function () {
      const destino = boton.getAttribute("data-ir-paso");
      if (destino === "2" && !validarPaso1()) {
        return;
      }
      if (destino === "3" && !validarPaso2()) {
        return;
      }
      mostrarPaso(destino);
    });
  });

  botonesVolver.forEach(function (boton) {
    boton.addEventListener("click", function () {
      mostrarPaso(boton.getAttribute("data-volver-paso"));
    });
  });

  if (motivo) {
    motivo.addEventListener("input", function () {
      actualizarContador();
      if (motivo.value.trim().length >= 10) {
        motivo.setAttribute("aria-invalid", "false");
      }
    });
    actualizarContador();
  }

  formulario.querySelectorAll("input[name='categoria']").forEach(function (radio) {
    radio.addEventListener("change", actualizarResumen);
  });

  if (fecha) {
    fecha.addEventListener("change", function () {
      const hoy = formulario.getAttribute("data-hoy");
      if (hoy && fecha.value > hoy) {
        fecha.value = hoy;
      }
      actualizarResumen();
    });
  }

  formulario.addEventListener("submit", function (evento) {
    if (!validarPaso1() || !validarPaso2()) {
      evento.preventDefault();
      mostrarPaso(selector && selector.value ? 2 : 1);
    }
  });

  if (botonGuardar) {
    botonGuardar.addEventListener("click", function (evento) {
      if (!validarPaso1() || !validarPaso2()) {
        evento.preventDefault();
        mostrarPaso(selector && selector.value ? 2 : 1);
      }
    });
  }

  document.querySelectorAll("[data-justificar]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      const asistenciaId = boton.getAttribute("data-justificar");
      if (selector) {
        selector.value = asistenciaId;
      }
      mostrarPaso(2);
      contenedor.scrollIntoView({ behavior: "smooth", block: "start" });
      if (motivo) {
        motivo.focus({ preventScroll: true });
      }
    });
  });

  if (contenedor.getAttribute("data-abrir-wizard") === "si") {
    mostrarPaso(selector && selector.value ? 2 : 1);
    contenedor.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    mostrarPaso(1);
  }
  actualizarResumen();
})();
