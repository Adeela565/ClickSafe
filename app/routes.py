from flask import Blueprint, render_template, request, redirect, url_for, Response, abort, flash, current_app, session
from functools import wraps
from sqlalchemy import func
from .db import db
from .models import Recipient, Campaign, Event, Department
from .emailer import send_email
from datetime import datetime
from flask import current_app
import random
import csv
import io

# Subject lines for each email template
TEMPLATE_SUBJECTS = {
    "microsoft_unusual_signin": "Microsoft account unusual sign-in activity",
    "rbc_password_disabled": "RBC: Your password has been disabled",
    "payroll_update": "Payroll update – action required",
    "delivery_notice": "Delivery notice – we couldn’t deliver your package",
    "vpn_mfa_notice": "VPN & MFA security notice",
}

# Reverse lookup: subject -> template key
SUBJECT_TO_TEMPLATE = {v: k for k, v in TEMPLATE_SUBJECTS.items()}

# Map each template key to its feedback HTML file
FEEDBACK_TEMPLATES = {
    "microsoft_unusual_signin": "feedback_microsoft_unusual_signin.html",
    "rbc_password_disabled": "feedback_rbc_password_disabled.html",
    "payroll_update": "feedback_payroll_update.html",
    "delivery_notice": "feedback_delivery_notice.html",
    "vpn_mfa_notice": "feedback_vpn_mfa_notice.html",
}

# Friendly display names for use in the campaign name
TEMPLATE_DISPLAY_NAMES = {
    "microsoft_unusual_signin": "Microsoft Sign-in Alert",
    "rbc_password_disabled": "RBC Password Disabled",
    "payroll_update": "Payroll Update",
    "delivery_notice": "Delivery Notice",
    "vpn_mfa_notice": "VPN & MFA Notice",
}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

bp = Blueprint("main", __name__)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        cfg = current_app.config
        if (username == cfg["ADMIN_USERNAME"]
                and password == cfg["ADMIN_PASSWORD"]):
            session["logged_in"] = True
            flash("Logged in successfully.", "success")
            next_url = request.args.get("next") or url_for("main.send_campaign")
            return redirect(next_url)

        flash("Invalid username or password.", "danger")

    return render_template("login.html", title="Admin Login")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))



@bp.route("/send", methods=["GET", "POST"])
@login_required
def send_campaign():
    if request.method == "GET":
        # Load departments with recipient counts
        departments = (
            Department.query.outerjoin(Recipient)
            .add_columns(
                Department.id,
                Department.name,
                db.func.count(Recipient.id).label("num_recipients"),
            )
            .group_by(Department.id)
            .order_by(Department.name.asc())
            .all()
        )
        return render_template(
            "send.html",
            title="Launch Campaign",
            departments=departments,
        )

    # ---------- POST: create campaign, send emails, record 'delivered' ---------- #

    # Which template was selected in the dropdown
    template_key = request.form.get("email_template", "").strip()

    # Subject line is driven by the template
    subject = TEMPLATE_SUBJECTS.get(template_key, "Phishing Simulation")

    # 1) Create campaign with a temporary name so we can get an ID
    campaign = Campaign(name="(pending name)", subject=subject)
    db.session.add(campaign)
    db.session.commit()  # campaign.id now exists

    # 2) Auto-generate a friendly campaign name based on ID + template
    display_name = TEMPLATE_DISPLAY_NAMES.get(template_key, subject)
    campaign.name = f"Campaign #{campaign.id} – {display_name}"
    db.session.commit()

    # ---------- Resolve recipients ---------- #
    use_all = request.form.get("use_all") == "on"
    if use_all:
        send_to = Recipient.query.filter(
            Recipient.department_id.isnot(None)
        ).all()
    else:
        selected_dept_ids = request.form.getlist("departments")  # list of strings
        if not selected_dept_ids:
            flash("Please select at least one department", "warning")
            return redirect(url_for("main.send_campaign"))

        send_to = Recipient.query.filter(
            Recipient.department_id.in_(selected_dept_ids)
        ).all()

    sent_count = 0
    base = request.url_root.rstrip("/")

    # Use the same key for picking the email template file
    tmpl = current_app.jinja_env.get_template(f"email/{template_key}.html")

    for r in send_to:
        tracking_url = f"{base}/l/{campaign.id}/{r.id}"
        report_url   = f"{base}/r/{campaign.id}/{r.id}"

        # Optional realistic fields
        date     = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
        country  = random.choice(["Russia", "Canada", "USA", "Mexico", "India", "China"])
        platform = random.choice(["Windows 10", "Windows 11", "macOS 12"])
        browser  = random.choice(["Chrome", "Firefox", "Edge"])

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
            ip=ip,
        )

        # Send & record 'delivered'
        send_email(r.email, subject, body_for_recipient)
        db.session.add(
            Event(
                campaign_id=campaign.id,
                recipient_id=r.id,
                event_type="delivered",
            )
        )
        sent_count += 1

    db.session.commit()
    recipients_sent = send_to

    return render_template(
        "send_done.html",
        title="Campaign Sent",
        campaign=campaign,
        sent=sent_count,
        recipients=recipients_sent,
    )

	

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
	
