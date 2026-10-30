from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from services import cuentas, i18n, rate_limit
from services.auth import usuario_actual
from services.i18n import _

bp = Blueprint("auth", __name__)


@bp.get("/entrar")
def entrar():
    u = usuario_actual()
    if u and u["rol"] == "docente":
        return redirect(url_for("panel.cursos"))
    if u and u["rol"] == "estudiante":
        return redirect(url_for("estudiante.mochila"))
    return render_template("auth/entrar.html")


@bp.post("/entrar")
def entrar_post():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    if not email or not password:
        flash(_("Escribe correo y contraseña."), "error")
        return render_template("auth/entrar.html"), 400
    try:
        # Contra fuerza bruta: por IP (muchas cuentas) y por correo (una cuenta desde muchas IP).
        rate_limit.comprobar(f"login-ip:{request.remote_addr}", 20, ventana_s=300)
        rate_limit.comprobar(f"login-email:{email.lower()}", 8, ventana_s=300)
    except rate_limit.DemasiadoRapido:
        flash(_("Demasiados intentos de inicio de sesión. Espera unos minutos y vuelve a intentarlo."), "error")
        return render_template("auth/entrar.html"), 429
    try:
        tokens = cuentas.iniciar_sesion(email, password)
    except Exception:
        flash(_("No se pudo iniciar sesión. Revisa el correo y la contraseña."), "error")
        return render_template("auth/entrar.html"), 401
    idioma_elegido = session.get("idioma_ui")
    _limpiar_sesion()
    session["access_token"] = tokens["access_token"]
    session["refresh_token"] = tokens["refresh_token"]
    session.permanent = True
    usuario = usuario_actual()
    if usuario is None:
        _limpiar_sesion()
        flash(_("Tu cuenta no tiene perfil. Vuelve a registrarte o avisa a quien administra el sistema."), "error")
        return render_template("auth/entrar.html"), 403
    if idioma_elegido and idioma_elegido != usuario.get("idioma_ui"):
        # Lo que eligió en la pantalla de entrada pasa a ser su preferencia.
        i18n.guardar_preferencia(usuario["id"], idioma_elegido)
    if usuario.get("debe_cambiar_clave"):
        flash(_("Estás usando una contraseña temporal. Crea una propia para continuar."), "ok")
        return redirect(url_for("auth.cambiar_clave"))
    return _a_su_panel(usuario)


def _limpiar_sesion() -> None:
    """Cierra la sesión de usuario pero conserva el idioma elegido."""
    idioma = session.get("idioma_ui")
    session.clear()
    if idioma:
        session["idioma_ui"] = idioma


def _a_su_panel(usuario: dict):
    if usuario["rol"] == "docente":
        return redirect(url_for("panel.cursos"))
    if usuario["rol"] == "estudiante":
        return redirect(url_for("estudiante.mochila"))
    _limpiar_sesion()
    flash(_("Este perfil no tiene un panel asignado."), "error")
    return render_template("auth/entrar.html"), 403


@bp.post("/salir")
def salir():
    _limpiar_sesion()
    return redirect(url_for("auth.entrar"))


@bp.post("/idioma")
def cambiar_idioma():
    codigo = i18n.normalizar(request.form.get("idioma"))
    if codigo:
        session["idioma_ui"] = codigo
        # La lengua elegida a mano en cada sesión deja paso al idioma nuevo.
        for clave in [k for k in session if k.startswith("idioma_") and k != "idioma_ui"]:
            session.pop(clave)
        g.idioma = codigo
        usuario = usuario_actual()
        if usuario:
            i18n.guardar_preferencia(usuario["id"], codigo)
    destino = request.form.get("volver") or ""
    # Solo rutas internas: evita usar el selector como redirección abierta.
    if not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        destino = url_for("raiz")
    return redirect(destino)


@bp.get("/cuenta/clave")
def cambiar_clave():
    usuario = usuario_actual()
    if usuario is None:
        return redirect(url_for("auth.entrar"))
    return render_template("cuenta/clave.html", obligatorio=usuario.get("debe_cambiar_clave"))


@bp.post("/cuenta/clave")
def cambiar_clave_post():
    usuario = usuario_actual()
    if usuario is None:
        return redirect(url_for("auth.entrar"))
    obligatorio = usuario.get("debe_cambiar_clave")
    try:
        rate_limit.comprobar(f"clave:{usuario['id']}", 5, ventana_s=300)
        cuentas.cambiar_clave(
            usuario,
            request.form.get("actual") or "",
            request.form.get("nueva") or "",
            request.form.get("confirmar") or "",
        )
    except (ValueError, rate_limit.DemasiadoRapido) as exc:
        flash(str(exc), "error")
        return render_template("cuenta/clave.html", obligatorio=obligatorio), 400
    usuario["debe_cambiar_clave"] = False
    flash(_("Contraseña actualizada."), "ok")
    return _a_su_panel(usuario)
