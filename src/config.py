"""Typed settings: config/<APP_ENV>.yaml, overridden by environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
VALID_ENVS = {"development", "testing", "production"}
MIN_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """The application cannot start safely with this configuration."""


@dataclass(frozen=True)
class Settings:
    environment: str
    random_seed: int
    raw_data_dir: Path
    model_dir: Path
    model_version: str
    database_url: str
    secret_key: str
    token_ttl_seconds: int
    cors_origins: tuple[str, ...]
    max_login_failures: int
    lockout_minutes: int
    max_body_bytes: int
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    allow_registration: bool = True
    s3_bucket: str = ""
    aws_region: str = ""
    upload_dir: Path | None = None
    max_upload_bytes: int = 5 * 1024 * 1024 + 1024

    @property
    def billing_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def billing_mode(self) -> str:
        if not self.billing_enabled:
            return "disabled"
        return "live" if self.razorpay_key_id.startswith("rzp_live_") else "test"

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production"

    def require_secret(self) -> None:
        if len(self.secret_key) < MIN_SECRET_LENGTH:
            raise ConfigError(
                "FLOWTOOL_SECRET_KEY must be set to at least "
                f"{MIN_SECRET_LENGTH} characters. Run: python -m scripts.seed"
            )


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_settings(environment: str | None = None) -> Settings:
    if environment != "testing" and os.environ.get("APP_ENV") != "testing":
        load_dotenv(ROOT / ".env", override=False)
    env = environment or os.environ.get("APP_ENV", "development")
    if env not in VALID_ENVS:
        raise ConfigError(f"APP_ENV must be one of {sorted(VALID_ENVS)}, got {env!r}.")

    with open(ROOT / "config" / f"{env}.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    paths, api, security = cfg["paths"], cfg["api"], cfg["security"]
    database = _resolve(paths["database"])
    origins = os.environ.get("FLOWTOOL_CORS_ORIGINS")
    cors = [o.strip() for o in origins.split(",") if o.strip()] if origins is not None \
        else api["cors_origins"]
    if "*" in cors:
        raise ConfigError("Wildcard CORS origins are not allowed.")

    return Settings(
        environment=env,
        random_seed=int(cfg["random_seed"]),
        raw_data_dir=_resolve(os.environ.get("DATA_DIR", paths["raw_data"])),
        model_dir=_resolve(os.environ.get("MODEL_DIR", paths["models"])),
        model_version=str(cfg["model"]["version"]),
        # `or` rather than a default: Compose passes unset variables as empty strings.
        database_url=os.environ.get("FLOWTOOL_DATABASE_URL") or f"sqlite:///{database.as_posix()}",
        secret_key=os.environ.get("FLOWTOOL_SECRET_KEY", ""),
        token_ttl_seconds=int(security["token_ttl_seconds"]),
        cors_origins=tuple(cors),
        max_login_failures=int(security["max_login_failures"]),
        lockout_minutes=int(security["lockout_minutes"]),
        max_body_bytes=int(api["max_body_bytes"]),
        razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", "").strip(),
        razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET", "").strip(),
        razorpay_webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip(),
        allow_registration=os.environ.get("FLOWTOOL_ALLOW_REGISTRATION", "true").lower() != "false",
        s3_bucket=os.environ.get("FLOWTOOL_S3_BUCKET", "").strip(),
        aws_region=(os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "").strip(),
        upload_dir=database.parent / "uploads",
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
