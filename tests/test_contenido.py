"""El contenido de la clase (texto, pautas, glosario, títulos, tutor) sigue al idioma elegido."""
import json
from types import SimpleNamespace

from fake_supabase import FakeDb

from app import create_app
from services import ai_router, chat_service, contenido, dua, mediacion
from services import estudiante as est

SID = "33333333-3333-3333-3333-333333333333"
EST = {"id": "u1", "rol": "estudiante", "nombre": "Ana", "email": "a@x.com", "token": "t"}


def _con_g(u):
    from flask import g

    g.usuario = dict(u)
    return g.usuario


def _en_request(idioma_ui="es", sesion=None):
    app = create_app()
    ctx = app.test_request_context("/")
    ctx.push()
    from flask import g, session

    g.idioma = idioma_ui
    session.update(sesion or {})
    return ctx


def test_prioridad_del_idioma_del_contenido():
    insc = {"idioma_preferido": "quechua"}
    ctx = _en_request("es")
    assert contenido.idioma_para_estudiante(SID, insc) == "quechua"  # lo que asignó el docente
    ctx.pop()
    ctx = _en_request("en")
    assert contenido.idioma_para_estudiante(SID, insc) == "Inglés"  # quien eligió inglés solo entiende inglés
    ctx.pop()
    ctx = _en_request("en", {f"idioma_{SID}": "Aymara"})
    assert contenido.idioma_para_estudiante(SID, insc) == "Aymara"  # eligió a mano en el panel DUA
    ctx.pop()


def test_mismo_idioma():
    assert contenido.mismo_idioma("Español", "es")
    assert contenido.mismo_idioma("Inglés", "en")
    assert contenido.mismo_idioma("English", "en")
    assert not contenido.mismo_idioma("Inglés", "es")
    assert not contenido.mismo_idioma("Español", "en")


