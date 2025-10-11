from app import create_app
from app.db import db
from app.models import Event

app = create_app()
with app.app_context():
	db.metadata.create_all(bind=db.engine, tables=[Event.__table__])
	print("Create table: events")

