// Fórmulas en el texto de la IA: \(...\), \[...\] y $$...$$ con KaTeX (static/vendor/katex).
// Se apartan antes de procesar el Markdown para que nada toque el LaTeX, y sin KaTeX se muestra el texto original.
(function (global) {
  var PATRON = /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)/g;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function extraer(texto) {
    var formulas = [];
    var limpio = String(texto || "").replace(PATRON, function (crudo, bloque, bloque2, linea) {
      formulas.push({ tex: bloque || bloque2 || linea, bloque: !linea, crudo: crudo });
      return "" + (formulas.length - 1) + "";
    });
    return { texto: limpio, formulas: formulas };
  }

  function formulaHtml(f) {
    if (!f) return "";
    if (!global.katex) return esc(f.crudo);
    try {
      return global.katex.renderToString(f.tex, { displayMode: f.bloque, throwOnError: false, output: "htmlAndMathml" });
    } catch (e) {
      return esc(f.crudo);
    }
  }

  function restaurar(html, formulas) {
    return String(html)
      .replace(/(\d+)/g, function (m, i) { return formulaHtml(formulas[+i]); })
      .replace(/\d*|/g, ""); // restos de una fórmula cortada por un título abreviado
  }

  // Para texto plano: <b data-mates>…</b>. Lo demás del contenido se sigue tratando como texto.
  function pintar(el) {
    var ext = extraer(el.textContent);
    if (ext.formulas.length) el.innerHTML = restaurar(esc(ext.texto), ext.formulas);
  }

  // La voz lee la fórmula (la parte MathML), no el marcado visual ni el LaTeX.
  function textoVoz(nodo) {
    var copia = nodo.cloneNode(true);
    copia.querySelectorAll(".katex").forEach(function (k) {
      var math = k.querySelector(".katex-mathml math");
      if (math) math.querySelectorAll("annotation").forEach(function (a) { a.remove(); });
      k.replaceWith(document.createTextNode(math ? " " + math.textContent + " " : ""));
    });
    return copia.textContent;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-mates]").forEach(pintar);
  });

  global.PrismaMates = { extraer: extraer, restaurar: restaurar, pintar: pintar, textoVoz: textoVoz };
})(window);
