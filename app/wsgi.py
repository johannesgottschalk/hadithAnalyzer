# app/wsgi.py
from app import create_app

# WSGI-Entry-Point für Gunicorn/Flask
app = create_app()
