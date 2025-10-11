from app import create_app
from app.emailer import send_email

app = create_app()
with app.app_context():
	to = input("Send test email to: ").strip()
	html = """<h3>ClickSafe test</h3><p>If you can read this, SMTP works </p>"""
	send_email(to, "ClickSafe SMTP test", html)
	print("Sent. Check the inbox (Mailtrap).")

