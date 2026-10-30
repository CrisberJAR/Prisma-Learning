"""Tareas periódicas de cumplimiento.

La página de privacidad promete que el chat del tutor se guarda como máximo
CHAT_RETENCION_DIAS días (Ley 29733). Esto lo hace cumplir: el worker de jobs lo llama
en cada vuelta, pero solo purga una vez cada 24 h; scripts/purgar_chat.py lo ejecuta a mano.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from config import settings
from services.supabase_client import get_service_client

log = logging.getLogger(__name__)
CADA_SEGUNDOS = 24 * 3600
_ultima = 0.0
_lock = threading.Lock()


def purgar_chat(dias: int | None = None) -> int:
    """Borra los mensajes del tutor más antiguos que la retención. Devuelve cuántos borró."""
    dias = settings.CHAT_RETENCION_DIAS if dias is None else dias
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    borrados = get_service_client().table("mensajes_chat").delete().lt("creado_en", limite).execute().data or []
    if borrados:
        log.info("Retención: %s mensajes de chat con más de %s días borrados", len(borrados), dias)
    return len(borrados)


def tareas_diarias() -> dict:
    """Lo que hace el worker cuando no hay proceso permanente. Un fallo no impide las demás."""
    from services import jobs, storage

    resultado = {}
    for nombre, tarea in (("chat", purgar_chat), ("previas", storage.purgar_previas), ("jobs", jobs.procesar_cola)):
        try:
            resultado[nombre] = tarea()
        except Exception:
            log.exception("Tarea diaria %s: falló", nombre)
            resultado[nombre] = "error"
    return resultado


def quizas_purgar_chat() -> None:
    """Purga como máximo una vez al día. Un fallo se registra y no detiene el worker."""
    global _ultima
    with _lock:
        if time.monotonic() - _ultima < CADA_SEGUNDOS and _ultima:
            return
        _ultima = time.monotonic()
    try:
        purgar_chat()
    except Exception:
        log.warning("No se pudo purgar el chat antiguo; se reintenta mañana", exc_info=True)
