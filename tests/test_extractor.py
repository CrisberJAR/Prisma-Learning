import pymupdf
import pytest

from services import ai_router, extractor


def _pdf_con_texto(paginas: int = 2) -> bytes:
    doc = pymupdf.open()
    for i in range(paginas):
        pagina = doc.new_page()
        pagina.insert_text((50, 100), f"Página {i + 1}. " + "Texto educativo de prueba. " * 10, fontsize=11)
    return doc.tobytes()


def _pdf_sin_texto(paginas: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(paginas):
        pagina = doc.new_page()
        pagina.draw_rect(pymupdf.Rect(20, 20, 200, 200), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    return doc.tobytes()


def test_pdf_con_texto_usa_pymupdf_sin_ia(monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("No debe llamarse a la IA para un PDF con texto")

    monkeypatch.setattr(ai_router, "gemini_generar", no_debe_llamarse)
    res = extractor.extraer(_pdf_con_texto(2), "pdf")
    assert res.metodo == "pymupdf"
    assert res.paginas == 2
    assert "Página 1" in res.texto and "Página 2" in res.texto
    assert "<!-- página 2 -->" in res.texto


def test_pdf_escaneado_sin_tesseract_usa_gemini(monkeypatch):
    llamadas = []

    def gemini_falso(partes, cadena=None, temperatura=0.1):
        llamadas.append(partes)
        return ai_router.RespuestaIA(texto="# Título OCR\n\nTexto reconocido.", modelo="modelo-vision-x")

    monkeypatch.setattr(extractor, "_tesseract_disponible", lambda: False)
    monkeypatch.setattr(ai_router, "gemini_generar", gemini_falso)
    res = extractor.extraer(_pdf_sin_texto(), "pdf")
    assert res.metodo == "gemini"
    assert res.modelo_usado == "modelo-vision-x"
    assert res.texto.startswith("# Título OCR")
    assert len(llamadas) == 1
    assert extractor.PROMPT_OCR in llamadas[0]
    assert "DATOS" in extractor.PROMPT_OCR  # el documento se marca como datos, no instrucciones


def test_texto_plano():
    res = extractor.extraer("Hola mundo\n".encode("utf-8"), "texto")
    assert res.metodo == "texto"
    assert res.texto == "Hola mundo"


def test_texto_latin1_no_rompe():
    res = extractor.extraer("Año de educación".encode("latin-1"), "texto")
    assert "educaci" in res.texto


def test_audio_no_soportado_aqui():
    with pytest.raises(extractor.ExtraccionNoSoportada):
        extractor.extraer(b"xxx", "audio")


def test_router_pasa_al_siguiente_modelo_en_429(monkeypatch):
    class Err429(ai_router.genai_errors.APIError):
        def __init__(self):
            self.code = 429
            self.message = "quota"

    intentos = []

    class ClienteFalso:
        class models:  # noqa: N801
            @staticmethod
            def generate_content(model, contents, config):
                intentos.append(model)
                if model == "primario":
                    raise Err429()

                class R:
                    text = "ok"

                return R()

    monkeypatch.setattr(ai_router, "_gemini", lambda: ClienteFalso())
    monkeypatch.setattr(ai_router.time, "sleep", lambda s: None)
    res = ai_router.gemini_generar(["hola"], cadena=("primario", "respaldo"))
    assert res.modelo == "respaldo"
    assert intentos == ["primario", "respaldo"]