def test_cortos_traduce_en_una_llamada_y_usa_cache(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(contenido, "get_service_client", lambda: db)
    llamadas = []

    def groq(mensajes, **k):
        lista = json.loads(mensajes[1]["content"].split("<DATOS>\n")[1].split("\n</DATOS>")[0])
        llamadas.append(lista)
        return SimpleNamespace(texto=json.dumps({"t": [f"EN:{x}" for x in lista]}))

    monkeypatch.setattr(ai_router, "groq_texto", groq)
    assert contenido.cortos(["La célula", "Biología", "La célula"], "Inglés") == ["EN:La célula", "EN:Biología", "EN:La célula"]
    assert len(llamadas) == 1 and sorted(llamadas[0]) == ["Biología", "La célula"]
    # Segunda vez: todo sale de la caché, sin llamar a la IA.
    assert contenido.cortos(["Biología"], "Inglés") == ["EN:Biología"]
    assert len(llamadas) == 1


def test_cortos_si_la_ia_falla_devuelve_el_original(monkeypatch):
    monkeypatch.setattr(contenido, "get_service_client", lambda: FakeDb())
    monkeypatch.setattr(ai_router, "groq_texto", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin cuota")))
    assert contenido.cortos(["La célula"], "Francés") == ["La célula"]


def test_cortos_no_traduce_si_ya_esta_en_ese_idioma(monkeypatch):
    monkeypatch.setattr(ai_router, "groq_texto", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")))
    assert contenido.cortos(["Cells"], "Inglés", "en") == ["Cells"]


def test_mediacion_se_genera_en_el_idioma_pedido(monkeypatch):
    vistos = {}
    monkeypatch.setattr(mediacion.imagen_educativa, "nivel_de_sesion", lambda s: "CINE 2")
    monkeypatch.setattr(mediacion.cache_ia, "buscar", lambda h, f, idioma, v: vistos.setdefault("buscar", idioma) and None)
    monkeypatch.setattr(mediacion.cache_ia, "guardar", lambda h, f, idioma, v, c: vistos.setdefault("guardar", idioma))

    def groq(mensajes, **k):
        vistos["prompt"] = mensajes[1]["content"]
        return SimpleNamespace(texto=json.dumps({
            "pauta_docente": "Use a concept map to guide the class about cells.",
            "pauta_estudiante": "You can draw the parts of the cell to remember them.",
            "glosario": [{"termino": "Cell", "definicion": "Basic unit of life."}],
        }))

    monkeypatch.setattr(mediacion.ai_router, "groq_texto", groq)
    out = mediacion.para_sesion({"id": SID, "titulo": "La célula", "texto_extraido": "La célula es...", "contenido_hash": "h"}, "Inglés")
    assert out["pauta_estudiante"].startswith("You can")
    assert "«Inglés»" in vistos["prompt"]
    assert vistos["buscar"] == "en" and vistos["guardar"] == "en"


def test_mediacion_respaldo_local_traducido_y_sin_cache(monkeypatch):
    guardados = []
    monkeypatch.setattr(mediacion.imagen_educativa, "nivel_de_sesion", lambda s: "")
    monkeypatch.setattr(mediacion.cache_ia, "buscar", lambda *a: None)
    monkeypatch.setattr(mediacion.cache_ia, "guardar", lambda *a: guardados.append(a))
    monkeypatch.setattr(mediacion.ai_router, "groq_texto", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin cuota")))
    out = mediacion.para_sesion({"titulo": "Cells", "texto_extraido": "x", "contenido_hash": "h"}, "Francés")
    assert out["origen"] == "local"
    assert out["pauta_estudiante"].startswith("Lisez « Cells »")
    assert guardados == []


def test_tutor_responde_siempre_en_el_idioma_de_la_persona():
    estilo = chat_service._estilo([], "Portugués")
    assert "SIEMPRE" in estilo and "«Portugués»" in estilo
    assert chat_service.VERSION_CHAT != "chat-v1"  # respuestas viejas en caché no se reutilizan


def test_traducir_material_en_ingles_al_espanol(monkeypatch):
    """Antes se saltaba cualquier traducción con destino español, aunque el material fuera inglés."""
    monkeypatch.setattr(dua.cache_ia, "buscar", lambda *a: None)
    monkeypatch.setattr(dua.cache_ia, "guardar", lambda *a: None)
    monkeypatch.setattr(dua.ai_router, "groq_texto", lambda *a, **k: SimpleNamespace(texto='{"texto": "La célula es la unidad."}'))
    assert dua.traducir("The cell is the unit.", "Español", "en") == "La célula es la unidad."
    assert dua.traducir("La célula.", "Español", "es") == "La célula."


def test_nombres_de_idioma_de_la_interfaz_son_reconocidos():
    for nombre in ("English", "Inglês", "Anglais", "Português", "Français", "Espanhol", "Espagnol"):
        assert dua.validar_idioma(nombre)["valido"], nombre


def _sesion_estudiante(monkeypatch, idioma_original="es"):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(EST))
    sesion = {"id": SID, "curso_id": "c1", "titulo": "La célula", "texto_extraido": "La célula es...", "estado": "publicado",
              "idioma_original": idioma_original}
    monkeypatch.setattr(est, "sesion_visible", lambda sid, uid: (sesion, {"preferencias": [], "idioma_preferido": "es"}))
    monkeypatch.setattr("services.cursos.paquetes_de_sesion", lambda sid: [])
    monkeypatch.setattr(chat_service, "conversacion", lambda sid, uid: {"id": "conv"})
    monkeypatch.setattr(chat_service, "mensajes", lambda cid: [])
    monkeypatch.setattr(chat_service, "cuota_hoy", lambda uid: 0)
    monkeypatch.setattr(contenido, "corto", lambda texto, idioma, original="es": f"[{idioma}] {texto}")


def test_pagina_de_sesion_en_ingles_traduce_titulo_y_texto(monkeypatch):
    _sesion_estudiante(monkeypatch)
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "en"})
    html = c.get(f"/estudiante/sesiones/{SID}").get_data(as_text=True)
    assert "<h1>[Inglés] La célula</h1>" in html
    assert "traducirAlCargar: true" in html
    assert 'idiomaInicial: "Ingl\\u00e9s"' in html or 'idiomaInicial: "Inglés"' in html
    assert 'window.PRISMA_VOZ_CONTENIDO = "en-US"' in html
    assert 'value="English"' in html  # el campo de lengua muestra el nombre en su idioma


def test_pagina_de_sesion_en_espanol_no_traduce(monkeypatch):
    _sesion_estudiante(monkeypatch)
    html = create_app().test_client().get(f"/estudiante/sesiones/{SID}").get_data(as_text=True)
    assert "<h1>La célula</h1>" in html
    assert "traducirAlCargar: false" in html


def test_material_en_ingles_con_interfaz_en_ingles_no_traduce(monkeypatch):
    _sesion_estudiante(monkeypatch, idioma_original="en")
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "en"})
    html = c.get(f"/estudiante/sesiones/{SID}").get_data(as_text=True)
    assert "traducirAlCargar: false" in html


