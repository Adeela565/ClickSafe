import os
from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    """Helper: read boolean env vars like 'True' / 'false' / '1'."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


class Config:
    # Core app settings
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SMTP / email settings (provider-agnostic; works for Gmail, etc.)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USE_TLS = _bool_env("SMTP_USE_TLS", True)

    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

    SMTP_FROM_ADDR = os.getenv("SMTP_FROM_ADDR", SMTP_USERNAME or "")
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "ClickSafe Alerts")