@bp.route("/feedback", methods=["GET"])
def feedback():
    cid = request.args.get("cid", type=int)
    rid = request.args.get("rid", type=int)

    if not cid or not rid:
        abort(404)

    campaign = Campaign.query.get_or_404(cid)
    recipient = Recipient.query.get_or_404(rid)

    # Determine which phishing template was used, based on subject
    template_key = SUBJECT_TO_TEMPLATE.get(campaign.subject)

    # Choose the correct feedback page
    if template_key and template_key in FEEDBACK_TEMPLATES:
        feedback_template = FEEDBACK_TEMPLATES[template_key]
    else:
        # If subject doesn't match anything → send generic feedback
        feedback_template = "feedback.html"

    return render_template(
        feedback_template,
        title="Phishing Simulation Feedback",
        campaign=campaign,
        recipient=recipient,
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
    # Dropdown options
    campaigns = Campaign.query.order_by(Campaign.id.desc()).all()

    # Filter (campaign_id from query string, e.g. /results?campaign_id=3)
    campaign_id = request.args.get("campaign_id", type=int)

    # ---- Base query for the table (JOINs so we can show campaign name & recipient email)
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
            Recipient.id.label("recipient_id"),
            Recipient.email.label("recipient_email"),
        )
    )

    # Only show CLICKED + REPORTED events in the bottom table
    query = query.filter(Event.event_type.in_(["clicked", "reported"]))

    if campaign_id:
        query = query.filter(Event.campaign_id == campaign_id)

    events = query.order_by(Event.id.desc()).all()

    # ---- Summary stats (these still look at ALL events, including delivered)
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
                           

@bp.route("/departments", methods=["GET", "POST"])
def manage_departments():
    # Handle "Add department"
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            # avoid duplicates
            existing = Department.query.filter(
                db.func.lower(Department.name) == name.lower()
            ).first()
            if existing:
                flash("That department already exists.", "warning")
            else:
                db.session.add(Department(name=name))
                db.session.commit()
                flash(f"Department '{name}' added.", "success")
        else:
            flash("Department name cannot be empty.", "danger")
        return redirect(url_for("main.manage_departments"))

    # For GET: load departments and recipient counts
    departments = Department.query.order_by(Department.name.asc()).all()
    recipient_counts = {
        d.id: Recipient.query.filter_by(department_id=d.id).count()
        for d in departments
    }

    return render_template(
        "departments.html",
        title="Manage Departments",
        departments=departments,
        recipient_counts=recipient_counts,
    )

	
