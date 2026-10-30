// Interfaz común: menú de la cuenta y paneles laterales de la clase (ajustes, apoyo, tutor).
(function () {
  // ---------- Menú de la cuenta: se cierra al pulsar fuera o con Escape ----------
  var menu = document.querySelector(".menu-cuenta");
  if (menu) {
    document.addEventListener("click", function (e) {
      if (menu.open && !menu.contains(e.target)) menu.open = false;
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.open) {
        menu.open = false;
        menu.querySelector("summary").focus();
      }
    });
  }

  // ---------- Paneles de la clase ----------
  // Sin JavaScript los paneles se ven debajo de la clase; con él, se abren de uno en uno.
  var clase = document.querySelector("[data-clase]");
  var barra = document.querySelector("[data-barra-clase]");
  if (!clase || !barra) return;
  var botones = Array.prototype.slice.call(barra.querySelectorAll("[data-panel-abrir]"));
  var abierto = null;


  function boton(id) {
    return botones.filter(function (b) { return b.getAttribute("data-panel-abrir") === id; })[0];
  }

  function cerrar(devolverFoco) {
    if (!abierto) return;
    var id = abierto.id;
    abierto.classList.remove("activo");
    abierto = null;
    clase.classList.remove("con-panel");
    document.body.classList.remove("panel-abierto");
    var b = boton(id);
    b.setAttribute("aria-expanded", "false");
    if (devolverFoco) b.focus();
  }

  function abrir(id) {
    cerrar(false);
    abierto = document.getElementById(id);
    if (!abierto) return;
    abierto.classList.add("activo");
    clase.classList.add("con-panel");
    // Una "hoja" deja ver la clase detrás en móvil: la página se sigue pudiendo mover.
    document.body.classList.toggle("panel-abierto", !abierto.classList.contains("hoja"));
    boton(id).setAttribute("aria-expanded", "true");
    abierto.focus({ preventScroll: true }); // abrir un panel no debe mover el punto de lectura
  }

  botones.forEach(function (b) {
    b.addEventListener("click", function () {
      var id = b.getAttribute("data-panel-abrir");
      if (abierto && abierto.id === id) cerrar(true);
      else abrir(id);
    });
  });
  clase.querySelectorAll("[data-panel-cerrar]").forEach(function (b) {
    b.addEventListener("click", function () { cerrar(true); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && abierto) cerrar(true);
  });
})();
