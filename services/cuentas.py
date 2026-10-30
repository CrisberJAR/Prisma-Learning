"""Cuentas: login, refresco de sesión, contraseñas temporales y cambio de contraseña."""
import secrets

from services.supabase_client import cliente_aislado, get_service_client

LARGO_MINIMO = 8


class ClaveInvalida(ValueError):
    pass


def clave_temporal() -> str:
    """Legible para dictarla en clase (Prisma-482193) y con mayúscula, minúscula, número y símbolo."""
    return f"Prisma-{secrets.randbelow(10**6):06d}"


def iniciar_sesion(email: str, password: str) -> dict:
    """Devuelve {"access_token", "refresh_token"}. Lanza excepción si las credenciales fallan."""
    with cliente_aislado() as client:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
    return {"access_token": res.session.access_token, "refresh_token": res.session.refresh_token}


def refrescar(refresh_token: str) -> dict | None:
    """Canjea el refresh token por una sesión nueva; None si ya no sirve."""
    try:
        with cliente_aislado() as client:
            res = client.auth.refresh_session(refresh_token)
    except Exception:
        return None
    if not res or not res.session:
        return None
    return {"access_token": res.session.access_token, "refresh_token": res.session.refresh_token}


def asignar_clave(user_id: str, clave: str, debe_cambiar: bool) -> None:
    # Con debe_cambiar, la marca va primero: si falta la migración no se cambia
    # una contraseña que el docente nunca llegaría a ver.
    if debe_cambiar:
        marcar_debe_cambiar(user_id, True)
    get_service_client().auth.admin.update_user_by_id(user_id, {"password": clave})
    if not debe_cambiar:
        marcar_debe_cambiar(user_id, False)


def marcar_debe_cambiar(user_id: str, valor: bool) -> None:
    try:
        get_service_client().table("perfiles").update({"debe_cambiar_clave": valor}).eq("id", user_id).execute()
    except Exception as exc:
        if "debe_cambiar_clave" in str(exc):
            if not valor:
                return  # Sin la columna no hay marca que quitar.
            raise ValueError("Falta ejecutar supabase/004_fase1.sql en el editor SQL de Supabase.") from exc
        raise


def restablecer_clave(user_id: str) -> str:
    """Pone una contraseña temporal nueva y obliga a cambiarla en el próximo ingreso."""
    clave = clave_temporal()
    asignar_clave(user_id, clave, debe_cambiar=True)
    return clave


def cambiar_clave(usuario: dict, actual: str, nueva: str, confirmar: str) -> None:
    if not actual:
        raise ClaveInvalida("Escribe tu contraseña actual.")
    if len(nueva or "") < LARGO_MINIMO:
        raise ClaveInvalida(f"La nueva contraseña debe tener al menos {LARGO_MINIMO} caracteres.")
    if nueva != confirmar:
        raise ClaveInvalida("La confirmación no coincide con la nueva contraseña.")
    if nueva == actual:
        raise ClaveInvalida("La nueva contraseña debe ser distinta de la actual.")
    try:
        iniciar_sesion(usuario["email"], actual)
    except Exception as exc:
        raise ClaveInvalida("La contraseña actual no es correcta.") from exc
    try:
        asignar_clave(usuario["id"], nueva, debe_cambiar=False)
    except ValueError:
        raise
    except Exception as exc:
        texto = str(exc).lower()
        if "weak" in texto or "password" in texto:
            raise ClaveInvalida(
                "Supabase rechazó la contraseña por débil. Usa letras, números y algún símbolo."
            ) from exc
        raise
