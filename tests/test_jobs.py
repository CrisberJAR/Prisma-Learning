from services import jobs


def test_reintento_reencola_si_queda_margen(monkeypatch):
    actualizaciones = []
    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))
    monkeypatch.setattr(jobs, "_job_extraer", lambda job: (_ for _ in ()).throw(RuntimeError("fallo transitorio")))
    monkeypatch.setattr(jobs, "_es_reintentable", lambda exc: True)
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "obtener_job", lambda jid: {"id": jid, "estado": actualizaciones[-1]["estado"]})
    monkeypatch.setattr(jobs, "get_service_client", lambda: None)

    final = jobs.ejecutar_job({"id": "j1", "tipo": "extraer", "intentos": 0, "sesion_id": "s1"})
    estados = [c.get("estado") for c in actualizaciones if "estado" in c]
    assert "queued" in estados
    assert "failed" not in estados
    assert final["estado"] == "queued"


def test_tercer_intento_marca_failed(monkeypatch):
    actualizaciones = []
    sesion_error = []

    class Db:
        def table(self, n):
            return self

        def update(self, campos):
            sesion_error.append(campos)
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return None

    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))
    monkeypatch.setattr(jobs, "_job_extraer", lambda job: (_ for _ in ()).throw(RuntimeError("sigue fallando")))
    monkeypatch.setattr(jobs, "_es_reintentable", lambda exc: True)
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "obtener_job", lambda jid: {"id": jid, "estado": actualizaciones[-1]["estado"]})
    monkeypatch.setattr(jobs, "get_service_client", lambda: Db())

    final = jobs.ejecutar_job({"id": "j1", "tipo": "extraer", "intentos": 2, "sesion_id": "s1"})
    assert final["estado"] == "failed"
    assert sesion_error[0]["estado"] == "error"


def test_ffmpeg_faltante_no_reintenta(monkeypatch):
    from services.transcriber import FfmpegNoDisponible

    actualizaciones = []
    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))
    monkeypatch.setattr(jobs, "_job_extraer", lambda job: (_ for _ in ()).throw(FfmpegNoDisponible("no ffmpeg")))
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "obtener_job", lambda jid: {"id": jid, "estado": actualizaciones[-1]["estado"]})

    class Db:
        def table(self, n):
            return self

        def update(self, c):
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return None

    monkeypatch.setattr(jobs, "get_service_client", lambda: Db())
    final = jobs.ejecutar_job({"id": "j1", "tipo": "extraer", "intentos": 0, "sesion_id": "s1"})
    assert final["estado"] == "failed"
    assert not any(c.get("estado") == "queued" for c in actualizaciones)


def test_polling_job_requiere_auth(client=None):
    from app import create_app

    c = create_app(con_worker=False).test_client()
    resp = c.get("/jobs/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 401


def test_sin_worker_la_consulta_ejecuta_el_job_una_sola_vez(monkeypatch):
    from services import jobs as j

    ejecutados = []
    monkeypatch.setattr(j, "ejecutar_job", lambda job: ejecutados.append(job["id"]) or {**job, "estado": "done"})
    monkeypatch.setattr(j, "reclamar", lambda jid: not ejecutados)
    assert j.atender_sin_worker({"id": "a", "estado": "queued"})["estado"] == "done"
    assert j.atender_sin_worker({"id": "a", "estado": "queued"})["estado"] == "queued"  # otro lo ganó
    assert ejecutados == ["a"]


def test_sin_worker_recupera_solo_los_jobs_colgados(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from services import jobs as j

    cambios = []
    monkeypatch.setattr(j, "_actualizar_job", lambda jid, **c: cambios.append(c))
    monkeypatch.setattr(j, "reclamar", lambda jid: False)
    reciente = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    antiguo = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    j.atender_sin_worker({"id": "a", "estado": "running", "iniciado_en": reciente})
    assert cambios == []
    j.atender_sin_worker({"id": "a", "estado": "running", "iniciado_en": antiguo})
    assert cambios[0]["estado"] == "queued"


def test_cron_exige_el_secreto(monkeypatch):
    from app import create_app
    from config import settings
    from services import mantenimiento

    monkeypatch.setattr(mantenimiento, "tareas_diarias", lambda: {"chat": 0})
    c = create_app().test_client()
    monkeypatch.setattr(settings, "CRON_SECRET", "")
    assert c.get("/cron/mantenimiento", headers={"Authorization": "Bearer "}).status_code == 401
    monkeypatch.setattr(settings, "CRON_SECRET", "s3creto")
    assert c.get("/cron/mantenimiento").status_code == 401
    assert c.get("/cron/mantenimiento", headers={"Authorization": "Bearer otro"}).status_code == 401
    r = c.get("/cron/mantenimiento", headers={"Authorization": "Bearer s3creto"})
    assert r.status_code == 200 and r.get_json() == {"chat": 0}


def test_tareas_diarias_siguen_si_una_falla(monkeypatch):
    from services import jobs as j, mantenimiento, storage

    def falla():
        raise RuntimeError("x")

    monkeypatch.setattr(mantenimiento, "purgar_chat", falla)
    monkeypatch.setattr(storage, "purgar_previas", lambda: 2)
    monkeypatch.setattr(j, "procesar_cola", lambda: 1)
    assert mantenimiento.tareas_diarias() == {"chat": "error", "previas": 2, "jobs": 1}
