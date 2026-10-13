import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    HF_TOKEN = os.getenv("HF_TOKEN", "")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")

    MODEL_TEXT_PRIMARY = os.getenv("MODEL_TEXT_PRIMARY", "")
    MODEL_TEXT_FALLBACK = os.getenv("MODEL_TEXT_FALLBACK", "")
    MODEL_VISION = os.getenv("MODEL_VISION", "")
    MODEL_LITE = os.getenv("MODEL_LITE", "")
    MODEL_STT = os.getenv("MODEL_STT", "")

    CHAT_LIMITE_DIARIO = int(os.getenv("CHAT_LIMITE_DIARIO", "30"))

    # Almacenamiento. El plan gratuito de Supabase limita cada archivo a 50 MB.
    STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "materiales")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
    SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL", "3600"))

    REQUIRED = (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "FLASK_SECRET_KEY",
        "MODEL_TEXT_PRIMARY",
        "MODEL_TEXT_FALLBACK",
        "MODEL_VISION",
        "MODEL_LITE",
        "MODEL_STT",
    )

    def missing(self):
        return [name for name in self.REQUIRED if not getattr(self, name)]


settings = Settings()
