from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


@dataclass(slots=True)
class Settings:
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    upload_dir: Path = field(default_factory=lambda: DATA_DIR / "uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    # Invoices at or above this confidence are approved automatically.
    auto_approve_threshold: int = 80
    page_size: int = 50

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            database_url=os.getenv("DATABASE_URL", defaults.database_url),
            upload_dir=Path(os.getenv("UPLOAD_DIR", str(defaults.upload_dir))),
            max_upload_bytes=int(float(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024),
            auto_approve_threshold=int(os.getenv("AUTO_APPROVE_THRESHOLD", "80")),
            page_size=int(os.getenv("PAGE_SIZE", "50")),
        )
