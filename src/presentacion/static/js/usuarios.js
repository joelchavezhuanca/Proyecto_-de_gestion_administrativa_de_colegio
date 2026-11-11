/* Gestión de usuarios: asistente de creación, disponibilidad y fortaleza. */
(function () {
  "use strict";

  const contenedor = document.querySelector("[data-contenedor-wizard-usuario]");
  if (!contenedor) {
    return;
  }

  const formulario = contenedor.querySelector("[data-form-usuario]");
  if (!formulario) {
    return;
  }

  const pasoInicial = Number(contenedor.getAttribute("data-paso-inicial") || "1");
  const nombre = formulario.querySelector("#nombre_completo");
  const username = formulario.querySelector("[data-username-disponible]");
  const mensajeUsername = formulario.querySelector("[data-username-mensaje]");
  const estadoCheckbox = formulario.querySelector("[data-estado-usuario]");
  const estadoOculto = formulario.querySelector("[data-estado-oculto]");
  const password = formulario.querySelector("[data-password-usuario]");
  const confirmar = formulario.querySelector("[data-password-confirmar]");
  const barraFuerza = formulario.querySelector("[data-fuerza-barra]");
  const mensajeConfirmar = formulario.querySelector("[data-confirmar-mensaje]");
  const requisitos = {
    longitud: formulario.querySelector("[data-requisito='longitud']"),
    mixta: formulario.querySelector("[data-requisito='mixta']"),
  };

  let usernameDisponible = true;
  let temporizador = null;

  function mostrarPaso(numero) {
    formulario.querySelectorAll("[data-paso]").forEach(function (paso) {
      paso.hidden = paso.getAttribute("data-paso") !== String(numero);
    });
    contenedor.querySelectorAll("[data-paso-indicador]").forEach(function (indicador) {
      const valor = Number(indicador.getAttribute("data-paso-indicador"));
      indicador.classList.toggle("activo", valor === numero);
      indicador.classList.toggle("completado", valor < numero);
    });
  }

  function mostrarMensajeUsuario(texto, tipo) {
    if (!mensajeUsername) {
      return;
    }
    mensajeUsername.textContent = texto;
    mensajeUsername.className = "field-message" + (tipo ? " " + tipo : "");
    if (username) {
      username.setAttribute("aria-invalid", tipo === "error" ? "true" : "false");
    }
  }

  function verificarDisponibilidad() {
    const valor = username.value.trim().toLowerCase();
    if (valor.length < 3) {
      usernameDisponible = false;
      mostrarMensajeUsuario("Use al menos 3 caracteres.", "error");
      return;
    }
    mostrarMensajeUsuario("Consultando disponibilidad…", "");
    fetch("/api/usuarios/disponible?username=" + encodeURIComponent(valor), {
      headers: { Accept: "application/json" },
    })
      .then(function (respuesta) {
        return respuesta.json();
      })
      .then(function (datos) {
        usernameDisponible = Boolean(datos.disponible);
        mostrarMensajeUsuario(
          datos.mensaje,
          usernameDisponible ? "ok" : "error"
        );
      })
      .catch(function () {
        usernameDisponible = true;
        mostrarMensajeUsuario("No se pudo verificar; el servidor validará al guardar.", "");
      });
  }

  function validarPaso1() {
    let valido = true;
    if (!nombre.value.trim()) {
      nombre.setAttribute("aria-invalid", "true");
      valido = false;
    } else {
      nombre.setAttribute("aria-invalid", "false");
    }
    if (!username.value.trim() || !usernameDisponible) {
      username.setAttribute("aria-invalid", "true");
      valido = false;
    }
    return valido;
  }

  function validarPaso2() {
    return Boolean(formulario.querySelector("input[name='rol']:checked"));
  }

  function validarPassword() {
    const valor = password.value;
    const largo = valor.length >= 8;
    const mixta = /[A-Za-z]/.test(valor) && /\d/.test(valor);
    if (requisitos.longitud) {
      requisitos.longitud.classList.toggle("cumplido", largo);
    }
    if (requisitos.mixta) {
      requisitos.mixta.classList.toggle("cumplido", mixta);
    }
    if (barraFuerza) {
      let porcentaje = 0;
      if (valor.length >= 8) porcentaje += 40;
      if (mixta) porcentaje += 30;
      if (/[^A-Za-z0-9]/.test(valor)) porcentaje += 20;
      if (valor.length >= 12) porcentaje += 10;
      barraFuerza.style.width = porcentaje + "%";
      barraFuerza.style.background =
        porcentaje >= 80 ? "#2e7d32" : porcentaje >= 50 ? "#fbc02d" : "#d32f2f";
    }
    password.setAttribute("aria-invalid", largo && mixta ? "false" : "true");
    return largo && mixta;
  }

  function validarConfirmacion() {
    const coincide = confirmar.value.length > 0 && confirmar.value === password.value;
    if (mensajeConfirmar) {
      mensajeConfirmar.textContent = coincide
        ? "Las contraseñas coinciden."
        : confirmar.value
          ? "Las contraseñas no coinciden."
          : "";
      mensajeConfirmar.className =
        "field-message" + (confirmar.value ? (coincide ? " ok" : " error") : "");
    }
    confirmar.setAttribute("aria-invalid", coincide ? "false" : "true");
    return coincide;
  }

  formulario.querySelectorAll("[data-ir-paso]").forEach(function (boton) {
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

  formulario.querySelectorAll("[data-volver-paso]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      mostrarPaso(boton.getAttribute("data-volver-paso"));
    });
  });

  if (username) {
    username.addEventListener("input", function () {
      usernameDisponible = false;
      window.clearTimeout(temporizador);
      temporizador = window.setTimeout(verificarDisponibilidad, 450);
    });
    username.addEventListener("blur", function () {
      window.clearTimeout(temporizador);
      verificarDisponibilidad();
    });
  }

  if (estadoCheckbox && estadoOculto) {
    estadoOculto.value = estadoCheckbox.checked ? "ACTIVO" : "INACTIVO";
    estadoCheckbox.addEventListener("change", function () {
      estadoOculto.value = estadoCheckbox.checked ? "ACTIVO" : "INACTIVO";
    });
  }

  if (password) {
    password.addEventListener("input", function () {
      validarPassword();
      if (confirmar.value) {
        validarConfirmacion();
      }
    });
    validarPassword();
  }

  if (confirmar) {
    confirmar.addEventListener("input", validarConfirmacion);
  }

  formulario.addEventListener("submit", function (evento) {
    if (!validarPaso1()) {
      evento.preventDefault();
      mostrarPaso(1);
      return;
    }
    if (!validarPaso2()) {
      evento.preventDefault();
      mostrarPaso(2);
      return;
    }
    if (!validarPassword() || !validarConfirmacion()) {
      evento.preventDefault();
      mostrarPaso(3);
    }
  });

  mostrarPaso(pasoInicial);
})();
