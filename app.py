from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, url_for

import httpx

from config import settings
from services import i18n
from routes.auth import bp as auth_bp
from routes.chat import bp as chat_bp
from routes.docente import bp as docente_bp
from routes.estudiante import bp as estudiante_bp
from routes.jobs import bp as jobs_bp
from routes.panel import bp as panel_bp


def create_app(con_worker: bool | None = None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.FLASK_SECRET_KEY or "dev-only-secret"
    app.config["MAX_CONTENT_LENGTH"] = settings.MAX_UPLOAD_MB * 1024 * 1024
    # Lax: el navegador no manda la cookie de sesión en POST que vienen de otros sitios (CSRF).
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    app.register_blueprint(auth_bp)
    app.register_blueprint(panel_bp)
    app.register_blueprint(estudiante_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(docente_bp)
    app.register_blueprint(jobs_bp)

    @app.before_request
    def cargar_usuario():
        from services.auth import usuario_actual

        usuario_actual()

    @app.before_request
    def cargar_idioma():
        from flask import g, request, session

        g.idioma = i18n.resolver(session, getattr(g, "usuario", None), request.accept_languages)

    @app.context_processor
    def contexto_idioma():
        from flask import g

        codigo = getattr(g, "idioma", i18n.DEFECTO)
        return {"idioma_ui": codigo, "idiomas_ui": i18n.IDIOMAS, "catalogo_js": i18n.catalogo_js(codigo)}

    app.jinja_env.globals["_"] = i18n._
    app.jinja_env.filters["etiqueta"] = i18n.etiqueta

    @app.before_request
    def proteger_csrf():
        """Segunda capa contra CSRF: un POST de navegador debe venir de este mismo sitio."""
        from flask import request

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        origen = request.headers.get("Origin") or request.headers.get("Referer")
        if not origen:
            return None  # Clientes sin navegador (scripts con Bearer) y tests.
        if urlparse(origen).netloc != request.host:
            return jsonify({"error": "Petición de otro sitio bloqueada"}), 403
        return None

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        # same-origin (no no-referrer): con no-referrer los formularios propios envían
        # "Origin: null" y la comprobación CSRF no podría distinguirlos de un ataque.
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        return resp

    @app.get("/offline")
    def offline():
        from flask import render_template

        return render_template("offline.html")

    @app.get("/privacidad")
    def privacidad():
        from flask import render_template

        return render_template("privacidad.html", retencion=settings.CHAT_RETENCION_DIAS)

    @app.get("/")
    def raiz():
        from flask import g

        rol = getattr(g, "usuario", None) and g.usuario.get("rol")
        if rol == "docente":
            return redirect(url_for("panel.cursos"))
        if rol == "estudiante":
            return redirect(url_for("estudiante.mochila"))
        return redirect(url_for("auth.entrar"))

    # Nunca arrancar el worker solo por importar este módulo (scripts y tests lo importan).
    if con_worker:
        from services import jobs

        jobs.iniciar_worker()

    @app.get("/ping")
    def ping():
        return jsonify({"ok": True})

    @app.get("/health/config")
    def health_config():
        return jsonify({"faltantes": settings.missing()})

    @app.get("/health/ia")
    def health_ia():
        from services import ai_router

        return jsonify(ai_router.resumen_uso())

    @app.errorhandler(413)
    def archivo_demasiado_grande(_):
        return jsonify({"error": f"El archivo supera el máximo de {settings.MAX_UPLOAD_MB} MB"}), 413

    @app.errorhandler(httpx.HTTPError)
    def error_de_red(_exc):
        from flask import render_template, request

        from services.supabase_client import invalidar_clientes

        invalidar_clientes()
        if request.accept_mimetypes.best == "application/json" or (request.path or "").startswith(("/jobs/", "/health/")):
            return jsonify({"error": "No se pudo conectar. Recarga e inténtalo de nuevo."}), 503
        return render_template("error_red.html"), 503

    return app


app = create_app(con_worker=False)

if __name__ == "__main__":
    from services import jobs

    jobs.iniciar_worker()
    # use_reloader=False evita dos procesos y dos workers en desarrollo.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
