"""Creación de jobs en la tabla `jobs`. El worker que los ejecuta llega en la Microfase 2.5."""
from services.supabase_client import get_service_client

ESTADOS_ACTIVOS = ("queued", "running")


def crear_job(sesion_id: str, tipo: str, formato: str | None = None) -> dict:
    """Crea un job. Idempotente: si ya hay uno activo para la misma sesión/tipo/formato lo devuelve."""
    db = get_service_client()
    consulta = (
        db.table("jobs")
        .select("*")
        .eq("sesion_id", sesion_id)
        .eq("tipo", tipo)
        .in_("estado", list(ESTADOS_ACTIVOS))
    )
    consulta = consulta.eq("formato", formato) if formato else consulta.is_("formato", "null")
    existentes = consulta.limit(1).execute().data
    if existentes:
        return existentes[0]

    fila = {"sesion_id": sesion_id, "tipo": tipo, "formato": formato, "estado": "queued"}
    return db.table("jobs").insert(fila).execute().data[0]


def obtener_job(job_id: str) -> dict | None:
    db = get_service_client()
    res = db.table("jobs").select("*").eq("id", job_id).limit(1).execute()
    return res.data[0] if res.data else None


def jobs_en_cola(limite: int = 10) -> list[dict]:
    db = get_service_client()
    return db.table("jobs").select("*").eq("estado", "queued").order("creado_en").limit(limite).execute().data


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------
def _actualizar_job(job_id: str, **campos) -> None:
    get_service_client().table("jobs").update(campos).eq("id", job_id).execute()


def ejecutar_job(job: dict) -> dict:
    """Ejecuta un job de forma síncrona y deja su estado final en la tabla. Devuelve el job actualizado."""
    db = get_service_client()
    _actualizar_job(job["id"], estado="running", iniciado_en=_ahora(), intentos=(job.get("intentos") or 0) + 1, error=None)
    try:
        if job["tipo"] == "extraer":
            _job_extraer(job)
        else:
            raise ValueError(f"Tipo de job desconocido: {job['tipo']}")
        _actualizar_job(job["id"], estado="done", progreso=100, terminado_en=_ahora())
    except Exception as exc:  # noqa: BLE001 - el error se persiste en el job
        _actualizar_job(job["id"], estado="failed", error=str(exc)[:2000], terminado_en=_ahora())
        if job.get("sesion_id"):
            db.table("sesiones_material").update({"estado": "error"}).eq("id", job["sesion_id"]).execute()
    return obtener_job(job["id"])


def _job_extraer(job: dict) -> None:
    from services import extractor, storage

    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", job["sesion_id"]).limit(1).execute().data
    if not sesion:
        raise ValueError("La sesión del job ya no existe")
    sesion = sesion[0]

    _actualizar_job(job["id"], progreso=10)
    datos = storage.download_bytes(sesion["archivo_url"])
    _actualizar_job(job["id"], progreso=30)

    resultado = extractor.extraer(datos, sesion["tipo_archivo"])
    _actualizar_job(job["id"], progreso=90)

    db.table("sesiones_material").update(
        {"texto_extraido": resultado.texto, "estado": "revision"}
    ).eq("id", sesion["id"]).execute()
    # Trazabilidad de qué método/modelo produjo el texto, en el propio job.
    _actualizar_job(job["id"], formato=f"{resultado.metodo}" + (f":{resultado.modelo_usado}" if resultado.modelo_usado else ""))


def _ahora() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
