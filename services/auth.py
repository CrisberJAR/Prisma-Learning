"""Identidad del usuario en cada petición.

El cliente manda el access token de Supabase Auth en `Authorization: Bearer <token>`.
Se valida contra Supabase y se carga el perfil (rol) con el cliente de servicio.
"""
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for

from services import cuentas
from services.supabase_client import get_anon_client, get_service_client


def _token_de_la_peticion() -> str | None:
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip() or None
    return session.get("access_token") or None


def _validar(token: str):
    try:
        return get_anon_client().auth.get_user(token).user
    except Exception:
        return None


def usuario_actual() -> dict | None:
    """Devuelve {"id", "email", "nombre", "rol", "token", "debe_cambiar_clave"} o None si no hay sesión válida."""
    if getattr(g, "usuario", None):
        return g.usuario
    token = _token_de_la_peticion()
    if not token:
        g.usuario = None
        return None
    auth_user = _validar(token)
    if auth_user is None and token == session.get("access_token"):
        # El access token dura ~1 h: con el refresh token se renueva sin pedir login.
        nueva = cuentas.refrescar(session.get("refresh_token") or "")
        if nueva:
            session["access_token"] = nueva["access_token"]
            session["refresh_token"] = nueva["refresh_token"]
            token = nueva["access_token"]
            auth_user = _validar(token)
    if not auth_user:
        g.usuario = None
        return None
    perfil = get_service_client().table("perfiles").select("*").eq("id", auth_user.id).limit(1).execute().data
    if not perfil:
        g.usuario = None
        return None
    g.usuario = {
        "id": auth_user.id,
        "email": auth_user.email,
        "nombre": perfil[0]["nombre"],
        "rol": perfil[0]["rol"],
        "token": token,
        "debe_cambiar_clave": bool(perfil[0].get("debe_cambiar_clave")),
    }
    return g.usuario


def requiere_rol(*roles: str):
    """Decorador: exige sesión válida y, si se indican, uno de los roles dados."""

    def decorador(fn):
        @wraps(fn)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return jsonify({"error": "No autenticado"}), 401
            if roles and usuario["rol"] not in roles:
                return jsonify({"error": "Sin permiso"}), 403
            if usuario.get("debe_cambiar_clave"):
                return jsonify({"error": "Debes cambiar tu contraseña temporal antes de continuar"}), 403
            return fn(*args, **kwargs)

        return envoltura

    return decorador


def requiere_pagina(*roles: str):
    """Igual que requiere_rol, pero redirige al login en vez de devolver JSON."""

    def decorador(fn):
        @wraps(fn)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return redirect(url_for("auth.entrar"))
            if roles and usuario["rol"] not in roles:
                return ("Sin permiso para esta página.", 403)
            if usuario.get("debe_cambiar_clave"):
                return redirect(url_for("auth.cambiar_clave"))
            return fn(*args, **kwargs)

        return envoltura

    return decorador
