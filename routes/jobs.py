import hmac

from flask import Blueprint, g, jsonify, request

from config import settings
from services import jobs, mantenimiento
from services.auth import requiere_rol
from services.i18n import _

bp = Blueprint("jobs", __name__)


@bp.get("/jobs/<uuid:job_id>")
@requiere_rol("docente")
def ver_job(job_id):
    """Polling del estado. El frontend pinta role=progressbar con progreso y texto."""
    job = jobs.docente_puede_ver_job(str(job_id), g.usuario["id"])
    if job is None:
        return jsonify({"error": _("Job no encontrado")}), 404
    if settings.SIN_WORKER:
        job = jobs.atender_sin_worker(job)
    return jsonify(
        {
            "id": job["id"],
            "tipo": job["tipo"],
            "estado": job["estado"],
            "progreso": job.get("progreso") or 0,
            "error": job.get("error"),
            "formato": job.get("formato"),
            "intentos": job.get("intentos") or 0,
        }
    )


@bp.get("/cron/mantenimiento")
def cron_mantenimiento():
    """Tareas diarias sin proceso permanente (vercel.json). Solo con el secreto: gasta IA y borra datos."""
    esperado = f"Bearer {settings.CRON_SECRET}"
    if not settings.CRON_SECRET or not hmac.compare_digest(request.headers.get("Authorization", ""), esperado):
        return jsonify({"error": "No autorizado"}), 401
    return jsonify(mantenimiento.tareas_diarias())
