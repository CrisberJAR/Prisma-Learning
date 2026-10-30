(function () {
  // Traducción de la interfaz (templates/_i18n_js.html); sin catálogo devuelve el español.
  var t = window.t || function (s, v) {
    return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s;
  };
  var ETIQUETAS = {
    queued: t("En cola"),
    running: t("En curso"),
    done: t("Listo"),
    failed: t("Falló"),
    extraer: t("Extracción"),
    formato: t("Formato"),
  };
  function etiqueta(v) {
    return ETIQUETAS[v] || v || "";
  }
  function iniciarTabs() {
    document.querySelectorAll('[role="tablist"]').forEach(function (lista) {
      var tabs = Array.prototype.slice.call(lista.querySelectorAll('[role="tab"]'));
      if (!tabs.length) return;
      function mostrar(elegida) {
        tabs.forEach(function (tab) {
          var on = tab === elegida;
          tab.setAttribute("aria-selected", on ? "true" : "false");
          var panel = document.getElementById(tab.getAttribute("aria-controls"));
          if (panel) panel.hidden = !on;
        });
      }
      tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
          mostrar(tab);
        });
      });
      mostrar(lista.querySelector('[aria-selected="true"]') || tabs[0]);
    });
  }

  iniciarTabs();

  var barras = document.querySelectorAll("[data-job-id]");
  if (!barras.length) return;

  function actualizar(barra) {
    var id = barra.getAttribute("data-job-id");
    fetch("/jobs/" + id, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (job) {
        if (!job) return;
        barra.setAttribute("aria-valuenow", String(job.progreso || 0));
        var fill = barra.querySelector("i");
        if (fill) fill.style.width = (job.progreso || 0) + "%";
        barra.setAttribute("data-job-estado", job.estado);
        var extra = job.formato ? " / " + job.formato : "";
        var texto = etiqueta(job.tipo) + extra + " · " + etiqueta(job.estado) + " · " + (job.progreso || 0) + "%";
        if (job.estado === "done") texto += " " + t("(listo: recarga para ver el resultado)");
        var label = document.querySelector('[data-job-label="' + id + '"]');
        if (label) label.textContent = texto;
        if (job.estado === "queued" || job.estado === "running") {
          setTimeout(function () { actualizar(barra); }, 2000);
        }
      })
      .catch(function () {});
  }

  barras.forEach(function (b) {
    // El estado viaja como atributo: el texto visible ya está traducido.
    var estado = b.getAttribute("data-job-estado") || "";
    if (estado === "queued" || estado === "running") {
      actualizar(b);
    }
  });
})();
