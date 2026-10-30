"""CRUD de cursos, inscripciones y publicación de sesiones."""
import hashlib
import unicodedata
from types import SimpleNamespace

from services import cuentas, dua, storage
from services.supabase_client import get_service_client

PREFERENCIAS = list(dua.CODIGOS)

# Código CINE (UNESCO) + etiqueta oficial. El formulario guarda ambos en cursos.
NIVELES_CINE = (
    {"codigo": "cine_1_inicial", "etiqueta": "CINE 1 - Primaria inicial (6 a 8 años)"},
    {"codigo": "cine_1_avanzada", "etiqueta": "CINE 1 - Primaria avanzada (9 a 11 años)"},
    {"codigo": "cine_2", "etiqueta": "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)"},
    {"codigo": "cine_3", "etiqueta": "CINE 3 - Secundaria superior / Bachillerato (15 a 17 años)"},
    {"codigo": "cine_6", "etiqueta": "CINE 6+ - Educación Terciaria / Superior (18+ años)"},
)
NIVELES_POR_CODIGO = {n["codigo"]: n["etiqueta"] for n in NIVELES_CINE}


def resolver_nivel(codigo: str) -> tuple[str, str]:
    clave = (codigo or "").strip()
    etiqueta = NIVELES_POR_CODIGO.get(clave)
    if not etiqueta:
        raise ValueError("Elige un nivel educativo CINE")
    return clave, etiqueta


