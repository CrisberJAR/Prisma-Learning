from app import create_app


def test_entrar_tiene_saltar_etiquetas_y_autocomplete():
    html = create_app().test_client().get("/entrar").get_data(as_text=True)
    assert 'lang="es"' in html
    assert 'href="#contenido"' in html
    assert 'Saltar al contenido' in html
    assert 'for="email"' in html
    assert 'for="password"' in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'id="contenido"' in html
    assert "tabindex=\"-1\"" in html
    assert "Privacidad" in html


def test_css_objetivos_tactiles_y_foco():
    css = create_app().test_client().get("/static/css/app.css").get_data(as_text=True)
    assert "min-height: 2.75rem" in css or "min-height:2.75rem" in css
    assert "min-width: 1.5rem" in css or "min-width:1.5rem" in css
    assert ":focus-visible" in css
    assert "scroll-margin-top" in css
    assert "prefers-reduced-motion" in css
    # Sistema de diseño: azul de marca, tipografía y superficies translúcidas.
    assert "--pri:#2563eb" in css
    assert "backdrop-filter:blur(" in css
    assert "Inter" in css
    # Los modos DUA siguen definidos: TDAH sin animaciones, baja visión y alto contraste.
    assert "body.dua-tdah *" in css and "animation:none!important" in css
    assert "body.dua-baja_vision" in css and ".tema-contraste" in css
    assert "OpenDyslexic" in css
    assert "dua-preview" in css
    assert "img-edu" in css
    assert "med-pauta" in css
    assert "med-glosario" in css
    assert "med-lista" in css
    assert "border-radius:16px" in css or "border-radius: 16px" in css


def test_offline_y_privacidad_saltar():
    c = create_app().test_client()
    off = c.get("/offline").get_data(as_text=True)
    assert 'href="#contenido"' in off
    assert 'lang="es"' in off
    priv = c.get("/privacidad").get_data(as_text=True)
    assert 'href="#contenido"' in priv


def test_health_ia(monkeypatch):
    """El uso de IA solo lo ve un docente (antes era público)."""
    assert create_app().test_client().get("/health/ia").status_code == 401
    _como_docente(monkeypatch)
    resp = create_app().test_client().get("/health/ia")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "llamadas" in data and "errores" in data


def _como_docente(monkeypatch):
    from flask import g

    def fake():
        g.usuario = {"id": "d1", "rol": "docente", "nombre": "Doc", "email": "d@x.com", "token": "t"}
        return g.usuario

    monkeypatch.setattr("services.auth.usuario_actual", fake)


def test_formulas_con_katex_servido_por_la_app():
    c = create_app().test_client()
    for ruta in ("vendor/katex/katex.min.js", "vendor/katex/katex.min.css", "vendor/katex/fonts/KaTeX_Main-Regular.woff2", "js/mates.js"):
        assert c.get("/static/" + ruta).status_code == 200, ruta
