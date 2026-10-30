"""Acceso a Supabase Storage. Siempre desde el servidor con la clave de servicio.

El bucket es privado: el navegador nunca recibe la ruta interna, solo URLs firmadas
con vencimiento que genera el backend cuando hacen falta.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from config import settings
from services.supabase_client import get_service_client

PREVIAS = "previas"


def ensure_bucket() -> None:
    client = get_service_client()
    existentes = {b.name for b in client.storage.list_buckets()}
    if settings.STORAGE_BUCKET not in existentes:
        client.storage.create_bucket(
            settings.STORAGE_BUCKET,
            options={"public": False, "file_size_limit": settings.MAX_UPLOAD_MB * 1024 * 1024},
        )


def upload_bytes(ruta: str, datos: bytes, content_type: str) -> str:
    """Sube el archivo y devuelve la ruta interna. Si ya existe (mismo hash) lo sobrescribe."""
    client = get_service_client()
    client.storage.from_(settings.STORAGE_BUCKET).upload(
        ruta, datos, {"content-type": content_type, "upsert": "true"}
    )
    return ruta


def signed_url(ruta: str, ttl: int | None = None) -> str:
    client = get_service_client()
    res = client.storage.from_(settings.STORAGE_BUCKET).create_signed_url(
        ruta, ttl or settings.SIGNED_URL_TTL
    )
    return res["signedURL"]


def download_bytes(ruta: str) -> bytes:
    client = get_service_client()
    return client.storage.from_(settings.STORAGE_BUCKET).download(ruta)


def remove(rutas: list[str]) -> None:
    """Borra archivos del bucket. Un fallo aquí no debe impedir borrar la sesión o el curso."""
    rutas = [r for r in rutas if r]
    if not rutas:
        return
    try:
        get_service_client().storage.from_(settings.STORAGE_BUCKET).remove(rutas)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Vistas previas: en servidores sin disco compartido, la petición que confirma puede
# caer en otra instancia distinta de la que extrajo, así que no pueden vivir en /tmp.
# ---------------------------------------------------------------------------
def guardar_previa(curso_id: str, clave: str, datos: bytes, meta: dict) -> None:
    base = f"{PREVIAS}/{curso_id}/{clave}"
    if datos:
        upload_bytes(f"{base}.bin", datos, "application/octet-stream")
    upload_bytes(f"{base}.json", json.dumps({**meta, "con_archivo": bool(datos)}).encode("utf-8"), "application/json")


def leer_previa(curso_id: str, clave: str) -> tuple[bytes, dict]:
    """Lanza una excepción de Storage si ya no existe."""
    base = f"{PREVIAS}/{curso_id}/{clave}"
    meta = json.loads(download_bytes(f"{base}.json"))
    return (download_bytes(f"{base}.bin") if meta.get("con_archivo") else b""), meta


def borrar_previa(curso_id: str, clave: str) -> None:
    base = f"{PREVIAS}/{curso_id}/{clave}"
    remove([f"{base}.bin", f"{base}.json"])


def url_subida_directa(curso_id: str, ext: str) -> dict:
    """URL firmada para que el navegador suba a Storage sin pasar por el servidor.

    Vercel rechaza peticiones de más de 4,5 MB; así caben los archivos de hasta MAX_UPLOAD_MB.
    """
    ruta = f"{PREVIAS}/{curso_id}/subida-{uuid.uuid4().hex}{ext}"
    res = get_service_client().storage.from_(settings.STORAGE_BUCKET).create_signed_upload_url(ruta)
    return {"url": res["signed_url"], "ruta": ruta}


def purgar_previas(horas: int = 24) -> int:
    """Borra las vistas previas y subidas que nadie confirmó. Devuelve cuántos archivos borró."""
    bucket = get_service_client().storage.from_(settings.STORAGE_BUCKET)
    limite = datetime.now(timezone.utc) - timedelta(hours=horas)
    viejos = []
    for curso in bucket.list(PREVIAS, {"limit": 1000}):
        carpeta = f"{PREVIAS}/{curso['name']}"
        for f in bucket.list(carpeta, {"limit": 1000}):
            creado = f.get("created_at")
            if creado and datetime.fromisoformat(creado.replace("Z", "+00:00")) < limite:
                viejos.append(f"{carpeta}/{f['name']}")
    remove(viejos)
    return len(viejos)