def nivel_de_curso(curso_id: str) -> dict:
    filas = (
        get_service_client()
        .table("cursos")
        .select("nivel_educativo, nivel_educativo_etiqueta")
        .eq("id", curso_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return filas[0] if filas else {}


def listar_cursos(docente_id: str) -> list[dict]:
    cursos = (
        get_service_client()
        .table("cursos")
        .select("*")
        .eq("docente_id", docente_id)
        .order("creado_en", desc=True)
        .execute()
        .data
        or []
    )
    _agregar_conteos(cursos)
    return cursos


def obtener_curso(curso_id: str, docente_id: str) -> dict | None:
    filas = (
        get_service_client()
        .table("cursos")
        .select("*")
        .eq("id", curso_id)
        .eq("docente_id", docente_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not filas:
        return None
    _agregar_conteos(filas)
    return filas[0]


def _agregar_conteos(cursos: list[dict]) -> None:
    """Dos consultas en total (no dos por curso) para contar sesiones y estudiantes."""
    if not cursos:
        return
    db = get_service_client()
    ids = [c["id"] for c in cursos]
    n_ses: dict[str, int] = {}
    for f in db.table("sesiones_material").select("curso_id").in_("curso_id", ids).execute().data or []:
        n_ses[f["curso_id"]] = n_ses.get(f["curso_id"], 0) + 1
    n_est: dict[str, int] = {}
    for f in db.table("inscripciones_curso").select("curso_id").in_("curso_id", ids).execute().data or []:
        n_est[f["curso_id"]] = n_est.get(f["curso_id"], 0) + 1
    for c in cursos:
        c["n_sesiones"] = n_ses.get(c["id"], 0)
        c["n_estudiantes"] = n_est.get(c["id"], 0)


def normalizar_texto(texto: str) -> str:
    """Minúsculas y sin tildes, para buscar «biologia» y encontrar «Biología»."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn").strip()


def filtrar(items: list[dict], q: str, *campos: str) -> list[dict]:
    """Respaldo sin JavaScript del buscador (?q=)."""
    q = normalizar_texto(q)
    if not q:
        return items
    return [i for i in items if q in normalizar_texto(" ".join(str(i.get(c) or "") for c in campos))]


def crear_curso(docente_id: str, nombre: str, descripcion: str = "", nivel_educativo: str = "") -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del curso es obligatorio")
    codigo, etiqueta = resolver_nivel(nivel_educativo)
    fila = {
        "docente_id": docente_id,
        "nombre_curso": nombre,
        "descripcion": descripcion.strip() or None,
        "nivel_educativo": codigo,
        "nivel_educativo_etiqueta": etiqueta,
    }
    try:
        return get_service_client().table("cursos").insert(fila).execute().data[0]
    except Exception as exc:
        if "nivel_educativo" in str(exc):
            raise ValueError(
                "Falta agregar en Supabase las columnas CINE. Ejecuta supabase/003_cine.sql en el editor SQL."
            ) from exc
        raise


def editar_curso(curso_id: str, docente_id: str, nombre: str, descripcion: str = "", nivel_educativo: str = "") -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del curso es obligatorio")
    codigo, etiqueta = resolver_nivel(nivel_educativo)
    filas = (
        get_service_client()
        .table("cursos")
        .update(
            {
                "nombre_curso": nombre,
                "descripcion": (descripcion or "").strip() or None,
                "nivel_educativo": codigo,
                "nivel_educativo_etiqueta": etiqueta,
            }
        )
        .eq("id", curso_id)
        .eq("docente_id", docente_id)
        .execute()
        .data
    )
    if not filas:
        raise ValueError("El curso no existe")
    return filas[0]


def eliminar_curso(curso_id: str, docente_id: str, confirmacion: str) -> None:
    """Borra el curso con sus sesiones, formatos, jobs, chats e inscripciones.

    Las cuentas de los estudiantes se conservan: pueden estar en otros cursos.
    """
    curso = obtener_curso(curso_id, docente_id)
    if curso is None:
        raise ValueError("El curso no existe")
    if (confirmacion or "").strip() != (curso.get("nombre_curso") or "").strip():
        raise ValueError("Para eliminar, escribe el nombre exacto del curso.")
    db = get_service_client()
    sesiones = db.table("sesiones_material").select("id, archivo_url").eq("curso_id", curso_id).execute().data or []
    ids = [x["id"] for x in sesiones]
    if ids:
        # Sin 004_fase1.sql esta FK no tiene cascada: se borra antes a mano.
        db.table("interacciones_progreso").delete().in_("sesion_id", ids).execute()
    db.table("cursos").delete().eq("id", curso_id).eq("docente_id", docente_id).execute()
    storage.remove([x["archivo_url"] for x in sesiones if x.get("archivo_url")])


def editar_sesion(sesion: dict, titulo: str, texto: str) -> dict:
    """Cambia título y/o texto. Si cambia el texto, los formatos IA quedan obsoletos y se regeneran."""
    titulo = (titulo or "").strip()
    texto = (texto or "").strip()
    if not titulo:
        raise ValueError("El título de la sesión es obligatorio")
    cambios: dict = {"titulo": titulo[:200]}
    texto_cambio = bool(texto) and texto != (sesion.get("texto_extraido") or "").strip()
    if texto_cambio:
        if sesion.get("estado") == "procesando":
            raise ValueError("Espera a que termine la extracción antes de editar el texto")
        cambios["texto_extraido"] = texto
        # Hash nuevo: imagen, mediación y formatos se cachean por hash del material.
        cambios["contenido_hash"] = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    db = get_service_client()
    fila = db.table("sesiones_material").update(cambios).eq("id", sesion["id"]).execute().data[0]
    if texto_cambio:
        from services import imagen_educativa, mediacion, package_builder

        db.table("paquetes_formato").delete().eq("sesion_id", sesion["id"]).execute()
        idioma = fila.get("idioma_original") or "es"
        try:
            package_builder.guardar_paquete(
                fila["id"],
                "alto_contraste",
                package_builder.generar("alto_contraste", texto, cambios["contenido_hash"], idioma),
            )
        except Exception:
            pass
        imagen_educativa.generar_en_fondo(fila)
        mediacion.generar_en_fondo(fila)
    fila["texto_cambio"] = texto_cambio
    return fila


def eliminar_sesion(sesion: dict) -> None:
    db = get_service_client()
    db.table("interacciones_progreso").delete().eq("sesion_id", sesion["id"]).execute()
    db.table("sesiones_material").delete().eq("id", sesion["id"]).execute()
    ruta = sesion.get("archivo_url")
    if ruta:
        # El archivo se guarda por hash: otra sesión del curso puede compartirlo.
        otras = db.table("sesiones_material").select("id").eq("archivo_url", ruta).limit(1).execute().data
        if not otras:
            storage.remove([ruta])


def sesiones_de_curso(curso_id: str) -> list[dict]:
    return (
        get_service_client()
        .table("sesiones_material")
        .select("id, titulo, estado, tipo_archivo, creado_en, texto_extraido")
        .eq("curso_id", curso_id)
        .order("creado_en", desc=True)
        .execute()
        .data
        or []
    )


def jobs_de_sesion(sesion_id: str) -> list[dict]:
    return (
        get_service_client()
        .table("jobs")
        .select("id, tipo, formato, estado, progreso, error, intentos, creado_en")
        .eq("sesion_id", sesion_id)
        .order("creado_en", desc=True)
        .execute()
        .data
        or []
    )


def paquetes_de_sesion(sesion_id: str) -> list[dict]:
    return (
        get_service_client()
        .table("paquetes_formato")
        .select("*")
        .eq("sesion_id", sesion_id)
        .execute()
        .data
        or []
    )


def publicar_sesion(sesion_id: str) -> dict:
    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", sesion_id).limit(1).execute().data
    if not sesion:
        raise ValueError("La sesión no existe")
    if sesion[0].get("estado") not in ("revision", "publicado"):
        raise ValueError("Solo se puede publicar una sesión en revisión")
    return db.table("sesiones_material").update({"estado": "publicado"}).eq("id", sesion_id).execute().data[0]


def guardar_edicion(sesion_id: str, formato: str, contenido: dict) -> dict:
    db = get_service_client()
    existente = (
        db.table("paquetes_formato")
        .select("id, version")
        .eq("sesion_id", sesion_id)
        .eq("formato", formato)
        .limit(1)
        .execute()
        .data
    )
    if not existente:
        raise ValueError("Ese formato aún no está generado")
    version = (existente[0].get("version") or 1) + 1
    return (
        db.table("paquetes_formato")
        .update({"contenido": contenido, "editado_por_docente": True, "version": version})
        .eq("id", existente[0]["id"])
        .execute()
        .data[0]
    )


def reintentar_job(job_id: str) -> dict:
    db = get_service_client()
    job = db.table("jobs").select("*").eq("id", job_id).limit(1).execute().data
    if not job:
        raise ValueError("Job no encontrado")
    if job[0]["estado"] != "failed":
        raise ValueError("Solo se reintentan jobs fallidos")
    return db.table("jobs").update({"estado": "queued", "error": None, "progreso": 0}).eq("id", job_id).execute().data[0]


def inscripciones(curso_id: str) -> list[dict]:
    db = get_service_client()
    filas = (
        db.table("inscripciones_curso")
        .select("id, estudiante_id, preferencias, idioma_preferido")
        .eq("curso_id", curso_id)
        .execute()
        .data
        or []
    )
    if not filas:
        return []
    ids = [f["estudiante_id"] for f in filas]
    # "*" y no columnas fijas: email solo existe tras 004_fase1.sql.
    perfiles = {p["id"]: p for p in db.table("perfiles").select("*").in_("id", ids).execute().data or []}
    out = []
    for f in filas:
        p = perfiles.get(f["estudiante_id"]) or {}
        out.append(
            {
                **f,
                "nombre": p.get("nombre") or "Sin nombre",
                "email": p.get("email") or "",
                "debe_cambiar_clave": bool(p.get("debe_cambiar_clave")),
                "preferencias": dua.normalizar_preferencias(f.get("preferencias")),
                "idioma_preferido": dua.normalizar_idioma(f.get("idioma_preferido") or "es"),
            }
        )
    return out


def inscribir(
    curso_id: str,
    email: str,
    nombre: str = "",
    preferencias: list[str] | None = None,
    idioma: str = "es",
) -> dict:
    """Inscribe por correo. Si la cuenta no existe, la crea con una contraseña temporal.

    Devuelve la fila de inscripción con "email" y "clave_temporal" (None si la cuenta ya
    existía). La clave solo se muestra una vez al docente para que se la entregue al estudiante.
    """
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Indica un correo válido")
    nombre = (nombre or "").strip() or email.split("@")[0]
    db = get_service_client()
    clave = None
    user = _usuario_por_email(email)
    if user is None:
        clave = cuentas.clave_temporal()
        user = _crear_estudiante(email, nombre, clave)
        if getattr(user, "ya_existia", False):
            clave = None
    perfil = db.table("perfiles").select("id, rol").eq("id", user.id).limit(1).execute().data
    if perfil and perfil[0]["rol"] != "estudiante":
        raise ValueError("Ese correo pertenece a una cuenta de docente; no se puede inscribir como estudiante.")
    if not perfil:
        _guardar_perfil(user.id, email, nombre, debe_cambiar=clave is not None)
    existente = (
        db.table("inscripciones_curso")
        .select("*")
        .eq("curso_id", curso_id)
        .eq("estudiante_id", user.id)
        .limit(1)
        .execute()
        .data
    )
    if existente:
        fila = {**existente[0], "ya_inscrito": True}
    else:
        fila = (
            db.table("inscripciones_curso")
            .insert(
                {
                    "curso_id": curso_id,
                    "estudiante_id": user.id,
                    "preferencias": dua.normalizar_preferencias(preferencias),
                    "idioma_preferido": dua.normalizar_idioma(idioma),
                }
            )
            .execute()
            .data[0]
        )
    return {**fila, "email": email, "clave_temporal": clave}


def _crear_estudiante(email: str, nombre: str, clave: str):
    try:
        creado = get_service_client().auth.admin.create_user(
            {
                "email": email,
                "password": clave,
                "email_confirm": True,
                "user_metadata": {"nombre": nombre, "rol": "estudiante"},
            }
        )
    except Exception as exc:
        texto = str(exc).lower()
        if "already" in texto or "registered" in texto or "exists" in texto:
            # Está en Auth pero su perfil no tenía correo: buscarlo en todas las páginas.
            user = _buscar_en_auth(email)
            if user is not None:
                return SimpleNamespace(id=user.id, email=email, ya_existia=True)
        if "database error" in texto:
            raise ValueError(
                "Supabase no pudo crear la cuenta (trigger de perfiles). "
                "Ejecuta supabase/002_rls_fix.sql y supabase/004_fase1.sql en el editor SQL."
            ) from exc
        raise ValueError(f"No se pudo crear la cuenta del estudiante: {exc}") from exc
    user = creado.user
    # No depender solo del trigger: si falta o falló, el perfil se crea aquí.
    _guardar_perfil(user.id, email, nombre, debe_cambiar=True)
    return user


def _guardar_perfil(user_id: str, email: str, nombre: str, debe_cambiar: bool) -> None:
    db = get_service_client()
    fila = {"id": user_id, "nombre": nombre, "rol": "estudiante", "email": email, "debe_cambiar_clave": debe_cambiar}
    try:
        db.table("perfiles").upsert(fila, on_conflict="id").execute()
    except Exception as exc:
        if "email" not in str(exc) and "debe_cambiar_clave" not in str(exc):
            raise
        # Sin 004_fase1.sql: guardar lo básico para que la inscripción funcione igual.
        db.table("perfiles").upsert({"id": user_id, "nombre": nombre, "rol": "estudiante"}, on_conflict="id").execute()


def inscripcion_de_curso(inscripcion_id: str, curso_id: str) -> dict | None:
    filas = (
        get_service_client()
        .table("inscripciones_curso")
        .select("id, estudiante_id")
        .eq("id", inscripcion_id)
        .eq("curso_id", curso_id)
        .limit(1)
        .execute()
        .data
    )
    return filas[0] if filas else None


def perfil_basico(user_id: str) -> dict:
    db = get_service_client()
    filas = db.table("perfiles").select("*").eq("id", user_id).limit(1).execute().data or []
    perfil = dict(filas[0]) if filas else {}
    if not perfil.get("email"):
        try:
            perfil["email"] = db.auth.admin.get_user_by_id(user_id).user.email
        except Exception:
            pass
    return perfil


def desinscribir(inscripcion_id: str, curso_id: str) -> None:
    """Quita al estudiante del curso. Su cuenta se conserva."""
    get_service_client().table("inscripciones_curso").delete().eq("id", inscripcion_id).eq("curso_id", curso_id).execute()


def actualizar_preferencias(inscripcion_id: str, curso_id: str, preferencias: list[str], idioma: str = "es") -> dict:
    validas = dua.normalizar_preferencias(preferencias)
    return (
        get_service_client()
        .table("inscripciones_curso")
        .update({"preferencias": validas, "idioma_preferido": dua.normalizar_idioma(idioma)})
        .eq("id", inscripcion_id)
        .eq("curso_id", curso_id)
        .execute()
        .data[0]
    )


def _usuario_por_email(email: str):
    """Busca la cuenta por correo. Devuelve un objeto con .id o None.

    supabase-py no tiene get_user_by_email y list_users() pagina de 50 en 50, así que
    primero se consulta perfiles.email (004_fase1.sql) y, si no está, se recorre Auth.
    """
    email = (email or "").strip().lower()
    try:
        filas = get_service_client().table("perfiles").select("id").eq("email", email).limit(1).execute().data
    except Exception:
        filas = None  # La columna email aún no existe.
    if filas:
        return SimpleNamespace(id=filas[0]["id"], email=email)
    return _buscar_en_auth(email)


def _buscar_en_auth(email: str):
    admin = get_service_client().auth.admin
    por_pagina = 1000
    for pagina in range(1, 201):
        lote = admin.list_users(page=pagina, per_page=por_pagina)
        lista = getattr(lote, "users", None) or lote or []
        for u in lista:
            if (getattr(u, "email", "") or "").lower() == email:
                return u
        if len(lista) < por_pagina:
            break
    return None
