from flask import Flask
from .db import db
from .routes import bp as main_bp

def create_app():
	app = Flask(__name__)
	app.config.from_object("config.Config")
	db.init_app(app)
	app.register_blueprint(main_bp)
	return app

