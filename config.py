import os
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()


class Config:
    """Base configuration for ClickSafe"""

    # ==== Security ====
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

    # ==== Database ====
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Mailtrap settings (for test / example.com) ---
    MAILTRAP_HOST = os.getenv("MAILTRAP_HOST", "sandbox.smtp.mailtrap.io")
    MAILTRAP_PORT = int(os.getenv("MAILTRAP_PORT", 2525))
    MAILTRAP_USERNAME = os.getenv("MAILTRAP_USERNAME")
    MAILTRAP_PASSWORD = os.getenv("MAILTRAP_PASSWORD")
    MAILTRAP_FROM_ADDR = os.getenv("MAILTRAP_FROM_ADDR", "clicksafe@example.com")
    MAILTRAP_FROM_NAME = os.getenv("MAILTRAP_FROM_NAME", "ClickSafe Test")

    # --- Gmail settings (for real recipients) ---
    GMAIL_HOST = os.getenv("GMAIL_HOST", "smtp.gmail.com")
    GMAIL_PORT = int(os.getenv("GMAIL_PORT", 587))
    GMAIL_USERNAME = os.getenv("GMAIL_USERNAME")
    GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
    GMAIL_FROM_ADDR = os.getenv("GMAIL_FROM_ADDR")
    GMAIL_FROM_NAME = os.getenv("GMAIL_FROM_NAME", "ClickSafe Alerts")

    # --- Admin login ---
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

