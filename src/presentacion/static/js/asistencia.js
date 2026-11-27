/* Módulo de asistencia: registro unificado sin recargar y refresco del dashboard de aforo.
 * Solo presentación: toda validación y regla de negocio ocurre en el servidor.
 */
(function () {
  "use strict";

  const INTERVALO_AFORO_MS = 30000;

  function tokenCsrf(formulario) {
    const campo = formulario.querySelector("input[name='csrf_token']");
    return campo ? campo.value : "";
  }

  function mostrarResultado(contenedor, ok, texto) {
    contenedor.hidden = false;
    contenedor.classList.toggle("resultado-error", !ok);
    contenedor.textContent = texto;
  }

  // --- Registro unificado (POST JSON con cabecera X-CSRF-Token) ---------------
  const formulario = document.querySelector("form[data-registro-asistencia]");
  const resultado = document.querySelector("[data-resultado-registro]");

  if (formulario && resultado && window.fetch) {
    formulario.addEventListener("submit", function (evento) {
      evento.preventDefault();
      const datos = Object.fromEntries(new FormData(formulario).entries());
      delete datos.csrf_token;
      const boton = formulario.querySelector("button[type='submit']");
      if (boton) {
        boton.disabled = true;
      }

      fetch(formulario.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": tokenCsrf(formulario),
        },
        body: JSON.stringify(datos),
      })
        .then(function (respuesta) {
          return respuesta.json().then(function (cuerpo) {
            return { ok: respuesta.ok, cuerpo: cuerpo };
          });
        })
        .then(function (r) {
          if (r.ok && r.cuerpo.ok) {
            const a = r.cuerpo.asistencia;
            const salon = [a.nivel, a.grado, a.seccion].filter(Boolean).join(" ");
            let texto = "Registrado: " + a.estado + " a las " + a.hora_efectiva.slice(0, 5);
            if (a.minutos_tardanza > 0) {
              texto += " (" + a.minutos_tardanza + " min de tardanza)";
            }
            if (salon) {
              texto += " · " + salon;
            }
            mostrarResultado(resultado, true, texto);
            formulario.reset();
          } else {
            mostrarResultado(resultado, false, (r.cuerpo && r.cuerpo.error) || "No se pudo registrar.");
          }
        })
        .catch(function () {
          mostrarResultado(resultado, false, "Error de conexión. Intente nuevamente.");
        })
        .finally(function () {
          if (boton) {
            boton.disabled = false;
          }
          const campo = formulario.querySelector("[name='valor']");
          if (campo) {
            campo.focus();
          }
        });
    });
  }

  // --- Refresco periódico de los KPI del dashboard de aforo -------------------
  const panelAforo = document.querySelector("[data-metricas-aforo]");

  if (panelAforo && window.fetch) {
    const url = panelAforo.getAttribute("data-url");

    const refrescar = function () {
      if (document.hidden) {
        return;
      }
      fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (respuesta) {
          return respuesta.ok ? respuesta.json() : null;
        })
        .then(function (cuerpo) {
          if (!cuerpo || !cuerpo.ok) {
            return;
          }
          panelAforo.querySelectorAll("[data-kpi]").forEach(function (nodo) {
            const clave = nodo.getAttribute("data-kpi");
            if (!(clave in cuerpo.metricas)) {
              return;
            }
            const valor = cuerpo.metricas[clave];
            nodo.textContent = clave === "porcentaje_asistencia" ? Number(valor).toFixed(1) : valor;
          });
        })
        .catch(function () {
          /* Silencioso: el siguiente ciclo reintenta. */
        });
    };

    window.setInterval(refrescar, INTERVALO_AFORO_MS);
  }
})();
