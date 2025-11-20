import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

# Read SMTP settings from environment (so any provider can be used)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "True").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
    "on",
)

SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

SMTP_FROM_ADDR = os.getenv("SMTP_FROM_ADDR", SMTP_USERNAME or "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "ClickSafe Alerts")


def send_email(to_addr: str, subject: str, html_body: str, text_body: str | None = None):
    """
    Send an email via the configured SMTP server.

    - to_addr: recipient email address (string)
    - subject: email subject
    - html_body: HTML content for the email
    - text_body: optional plain-text fallback; if None, a default message is used
    """
    if text_body is None:
        text_body = (
            "This is an HTML email. Please open it in an HTML-capable mail client."
        )

    # Build MIME message
    msg = MIMEMultipart("alternative")
    from_header = (
        f"{SMTP_FROM_NAME} <{SMTP_FROM_ADDR}>" if SMTP_FROM_NAME else SMTP_FROM_ADDR
    )

    msg["From"] = from_header
    msg["To"] = to_addr
    msg["Subject"] = subject

    # Attach plain-text and HTML parts
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Send via SMTP
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        if SMTP_USE_TLS:
            s.ehlo()
            s.starttls()
            s.ehlo()

        if SMTP_USERNAME and SMTP_PASSWORD:
            s.login(SMTP_USERNAME, SMTP_PASSWORD)

        s.sendmail(SMTP_FROM_ADDR, [to_addr], msg.as_string())

