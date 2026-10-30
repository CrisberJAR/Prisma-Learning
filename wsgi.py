"""Entrada de producción: Gunicorn carga este módulo y arranca el worker de jobs."""
import logging
import os

from app import create_app

# En producción los logs van a la salida estándar de la plataforma (Render, Heroku, Docker).
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app(con_worker=True)
