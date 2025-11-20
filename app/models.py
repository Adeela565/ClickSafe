from .db import db
from sqlalchemy.sql import func

class Department(db.Model):
	__tablename__ = "departments"
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False, unique=True)
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
	recipients = db.relationship("Recipient", back_populates="department")

class Recipient(db.Model):
	__tablename__ = "recipients"
	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(255), unique=True, nullable=False)
	name = db.Column(db.String(150))
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
	department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
	department = db.relationship("Department", back_populates="recipients")

class Campaign(db.Model):
	__tablename__ = "campaigns"
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(200), nullable=False)
	subject = db.Column(db.String(255))
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

class Event(db.Model):
	__tablename__ = "events"
	id = db.Column(db.Integer, primary_key=True)
	campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
	recipient_id = db.Column(db.Integer, db.ForeignKey("recipients.id", ondelete="CASCADE"), nullable=False)
	event_type = db.Column(db.String(50), nullable=False)	# 'delivered', 'clicked', 'reported'
	ip = db.Column(db.String(45))
	ts = db.Column(db.DateTime(timezone=True), server_default=func.now())
