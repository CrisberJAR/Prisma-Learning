(function () {
  // Traducción de la interfaz (templates/_i18n_js.html); sin catálogo devuelve el español.
  var t = window.t || function (s, v) {
    return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s;
  };
  var caja = document.getElementById("imagen-educativa");
  if (!caja) return;
  var img = document.getElementById("img-edu");
  var estado = document.getElementById("img-edu-estado");
  var endpoint = caja.getAttribute("data-img-url");
  if (!endpoint || !img) return;
  if (document.body.classList.contains("dua-baja_vision")) {
    caja.classList.add("img-edu-contraste");
  }

  // Sin imagen no queda el recuadro de carga: solo el mensaje.
  function sinImagen() {
    var figura = img.closest("figure");
    if (figura) figura.hidden = true;
  }

  function mostrar(url, alt) {
    img.alt = alt || t("Imagen educativa del tema");
    img.onload = function () {
      img.hidden = false;
      if (estado) estado.hidden = true;
    };
    img.onerror = function () {
      sinImagen();
      if (estado) {
        estado.hidden = false;
        estado.textContent = t("No se pudo cargar la ilustración. Recarga la página para reintentar.");
      }
    };
    img.src = url;
  }

  fetch(endpoint, { headers: { Accept: "application/json" }, credentials: "same-origin" })
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      var cajaPrompt = document.getElementById("img-edu-prompt");
      if (cajaPrompt && j && j.prompt_ingles) {
        document.getElementById("img-edu-prompt-texto").textContent = j.prompt_ingles;
        cajaPrompt.hidden = false;
      }
      if (j && j.url) {
        mostrar(j.url, j.alt);
        return;
      }
      sinImagen();
      if (estado) {
        if (j && j.estado === "sin_texto") {
          estado.textContent = t("Cuando haya texto de la clase se generará la ilustración.");
        } else if (j && (j.error || j.estado === "error")) {
          estado.textContent = j.error || t("No se pudo generar la ilustración. Revisa el servidor e inténtalo de nuevo.");
        } else {
          estado.textContent = t("Aún no hay ilustración para este tema.");
        }
      }
    })
    .catch(function () {
      sinImagen();
      if (estado) estado.textContent = t("No se pudo generar la ilustración ahora. Recarga la página.");
    });

  var form = document.getElementById("form-dua-sim") || document.getElementById("form-dua-est");
  if (form) {
    form.addEventListener("change", function () {
      var baja = form.querySelector('[data-dua="baja_vision"]:checked');
      caja.classList.toggle("img-edu-contraste", !!baja);
    });
  }
})();
