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
