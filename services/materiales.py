"""Alta de material de una sesión: validación, hash, subida y creación del job de extracción."""
import hashlib
import os

from services import jobs, storage
from services.supabase_client import get_service_client

# Extensión -> (tipo lógico usado por el extractor, content-type para Storage)
TIPOS_PERMITIDOS = {
    ".pdf": ("pdf", "application/pdf"),
    ".txt": ("texto", "text/plain"),
    ".md": ("texto", "text/markdown"),
    ".png": ("imagen", "image/png"),
    ".jpg": ("imagen", "image/jpeg"),
    ".jpeg": ("imagen", "image/jpeg"),
    ".webp": ("imagen", "image/webp"),
    ".mp3": ("audio", "audio/mpeg"),
    ".m4a": ("audio", "audio/mp4"),
    ".wav": ("audio", "audio/wav"),
    ".ogg": ("audio", "audio/ogg"),
    ".mp4": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
}


class MaterialInvalido(ValueError):
    pass


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def clasificar_archivo(nombre: str) -> tuple[str, str, str]:
    """Devuelve (extensión, tipo lógico, content-type) o lanza MaterialInvalido."""
    ext = os.path.splitext(nombre or "")[1].lower()
    if ext not in TIPOS_PERMITIDOS:
        permitidas = ", ".join(sorted(TIPOS_PERMITIDOS))
        raise MaterialInvalido(f"Tipo de archivo no permitido. Usa: {permitidas}")
    tipo, content_type = TIPOS_PERMITIDOS[ext]
    return ext, tipo, content_type


def docente_es_dueno(curso_id: str, docente_id: str) -> bool:
    res = (
        get_service_client()
        .table("cursos")
        .select("id")
        .eq("id", curso_id)
        .eq("docente_id", docente_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def registrar_material(curso_id: str, titulo: str, nombre_archivo: str, datos: bytes, idioma: str = "es") -> dict:
    """Sube el archivo, crea la sesión en estado 'procesando' y encola el job 'extraer'."""
    if not datos:
        raise MaterialInvalido("El archivo está vacío")
    ext, tipo, content_type = clasificar_archivo(nombre_archivo)
    hash_contenido = sha256_bytes(datos)

    ruta = f"{curso_id}/{hash_contenido}{ext}"
    storage.upload_bytes(ruta, datos, content_type)

    db = get_service_client()
    sesion = (
        db.table("sesiones_material")
        .insert(
            {
                "curso_id": curso_id,
                "titulo": titulo.strip() or os.path.basename(nombre_archivo),
                "archivo_url": ruta,
                "tipo_archivo": tipo,
                "contenido_hash": hash_contenido,
                "idioma_original": idioma,
                "estado": "procesando",
            }
        )
        .execute()
        .data[0]
    )
    job = jobs.crear_job(sesion["id"], "extraer")
    return {"sesion_id": sesion["id"], "job_id": job["id"], "tipo_archivo": tipo, "hash": hash_contenido}
