from flask import Flask, jsonify

from config import settings
from routes.docente import bp as docente_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.FLASK_SECRET_KEY or "dev-only-secret"
    app.config["MAX_CONTENT_LENGTH"] = settings.MAX_UPLOAD_MB * 1024 * 1024

    app.register_blueprint(docente_bp)

    @app.get("/ping")
    def ping():
        return jsonify({"ok": True})

    @app.get("/health/config")
    def health_config():
        return jsonify({"faltantes": settings.missing()})

    @app.errorhandler(413)
    def archivo_demasiado_grande(_):
        return jsonify({"error": f"El archivo supera el máximo de {settings.MAX_UPLOAD_MB} MB"}), 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
