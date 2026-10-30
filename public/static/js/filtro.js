// Buscador en vivo: <input data-filtro="#contenedor"> oculta los hijos [data-buscar] que no coinciden.
// Ignora mayúsculas y tildes ("biologia" encuentra "Biología") y anuncia el número de resultados.
(function () {
  // Traducción de la interfaz (templates/_i18n_js.html); sin catálogo devuelve el español.
  var t = window.t || function (s, v) {
    return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s;
  };
  function normalizar(t) {
    return String(t || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .trim();
  }

  document.querySelectorAll("input[data-filtro]").forEach(function (input) {
    var contenedor = document.querySelector(input.getAttribute("data-filtro"));
    if (!contenedor) return;
    var estado = document.querySelector(input.getAttribute("data-filtro-estado") || "");
    var vacio = document.querySelector('[data-filtro-vacio="' + input.getAttribute("data-filtro") + '"]');
    var items = Array.prototype.slice.call(contenedor.querySelectorAll("[data-buscar]"));
    items.forEach(function (el) {
      el._texto = normalizar(el.getAttribute("data-buscar"));
    });
    var espera;

    function aplicar() {
      var palabras = normalizar(input.value).split(/\s+/).filter(Boolean);
      var visibles = 0;
      items.forEach(function (el) {
        var ok = palabras.every(function (p) {
          return el._texto.indexOf(p) >= 0;
        });
        el.hidden = !ok;
        if (ok) visibles++;
      });
      if (vacio) vacio.hidden = visibles > 0;
      if (estado) {
        estado.textContent = palabras.length
          ? visibles === 1
            ? t("1 resultado de {total}", { total: items.length })
            : t("{n} resultados de {total}", { n: visibles, total: items.length })
          : "";
      }
    }

    input.addEventListener("input", function () {
      clearTimeout(espera);
      espera = setTimeout(aplicar, 120);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && input.value) {
        input.value = "";
        aplicar();
      }
      // Con JS activo, Enter no recarga la página: el filtro ya está aplicado.
      if (e.key === "Enter") e.preventDefault();
    });
    if (input.value) aplicar();
  });

  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirmar"))) e.preventDefault();
    });
  });
})();
