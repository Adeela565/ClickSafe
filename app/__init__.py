# app/__init__.py
from flask import Flask
from config import Config          # <- import the Config class directly
from .db import db                 # <- your SQLAlchemy instance
from .routes import bp as main_bp  # <- your blueprint

def create_app():
    app = Flask(__name__)

    # Load configuration (SECRET_KEY, DATABASE_URL, SMTP settings, etc.)
    app.config.from_object(Config)

    # Initialize database extension
    db.init_app(app)

    # Register main blueprint (routes)
    app.register_blueprint(main_bp)

    return app

