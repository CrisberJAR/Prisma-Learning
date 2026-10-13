from flask import Blueprint, g, jsonify, request

from services import materiales
from services.auth import requiere_rol

bp = Blueprint("docente", __name__)


@bp.post("/cursos/<uuid:curso_id>/materiales")
@requiere_rol("docente")
def subir_material(curso_id):
    """Recibe un archivo, lo guarda y encola la extracción. Responde de inmediato con el job_id."""
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return jsonify({"error": "El curso no existe o no te pertenece"}), 404

    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify({"error": "Falta el campo 'archivo'"}), 400

    try:
        resultado = materiales.registrar_material(
            curso_id=curso_id,
            titulo=request.form.get("titulo", ""),
            nombre_archivo=archivo.filename,
            datos=archivo.read(),
            idioma=request.form.get("idioma", "es"),
        )
    except materiales.MaterialInvalido as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(resultado), 202
