// Simulador DUA del docente: panel flotante y ocultable, resumen de lo activo y comparación con el original.
(function () {
  // Traducción de la interfaz (templates/_i18n_js.html); sin catálogo devuelve el español.
  var t = window.t || function (s, v) {
    return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s;
  };
  var sim = document.getElementById("simulador");
  var panel = document.getElementById("sim-panel");
  var form = document.getElementById("form-dua-sim");
  if (!sim || !panel || !form) return;
  var boton = document.getElementById("sim-abrir");
  var cuenta = document.getElementById("sim-cuenta");
  var chips = document.getElementById("sim-chips");
  var comparar = document.getElementById("sim-comparar");
  var vista = document.getElementById("sim-vista");
  var original = document.getElementById("sim-original");

  // A <body>: un ancestro con animación o backdrop-filter recortaría su position:fixed.
  document.body.appendChild(panel);

  var abierto = false;
  var enPantalla = true;

  function actualizarPanel() {
    panel.hidden = !(abierto && enPantalla);
    sim.classList.toggle("con-flotante", abierto);
    boton.setAttribute("aria-expanded", abierto ? "true" : "false");
  }

  function abrir() {
    abierto = true;
    actualizarPanel();
    panel.focus({ preventScroll: true }); // abrir el panel no debe mover lo que se está mirando
  }

  function cerrar() {
    abierto = false;
    actualizarPanel();
    boton.focus({ preventScroll: true });
  }

  boton.addEventListener("click", function () {
    if (abierto) cerrar();
    else abrir();
  });
  panel.querySelector("[data-sim-cerrar]").addEventListener("click", cerrar);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && abierto) cerrar();
  });

  // Fuera de la vista (otra pestaña) el panel se oculta y vuelve al regresar.
  if (window.IntersectionObserver) {
    new IntersectionObserver(function (entradas) {
      enPantalla = entradas[entradas.length - 1].isIntersecting;
      actualizarPanel();
    }).observe(sim);
  }

  // ---------- Resumen de adaptaciones activas ----------
  function activas() {
    return Array.prototype.slice.call(form.querySelectorAll("[data-dua]:checked"));
  }

  function quitar(casilla) {
    casilla.checked = false;
    casilla.dispatchEvent(new Event("change", { bubbles: true })); // dua.js repinta la vista
  }

  function pintarResumen() {
    var lista = activas();
    cuenta.textContent = lista.length;
    cuenta.hidden = !lista.length;
    chips.textContent = "";
    if (!lista.length) {
      var nada = document.createElement("span");
      nada.className = "mut";
      nada.textContent = t("Sin adaptaciones: así se ve el texto original.");
      chips.appendChild(nada);
      return;
    }
    lista.forEach(function (casilla) {
      var nombre = casilla.closest("label").textContent.trim();
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip sim-chip";
      chip.setAttribute("aria-label", t("Quitar {nombre}", { nombre: nombre }));
      chip.textContent = nombre;
      chip.insertAdjacentHTML("beforeend", '<svg class="ico" aria-hidden="true" focusable="false"><use href="#i-x"></use></svg>');
      chip.addEventListener("click", function () {
        quitar(casilla);
        boton.focus({ preventScroll: true }); // el chip pulsado desaparece: el foco no se pierde
      });
      chips.appendChild(chip);
    });
  }

  form.addEventListener("change", pintarResumen);
  document.getElementById("sim-quitar-todas").addEventListener("click", function () {
    activas().forEach(quitar);
  });
  pintarResumen();

  // ---------- Comparar con el original ----------
  var originalPintado = false;
  comparar.addEventListener("click", function () {
    var activo = comparar.getAttribute("aria-pressed") !== "true";
    comparar.setAttribute("aria-pressed", activo ? "true" : "false");
    vista.classList.toggle("comparando", activo);
    if (activo && !originalPintado && window.PrismaDUA) {
      var nodo = document.getElementById("dua-texto");
      try { original.textContent = JSON.parse(nodo.textContent || '""'); } catch (e) { original.textContent = ""; }
      window.PrismaDUA.pintarMd(original);
      originalPintado = true;
    }
  });
})();
