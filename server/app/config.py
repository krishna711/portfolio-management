import os
from pathlib import Path
from typing import List


def _default_sqlite_url() -> str:
    # Default DB file: <repo>/server/portfolio.db
    base = Path(__file__).resolve().parents[1]
    db_path = base / "portfolio.db"
    # SQLAlchemy expects sqlite:///C:/... on Windows (forward slashes)
    db_str = str(db_path).replace("\\", "/")
    return f"sqlite:///{db_str}"


class Settings:
    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "Portfolio Management API")
        self.secret_key: str = os.getenv("SECRET_KEY", "change-me")
        self.algorithm: str = os.getenv("ALGORITHM", "HS256")
        self.access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "43200"))
        self.database_url: str = os.getenv("DATABASE_URL", _default_sqlite_url())
        self.enable_internal_scheduler: bool = os.getenv("ENABLE_INTERNAL_SCHEDULER", "0") == "1"
        self.dashboard_warm_time: str = os.getenv("DASHBOARD_WARM_TIME", "16:05")
        self.scanners_warm_time: str = os.getenv("SCANNERS_WARM_TIME", "17:05")
        self.ipo_metrics_warm_time: str = os.getenv("IPO_METRICS_WARM_TIME", "16:30")
        self.smtp_host: str = os.getenv("SMTP_HOST", "smtp.resend.com")
        self.smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user: str = os.getenv("SMTP_USER", "resend")
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from: str = os.getenv("SMTP_FROM", "noreply@yotek.net")
        self.smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "1") == "1"
        cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        self.cors_origins: List[str] = [o.strip() for o in cors_origins_str.split(",") if o.strip()]


settings = Settings()
