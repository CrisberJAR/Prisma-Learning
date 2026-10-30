"""Borra a mano los mensajes del tutor que superan la retención (CHAT_RETENCION_DIAS).

  python scripts/purgar_chat.py           # usa la retención configurada
  python scripts/purgar_chat.py --dias 30
El worker de jobs ya lo hace una vez al día; esto sirve para cron externos o auditorías.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from services import mantenimiento  # noqa: E402

if __name__ == "__main__":
    dias = int(sys.argv[sys.argv.index("--dias") + 1]) if "--dias" in sys.argv else settings.CHAT_RETENCION_DIAS
    print(f"Borrados {mantenimiento.purgar_chat(dias)} mensajes con más de {dias} días.")
