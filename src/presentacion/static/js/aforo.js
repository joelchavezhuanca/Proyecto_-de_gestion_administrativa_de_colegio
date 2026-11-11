/* Dashboard: modal defensivo del cierre escolar. */
(function () {
  "use strict";

  const modal = document.getElementById("modal-cierre");
  const abrir = document.querySelector("[data-abrir-cierre]");
  if (!modal) {
    return;
  }

  const checkbox = modal.querySelector("[data-check-cierre]");
  const botonConfirmar = modal.querySelector("[data-boton-cierre]");
  const cerrarBotones = modal.querySelectorAll("[data-cerrar-cierre]");

  function actualizarBoton() {
    if (botonConfirmar && checkbox) {
      botonConfirmar.disabled = !checkbox.checked;
    }
  }

  function abrirModal() {
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    if (checkbox) {
      checkbox.focus();
    }
  }

  function cerrarModal() {
    modal.hidden = true;
    document.body.style.overflow = "";
    if (abrir) {
      abrir.focus();
    }
  }

  if (abrir) {
    abrir.addEventListener("click", abrirModal);
  }

  cerrarBotones.forEach(function (boton) {
    boton.addEventListener("click", cerrarModal);
  });

  if (checkbox) {
    checkbox.addEventListener("change", actualizarBoton);
  }

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape" && !modal.hidden) {
      cerrarModal();
    }
  });

  actualizarBoton();
})();
