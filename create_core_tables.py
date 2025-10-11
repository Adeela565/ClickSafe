from app import create_app
from app.db import db
from app.models import Recipient, Campaign

app = create_app()
with app.app_context():
	db.metadata.create_all(bind=db.engine, tables=[Recipient.__table__, Campaign.__table__])
	print("Created tables: recipients, campaigns")
