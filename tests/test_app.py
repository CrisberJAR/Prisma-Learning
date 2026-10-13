from app import create_app


def test_ping():
    client = create_app().test_client()
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_health_config_lists_missing_vars():
    client = create_app().test_client()
    resp = client.get("/health/config")
    assert resp.status_code == 200
    assert isinstance(resp.get_json()["faltantes"], list)
