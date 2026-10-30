"""Fase 5: correcciones de robustez y seguridad encontradas en la revisión de arquitectura."""
import threading
from types import SimpleNamespace

from fake_supabase import FakeDb

from app import create_app
from config import settings
from services import cuentas, jobs, mantenimiento, rate_limit


def test_reclamar_job_solo_lo_gana_un_hilo(monkeypatch):
    """Antes dos hilos del worker podían ejecutar el mismo job (doble gasto de IA)."""
    db = FakeDb()
    db.tablas["jobs"] = [{"id": "j1", "estado": "queued"}]
    monkeypatch.setattr(jobs, "get_service_client", lambda: db)
    ganadores = []
    barrera = threading.Barrier(5)

    def intento():
        barrera.wait()
        if jobs.reclamar("j1"):
            ganadores.append(1)

    hilos = [threading.Thread(target=intento) for _ in range(5)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(ganadores) == 1
    assert db.tablas["jobs"][0]["estado"] == "running"
    assert jobs.reclamar("j1") is False


def test_purga_de_chat_respeta_la_retencion(monkeypatch):
    db = FakeDb()
    db.tablas["mensajes_chat"] = [
        {"id": "viejo", "creado_en": "2020-01-01T00:00:00+00:00"},
        {"id": "nuevo", "creado_en": "2999-01-01T00:00:00+00:00"},
    ]
    # El doble en memoria no implementa lt(): se agrega para esta prueba.
    from fake_supabase import _Consulta

    def lt(self, col, valor):
        self.filtros.append(lambda f: str(f.get(col)) < valor)
        return self

    monkeypatch.setattr(_Consulta, "lt", lt, raising=False)
    monkeypatch.setattr(mantenimiento, "get_service_client", lambda: db)
    assert mantenimiento.purgar_chat(90) == 1
    assert [m["id"] for m in db.tablas["mensajes_chat"]] == ["nuevo"]


def test_purga_como_maximo_una_vez_al_dia(monkeypatch):
    llamadas = []
    monkeypatch.setattr(mantenimiento, "purgar_chat", lambda: llamadas.append(1))
    monkeypatch.setattr(mantenimiento, "_ultima", 0.0)
    mantenimiento.quizas_purgar_chat()
    mantenimiento.quizas_purgar_chat()
    assert llamadas == [1]


def test_login_limita_intentos_por_correo(monkeypatch):
    rate_limit.reiniciar()
    monkeypatch.setattr(cuentas, "iniciar_sesion", lambda e, p: (_ for _ in ()).throw(Exception("credenciales")))
    c = create_app().test_client()
    codigos = [c.post("/entrar", data={"email": "ana@x.com", "password": f"x{i}"}).status_code for i in range(9)]
    assert codigos[:8] == [401] * 8 and codigos[8] == 429
    assert "Demasiados intentos".encode() in c.post("/entrar", data={"email": "ana@x.com", "password": "y"}).data
    rate_limit.reiniciar()


def test_health_no_revela_configuracion_al_publico():
    c = create_app().test_client()
    cuerpo = c.get("/health/config").get_json()
    assert set(cuerpo) == {"ok"}
    assert c.get("/health/ia").status_code == 401


def test_produccion_exige_clave_y_cookie_segura(monkeypatch):
    monkeypatch.setattr(settings, "ENTORNO", "produccion")
    monkeypatch.setattr(settings, "FLASK_SECRET_KEY", "")
    try:
        create_app()
        assert False, "debió negarse a arrancar sin FLASK_SECRET_KEY"
    except RuntimeError as exc:
        assert "FLASK_SECRET_KEY" in str(exc)
    monkeypatch.setattr(settings, "FLASK_SECRET_KEY", "clave-larga-de-prueba")
    app = create_app()
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert type(app.wsgi_app).__name__ == "ProxyFix"


def test_desarrollo_sigue_igual():
    app = create_app()
    assert not app.config.get("SESSION_COOKIE_SECURE")
    assert type(app.wsgi_app).__name__ != "ProxyFix"
