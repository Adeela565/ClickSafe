from flask import Blueprint, render_template, request, redirect, url_for, Response, abort, flash
from .db import db
from .models import Recipient, Campaign, Event
from .emailer import send_email
from datetime import datetime

bp = Blueprint("main", __name__)

@bp.route("/send", methods=["GET", "POST"])
def send_campaign():
	if request.method == "GET":
		recipients = Recipient.query.order_by(Recipient.email.asc()).all()
		return render_template("send.html", title="Launch Campaign", recipients=recipients)

	# POST: create campaign, send to chosen recipients, record 'delivered'
	name = (request.form.get("campaign_name") or "Untitled Campaign").strip()
	subject = (request.form.get("subject") or "(no subject)").strip()
	html_body = request.form.get("html_body") or "<p>Hello! Click below for some cute cat pics!</p>"

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
		tracking_url = f"{base}/l/{campaign.id}/{r.id}"
		# Report link
		report_url = f"{base}/r/{campaign.id}/{r.id}"

		if "[[TRACKING_URL]]" in html_body or "[[REPORT_URL]]" in html_body:
			body_for_recipient = (
				html_body
					.replace("[[TRACKING_URL]]", tracking_url)
					.replace("[[REPORT_URL]]", report_url)
			)
		else:
			body_for_recipient = html_body + f"""
		<p>
			<a href="{tracking_url}" style="background:#2563eb;color:#fff;padding:.5rem .75rem;border-radius:.375rem;text-decoration:none;display:inline-block;margin-right:.5rem;">Cat Pics</a>
			<a href="{report_url}" style="background:#ef4444;color:#fff;padding:.5rem .75rem;border-radius:.375rem;text-decoration:none;display:inline-block;">Report this email</a>
		</p>
		"""
		send_email(r.email, subject, body_for_recipient)
		db.session.add(Event(campaign_id=campaign.id, recipient_id=r.id, event_type="delivered"))
		sent_count += 1

		# Record a basic 'delivered' event
		send_email(r.email, subject, body_for_recipient)
		db.session.add(Event(campaign_id=campaign.id, recipient_id=r.id, event_type="delivered"))
		sent_count += 1

	db.session.commit()
	return render_template("send_done.html", title="Campaign Sent", campaign=campaign, sent=sent_count)

@bp.route("/l/<int:cid>/<int:rid>", methods=["GET"])
def track_click(cid: int, rid: int):
	""" Record a click event for campaign cid and recipient rid, then respond. """
	# Validate foreign ids exist (keep data clean)
	campaign = Campaign.query.get(cid)
	recipient = Recipient.query.get(rid)
	if not campaign or not recipient:
		return abort(404)

	# Get client IP (handles proxies too)
	ip = request.headers.get("X-Forwarded-For", request.remote_addr)
	if ip and "," in ip: # if behind proxy, take first hop
		ip = ip.split(",")[0].strip()

	# Avoid duplicate 'clicked' rows for this (cid, rid)
	already = (Event.query.filter_by(campaign_id=cid, recipient_id=rid, event_type="clicked").first())
	if not already:
		db.session.add(Event(campaign_id=cid, recipient_id=rid, event_type="clicked", ip=ip))
		db.session.commit()

	# Landing page
	return redirect(url_for("main.feedback", cid=cid, rid=rid))

@bp.route("/r/<int:cid>/<int:rid>", methods=["GET"])
def track_report(cid: int, rid: int):
	"""Record a 'reported' event and redirect to thank-you page."""
	campaign = Campaign.query.get(cid)
	recipient = Recipient.query.get(rid)
	if not campaign or not recipient:
		return abort(404)

	ip = request.headers.get("X-Forwarded-For", request.remote_addr)
	if ip and "," in ip:
		ip = ip.split(",")[0].strip()

	# De-dupe: only one 'reported' per (cid, rid)
	already = (Event.query.filter_by(campaign_id=cid, recipient_id=rid, event_type="reported").first())
	if not already:
		db.session.add(Event(campaign_id=cid, recipient_id=rid, event_type="reported", ip=ip))
		db.session.commit()
	
	return redirect(url_for("main.thankyou", cid=cid, rid=rid))


@bp.route("/landing/<int:cid>/<int:rid>")
def landing(cid: int, rid: int):
	campaign = Campaign.query.get(cid)
	recipient = Recipient.query.get(rid)
	if not campaign or not recipient:
		return abort(404)

	# Show current time
	now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	return render_template(
		"landing.html",
		title="Click Recorded",
		campaign=campaign,
		recipient=recipient,
		ts=now_str,
		ip=request.headers.get("X-Forwarded-For", request.remote_addr),
	)

@bp.route("/feedback")
def feedback():
	"""Show phishing warning/education page."""
	cid = request.args.get("cid", type=int)
	rid = request.args.get("rid", type=int)
	campaign = Campaign.query.get(cid) if cid else None
	recipient = Recipient.query.get(rid) if rid else None
	return render_template(
		"feedback.html",
		title="Phishing Safety",
		campaign=campaign,
		recipient=recipient,
		reported=False,
	)

@bp.route("/feedback/report", methods=["POST"])
def feedback_report():
	"""Record a 'reported' event for the campaign/recipient."""
	cid = request.form.get("cid", type=int)
	rid = request.form.get("rid", type-int)

	ip = request.headers.get("X-Forwarded-For", request.remote_addr)
	if ip and "," in ip:
		ip = ip.split(",")[0].strip()

	# Only log if we have both IDs and they exist
	if cid and rid:
		if Campaign.query.get(cid) and Recipient.query.get(rid):
			exists = Event.query.filter_by(campaign_id=cid, recipient_id=rid, event_type="reported").first()
		if not exists:
			db.session.add(Event(campaign_id=cid, recipient_id=rid, event_type="reported", ip=ip))
			db.session.commit()

	# Re-render page with a success banner
	campaign = Campaign.query.get(cid) if cid else None
	recipient = Recipient.query.get(rid) if rid else None
	return render_template("feedback.html", title="Phishing Safety", campaign=campaign, recipient=recipient, reported=True)

@bp.route("/thankyou/<int:cid>/<int:rid>")
def thankyou(cid: int, rid: int):
	campaign = Campaign.query.get(cid)
	recipient = Recipient.query.get(rid)
	if not campaign or not recipient:
		return abort(404)
	return render_template("thankyou.html", title="Reported", campaign=campaign, recipient=recipient)
