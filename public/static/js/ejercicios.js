// Editor de ejercicios del docente: edita, agrega, quita y reordena; al guardar se envía como JSON.
// También: formularios con data-esperando muestran un aviso y bloquean el botón mientras la IA trabaja.
(function () {
  // Traducción de la interfaz (templates/_i18n_js.html); sin catálogo devuelve el español.
  var t = window.t || function (s, v) {
    return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s;
  };

  document.querySelectorAll("form[data-esperando]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector("button[type=submit]");
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
      }
      var aviso = document.createElement("p");
      aviso.className = "aviso";
      aviso.setAttribute("role", "status");
      aviso.textContent = form.getAttribute("data-esperando");
      form.appendChild(aviso);
    });
  });

  var raiz = document.getElementById("editor-ejercicios");
  var datos = document.getElementById("ejercicios-datos");
  var form = document.getElementById("form-ejercicios");
  if (!raiz || !datos || !form) return;

  var inicial = JSON.parse(datos.textContent || "{}");
  var TIPOS = inicial.tipos || {};
  var items = (inicial.items || []).map(function (it) { return JSON.parse(JSON.stringify(it)); });
  var estado = document.getElementById("estado-editor");
  var cambios = false;

  function marcar() {
    cambios = true;
    if (estado) estado.textContent = t("Hay cambios sin guardar.");
  }

  function el(tag, attrs, hijos) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "texto") n.textContent = attrs[k];
      else if (k in n && k !== "list") n[k] = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (hijos || []).forEach(function (h) { if (h) n.appendChild(h); });
    return n;
  }

  function icono(nombre) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ico");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-" + nombre);
    svg.appendChild(use);
    return svg;
  }

  function campo(id, etiqueta, control) {
    return el("p", {}, [el("label", { htmlFor: id, texto: etiqueta }), control]);
  }

  function nuevo(tipo) {
    var base = { id: Math.random().toString(16).slice(2, 12), tipo: tipo, enunciado: "", explicacion: "" };
    if (tipo === "opcion_multiple") { base.opciones = ["", "", "", ""]; base.correcta = 0; }
    else if (tipo === "verdadero_falso") base.correcta = true;
    else base.correcta = "";
    return base;
  }

  function pintar() {
    raiz.innerHTML = "";
    if (!items.length) {
      raiz.appendChild(el("p", { className: "aviso", texto: t("No hay ejercicios. Agrega uno o genera con IA.") }));
    }
    items.forEach(function (it, i) {
      var pre = "ej-" + i + "-";
      var tarjeta = el("fieldset", { className: "glass caja ejercicio" });
      tarjeta.appendChild(el("legend", { texto: t("Ejercicio {n}", { n: i + 1 }) }));

      var selTipo = el("select", { id: pre + "tipo" });
      Object.keys(TIPOS).forEach(function (k) {
        // Los nombres de tipo ya vienen traducidos desde el servidor.
        selTipo.appendChild(el("option", { value: k, texto: TIPOS[k], selected: k === it.tipo }));
      });
      selTipo.addEventListener("change", function () {
        var reemplazo = nuevo(selTipo.value);
        reemplazo.id = it.id;
        reemplazo.enunciado = it.enunciado;
        reemplazo.explicacion = it.explicacion;
        items[i] = reemplazo;
        marcar();
        pintar();
      });
      tarjeta.appendChild(campo(pre + "tipo", t("Tipo"), selTipo));

      var enunciado = el("textarea", { id: pre + "enunciado", rows: 2, value: it.enunciado || "", required: true });
      enunciado.addEventListener("input", function () { it.enunciado = enunciado.value; marcar(); });
      tarjeta.appendChild(campo(pre + "enunciado", t("Enunciado"), enunciado));

      if (it.tipo === "opcion_multiple") {
        var grupo = el("fieldset", {}, [el("legend", { texto: t("Opciones (marca la correcta)") })]);
        it.opciones.forEach(function (op, j) {
          var radio = el("input", { type: "radio", name: pre + "correcta", checked: it.correcta === j, "aria-label": t("Opción {n} es la correcta", { n: j + 1 }) });
          radio.addEventListener("change", function () { it.correcta = j; marcar(); });
          var texto = el("input", { type: "text", value: op, "aria-label": t("Texto de la opción {n}", { n: j + 1 }), maxLength: 300 });
          texto.addEventListener("input", function () { it.opciones[j] = texto.value; marcar(); });
          var quitar = el("button", { type: "button", className: "btn", "aria-label": t("Quitar la opción {n}", { n: j + 1 }), disabled: it.opciones.length <= 2 });
          quitar.appendChild(icono("x"));
          quitar.addEventListener("click", function () {
            it.opciones.splice(j, 1);
            if (it.correcta >= it.opciones.length) it.correcta = 0;
            else if (it.correcta > j) it.correcta -= 1;
            marcar();
            pintar();
          });
          grupo.appendChild(el("p", { className: "opcion" }, [radio, texto, quitar]));
        });
        if (it.opciones.length < 6) {
          var mas = el("button", { type: "button", className: "btn" }, [icono("plus"), document.createTextNode(t("Agregar opción"))]);
          mas.addEventListener("click", function () { it.opciones.push(""); marcar(); pintar(); });
          grupo.appendChild(mas);
        }
        tarjeta.appendChild(grupo);
      } else if (it.tipo === "verdadero_falso") {
        var vf = el("fieldset", {}, [el("legend", { texto: t("Respuesta correcta") })]);
        [[true, t("Verdadero")], [false, t("Falso")]].forEach(function (par) {
          var r = el("input", { type: "radio", name: pre + "vf", checked: it.correcta === par[0] });
          r.addEventListener("change", function () { it.correcta = par[0]; marcar(); });
          vf.appendChild(el("label", { className: "chk" }, [r, document.createTextNode(" " + par[1])]));
        });
        tarjeta.appendChild(vf);
      } else {
        var esperada = el("textarea", { id: pre + "esperada", rows: 2, value: it.correcta || "" });
        esperada.addEventListener("input", function () { it.correcta = esperada.value; marcar(); });
        tarjeta.appendChild(campo(pre + "esperada", t("Respuesta esperada y criterios (la IA la usa para evaluar)"), esperada));
      }

      var expl = el("textarea", { id: pre + "explicacion", rows: 2, value: it.explicacion || "" });
      expl.addEventListener("input", function () { it.explicacion = expl.value; marcar(); });
      tarjeta.appendChild(campo(pre + "explicacion", t("Explicación para el estudiante (se muestra al terminar)"), expl));

      var acciones = el("p", { className: "acciones" });
      var subir = el("button", { type: "button", className: "btn", "aria-label": t("Subir el ejercicio {n}", { n: i + 1 }), disabled: i === 0 });
      subir.appendChild(icono("arrow-up"));
      subir.addEventListener("click", function () { items.splice(i - 1, 0, items.splice(i, 1)[0]); marcar(); pintar(); });
      var bajar = el("button", { type: "button", className: "btn", "aria-label": t("Bajar el ejercicio {n}", { n: i + 1 }), disabled: i === items.length - 1 });
      bajar.appendChild(icono("arrow-down"));
      bajar.addEventListener("click", function () { items.splice(i + 1, 0, items.splice(i, 1)[0]); marcar(); pintar(); });
      var borrar = el("button", { type: "button", className: "btn d" }, [icono("trash"), document.createTextNode(t("Eliminar ejercicio"))]);
      borrar.addEventListener("click", function () {
        if (!window.confirm(t("¿Eliminar el ejercicio {n}?", { n: i + 1 }))) return;
        items.splice(i, 1);
        marcar();
        pintar();
      });
      acciones.appendChild(subir);
      acciones.appendChild(bajar);
      acciones.appendChild(borrar);
      tarjeta.appendChild(acciones);
      raiz.appendChild(tarjeta);
    });
  }

  document.getElementById("btn-agregar-ejercicio").addEventListener("click", function () {
    items.push(nuevo("opcion_multiple"));
    marcar();
    pintar();
    var ultimo = raiz.querySelectorAll("textarea[id$=enunciado]");
    if (ultimo.length) ultimo[ultimo.length - 1].focus();
  });

  form.addEventListener("submit", function () {
    document.getElementById("items-json").value = JSON.stringify(items);
    cambios = false;
  });

  window.addEventListener("beforeunload", function (e) {
    if (cambios) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  pintar();
})();
