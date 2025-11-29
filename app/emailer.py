import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

# --- Mailtrap: used for test addresses like *@example.com --- #
MAILTRAP_HOST = os.getenv("MAILTRAP_HOST", "sandbox.smtp.mailtrap.io")
MAILTRAP_PORT = int(os.getenv("MAILTRAP_PORT", "2525"))
MAILTRAP_USERNAME = os.getenv("MAILTRAP_USERNAME")
MAILTRAP_PASSWORD = os.getenv("MAILTRAP_PASSWORD")
MAILTRAP_FROM_ADDR = os.getenv("MAILTRAP_FROM_ADDR", MAILTRAP_USERNAME or "")
MAILTRAP_FROM_NAME = os.getenv("MAILTRAP_FROM_NAME", "ClickSafe Test")

# --- Gmail: used for real addresses --- #
GMAIL_HOST = os.getenv("GMAIL_HOST", "smtp.gmail.com")
GMAIL_PORT = int(os.getenv("GMAIL_PORT", "587"))
GMAIL_USERNAME = os.getenv("GMAIL_USERNAME")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
GMAIL_FROM_ADDR = os.getenv("GMAIL_FROM_ADDR", GMAIL_USERNAME or "")
GMAIL_FROM_NAME = os.getenv("GMAIL_FROM_NAME", "ClickSafe Alerts")

def _send_via_smtp(host, port, username, password,
                   from_addr, from_name,
                   to_addr, subject, html_body, text_body: str | None = None):
    """
    Low-level helper: send a single HTML email via the given SMTP settings.
    """
    if text_body is None:
        text_body = "This is an HTML email. Please open it in an HTML-capable mail client."

    msg = MIMEMultipart("alternative")
    from_header = f"{from_name} <{from_addr}>" if from_name else from_addr

    msg["From"] = from_header
    msg["To"] = to_addr
    msg["Subject"] = subject

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(host, port, timeout=20) as s:
        s.ehlo()
        # Both Mailtrap and Gmail use TLS
        s.starttls()
        s.ehlo()

        if username and password:
            s.login(username, password)

        s.sendmail(from_addr, [to_addr], msg.as_string())

def send_email(to_addr: str, subject: str, html_body: str, text_body: str | None = None):
    """
    High-level send function used by the app.

    Routing logic:
    - If recipient ends with @example.com → send via Mailtrap
    - Otherwise → send via Gmail (real)
    """
    domain = to_addr.split("@")[-1].lower()

    if domain == "example.com":
        # Route to Mailtrap (test inbox)
        _send_via_smtp(
            host=MAILTRAP_HOST,
            port=MAILTRAP_PORT,
            username=MAILTRAP_USERNAME,
            password=MAILTRAP_PASSWORD,
            from_addr=MAILTRAP_FROM_ADDR,
            from_name=MAILTRAP_FROM_NAME,
            to_addr=to_addr,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    else:
        # Route to Gmail (real inbox)
        _send_via_smtp(
            host=GMAIL_HOST,
            port=GMAIL_PORT,
            username=GMAIL_USERNAME,
            password=GMAIL_PASSWORD,
            from_addr=GMAIL_FROM_ADDR,
            from_name=GMAIL_FROM_NAME,
            to_addr=to_addr,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

