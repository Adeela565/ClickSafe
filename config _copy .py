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

    # ==== SMTP / Email Settings ====
    # These allow ClickSafe to send real emails through Gmail, Outlook,
    # Mailtrap, or a corporate SMTP server — depending on your .env values.

    SMTP_HOST = os.getenv("SMTP_HOST", "sandbox.smtp.mailtrap.io")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 2525))

    # True/False toggle for TLS
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    # Credentials (can be empty for servers that allow unauthenticated sending)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

    # From address + display name seen by the recipient
    SMTP_FROM_ADDR = os.getenv("SMTP_FROM_ADDR", "clicksafe@example.com")
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "ClickSafe Simulation")

    # ==== Optional Future Expansions ====
    # (For scaling or enterprise deployments — safe to ignore for now)
    # RATE_LIMIT = os.getenv("RATE_LIMIT", "100/hour")
    # LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

