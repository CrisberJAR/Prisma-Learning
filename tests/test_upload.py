import io

import pytest

from app import create_app
from services import materiales

CURSO = "11111111-1111-1111-1111-111111111111"
DOCENTE = {"id": "22222222-2222-2222-2222-222222222222", "rol": "docente", "nombre": "Doc", "email": "d@x.com"}


@pytest.fixture
def client():
    return create_app().test_client()


def _post(client, nombre="clase1.pdf", contenido=b"%PDF-1.4 hola", titulo="Clase 1"):
    data = {"archivo": (io.BytesIO(contenido), nombre), "titulo": titulo}
    return client.post(f"/cursos/{CURSO}/materiales", data=data, content_type="multipart/form-data",
                       headers={"Authorization": "Bearer token-falso"})


def test_sin_token_devuelve_401(client):
    resp = client.post(f"/cursos/{CURSO}/materiales", data={}, content_type="multipart/form-data")
    assert resp.status_code == 401


def test_extension_no_permitida(client, monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr("routes.docente.materiales.docente_es_dueno", lambda c, d: True)
    resp = _post(client, nombre="virus.exe")
    assert resp.status_code == 400
    assert "no permitido" in resp.get_json()["error"]


def test_subida_correcta_devuelve_202_con_job(client, monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr("routes.docente.materiales.docente_es_dueno", lambda c, d: True)
    subidas = []
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda ruta, datos, ct: subidas.append((ruta, ct)) or ruta)
    monkeypatch.setattr(materiales, "get_service_client", lambda: _DbFalsa())
    monkeypatch.setattr(materiales.jobs, "crear_job", lambda sesion_id, tipo, formato=None: {"id": "job-1", "tipo": tipo})

    resp = _post(client)
    assert resp.status_code == 202
    cuerpo = resp.get_json()
    assert cuerpo["job_id"] == "job-1"
    assert cuerpo["sesion_id"] == "sesion-1"
    assert cuerpo["tipo_archivo"] == "pdf"
    assert cuerpo["hash"] == materiales.sha256_bytes(b"%PDF-1.4 hola")
    assert subidas[0][0] == f"{CURSO}/{cuerpo['hash']}.pdf"
    assert subidas[0][1] == "application/pdf"


def test_hash_es_sha256_estable():
    assert materiales.sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _con_g(usuario):
    from flask import g

    g.usuario = usuario
    return usuario


class _DbFalsa:
    """Simula lo mínimo de supabase-py usado por registrar_material."""

    def table(self, nombre):
        assert nombre == "sesiones_material"
        return self

    def insert(self, fila):
        assert fila["estado"] == "procesando"
        assert fila["curso_id"] == CURSO
        self._fila = fila
        return self

    def execute(self):
        class R:
            data = [{"id": "sesion-1", **self._fila}]

        return R()