def test_mediacion_e_imagen_del_estudiante_en_su_idioma(monkeypatch):
    _sesion_estudiante(monkeypatch)
    pedidos = []
    monkeypatch.setattr(mediacion, "para_sesion", lambda s, idioma="Español": pedidos.append(idioma) or {"estado": "lista"})
    monkeypatch.setattr("services.imagen_educativa.para_sesion", lambda s: {"estado": "lista", "url": "data:image/x", "alt": "x"})
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "pt"})
    c.get(f"/estudiante/sesiones/{SID}/mediacion")
    assert pedidos == ["Portugués"]
    alt = c.get(f"/estudiante/sesiones/{SID}/imagen").get_json()["alt"]
    assert alt == "Imagem educativa do tema: [Portugués] La célula"


def test_cambiar_idioma_borra_la_lengua_elegida_por_sesion():
    c = create_app().test_client()
    with c.session_transaction() as s:
        s[f"idioma_{SID}"] = "Español"
        s[f"fmt_{SID}"] = ["tdah"]
    c.post("/idioma", data={"idioma": "fr"})
    with c.session_transaction() as s:
        assert f"idioma_{SID}" not in s
        assert s[f"fmt_{SID}"] == ["tdah"]  # los demás ajustes DUA se conservan
        assert s["idioma_ui"] == "fr"


def test_mochila_traduce_cursos_y_sesiones(monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(EST))
    monkeypatch.setattr(est, "mochila", lambda uid: [
        {"id": "c1", "nombre_curso": "Biología", "descripcion": "Seres vivos", "sesiones": [{"id": SID, "titulo": "La célula"}]}
    ])
    pedidos = []
    monkeypatch.setattr(contenido, "cortos", lambda textos, idioma, original="es": pedidos.append(list(textos)) or [f"EN:{t}" for t in textos])
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "en"})
    html = c.get("/estudiante/cursos").get_data(as_text=True)
    assert "EN:Biología" in html and "EN:Seres vivos" in html and "EN:La célula" in html
    assert pedidos == [["Biología", "Seres vivos", "La célula"]]  # una sola llamada para toda la mochila


def test_traducir_pide_texto_plano_y_limpia_envoltorios(monkeypatch):
    """Con JSON, Groq rechazaba traducciones largas (json_validate_failed) y la clase quedaba en español."""
    pedidos = []
    monkeypatch.setattr(dua.cache_ia, "buscar", lambda *a: None)
    monkeypatch.setattr(dua.cache_ia, "guardar", lambda *a: None)

    def groq(mensajes, **k):
        pedidos.append(k)
        return SimpleNamespace(texto="```markdown\n## Résumé\nLa cellule est l'unité du vivant.\n```")

    monkeypatch.setattr(dua.ai_router, "groq_texto", groq)
    assert dua.traducir("## Resumen\nLa célula es la unidad.", "Francés") == "## Résumé\nLa cellule est l'unité du vivant."
    assert pedidos[0]["json_mode"] is False


def test_tutor_lee_el_material_traducido(monkeypatch):
    _sesion_estudiante(monkeypatch)
    monkeypatch.setattr("services.rate_limit.comprobar", lambda *a, **k: None)
    monkeypatch.setattr(dua, "traducir", lambda texto, idioma, origen="es": f"[{idioma}] {texto}")
    vistos = {}

    def responder(sesion, uid, pregunta, prefs, idioma):
        vistos.update(texto=sesion["texto_extraido"], idioma=idioma)
        yield "ok"

    monkeypatch.setattr(chat_service, "responder_stream", responder)
    c = create_app().test_client()
    c.post("/idioma", data={"idioma": "en"})
    c.post(f"/chat/{SID}", json={"pregunta": "What is a cell?"}).get_data()
    assert vistos == {"texto": "[Inglés] La célula es...", "idioma": "Inglés"}
