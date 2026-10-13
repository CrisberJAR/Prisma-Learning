"""Lista los modelos disponibles en Groq y Gemini y verifica los nombres configurados en .env.

Uso: python scripts/check_models.py
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402


def groq_models():
    resp = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        timeout=20,
    )
    resp.raise_for_status()
    return {m["id"] for m in resp.json().get("data", [])}


def gemini_models():
    names, token = set(), None
    while True:
        params = {"pageSize": 100}
        if token:
            params["pageToken"] = token
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        names |= {m["name"].removeprefix("models/") for m in data.get("models", [])}
        token = data.get("nextPageToken")
        if not token:
            return names


def check(provider, fetch, configured):
    print(f"\n== {provider} ==")
    try:
        available = fetch()
    except Exception as exc:
        print(f"  ERROR al listar modelos: {exc}")
        return False
    print(f"  {len(available)} modelos disponibles:")
    for name in sorted(available):
        print(f"    - {name}")
    ok = True
    for var, model in configured.items():
        status = "OK" if model in available else "NO ENCONTRADO"
        ok &= model in available
        print(f"  {var}={model!r}: {status}")
    return ok


def main():
    groq_ok = check(
        "Groq",
        groq_models,
        {
            "MODEL_TEXT_PRIMARY": settings.MODEL_TEXT_PRIMARY,
            "MODEL_TEXT_FALLBACK": settings.MODEL_TEXT_FALLBACK,
            "MODEL_STT": settings.MODEL_STT,
        },
    )
    gemini_ok = check(
        "Gemini",
        gemini_models,
        {
            "MODEL_VISION": settings.MODEL_VISION,
            "MODEL_LITE": settings.MODEL_LITE,
        },
    )
    sys.exit(0 if groq_ok and gemini_ok else 1)


if __name__ == "__main__":
    main()
