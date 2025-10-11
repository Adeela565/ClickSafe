import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "ClickSafe <no-reply@clicksafe.local>")

def send_email(to_addr: str, subject: str, html_body: str, text_body: str | None = None):
	if text_body is None:
		text_body = "This is an HTML email. Please use an HTML-capable client."

	msg = MIMEMultipart("alternative")
	msg["From"] = SMTP_FROM
	msg["To"] = to_addr
	msg["Subject"] = subject
	msg.attach(MIMEText(text_body, "plain"))
	msg.attach(MIMEText(html_body, "html"))

	# STARTTLS ON 587
	with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
		s.ehlo()
		s.starttls()
		s.ehlo()
		if SMTP_USER and SMTP_PASS:
			s.login(SMTP_USER, SMTP_PASS)
		s.sendmail(SMTP_FROM, [to_addr], msg.as_string())
