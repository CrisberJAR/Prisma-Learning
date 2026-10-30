from fake_supabase import FakeDb, usar

from app import create_app
from services import cursos as svc
from services import imagen_educativa, materiales, mediacion, package_builder

CID = "11111111-1111-1111-1111-111111111111"
SID = "55555555-5555-5555-5555-555555555555"
DOCENTE = {"id": "22222222-2222-2222-2222-222222222222", "rol": "docente", "nombre": "Doc", "email": "d@x.com", "token": "t"}


def _con_g(u):
    from flask import g

    g.usuario = u
    return u


def _base_curso():
    return {"id": CID, "docente_id": DOCENTE["id"], "nombre_curso": "Biología", "nivel_educativo": "cine_2"}


def test_listar_cursos_cuenta_en_dos_consultas(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["cursos"] = [_base_curso(), {**_base_curso(), "id": "c2", "nombre_curso": "Física"}]
    db.tablas["sesiones_material"] = [{"id": "s1", "curso_id": CID}, {"id": "s2", "curso_id": CID}]
    db.tablas["inscripciones_curso"] = [{"id": "i1", "curso_id": "c2"}]
    cursos = {c["id"]: c for c in svc.listar_cursos(DOCENTE["id"])}
    assert (cursos[CID]["n_sesiones"], cursos[CID]["n_estudiantes"]) == (2, 0)
    assert (cursos["c2"]["n_sesiones"], cursos["c2"]["n_estudiantes"]) == (0, 1)
    assert len(db.consultas) == 3


def test_editar_curso_valida_y_guarda(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["cursos"] = [_base_curso()]
    for nombre, nivel in (("", "cine_2"), ("Bio", "inventado")):
        try:
            svc.editar_curso(CID, DOCENTE["id"], nombre, "", nivel)
            assert False
        except ValueError:
            pass
    out = svc.editar_curso(CID, DOCENTE["id"], " Biología II ", " Nueva ", "cine_3")
    assert out["nombre_curso"] == "Biología II"
    assert out["descripcion"] == "Nueva"
    assert out["nivel_educativo_etiqueta"].startswith("CINE 3")


def test_editar_curso_de_otro_docente_falla(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["cursos"] = [_base_curso()]
    try:
        svc.editar_curso(CID, "otro-docente", "Hack", "", "cine_2")
        assert False
    except ValueError:
        pass
    assert db.tablas["cursos"][0]["nombre_curso"] == "Biología"


def test_eliminar_curso_exige_nombre_y_limpia_todo(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["cursos"] = [_base_curso()]
    db.tablas["sesiones_material"] = [
        {"id": "s1", "curso_id": CID, "archivo_url": f"{CID}/abc.pdf"},
        {"id": "s2", "curso_id": CID, "archivo_url": None},
    ]
    db.tablas["interacciones_progreso"] = [{"id": "p1", "sesion_id": "s1"}, {"id": "p2", "sesion_id": "otra"}]
    try:
        svc.eliminar_curso(CID, DOCENTE["id"], "biologia")
        assert False
    except ValueError as exc:
        assert "nombre exacto" in str(exc)
    assert db.tablas["cursos"]

    svc.eliminar_curso(CID, DOCENTE["id"], "Biología")

    assert db.tablas["cursos"] == []
    assert [p["id"] for p in db.tablas["interacciones_progreso"]] == ["p2"]
    assert db.borrados == [f"{CID}/abc.pdf"]


def _sesion(**extra):
    return {"id": SID, "curso_id": CID, "titulo": "Célula", "texto_extraido": "La célula es...", "estado": "revision",
            "contenido_hash": "h0", "idioma_original": "es", "archivo_url": f"{CID}/h0.pdf", **extra}


def _sin_ia(monkeypatch):
    llamadas = []
    monkeypatch.setattr(imagen_educativa, "generar_en_fondo", lambda s: llamadas.append(("img", s["contenido_hash"])))
    monkeypatch.setattr(mediacion, "generar_en_fondo", lambda s: llamadas.append(("med", s["contenido_hash"])))
    monkeypatch.setattr(package_builder, "guardar_paquete", lambda sid, f, c: llamadas.append(("paq", f)))
    monkeypatch.setattr(package_builder, "generar", lambda *a: {})
    return llamadas


def test_editar_sesion_solo_titulo_conserva_formatos(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    llamadas = _sin_ia(monkeypatch)
    db.tablas["sesiones_material"] = [_sesion()]
    db.tablas["paquetes_formato"] = [{"id": "p", "sesion_id": SID}]
    out = svc.editar_sesion(_sesion(), "La célula animal", "La célula es...")
    assert out["titulo"] == "La célula animal"
    assert out["texto_cambio"] is False
    assert db.tablas["paquetes_formato"]
    assert llamadas == []


def test_editar_sesion_con_texto_nuevo_regenera(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    llamadas = _sin_ia(monkeypatch)
    db.tablas["sesiones_material"] = [_sesion()]
    db.tablas["paquetes_formato"] = [{"id": "p", "sesion_id": SID}, {"id": "q", "sesion_id": "otra"}]
    out = svc.editar_sesion(_sesion(), "Célula", "Texto corregido por el docente")
    assert out["texto_cambio"] is True
    assert out["contenido_hash"] != "h0"
    assert [p["id"] for p in db.tablas["paquetes_formato"]] == ["q"]
    assert ("paq", "alto_contraste") in llamadas
    assert ("img", out["contenido_hash"]) in llamadas and ("med", out["contenido_hash"]) in llamadas


def test_editar_sesion_procesando_no_permite_texto(monkeypatch):
    usar(monkeypatch, FakeDb())
    try:
        svc.editar_sesion(_sesion(estado="procesando", texto_extraido=""), "Célula", "texto")
        assert False
    except ValueError as exc:
        assert "extracción" in str(exc)


def test_eliminar_sesion_respeta_archivo_compartido(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["sesiones_material"] = [_sesion(), {"id": "s2", "curso_id": CID, "archivo_url": f"{CID}/h0.pdf"}]
    db.tablas["interacciones_progreso"] = [{"id": "p1", "sesion_id": SID}]
    svc.eliminar_sesion(_sesion())
    assert [s["id"] for s in db.tablas["sesiones_material"]] == ["s2"]
    assert db.tablas["interacciones_progreso"] == []
    assert db.borrados == []

    svc.eliminar_sesion(db.tablas["sesiones_material"][0])
    assert db.borrados == [f"{CID}/h0.pdf"]


def test_filtrar_ignora_tildes_y_mayusculas():
    items = [{"n": "Biología celular"}, {"n": "Física"}, {"n": None}]
    assert svc.filtrar(items, "BIOLOGIA", "n") == [items[0]]
    assert svc.filtrar(items, "  ", "n") == items
    assert svc.filtrar(items, "quimica", "n") == []


def _docente(monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))


def test_ruta_eliminar_sesion_pide_confirmacion(monkeypatch):
    _docente(monkeypatch)
    borradas = []
    monkeypatch.setattr(materiales, "docente_es_dueno_de_sesion", lambda sid, did: _sesion())
    monkeypatch.setattr(svc, "eliminar_sesion", lambda s: borradas.append(s["id"]))
    c = create_app().test_client()
    resp = c.post(f"/docente/sesiones/{SID}/eliminar")
    assert resp.status_code == 302 and f"/docente/sesiones/{SID}" in resp.headers["Location"]
    assert borradas == []
    resp = c.post(f"/docente/sesiones/{SID}/eliminar", data={"confirmar": "si"})
    assert resp.status_code == 302 and f"/docente/cursos/{CID}" in resp.headers["Location"]
    assert borradas == [SID]


def test_ruta_eliminar_sesion_ajena_da_404(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(materiales, "docente_es_dueno_de_sesion", lambda sid, did: None)
    monkeypatch.setattr(svc, "eliminar_sesion", lambda s: (_ for _ in ()).throw(AssertionError("no")))
    c = create_app().test_client()
    assert c.post(f"/docente/sesiones/{SID}/eliminar", data={"confirmar": "si"}).status_code == 404
    assert c.post(f"/docente/sesiones/{SID}/editar", data={"titulo": "x"}).status_code == 404


def test_ruta_eliminar_curso(monkeypatch):
    _docente(monkeypatch)
    vistos = []
    monkeypatch.setattr(svc, "eliminar_curso", lambda cid, did, conf: vistos.append((cid, did, conf)))
    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/eliminar", data={"confirmacion": "Biología"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/docente/cursos")
    assert vistos == [(CID, DOCENTE["id"], "Biología")]


def test_buscador_de_cursos_filtra_en_servidor(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(
        svc,
        "listar_cursos",
        lambda did: [{"id": "c1", "nombre_curso": "Biología", "descripcion": ""}, {"id": "c2", "nombre_curso": "Física", "descripcion": ""}],
    )
    c = create_app().test_client()
    html = c.get("/docente/cursos?q=biologia").get_data(as_text=True)
    assert "Biología" in html and "Física" not in html
    assert 'data-filtro="#lista-cursos"' in html
    assert "js/filtro.js" in html


def test_pagina_curso_muestra_gestion_y_buscadores(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(materiales, "docente_es_dueno", lambda cid, did: True)
    monkeypatch.setattr(svc, "obtener_curso", lambda cid, did: {**_base_curso(), "n_sesiones": 1, "n_estudiantes": 1})
    monkeypatch.setattr(svc, "sesiones_de_curso", lambda cid: [{"id": SID, "titulo": "Célula", "estado": "revision"}])
    monkeypatch.setattr(svc, "jobs_de_sesion", lambda sid: [])
    monkeypatch.setattr(
        svc, "inscripciones", lambda cid: [{"id": "i1", "nombre": "Ana", "email": "ana@x.com", "preferencias": [], "debe_cambiar_clave": True}]
    )
    c = create_app().test_client()
    html = c.get(f"/docente/cursos/{CID}").get_data(as_text=True)
    for texto in ("Editar curso", "Eliminar curso", 'id="buscar-sesiones"', 'id="buscar-estudiantes"',
                  "Restablecer contraseña", "Quitar del curso", "ana@x.com", "contraseña temporal"):
        assert texto in html, texto


def test_lista_de_cursos_compacta_y_con_singular(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(svc, "listar_cursos", lambda did: [{"id": CID, "nombre_curso": "Biología", "n_sesiones": 1, "n_estudiantes": 2}])
    html = create_app().test_client().get("/docente/cursos").get_data(as_text=True)
    assert "1 sesión · 2 estudiantes" in html and "1 sesiones" not in html
    assert '<details class="gestion accion" >' in html  # con cursos, el formulario de crear empieza plegado


def test_acciones_de_estudiantes_vuelven_a_su_pestana(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(materiales, "docente_es_dueno", lambda cid, did: True)
    monkeypatch.setattr(svc, "actualizar_preferencias", lambda *a: None)
    resp = create_app().test_client().post(f"/docente/cursos/{CID}/inscripciones/{SID}", data={"idioma": "es"})
    assert "pestana=estudiantes" in resp.headers["Location"]


def test_pestanas_inactivas_llegan_ocultas_sin_parpadeo(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(materiales, "docente_es_dueno", lambda cid, did: True)
    monkeypatch.setattr(svc, "obtener_curso", lambda cid, did: _base_curso())
    monkeypatch.setattr(svc, "sesiones_de_curso", lambda cid: [])
    monkeypatch.setattr(svc, "inscripciones", lambda cid: [])
    c = create_app().test_client()
    html = c.get(f"/docente/cursos/{CID}").get_data(as_text=True)
    assert '<section id="panel-sesiones"  role="tabpanel"' in html
    assert '<section id="panel-estudiantes" hidden role="tabpanel"' in html
    assert 'id="panel-ajustes" hidden role="tabpanel"' in html
    assert "<noscript>" in html  # sin JavaScript se ven todas
    html = c.get(f"/docente/cursos/{CID}?pestana=estudiantes").get_data(as_text=True)
    assert '<section id="panel-estudiantes"  role="tabpanel"' in html
    assert '<section id="panel-sesiones" hidden role="tabpanel"' in html


def test_csrf_bloquea_post_de_otro_sitio(monkeypatch):
    _docente(monkeypatch)
    monkeypatch.setattr(svc, "eliminar_curso", lambda *a: (_ for _ in ()).throw(AssertionError("no")))
    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/eliminar", data={"confirmacion": "Biología"}, headers={"Origin": "https://malo.example"})
    assert resp.status_code == 403
    resp = c.post("/salir", headers={"Origin": "http://localhost"})
    assert resp.status_code == 302


def test_cookie_de_sesion_samesite_lax():
    app = create_app()
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    resp = app.test_client().get("/ping")
    assert resp.headers["Referrer-Policy"] == "same-origin"
