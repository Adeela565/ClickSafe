from flask import Blueprint, render_template, request, redirect, url_for, Response, abort, flash
from sqlalchemy import func
from .db import db
from .models import Recipient, Campaign, Event, Department
from .emailer import send_email
from datetime import datetime
from flask import current_app
import random

bp = Blueprint("main", __name__)

@bp.route("/send", methods=["GET", "POST"])
def send_campaign():
	if request.method == "GET":
		recipients = Recipient.query.order_by(Recipient.email.asc()).all()
		return render_template("send.html", title="Launch Campaign", recipients=recipients)

	# POST: create campaign, send to chosen recipients, record 'delivered'
	name = (request.form.get("campaign_name") or "Untitled Campaign").strip()
	subject = (request.form.get("subject") or "(no subject)").strip()
	html_body = request.form.get("html_body") 

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
		# per-recipient tracking/report urls
		tracking_url = f"{base}/l/{campaign.id}/{r.id}"
		report_url   = f"{base}/r/{campaign.id}/{r.id}"

		# select template name from form 
		template_name = (request.form.get("email_template"))

		tmpl = current_app.jinja_env.get_template(f"email/{template_name}.html")

		# optional realistic fields (you can randomize later)
		date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
		country = random.choice(["Russia", "Canada", "USA", "Mexico", "India", "China"])
		platform = random.choice(["Windows 10", "Windows 11", "macOS 12"])
		browser = random.choice(["Chrome", "Firefox", "Edge"])
		
		# generate a random ipv4 for realism
		def _random_ipv4():
			return ".".join(str(random.randint(10, 250)) for _ in range(4))
		ip = _random_ipv4()

		body_for_recipient = tmpl.render(
		    tracking_url=tracking_url,
		    report_url=report_url,
		    recipient=r,
		    campaign=campaign,
		    date=date,
		    country=country,
		    platform=platform,
		    browser=browser,
		    ip=ip
		)
		
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
    """Record a 'reported' event and show a popup message instead of redirecting."""
    campaign = Campaign.query.get(cid)
    recipient = Recipient.query.get(rid)
    if not campaign or not recipient:
        return abort(404)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    # Avoid duplicate reports
    already = Event.query.filter_by(
        campaign_id=cid, recipient_id=rid, event_type="reported"
    ).first()
    if not already:
        db.session.add(Event(campaign_id=cid, recipient_id=rid, event_type="reported", ip=ip))
        db.session.commit()

    # Popup message
    html = """<!doctype html>
    <meta charset="utf-8">
    <title>Reported</title>
    <script>
      alert("Thank you for identifying this phishing email. Your report has been recorded.");
      try { window.close(); } catch(e) {}
    </script>
    <p style="font-family: Arial, sans-serif; margin: 20px;">
      You can now close this tab. If it doesn't close automatically, please close it manually.
    </p>
    """
    return Response(html, mimetype="text/html")


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
	
@bp.route("/results", methods=["GET"])
def results():
    """
    List campaign events with optional filter by campaign_id.
    Show summary: delivered, clicked, reported totals.
    """
    # dropdown options
    campaigns = Campaign.query.order_by(Campaign.id.desc()).all()

    # filter
    campaign_id = request.args.get("campaign_id", type=int)

    # base query with joins (to show recipient email and campaign name)
    query = (
        Event.query
        .join(Campaign, Campaign.id == Event.campaign_id)
        .join(Recipient, Recipient.id == Event.recipient_id)
        .add_columns(
            Event.id.label("event_id"),
            Event.event_type,
            Event.ip,
            Event.ts,
            Campaign.id.label("cid"),
            Campaign.name.label("campaign_name"),
            Recipient.email.label("recipient_email"),
        )
    )

    if campaign_id:
        query = query.filter(Event.campaign_id == campaign_id)

    events = query.order_by(Event.id.desc()).all()

    # summary stats
    base_count = db.session.query(func.count(Event.id))
    if campaign_id:
        base_count = base_count.filter(Event.campaign_id == campaign_id)

    total_delivered = base_count.filter(Event.event_type == "delivered").scalar()
    total_clicked   = base_count.filter(Event.event_type == "clicked").scalar()
    total_reported  = base_count.filter(Event.event_type == "reported").scalar()

    return render_template(
        "results.html",
        title="Results",
        campaigns=campaigns,
        campaign_id=campaign_id,
        events=events,
        total_delivered=total_delivered or 0,
        total_clicked=total_clicked or 0,
        total_reported=total_reported or 0,
    )


@bp.route("/results.csv", methods=["GET"])
def results_csv():
    """
    Download events as CSV; supports ?campaign_id=<id> filter (same as /results).
    """
    import csv, io

    campaign_id = request.args.get("campaign_id", type=int)

    query = (
        Event.query
        .join(Campaign, Campaign.id == Event.campaign_id)
        .join(Recipient, Recipient.id == Event.recipient_id)
        .add_columns(
            Event.id.label("event_id"),
            Campaign.id.label("cid"),
            Campaign.name.label("campaign_name"),
            Recipient.email.label("recipient_email"),
            Event.event_type,
            Event.ip,
            Event.ts,
        )
    )
    if campaign_id:
        query = query.filter(Event.campaign_id == campaign_id)

    rows = query.order_by(Event.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["event_id", "campaign_id", "campaign_name", "recipient_email", "event_type", "ip", "timestamp"])

    for r in rows:
        writer.writerow([r.event_id, r.cid, r.campaign_name, r.recipient_email, r.event_type, r.ip or "", r.ts])

    csv_bytes = output.getvalue()
    output.close()

    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=clicksafe_events.csv"}
    )

@bp.post("/results/delete")
def delete_campaigns():
    """
    Delete selected campaigns (and their events).
    If 'ALL' is present, delete ALL campaigns and events.
    """
    ids = request.form.getlist("campaign_ids")  # list[str]
    if not ids:
        flash("No campaigns selected for deletion.", "warning")
        return redirect(url_for("main.results"))

    try:
        if "ALL" in ids:
            # delete all events first (avoid FK constraint), then campaigns
            Event.query.delete(synchronize_session=False)
            Campaign.query.delete(synchronize_session=False)
        else:
            int_ids = [int(x) for x in ids if x.isdigit()]
            if int_ids:
                Event.query.filter(Event.campaign_id.in_(int_ids)) \
                           .delete(synchronize_session=False)
                Campaign.query.filter(Campaign.id.in_(int_ids)) \
                              .delete(synchronize_session=False)
        db.session.commit()
        flash("Campaign(s) deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("main.results"))
    
@bp.route("/preview/<template>")
def preview_template(template):
    return render_template(f"email/{template}.html",
                           tracking_url="#", report_url="#",
                           recipient=None, campaign=None)


	

