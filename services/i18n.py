"""Idioma de la interfaz (no del contenido de la clase: eso lo adapta services/dua.py).

La clave de cada traducción es el texto en español tal como aparece en el código:
    _("Curso creado.")                       -> "Course created."
    _("Sesión «{titulo}» eliminada.", titulo=t)
Si falta una traducción se muestra el español, así nada se rompe. Los catálogos están en
translations/<codigo>.json y tests/test_i18n.py falla si alguno queda incompleto.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "translations"

DEFECTO = "es"
IDIOMAS = (
    {"codigo": "es", "nombre": "Español"},
    {"codigo": "en", "nombre": "English"},
    {"codigo": "pt", "nombre": "Português"},
    {"codigo": "fr", "nombre": "Français"},
)
CODIGOS = tuple(i["codigo"] for i in IDIOMAS)

# Valores que vienen de la base de datos y se muestran traducidos.
ETIQUETAS = {
    "procesando": "Procesando",
    "revision": "En revisión",
    "publicado": "Publicado",
    "error": "Error",
    "queued": "En cola",
    "running": "En curso",
    "done": "Listo",
    "failed": "Falló",
    "extraer": "Extracción",
    "formato": "Formato",
    "borrador": "Borrador",
    "enviado": "Enviado",
    "evaluado": "Evaluado",
    "avanzado": "Avanzado",
    "satisfactorio": "Satisfactorio",
    "en_proceso": "En proceso",
    "inicial": "Inicial",
}

# Llamadas a traducir en el código: _("..."), t("...") en JS. Lo usa el extractor y el test.
PATRON = re.compile(r"""(?<![\w.])(?:_|t)\(\s*(["'])((?:\\.|(?!\1).)*)\1""", re.S)


def normalizar(codigo: str | None) -> str | None:
    c = (codigo or "").strip().lower().replace("_", "-").split("-")[0]
    return c if c in CODIGOS else None


@lru_cache(maxsize=None)
def catalogo(codigo: str) -> dict[str, str]:
    if codigo == DEFECTO:
        return {}
    ruta = CARPETA / f"{codigo}.json"
    if not ruta.is_file():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def idioma_actual() -> str:
    from flask import g, has_app_context

    if has_app_context():
        return getattr(g, "idioma", None) or DEFECTO
    return DEFECTO


def traducir(texto: str, codigo: str | None = None, **valores) -> str:
    cat = catalogo(codigo or idioma_actual())
    salida = cat.get(texto) or texto
    if valores:
        try:
            return salida.format(**valores)
        except (KeyError, IndexError, ValueError):
            return texto.format(**valores)
    return salida


def _(texto: str, **valores) -> str:
    return traducir(texto, **valores)


def etiqueta(valor: str | None) -> str:
    """Traduce un valor guardado en la base (estado de sesión, estado de job...)."""
    if not valor:
        return ""
    return _(ETIQUETAS.get(valor, valor))


def resolver(session, usuario: dict | None, accept_languages) -> str:
    """Elección explícita en esta sesión > preferencia del perfil > navegador > español."""
    return (
        normalizar(session.get("idioma_ui"))
        or normalizar((usuario or {}).get("idioma_ui"))
        or normalizar(accept_languages.best_match(CODIGOS) if accept_languages else None)
        or DEFECTO
    )


def claves_en(texto: str) -> list[str]:
    return [m.group(2).replace('\\"', '"').replace("\\'", "'") for m in PATRON.finditer(texto)]


@lru_cache(maxsize=None)
def claves_js() -> frozenset[str]:
    """Textos que usan los scripts del navegador: solo esos viajan a la página."""
    claves: set[str] = set()
    for f in (RAIZ / "public" / "static" / "js").glob("*.js"):
        claves.update(claves_en(f.read_text(encoding="utf-8")))
    return frozenset(claves)


def claves_dinamicas() -> set[str]:
    """Textos que se traducen como variable (_(n.etiqueta)): el extractor no los ve en el código."""
    from services import cursos, dua, ejercicios, mediacion, package_builder

    claves = set(ETIQUETAS.values()) | {dua.MSG_IDIOMA_INVALIDO}
    claves |= {mediacion.PAUTA_LOCAL_DOCENTE, mediacion.PAUTA_LOCAL_ESTUDIANTE}
    claves.update(ejercicios.NOMBRES_TIPO.values())
    claves.update(n["etiqueta"] for n in dua.NECESIDADES)
    claves.update(n["ayuda"] for n in dua.NECESIDADES)
    claves.update(l["etiqueta"] for l in dua.LENGUAS)
    claves.update(package_builder.NOMBRES_UI.values())
    claves.update(n["etiqueta"] for n in cursos.NIVELES_CINE)
    return claves


def todas_las_claves() -> set[str]:
    """Todo lo que debe tener cada catálogo (lo usan scripts/i18n_extraer.py y el test)."""
    claves = claves_dinamicas()
    fuentes = [*(RAIZ / "templates").rglob("*.html"), *(RAIZ / "routes").glob("*.py"),
               *(RAIZ / "services").glob("*.py"), *(RAIZ / "public" / "static" / "js").glob("*.js"), RAIZ / "app.py"]
    for f in fuentes:
        if f.name == "i18n.py":
            continue  # Sus ejemplos del docstring no son textos de la interfaz.
        claves.update(claves_en(f.read_text(encoding="utf-8")))
    return claves


def catalogo_js(codigo: str) -> dict[str, str]:
    cat = catalogo(codigo)
    return {k: cat[k] for k in claves_js() if k in cat}


def guardar_preferencia(user_id: str, codigo: str) -> None:
    """Recuerda el idioma en el perfil. Sin 005_idioma.sql solo queda en la sesión."""
    from services.supabase_client import get_service_client

    try:
        get_service_client().table("perfiles").update({"idioma_ui": codigo}).eq("id", user_id).execute()
    except Exception:
        pass
