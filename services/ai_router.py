"""Punto único de acceso a los modelos de IA.

Reglas:
- Los nombres de modelo vienen de config/.env, nunca del código.
- Cada llamada recibe una cadena de modelos: si el primero devuelve 429 (cuota agotada)
  o un error transitorio, se intenta con el siguiente.
- Se devuelve siempre el modelo que respondió, para guardarlo en `modelo_usado`.
"""
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from config import settings

log = logging.getLogger(__name__)

# 429: cuota agotada · 404: modelo retirado para la cuenta · 500/503: error o saturación transitoria
CODIGOS_REINTENTABLES = {404, 429, 500, 503}


class CuotaAgotada(RuntimeError):
    """Todos los modelos de la cadena fallaron por cuota o errores transitorios."""


@dataclass
class RespuestaIA:
    texto: str
    modelo: str


@lru_cache(maxsize=1)
def _gemini() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _codigo_http(exc: Exception) -> int | None:
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


def gemini_generar(partes: list, cadena: tuple[str, ...] | None = None, temperatura: float = 0.1) -> RespuestaIA:
    """Genera texto con Gemini probando cada modelo de la cadena hasta que uno responda.

    `partes` es una lista de str y/o google.genai.types.Part (por ejemplo PDF o imágenes).
    """
    cadena = cadena or (settings.MODEL_VISION, settings.MODEL_LITE)
    ultimo_error: Exception | None = None
    for modelo in cadena:
        if not modelo:
            continue
        try:
            res = _gemini().models.generate_content(
                model=modelo,
                contents=partes,
                config=genai_types.GenerateContentConfig(temperature=temperatura),
            )
            return RespuestaIA(texto=res.text or "", modelo=modelo)
        except genai_errors.APIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                log.warning("Gemini %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
    raise CuotaAgotada(f"Sin cuota en Gemini para {cadena}: {ultimo_error}")


def parte_binaria(datos: bytes, mime_type: str) -> genai_types.Part:
    return genai_types.Part.from_bytes(data=datos, mime_type=mime_type)
