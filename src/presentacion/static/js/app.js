/* Interacciones comunes: navegación móvil, alertas y confirmaciones. */
(function () {
  "use strict";

  const botonMenu = document.querySelector("[data-menu-toggle]");
  const sidebar = document.getElementById("sidebar");

  if (botonMenu && sidebar) {
    botonMenu.addEventListener("click", function () {
      const abierto = sidebar.classList.toggle("abierto");
      botonMenu.setAttribute("aria-expanded", abierto ? "true" : "false");
    });

    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && sidebar.classList.contains("abierto")) {
        sidebar.classList.remove("abierto");
        botonMenu.setAttribute("aria-expanded", "false");
        botonMenu.focus();
      }
    });
  }

  document.querySelectorAll("[data-cerrar-alerta]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      const alerta = boton.closest(".alert");
      if (alerta) {
        alerta.remove();
      }
    });
  });

  document.querySelectorAll("form[data-confirmar]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      const mensaje = formulario.getAttribute("data-confirmar");
      if (mensaje && !window.confirm(mensaje)) {
        evento.preventDefault();
      }
    });
  });

  document.querySelectorAll("form[data-auto-filtro]").forEach(function (formulario) {
    formulario.querySelectorAll("select, input[type='date']").forEach(function (control) {
      control.addEventListener("change", function () {
        if (formulario.requestSubmit) {
          formulario.requestSubmit();
        } else {
          formulario.submit();
        }
      });
    });
  });
})();
