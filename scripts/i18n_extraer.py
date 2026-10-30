"""Revisa los catálogos de traducción contra los textos del código.

  python scripts/i18n_extraer.py              # informa claves faltantes y sobrantes
  python scripts/i18n_extraer.py --actualizar # añade las faltantes (valor vacío) y quita las sobrantes

Las claves con valor vacío se muestran en español hasta que alguien las traduzca.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import i18n  # noqa: E402


def main() -> int:
    actualizar = "--actualizar" in sys.argv
    claves = i18n.todas_las_claves()
    problemas = 0
    for codigo in i18n.CODIGOS:
        if codigo == i18n.DEFECTO:
            continue
        ruta = i18n.CARPETA / f"{codigo}.json"
        cat = json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}
        faltan = sorted(claves - {k for k, v in cat.items() if v})
        sobran = sorted(set(cat) - claves)
        problemas += len(faltan) + len(sobran)
        print(f"{codigo}: {len(cat)} claves, {len(faltan)} sin traducir, {len(sobran)} sobrantes")
        for k in faltan[:20]:
            print("   falta:", k[:100])
        if actualizar:
            nuevo = {k: cat.get(k, "") for k in sorted(claves)}
            ruta.parent.mkdir(exist_ok=True)
            ruta.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if problemas and not actualizar else 0


if __name__ == "__main__":
    raise SystemExit(main())
