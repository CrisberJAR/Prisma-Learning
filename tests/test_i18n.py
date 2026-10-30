import json
import re

from app import create_app
from services import i18n

DOCENTE = {"id": "22222222-2222-2222-2222-222222222222", "rol": "docente", "nombre": "Doc", "email": "d@x.com", "token": "t"}
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _con_g(u):
    from flask import g

    g.usuario = dict(u)
    return g.usuario


def _como(monkeypatch, u):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(u))
    monkeypatch.setattr("routes.auth.usuario_actual", lambda: _con_g(u))


def test_catalogos_completos_y_sin_sobrantes():
    """Si falla: python scripts/i18n_extraer.py --actualizar y traduce las claves vacías."""
    claves = i18n.todas_las_claves()
    for codigo in ("en", "pt", "fr"):
        cat = i18n.catalogo(codigo)
        faltan = sorted(k for k in claves if not cat.get(k))
        sobran = sorted(set(cat) - claves)
        assert not faltan, f"{codigo} sin traducir: {faltan[:5]}"
        assert not sobran, f"{codigo} sobrantes: {sobran[:5]}"


def test_traducciones_conservan_los_marcadores():
    for codigo in ("en", "pt", "fr"):
        for es, otro in i18n.catalogo(codigo).items():
            assert set(PLACEHOLDER.findall(es)) == set(PLACEHOLDER.findall(otro)), (codigo, es)


def test_traducir_y_respaldo_en_espanol():
    assert i18n.traducir("Curso creado.", "en") == "Course created."
    assert i18n.traducir("Texto que no existe", "en") == "Texto que no existe"
    assert i18n.traducir("Sesión «{titulo}» eliminada.", "fr", titulo="Célula") == "Séance « Célula » supprimée."
    assert i18n.traducir("{n} sesiones", "es", n=3) == "3 sesiones"


def test_normalizar_idioma():
    assert i18n.normalizar("pt-BR") == "pt"
    assert i18n.normalizar("EN_us") == "en"
    assert i18n.normalizar("de") is None
    assert i18n.normalizar(None) is None


def test_por_defecto_espanol():
    html = create_app().test_client().get("/entrar").get_data(as_text=True)
    assert '<html lang="es">' in html
    assert "Entrar a Prisma" in html
    assert 'name="idioma"' in html


def test_detecta_idioma_del_navegador():
    c = create_app().test_client()
    html = c.get("/entrar", headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"}).get_data(as_text=True)
    assert '<html lang="pt">' in html
    assert "Entrar no Prisma" in html


def test_selector_cambia_idioma_y_vuelve_a_la_pagina():
    c = create_app().test_client()
    resp = c.post("/idioma", data={"idioma": "en", "volver": "/privacidad"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/privacidad")
    html = c.get("/privacidad").get_data(as_text=True)
    assert "Privacy and personal data" in html
    assert "legally binding" in html  # aviso de traducción informativa


def test_selector_no_permite_redireccion_abierta():
    c = create_app().test_client()
    for malo in ("https://malo.example/", "//malo.example", "/\\malo.example", "javascript:alert(1)"):
        resp = c.post("/idioma", data={"idioma": "fr", "volver": malo})
        assert "malo.example" not in resp.headers["Location"]
        assert "javascript" not in resp.headers["Location"]


def test_idioma_invalido_se_ignora():
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "xx"})
    with c.session_transaction() as s:
        assert "idioma_ui" not in s


def test_preferencia_del_perfil_y_prioridad_de_la_sesion(monkeypatch):
    monkeypatch.setattr("services.cursos.listar_cursos", lambda did: [])
    _como(monkeypatch, {**DOCENTE, "idioma_ui": "pt"})
    c = create_app().test_client()
    assert "Seus cursos" in c.get("/docente/cursos").get_data(as_text=True)
    guardados = []
    monkeypatch.setattr(i18n, "guardar_preferencia", lambda uid, cod: guardados.append((uid, cod)))
    c.post("/idioma", data={"idioma": "fr", "volver": "/docente/cursos"})
    assert guardados == [(DOCENTE["id"], "fr")]
    assert "Vos cours" in c.get("/docente/cursos").get_data(as_text=True)


def test_mensajes_flash_y_errores_traducidos():
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "en"})
    html = c.post("/entrar", data={"email": "", "password": ""}).get_data(as_text=True)
    assert "Enter your email and password." in html


def test_cerrar_sesion_conserva_el_idioma():
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "fr"})
    with c.session_transaction() as s:
        s["access_token"] = "x"
    c.post("/salir")
    with c.session_transaction() as s:
        assert s.get("idioma_ui") == "fr"
        assert "access_token" not in s


def test_login_guarda_el_idioma_elegido_en_el_perfil(monkeypatch):
    from services import cuentas

    monkeypatch.setattr(cuentas, "iniciar_sesion", lambda e, p: {"access_token": "a", "refresh_token": "r"})
    guardados = []
    monkeypatch.setattr(i18n, "guardar_preferencia", lambda uid, cod: guardados.append(cod))
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "pt"})  # aún sin sesión: no hay perfil donde guardarlo
    assert guardados == []
    monkeypatch.setattr("routes.auth.usuario_actual", lambda: _con_g({**DOCENTE, "idioma_ui": None}))
    c.post("/entrar", data={"email": "d@x.com", "password": "x"})
    assert guardados == ["pt"]
    with c.session_transaction() as s:
        assert s["idioma_ui"] == "pt" and s["access_token"] == "a"


def test_catalogo_js_en_la_pagina_solo_con_textos_de_scripts(monkeypatch):
    monkeypatch.setattr("services.cursos.listar_cursos", lambda did: [])
    _como(monkeypatch, {**DOCENTE, "idioma_ui": "en"})
    html = create_app().test_client().get("/docente/cursos").get_data(as_text=True)
    m = re.search(r"window\.PRISMA_I18N = (\{.*?\});", html)
    cat = json.loads(m.group(1))
    assert cat["Pausar"] == "Pause"
    assert cat["{n} resultados de {total}"] == "{n} results of {total}"
    assert "Tus cursos" not in cat  # texto de plantilla: no viaja al navegador


def test_estados_de_la_base_se_traducen():
    app = create_app()
    with app.test_request_context("/"):
        from flask import g

        g.idioma = "en"
        assert i18n.etiqueta("publicado") == "Published"
        assert i18n.etiqueta("failed") == "Failed"
        assert i18n.etiqueta("desconocido") == "desconocido"
        assert i18n.etiqueta(None) == ""


def test_etiquetas_dinamicas_cine_y_dua_traducidas(monkeypatch):
    monkeypatch.setattr("services.cursos.listar_cursos", lambda did: [])
    _como(monkeypatch, {**DOCENTE, "idioma_ui": "en"})
    html = create_app().test_client().get("/docente/cursos").get_data(as_text=True)
    assert "ISCED 2 - Lower secondary (ages 12 to 14)" in html
    assert "CINE 2" not in html
