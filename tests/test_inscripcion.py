import re

from fake_supabase import FakeDb, usar

from app import create_app
from services import cursos as svc
from services import materiales

CID = "11111111-1111-1111-1111-111111111111"
DOCENTE = {"id": "22222222-2222-2222-2222-222222222222", "rol": "docente", "nombre": "Doc", "email": "d@x.com", "token": "t"}


def _con_g(u):
    from flask import g

    g.usuario = u
    return u


def test_inscribe_estudiante_nuevo_con_clave_temporal_y_perfil(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    fila = svc.inscribir(CID, "  Ana@Colegio.PE ", "Ana", ["dislexia"], "es")

    assert re.fullmatch(r"Prisma-\d{6}", fila["clave_temporal"])
    assert fila["email"] == "ana@colegio.pe"
    user = db.auth.admin.usuarios[0]
    assert db.auth.admin.claves[user.id] == fila["clave_temporal"]
    # El perfil se crea desde el backend aunque no exista el trigger.
    perfil = db.tablas["perfiles"][0]
    assert perfil["id"] == user.id
    assert perfil["rol"] == "estudiante"
    assert perfil["email"] == "ana@colegio.pe"
    assert perfil["debe_cambiar_clave"] is True
    assert db.tablas["inscripciones_curso"][0]["estudiante_id"] == user.id


def test_encuentra_cuenta_existente_mas_alla_de_la_primera_pagina(monkeypatch):
    """Antes list_users() solo veía 50 usuarios y create_user fallaba con 'already registered'."""
    db = usar(monkeypatch, FakeDb(faltantes={"perfiles": {"email", "debe_cambiar_clave"}}))
    for i in range(1200):
        db.auth.admin.agregar(f"otro{i}@x.com")
    viejo = db.auth.admin.agregar("luis@x.com")
    db.tablas["perfiles"] = [{"id": viejo.id, "nombre": "Luis", "rol": "estudiante"}]

    fila = svc.inscribir(CID, "luis@x.com")

    assert fila["clave_temporal"] is None
    assert fila["estudiante_id"] == viejo.id
    assert len(db.auth.admin.usuarios) == 1201


def test_usa_perfiles_email_sin_recorrer_auth(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["perfiles"] = [{"id": "u1", "nombre": "Eva", "rol": "estudiante", "email": "eva@x.com"}]
    llamado = []
    monkeypatch.setattr(db.auth.admin, "list_users", lambda **k: llamado.append(k) or [])

    fila = svc.inscribir(CID, "eva@x.com")

    assert fila["estudiante_id"] == "u1"
    assert llamado == []


def test_rechaza_correo_de_docente(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.tablas["perfiles"] = [{"id": "u1", "nombre": "Profe", "rol": "docente", "email": "profe@x.com"}]
    try:
        svc.inscribir(CID, "profe@x.com")
        assert False
    except ValueError as exc:
        assert "docente" in str(exc)
    assert not db.tablas.get("inscripciones_curso")


def test_reinscribir_no_duplica(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    primera = svc.inscribir(CID, "ana@x.com")
    segunda = svc.inscribir(CID, "ana@x.com")
    assert segunda.get("ya_inscrito") is True
    assert segunda["clave_temporal"] is None
    assert segunda["id"] == primera["id"]
    assert len(db.tablas["inscripciones_curso"]) == 1


def test_error_del_trigger_da_mensaje_claro(monkeypatch):
    db = usar(monkeypatch, FakeDb())
    db.auth.admin.error_crear = Exception("Database error creating new user")
    try:
        svc.inscribir(CID, "ana@x.com")
        assert False
    except ValueError as exc:
        assert "002_rls_fix.sql" in str(exc)


def test_funciona_sin_migracion_004(monkeypatch):
    db = usar(monkeypatch, FakeDb(faltantes={"perfiles": {"email", "debe_cambiar_clave"}}))
    fila = svc.inscribir(CID, "ana@x.com", "Ana")
    assert fila["clave_temporal"]
    assert db.tablas["perfiles"][0] == {"id": db.auth.admin.usuarios[0].id, "nombre": "Ana", "rol": "estudiante"}


def test_correo_invalido():
    for malo in ("", "ana", "ana@", "ana@local"):
        try:
            svc.inscribir(CID, malo)
            assert False, malo
        except ValueError:
            pass


def _pagina_curso_falsa(monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr(materiales, "docente_es_dueno", lambda cid, did: True)
    monkeypatch.setattr(svc, "obtener_curso", lambda cid, did: {"id": CID, "nombre_curso": "Biología", "nivel_educativo": "cine_2"})
    monkeypatch.setattr(svc, "sesiones_de_curso", lambda cid: [])
    monkeypatch.setattr(svc, "inscripciones", lambda cid: [])


def test_ruta_muestra_la_clave_una_vez_y_no_la_guarda_en_cookie(monkeypatch):
    _pagina_curso_falsa(monkeypatch)
    monkeypatch.setattr(
        svc, "inscribir", lambda *a, **k: {"id": "i1", "email": "ana@x.com", "clave_temporal": "Prisma-123456"}
    )
    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/alumnos", data={"email": "ana@x.com"})
    assert resp.status_code == 200
    assert b"Prisma-123456" in resp.data
    assert b"ana@x.com" in resp.data
    assert b"Prisma-123456" not in (resp.headers.get("Set-Cookie") or "").encode()


def test_ruta_inscribir_error_inesperado_no_da_500(monkeypatch):
    _pagina_curso_falsa(monkeypatch)

    def falla(*a, **k):
        raise RuntimeError("timeout de Supabase")

    monkeypatch.setattr(svc, "inscribir", falla)
    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/alumnos", data={"email": "ana@x.com"})
    assert resp.status_code == 302


def test_restablecer_clave_de_alumno_del_curso(monkeypatch):
    _pagina_curso_falsa(monkeypatch)
    db = usar(monkeypatch, FakeDb())
    u = db.auth.admin.agregar("ana@x.com")
    db.tablas["perfiles"] = [{"id": u.id, "nombre": "Ana", "rol": "estudiante", "email": "ana@x.com", "debe_cambiar_clave": False}]
    db.tablas["inscripciones_curso"] = [{"id": "33333333-3333-3333-3333-333333333333", "curso_id": CID, "estudiante_id": u.id}]

    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/inscripciones/33333333-3333-3333-3333-333333333333/clave")

    assert resp.status_code == 200
    nueva = db.auth.admin.claves[u.id]
    assert nueva.encode() in resp.data
    assert db.tablas["perfiles"][0]["debe_cambiar_clave"] is True


def test_restablecer_clave_de_otro_curso_da_404(monkeypatch):
    _pagina_curso_falsa(monkeypatch)
    db = usar(monkeypatch, FakeDb())
    db.tablas["inscripciones_curso"] = [{"id": "33333333-3333-3333-3333-333333333333", "curso_id": "otro", "estudiante_id": "u1"}]
    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/inscripciones/33333333-3333-3333-3333-333333333333/clave")
    assert resp.status_code == 404
    assert db.auth.admin.claves == {}


def test_desinscribir_solo_borra_la_inscripcion(monkeypatch):
    _pagina_curso_falsa(monkeypatch)
    db = usar(monkeypatch, FakeDb())
    db.tablas["perfiles"] = [{"id": "u1", "rol": "estudiante"}]
    db.tablas["inscripciones_curso"] = [
        {"id": "33333333-3333-3333-3333-333333333333", "curso_id": CID, "estudiante_id": "u1"},
        {"id": "44444444-4444-4444-4444-444444444444", "curso_id": "otro", "estudiante_id": "u1"},
    ]
    c = create_app().test_client()
    resp = c.post(f"/docente/cursos/{CID}/inscripciones/33333333-3333-3333-3333-333333333333/eliminar")
    assert resp.status_code == 302
    assert [f["curso_id"] for f in db.tablas["inscripciones_curso"]] == ["otro"]
    assert db.tablas["perfiles"]
