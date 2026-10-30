from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from services import analitica, chat_service, contenido, cuentas, dua, imagen_educativa, jobs, materiales, mediacion, package_builder
from services import cursos as svc
from services.auth import requiere_pagina, requiere_rol
from services.i18n import _

bp = Blueprint("panel", __name__, url_prefix="/docente")


@bp.get("/")
@requiere_pagina("docente")
def inicio():
    return redirect(url_for("panel.cursos"))


@bp.get("/cursos")
@requiere_pagina("docente")
def cursos():
    q = (request.args.get("q") or "").strip()
    lista = svc.filtrar(
        svc.listar_cursos(g.usuario["id"]), q, "nombre_curso", "descripcion", "nivel_educativo_etiqueta"
    )
    return render_template("docente/cursos.html", cursos=lista, niveles_cine=svc.NIVELES_CINE, q=q)


@bp.post("/cursos")
@requiere_pagina("docente")
def crear_curso():
    try:
        curso = svc.crear_curso(
            g.usuario["id"],
            request.form.get("nombre", ""),
            request.form.get("descripcion", ""),
            request.form.get("nivel_educativo", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.cursos"))
    flash(_("Curso creado."), "ok")
    return redirect(url_for("panel.curso", curso_id=curso["id"]))


@bp.post("/cursos/<uuid:curso_id>/editar")
@requiere_pagina("docente")
def editar_curso(curso_id):
    curso_id = str(curso_id)
    try:
        svc.editar_curso(
            curso_id,
            g.usuario["id"],
            request.form.get("nombre", ""),
            request.form.get("descripcion", ""),
            request.form.get("nivel_educativo", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash(_("Curso actualizado."), "ok")
    return redirect(url_for("panel.curso", curso_id=curso_id))


@bp.post("/cursos/<uuid:curso_id>/eliminar")
@requiere_pagina("docente")
def eliminar_curso(curso_id):
    curso_id = str(curso_id)
    try:
        svc.eliminar_curso(curso_id, g.usuario["id"], request.form.get("confirmacion", ""))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    flash(_("Curso eliminado con sus sesiones e inscripciones. Las cuentas de los estudiantes se conservan."), "ok")
    return redirect(url_for("panel.cursos"))


def _pagina_curso(curso_id: str, previa: dict | None = None, codigo: int = 200, credencial: dict | None = None):
    curso = svc.obtener_curso(curso_id, g.usuario["id"])
    if curso is None:
        return (_("Curso no encontrado."), 404)
    sesiones = svc.sesiones_de_curso(curso_id)
    for s in sesiones:
        s["jobs"] = svc.jobs_de_sesion(s["id"])
        s["tiene_texto"] = bool((s.get("texto_extraido") or "").strip())
    html = render_template(
        "docente/curso.html",
        curso=curso,
        sesiones=sesiones,
        inscripciones=svc.inscripciones(curso_id),
        preferencias=svc.PREFERENCIAS,
        necesidades_dua=dua.NECESIDADES,
        lenguas_dua=dua.LENGUAS,
        nombres=package_builder.NOMBRES_UI,
        tipos=sorted(materiales.TIPOS_PERMITIDOS),
        accept_archivos=materiales.accept_html(),
        previa=previa,
        niveles_cine=svc.NIVELES_CINE,
        credencial=credencial,
    )
    return html, codigo


@bp.get("/cursos/<uuid:curso_id>")
@requiere_pagina("docente")
def curso(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    return _pagina_curso(curso_id)


@bp.get("/cursos/<uuid:curso_id>/analitica")
@requiere_pagina("docente")
def analitica_curso(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    curso = svc.obtener_curso(curso_id, g.usuario["id"])
    if curso is None:
        return (_("Curso no encontrado."), 404)
    return render_template("docente/analitica.html", curso=curso, resumen=analitica.resumen_curso(curso_id))


@bp.post("/cursos/<uuid:curso_id>/materiales")
@requiere_pagina("docente")
def subir(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    archivo = request.files.get("archivo")
    titulo = (request.form.get("titulo") or "").strip()
    tiene_archivo = archivo is not None and bool(archivo.filename)
    if not tiene_archivo and not titulo:
        flash(_("Escribe un título o sube un archivo."), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    try:
        if tiene_archivo:
            previa = materiales.previsualizar_material(
                curso_id=curso_id,
                titulo=titulo,
                nombre_archivo=archivo.filename,
                datos=archivo.read(),
                idioma=request.form.get("idioma", "es"),
            )
        else:
            previa = materiales.previsualizar_desde_titulo(
                curso_id=curso_id,
                titulo=titulo,
                idioma=request.form.get("idioma", "es"),
            )
    except materiales.MaterialInvalido as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    flash(_("Revisa lo extraído. Puedes editarlo antes de crear la sesión."), "ok")
    return _pagina_curso(curso_id, previa=previa)


@bp.post("/cursos/<uuid:curso_id>/materiales/confirmar")
@requiere_pagina("docente")
def confirmar_material(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    try:
        sesion = materiales.confirmar_material(
            curso_id=curso_id,
            titulo=request.form.get("titulo", ""),
            texto=request.form.get("texto", ""),
            ruta=request.form.get("ruta", ""),
            hash_contenido=request.form.get("hash", ""),
            tipo=request.form.get("tipo", ""),
            idioma=request.form.get("idioma", "es"),
        )
    except materiales.MaterialInvalido as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    flash(_("Sesión creada. Revisa los formatos DUA y publícala cuando quieras."), "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/cursos/<uuid:curso_id>/materiales/preview_json")
@requiere_rol("docente")
def preview_material_json(curso_id):
    """API: recibe archivo y devuelve la previsualización (JSON) sin crear la sesión."""
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return jsonify({"error": _("El curso no existe o no te pertenece")}), 404
    archivo = request.files.get("archivo")
    titulo = (request.form.get("titulo") or "").strip()
    tiene_archivo = archivo is not None and bool(archivo.filename)
    if not tiene_archivo and not titulo:
        return jsonify({"error": _("Escribe un título o sube un archivo")}), 400
    try:
        if tiene_archivo:
            previa = materiales.previsualizar_material(
                curso_id=curso_id,
                titulo=titulo,
                nombre_archivo=archivo.filename,
                datos=archivo.read(),
                idioma=request.form.get("idioma", "es"),
            )
        else:
            previa = materiales.previsualizar_desde_titulo(
                curso_id=curso_id,
                titulo=titulo,
                idioma=request.form.get("idioma", "es"),
            )
    except materiales.MaterialInvalido as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": _("No se pudo extraer el archivo: {detalle}", detalle=exc)}), 500
    return jsonify(previa), 200


@bp.post("/cursos/<uuid:curso_id>/alumnos")
@requiere_pagina("docente")
def inscribir(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    try:
        fila = svc.inscribir(
            curso_id,
            request.form.get("email", ""),
            request.form.get("nombre", ""),
            request.form.getlist("preferencias"),
            request.form.get("idioma", "es"),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    except Exception as exc:
        flash(_("No se pudo inscribir al estudiante. Detalle: {detalle}", detalle=exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    if fila.get("clave_temporal"):
        # Se renderiza en vez de redirigir: la clave no viaja en la cookie de flash.
        flash(_("Cuenta creada e inscrita. Entrega estos datos al estudiante."), "ok")
        return _pagina_curso(curso_id, credencial={"email": fila["email"], "clave": fila["clave_temporal"]})
    if fila.get("ya_inscrito"):
        flash(_("Ese estudiante ya estaba inscrito en este curso."), "ok")
    else:
        flash(_("Estudiante inscrito. Ya tenía cuenta: entra con su contraseña de siempre."), "ok")
    return redirect(url_for("panel.curso", curso_id=curso_id))


@bp.post("/cursos/<uuid:curso_id>/inscripciones/<uuid:inscripcion_id>/clave")
@requiere_pagina("docente")
def restablecer_clave(curso_id, inscripcion_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    insc = svc.inscripcion_de_curso(str(inscripcion_id), curso_id)
    if insc is None:
        return (_("Inscripción no encontrada."), 404)
    try:
        clave = cuentas.restablecer_clave(insc["estudiante_id"])
    except Exception as exc:
        flash(_("No se pudo restablecer la contraseña: {detalle}", detalle=exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    perfil = svc.perfil_basico(insc["estudiante_id"])
    flash(_("Contraseña restablecida. El estudiante deberá cambiarla al entrar."), "ok")
    return _pagina_curso(curso_id, credencial={"email": perfil.get("email") or "", "clave": clave})


@bp.post("/cursos/<uuid:curso_id>/inscripciones/<uuid:inscripcion_id>/eliminar")
@requiere_pagina("docente")
def desinscribir(curso_id, inscripcion_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    svc.desinscribir(str(inscripcion_id), curso_id)
    flash(_("Estudiante quitado del curso. Su cuenta sigue activa."), "ok")
    return redirect(url_for("panel.curso", curso_id=curso_id))


@bp.post("/cursos/<uuid:curso_id>/inscripciones/<uuid:inscripcion_id>")
@requiere_pagina("docente")
def preferencias(curso_id, inscripcion_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return (_("Curso no encontrado."), 404)
    prefs = request.form.getlist("preferencias")
    svc.actualizar_preferencias(str(inscripcion_id), curso_id, prefs, request.form.get("idioma", "es"))
    flash(_("Necesidades DUA actualizadas. El estudiante las verá combinadas en la clase."), "ok")
    return redirect(url_for("panel.curso", curso_id=curso_id))


@bp.get("/sesiones/<uuid:sesion_id>")
@requiere_pagina("docente")
def sesion(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return (_("Sesión no encontrada."), 404)
    paquetes = {p["formato"]: p for p in svc.paquetes_de_sesion(sesion["id"])}
    return render_template(
        "docente/sesion.html",
        sesion=sesion,
        jobs=svc.jobs_de_sesion(sesion["id"]),
        paquetes=paquetes,
        formatos=package_builder.FORMATOS_MVP,
        nombres=package_builder.NOMBRES_UI,
        necesidades_dua=dua.NECESIDADES,
        lenguas_dua=dua.LENGUAS,
        dudas=chat_service.dudas_de_sesion(sesion["id"]),
        idioma_contenido=contenido.idioma_interfaz(),
        traducir_al_cargar=not contenido.mismo_idioma(contenido.idioma_interfaz(), sesion.get("idioma_original") or "es"),
        url_imagen=url_for("panel.imagen_educativa_json", sesion_id=sesion["id"]),
        url_mediacion=url_for("panel.mediacion_json", sesion_id=sesion["id"]),
        rol_mediacion="docente",
    )


@bp.post("/sesiones/<uuid:sesion_id>/editar")
@requiere_pagina("docente")
def editar_sesion(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return (_("Sesión no encontrada."), 404)
    try:
        fila = svc.editar_sesion(sesion, request.form.get("titulo", ""), request.form.get("texto", ""))
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        if fila.get("texto_cambio"):
            flash(_("Sesión actualizada. Como cambió el texto, vuelve a generar los formatos DUA."), "ok")
        else:
            flash(_("Sesión actualizada."), "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/sesiones/<uuid:sesion_id>/eliminar")
@requiere_pagina("docente")
def eliminar_sesion(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return (_("Sesión no encontrada."), 404)
    if request.form.get("confirmar") != "si":
        flash(_("Marca la casilla de confirmación para eliminar la sesión."), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    svc.eliminar_sesion(sesion)
    flash(_("Sesión «{titulo}» eliminada.", titulo=sesion["titulo"]), "ok")
    return redirect(url_for("panel.curso", curso_id=sesion["curso_id"]))


@bp.post("/sesiones/<uuid:sesion_id>/dua_traducir")
@requiere_rol("docente")
def dua_traducir(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": _("Sesión no encontrada")}), 404
    cuerpo = request.get_json(silent=True) or {}
    out = dua.adaptar_a_lengua(sesion.get("texto_extraido") or "", cuerpo.get("idioma") or "", sesion.get("idioma_original") or "es")
    return jsonify(out)


@bp.get("/sesiones/<uuid:sesion_id>/imagen")
@requiere_rol("docente")
def imagen_educativa_json(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": _("Sesión no encontrada")}), 404
    try:
        out = imagen_educativa.para_sesion(sesion)
        out["alt"] = _("Imagen educativa del tema: {titulo}", titulo=sesion.get("titulo") or "")
        return jsonify(out)
    except Exception as exc:
        return jsonify({"estado": "error", "url": "", "alt": "", "error": str(exc)}), 500


@bp.get("/sesiones/<uuid:sesion_id>/mediacion")
@requiere_rol("docente")
def mediacion_json(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": _("Sesión no encontrada")}), 404
    try:
        return jsonify(mediacion.para_sesion(sesion, contenido.idioma_interfaz()))
    except Exception as exc:
        return jsonify(
            {
                "estado": "error",
                "pauta_docente": "",
                "pauta_estudiante": "",
                "glosario": [],
                "error": str(exc),
            }
        ), 500


@bp.post("/sesiones/<uuid:sesion_id>/formatos")
@requiere_pagina("docente")
def pedir_formato(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return (_("Sesión no encontrada."), 404)
    formato = (request.form.get("formato") or "").strip()
    if formato not in package_builder.FORMATOS_MVP:
        flash(_("Formato no soportado."), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    if not (sesion.get("texto_extraido") or "").strip():
        flash(_("Aún no hay texto extraído."), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    if formato == "alto_contraste":
        package_builder.guardar_paquete(
            sesion["id"],
            formato,
            package_builder.generar(
                formato, sesion["texto_extraido"], sesion.get("contenido_hash") or "", sesion.get("idioma_original") or "es"
            ),
        )
        flash(_("Alto contraste listo (sin IA)."), "ok")
    else:
        jobs.crear_job(sesion["id"], "formato", formato=formato)
        flash(_("Generación en cola. Recarga en unos segundos."), "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/sesiones/<uuid:sesion_id>/formatos/<formato>")
@requiere_pagina("docente")
def editar_formato(sesion_id, formato):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return (_("Sesión no encontrada."), 404)
    try:
        contenido = _contenido_desde_form(formato, request.form)
        svc.guardar_edicion(sesion["id"], formato, contenido)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    flash(_("Cambios guardados. Quedaron marcados como editados por el docente."), "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/sesiones/<uuid:sesion_id>/publicar")
@requiere_pagina("docente")
def publicar(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return (_("Sesión no encontrada."), 404)
    try:
        svc.publicar_sesion(sesion["id"])
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    flash(_("Publicado. Los estudiantes inscritos ya pueden ver todos los formatos."), "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/jobs/<uuid:job_id>/reintentar")
@requiere_pagina("docente")
def reintentar(job_id):
    job = jobs.docente_puede_ver_job(str(job_id), g.usuario["id"])
    if job is None:
        return (_("Job no encontrado."), 404)
    try:
        svc.reintentar_job(job["id"])
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash(_("Job vuelto a la cola."), "ok")
    return redirect(url_for("panel.sesion", sesion_id=job["sesion_id"]))


def _contenido_desde_form(formato: str, form) -> dict:
    if formato == "lectura_accesible":
        avisos = [a.strip() for a in (form.get("avisos") or "").split("\n") if a.strip()]
        return {"markdown": form.get("markdown") or "", "avisos": avisos}
    if formato == "alto_contraste":
        return {
            "tokens": {
                "fondo": form.get("fondo") or "#000000",
                "texto": form.get("texto") or "#FFFFFF",
                "enlace": form.get("enlace") or "#FFFF00",
                "foco": form.get("foco") or "#00FFFF",
                "aviso": form.get("aviso") or "#FFD700",
            },
            "tamano_base_px": int(form.get("tamano_base_px") or 20),
            "tamano_min_px": 16,
            "tamano_max_px": 32,
        }
    if formato == "modo_enfoque":
        titulos = form.getlist("pildora_titulo")
        textos = form.getlist("pildora_texto")
        pildoras = [{"titulo": t.strip(), "texto": x.strip()} for t, x in zip(titulos, textos) if t.strip() or x.strip()]
        return {"pildoras": pildoras}
    raise ValueError("Formato no editable")