@bp.route("/departments/<int:dept_id>/recipients", methods=["GET", "POST"])
def manage_department_recipients(dept_id):
    department = Department.query.get_or_404(dept_id)

    if request.method == "POST":
     
        # 1) CSV UPLOAD: bulk add recipients (Name + Email only)
        upload_file = request.files.get("upload_file")
        if upload_file and upload_file.filename:
            added = 0

            def add_recipient_from_row(name_val: str, email_val: str):
                nonlocal added
                name_val = (name_val or "").strip()
                email_val = (email_val or "").strip()

                # Skip completely empty lines
                if not email_val:
                    return

                # Skip header-like row (e.g., "email" without @)
                if "email" in email_val.lower() and "@" not in email_val:
                    return

                # Look up by email; create if needed
                existing = Recipient.query.filter_by(email=email_val).first()
                if existing is None:
                    existing = Recipient(name=name_val or None, email=email_val)
                    db.session.add(existing)
                    db.session.flush()  # ensure existing.id is set

                # Attach to department if not already linked
                if existing not in department.recipients:
                    department.recipients.append(existing)
                    added += 1

            # Read CSV as UTF-8 (handles BOM with utf-8-sig)
            stream = io.StringIO(
                upload_file.stream.read().decode("utf-8-sig"),
                newline=""
            )
            reader = csv.reader(stream)

            for row in reader:
                if not row:
                    continue
                # Expecting: [Name, Email]
                name_val = row[0] if len(row) > 0 else ""
                email_val = row[1] if len(row) > 1 else ""
                add_recipient_from_row(name_val, email_val)

            db.session.commit()
            flash(f"Imported {added} recipient(s) into {department.name}.", "success")
            return redirect(url_for("main.manage_department_recipients", dept_id=dept_id))

        
        # 2) SINGLE RECIPIENT ADD
      
        name = request.form.get("name", "").strip() or None
        email = request.form.get("email", "").strip()

        if email:
            recipient = Recipient.query.filter_by(email=email).first()
            if recipient is None:
                recipient = Recipient(name=name, email=email)
                db.session.add(recipient)
                db.session.flush()

            if recipient not in department.recipients:
                department.recipients.append(recipient)
                db.session.commit()
                flash("Recipient added.", "success")
            else:
                flash("Recipient is already in this department.", "info")
        else:
            flash("Email is required.", "warning")

        return redirect(url_for("main.manage_department_recipients", dept_id=dept_id))

   
    # GET – show recipients for this department
  
    recipients = (
        department.recipients.order_by(Recipient.email.asc())
        if hasattr(department.recipients, "order_by")
        else sorted(department.recipients, key=lambda r: r.email.lower())
    )

    return render_template(
        "department_recipients.html",
        department=department,
        recipients=recipients,
    )

	
@bp.route("/departments/<int:dept_id>/recipients/<int:rid>/delete", methods=["POST"])
def delete_department_recipient(dept_id, rid):
	dept = Department.query.get_or_404(dept_id)
	r = Recipient.query.get_or_404(rid)
	if r.department_id == dept.id:
		db.session.delete(r)
		db.session.commit()
		flash("Recipient removed", "success")
	return redirect(url_for("main.manage_department_recipients", dept_id=dept_id))
	
@bp.route("/departments/<int:dept_id>/delete", methods=["POST"])
def delete_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    # Optional: clear department_id for recipients first
    for r in dept.recipients:
        r.department_id = None
    db.session.delete(dept)
    db.session.commit()
    flash("Department deleted.", "success")
    return redirect(url_for("main.manage_departments"))
    
@bp.route("/departments/<int:dept_id>/recipients/<int:rid>/edit",
          methods=["GET", "POST"])
def edit_department_recipient(dept_id: int, rid: int):
    # Get department and recipient, or 404 if not found
    department = Department.query.get_or_404(dept_id)
    recipient = Recipient.query.get_or_404(rid)

    # Optional safety check: make sure this recipient belongs to this department
    if recipient.department_id != department.id:
        abort(404)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()

        # Very simple validation – you can improve this later
        if not email:
            flash("Email is required.", "error")
            return redirect(
                url_for("main.edit_department_recipient",
                        dept_id=dept_id, rid=rid)
            )

        # Update in-place – ID stays the same
        recipient.name = name or None
        recipient.email = email

        db.session.commit()
        flash("Recipient updated successfully.", "success")

        return redirect(
            url_for("main.manage_department_recipients", dept_id=dept_id)
        )

    # GET: show edit form
    return render_template(
        "edit_recipient.html",
        department=department,
        recipient=recipient,
        title="Edit Recipient",
    )

@bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    # 1) Click rate over time (by date)
    click_rows = (
        db.session.query(
            func.date(Event.ts).label("day"),
            func.count(Event.id).label("clicks"),
        )
        .filter(Event.event_type == "clicked")
        .group_by(func.date(Event.ts))
        .order_by(func.date(Event.ts))
        .all()
    )
    click_labels = [r.day.strftime("%Y-%m-%d") for r in click_rows]
    click_values = [r.clicks for r in click_rows]

    # 2) Report rate per campaign (reported vs delivered)
    delivered_rows = (
        db.session.query(
            Campaign.id,
            Campaign.name,
            func.count(Event.id).label("delivered"),
        )
        .join(Event, Event.campaign_id == Campaign.id)
        .filter(Event.event_type == "delivered")
        .group_by(Campaign.id)
        .all()
    )

    reported_rows = (
        db.session.query(
            Campaign.id,
            Campaign.name,
            func.count(Event.id).label("reported"),
        )
        .join(Event, Event.campaign_id == Campaign.id)
        .filter(Event.event_type == "reported")
        .group_by(Campaign.id)
        .all()
    )

    # Map campaign_id -> {name, delivered, reported}
    camp_stats = {}
    for row in delivered_rows:
        camp_stats[row.id] = {
            "name": row.name,
            "delivered": row.delivered,
            "reported": 0,
        }
    for row in reported_rows:
        camp_stats.setdefault(row.id, {"name": row.name, "delivered": 0, "reported": 0})
        camp_stats[row.id]["reported"] = row.reported

    camp_labels = [v["name"] for v in camp_stats.values()]
    camp_delivered = [v["delivered"] for v in camp_stats.values()]
    camp_reported = [v["reported"] for v in camp_stats.values()]

    # 3) Department risk (clicked events by department)
    dept_rows = (
        db.session.query(
            Department.name.label("dept_name"),
            func.count(Event.id).label("clicks"),
        )
        .join(Recipient, Recipient.department_id == Department.id)
        .join(Event, Event.recipient_id == Recipient.id)
        .filter(Event.event_type == "clicked")
        .group_by(Department.id)
        .order_by(Department.name)
        .all()
    )
    dept_labels = [r.dept_name for r in dept_rows]
    dept_clicks = [r.clicks for r in dept_rows]

    return render_template(
        "dashboard.html",
        title="Dashboard",
        click_labels=click_labels,
        click_values=click_values,
        camp_labels=camp_labels,
        camp_delivered=camp_delivered,
        camp_reported=camp_reported,
        dept_labels=dept_labels,
        dept_clicks=dept_clicks,
    )

@bp.route("/recipients/<int:rid>/history", methods=["GET"])
@login_required
def recipient_history(rid: int):
    recipient = Recipient.query.get_or_404(rid)

    # All events for this recipient with campaign info
    base_query = (
        db.session.query(
            Event,
            Campaign.name.label("campaign_name"),
        )
        .join(Campaign, Campaign.id == Event.campaign_id)
        .filter(Event.recipient_id == rid)
    )
    
    rows_all = base_query.order_by(Event.ts.desc()).all()
    

    total_clicked = sum(1 for e, _ in rows_all if e.event_type == "clicked")
    total_reported = sum(1 for e, _ in rows_all if e.event_type == "reported")
    total_delivered = sum(1 for e, _ in rows_all if e.event_type == "delivered")

    campaigns_seen = sorted({campaign_name for _, campaign_name in rows_all})
    
    event_types = sorted({e.event_type for e, _ in rows_all})
    selected_type = (request.args.get("event_type") or "").strip()
    
    if selected_type:
    	rows = [row for row in rows_all if row[0].event_type == selected_type]
    else:
    	rows = rows_all

    return render_template(
        "recipient_history.html",
        title=f"History for {recipient.name or recipient.email}",
        recipient=recipient,
        events=rows,
        total_clicked=total_clicked,
        total_reported=total_reported,
        total_delivered=total_delivered,
        campaigns_seen=campaigns_seen,
        event_types=event_types,
        event_type=selected_type,
    )





	

