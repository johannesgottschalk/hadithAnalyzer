# app/__init__.py
import os
from flask import Flask
from hadith_analyzer.hf import HF  # dein Loader

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev")

    data_dir = os.getenv("APP_DATA_DIR", "data/hf-2025.08")
    try:
        app.hf = HF(data_dir)
    except Exception as e:
        # Loader-Fehler sichtbar machen, App startet trotzdem
        app.hf = None
        app.config["HF_INIT_ERROR"] = str(e)

    from .routes import bp
    app.register_blueprint(bp)

    @app.route("/_health")
    def _health():
        ok = app.hf is not None
        return ({"ok": ok, "error": app.config.get("HF_INIT_ERROR", "")}, 200 if ok else 500)

    return app
