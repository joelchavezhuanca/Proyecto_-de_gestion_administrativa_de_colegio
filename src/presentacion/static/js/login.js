/* Inicio de sesión: mostrar contraseña y validación en línea. */
(function () {
  "use strict";

  const formulario = document.querySelector("[data-login-form]");
  if (!formulario) {
    return;
  }

  const usuario = formulario.querySelector("#username");
  const password = formulario.querySelector("#password");
  const botonVer = formulario.querySelector("[data-toggle-password]");

  function mensaje(campo, texto, tipo) {
    const destino = formulario.querySelector('[data-error-for="' + campo.id + '"]');
    if (!destino) {
      return;
    }
    destino.textContent = texto;
    destino.className = "field-message" + (tipo ? " " + tipo : "");
    campo.setAttribute("aria-invalid", tipo === "error" ? "true" : "false");
  }

  function validarUsuario() {
    if (!usuario.value.trim()) {
      mensaje(usuario, "El nombre de usuario es obligatorio.", "error");
      return false;
    }
    mensaje(usuario, "Formato correcto.", "ok");
    return true;
  }

  function validarPassword() {
    if (!password.value) {
      mensaje(password, "La contraseña es obligatoria.", "error");
      return false;
    }
    if (password.value.length < 8) {
      mensaje(password, "La contraseña debe tener mínimo 8 caracteres.", "error");
      return false;
    }
    mensaje(password, "Longitud correcta.", "ok");
    return true;
  }

  if (botonVer) {
    botonVer.addEventListener("click", function () {
      const mostrar = password.type === "password";
      password.type = mostrar ? "text" : "password";
      botonVer.textContent = mostrar ? "Ocultar" : "Ver";
      botonVer.setAttribute("aria-pressed", mostrar ? "true" : "false");
      botonVer.setAttribute(
        "aria-label",
        mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
      );
    });
  }

  usuario.addEventListener("blur", validarUsuario);
  usuario.addEventListener("input", function () {
    if (usuario.value.trim()) {
      mensaje(usuario, "", "");
    }
  });

  password.addEventListener("blur", validarPassword);
  password.addEventListener("input", function () {
    if (password.value.length >= 8) {
      mensaje(password, "", "");
    }
  });

  formulario.addEventListener("submit", function (evento) {
    const usuarioValido = validarUsuario();
    const passwordValido = validarPassword();
    if (!usuarioValido || !passwordValido) {
      evento.preventDefault();
    }
  });
})();
