from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services import cuentas, rate_limit
from services.auth import usuario_actual

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
        flash("Escribe correo y contraseña.", "error")
        return render_template("auth/entrar.html"), 400
    try:
        tokens = cuentas.iniciar_sesion(email, password)
    except Exception:
        flash("No se pudo iniciar sesión. Revisa el correo y la contraseña.", "error")
        return render_template("auth/entrar.html"), 401
    session.clear()
    session["access_token"] = tokens["access_token"]
    session["refresh_token"] = tokens["refresh_token"]
    session.permanent = True
    usuario = usuario_actual()
    if usuario is None:
        session.clear()
        flash("Tu cuenta no tiene perfil. Vuelve a registrarte o avisa a quien administra el sistema.", "error")
        return render_template("auth/entrar.html"), 403
    if usuario.get("debe_cambiar_clave"):
        flash("Estás usando una contraseña temporal. Crea una propia para continuar.", "ok")
        return redirect(url_for("auth.cambiar_clave"))
    return _a_su_panel(usuario)


def _a_su_panel(usuario: dict):
    if usuario["rol"] == "docente":
        return redirect(url_for("panel.cursos"))
    if usuario["rol"] == "estudiante":
        return redirect(url_for("estudiante.mochila"))
    session.clear()
    flash("Este perfil no tiene un panel asignado.", "error")
    return render_template("auth/entrar.html"), 403


@bp.post("/salir")
def salir():
    session.clear()
    return redirect(url_for("auth.entrar"))


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
    flash("Contraseña actualizada.", "ok")
    return _a_su_panel(usuario)
