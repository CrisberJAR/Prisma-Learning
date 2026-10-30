import re
from types import SimpleNamespace

from fake_supabase import FakeDb, usar

from app import create_app
from services import auth, cuentas, rate_limit

EST = {"id": "u1", "rol": "estudiante", "nombre": "Ana", "email": "ana@x.com", "token": "t", "debe_cambiar_clave": False}
TEMPORAL = {**EST, "debe_cambiar_clave": True}


def _con_g(u):
    from flask import g

    g.usuario = dict(u)
    return g.usuario


def _como(monkeypatch, u):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(u))
    monkeypatch.setattr("routes.auth.usuario_actual", lambda: _con_g(u))


def test_clave_temporal_es_legible_y_variada():
    claves = {cuentas.clave_temporal() for _ in range(50)}
    assert all(re.fullmatch(r"Prisma-\d{6}", c) for c in claves)
    assert len(claves) > 40


def test_cambiar_clave_valida_antes_de_tocar_supabase(monkeypatch):
    monkeypatch.setattr(cuentas, "iniciar_sesion", lambda *a: (_ for _ in ()).throw(AssertionError("no debe llamarse")))
    casos = [
        ("", "nuevaClave1", "nuevaClave1", "actual"),
        ("vieja", "corta", "corta", "8"),
        ("vieja", "nuevaClave1", "otraClave1", "confirmación"),
        ("nuevaClave1", "nuevaClave1", "nuevaClave1", "distinta"),
    ]
    for actual, nueva, conf, palabra in casos:
        try:
            cuentas.cambiar_clave(EST, actual, nueva, conf)
            assert False
        except cuentas.ClaveInvalida as exc:
            assert palabra in str(exc)


def test_cambiar_clave_rechaza_clave_actual_incorrecta(monkeypatch):
    def falla(email, password):
        raise Exception("Invalid login credentials")

    monkeypatch.setattr(cuentas, "iniciar_sesion", falla)
    try:
        cuentas.cambiar_clave(EST, "mala", "nuevaClave1", "nuevaClave1")
        assert False
    except cuentas.ClaveInvalida as exc:
        assert "actual no es correcta" in str(exc)


def test_cambiar_clave_ok_actualiza_y_quita_la_marca(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["perfiles"] = [{"id": "u1", "rol": "estudiante", "debe_cambiar_clave": True}]
    monkeypatch.setattr(cuentas, "iniciar_sesion", lambda e, p: {"access_token": "a", "refresh_token": "r"})
    cuentas.cambiar_clave(TEMPORAL, "Prisma-123456", "MiClaveNueva9", "MiClaveNueva9")
    assert db.auth.admin.claves["u1"] == "MiClaveNueva9"
    assert db.tablas["perfiles"][0]["debe_cambiar_clave"] is False


def test_restablecer_sin_migracion_no_cambia_la_clave(monkeypatch):
    """Si falta la columna, no se cambia una contraseña que el docente no llegaría a ver."""
    db = usar(monkeypatch, FakeDb(faltantes={"perfiles": {"debe_cambiar_clave"}}))
    try:
        cuentas.restablecer_clave("u1")
        assert False
    except ValueError as exc:
        assert "004_fase1.sql" in str(exc)
    assert db.auth.admin.claves == {}


def test_clave_temporal_obliga_a_cambiarla_en_paginas_y_api(monkeypatch):
    _como(monkeypatch, TEMPORAL)
    c = create_app().test_client()
    resp = c.get("/estudiante/cursos")
    assert resp.status_code == 302
    assert "/cuenta/clave" in resp.headers["Location"]
    sid = "33333333-3333-3333-3333-333333333333"
    resp = c.post(f"/chat/{sid}", json={"pregunta": "hola"})
    assert resp.status_code == 403
    assert "contraseña" in resp.get_json()["error"]


def test_pagina_cambiar_clave_para_estudiante(monkeypatch):
    _como(monkeypatch, EST)
    c = create_app().test_client()
    resp = c.get("/cuenta/clave")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Cambiar contraseña" in html
    assert 'autocomplete="new-password"' in html
    assert "mochila" in html  # usa la plantilla del estudiante


def test_post_cambiar_clave_redirige_a_su_panel(monkeypatch):
    rate_limit.reiniciar()
    _como(monkeypatch, TEMPORAL)
    vistos = []
    monkeypatch.setattr(cuentas, "cambiar_clave", lambda *a: vistos.append(a))
    c = create_app().test_client()
    resp = c.post("/cuenta/clave", data={"actual": "Prisma-123456", "nueva": "MiClave99x", "confirmar": "MiClave99x"})
    assert resp.status_code == 302
    assert "/estudiante/cursos" in resp.headers["Location"]
    assert vistos[0][1:] == ("Prisma-123456", "MiClave99x", "MiClave99x")


def test_post_cambiar_clave_error_muestra_mensaje(monkeypatch):
    rate_limit.reiniciar()
    _como(monkeypatch, EST)

    def falla(*a):
        raise cuentas.ClaveInvalida("La contraseña actual no es correcta.")

    monkeypatch.setattr(cuentas, "cambiar_clave", falla)
    c = create_app().test_client()
    resp = c.post("/cuenta/clave", data={"actual": "x", "nueva": "y", "confirmar": "y"})
    assert resp.status_code == 400
    assert "actual no es correcta" in resp.get_data(as_text=True)


def test_login_guarda_refresh_token_y_pide_cambio_si_es_temporal(monkeypatch):
    monkeypatch.setattr(cuentas, "iniciar_sesion", lambda e, p: {"access_token": "acc", "refresh_token": "ref"})
    monkeypatch.setattr("routes.auth.usuario_actual", lambda: _con_g(TEMPORAL))
    c = create_app().test_client()
    resp = c.post("/entrar", data={"email": "ana@x.com", "password": "Prisma-123456"})
    assert resp.status_code == 302
    assert "/cuenta/clave" in resp.headers["Location"]
    with c.session_transaction() as s:
        assert s["access_token"] == "acc"
        assert s["refresh_token"] == "ref"


def test_token_vencido_se_renueva_con_refresh(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["perfiles"] = [{"id": "u1", "nombre": "Ana", "rol": "estudiante"}]
    validos = {"nuevo": SimpleNamespace(id="u1", email="ana@x.com")}
    monkeypatch.setattr(auth, "_validar", lambda token: validos.get(token))
    monkeypatch.setattr(cuentas, "refrescar", lambda rt: {"access_token": "nuevo", "refresh_token": "ref2"} if rt == "ref" else None)
    app = create_app()
    with app.test_request_context("/"):
        from flask import session

        session["access_token"] = "vencido"
        session["refresh_token"] = "ref"
        u = auth.usuario_actual()
        assert u["id"] == "u1"
        assert u["debe_cambiar_clave"] is False
        assert session["access_token"] == "nuevo"
        assert session["refresh_token"] == "ref2"


def test_cliente_de_login_es_aislado():
    """El login no debe usar el cliente anon compartido (heredaría la sesión del usuario)."""
    import inspect

    from routes import auth as rutas

    assert "get_anon_client" not in inspect.getsource(rutas)
    assert "cliente_aislado" in inspect.getsource(cuentas.iniciar_sesion)
