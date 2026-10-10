"""Runtime configuration, read once from the environment (and `.env` for local runs)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    # repr=False keeps secrets out of logs and tracebacks
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or None, repr=False)
    gemini_model: str | None = field(default_factory=lambda: os.getenv("GEMINI_MODEL") or None)
    groq_api_key: str | None = field(default_factory=lambda: os.getenv("GROQ_API_KEY") or None, repr=False)
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
    request_timeout_s: float = field(default_factory=lambda: float(os.getenv("VLM_TIMEOUT_S", "90")))

    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", ROOT / "cache")))
    samples_dir: Path = ROOT / "samples"

    max_upload_bytes: int = 12 * 1024 * 1024
    max_image_pixels: int = 40_000_000           # reject decompression bombs before decoding
    allowed_origins: list[str] = field(default_factory=_origins)
    allow_sample_upload: bool = field(default_factory=lambda: _flag("ALLOW_SAMPLE_UPLOAD", False))
    rate_limit_per_min: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MIN", "12")))


settings = Settings()
