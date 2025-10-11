from flask import Blueprint, render_template, request
from .db import db
from .models import Recipient, Campaign, Event
from .emailer import send_email

bp = Blueprint("main", __name__)

@bp.route("/send", methods=["GET", "POST"])
def send_campaign():
	if request.method == "GET":
		recipients = Recipient.query.order_by(Recipient.email.asc()).all()
		return render_template("send.html", title="Launch Campaign", recipients=recipients)

	# POST: create campaign, send to chosen recipients, record 'delivered'
	name = (request.form.get("campaign_name") or "Untitled Campaign").strip()
	subject = (request.form.get("subject") or "(no subject)").strip()
	html_body = request.form.get("html_body") or "<p>Hello from ClickSafe.</p>"

	# Create the campaign row
	campaign = Campaign(name=name, subject=subject)
	db.session.add(campaign)
	db.session.commit() # so campaign.id exists

	# Resolve recipients
	use_all = request.form.get("use_all") == "on"
	selected_ids = request.form.getlist("recipients") # list of string ids
	send_to = (Recipient.query.all() if use_all or not selected_ids
		else Recipient.query.filter(Recipient.id.in_(selected_ids)).all())

	sent_count = 0
	base = request.url_root.rstrip("/")

	for r in send_to:
		# Tracking link
		tracking_url = f"{base}/1/{campaign.id}/{r.id}"

		if "[[TRACKING_URL]]" in html_body:
			body_for_recipient = html_body.replace("[[TRACKING_URL]]", tracking_url)
		else:
			body_for_recipient = html_body + f"<p><a href='{tracking_url}'>View details</a></p>"

		# Record a basic 'delivered' event
		send_email(r.email, subject, body_for_recipient)
		db.session.add(Event(campaign_id=campaign.id, recipient_id=r.id, event_type="delivered"))
		sent_count += 1

	db.session.commit()
	return render_template("send_done.html", title="Campaign Sent", campaign=campaign, sent=sent_count)

