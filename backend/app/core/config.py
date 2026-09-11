import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

# Values that have been published in this repository, shipped in .env.example, or are
# common throwaway placeholders. Any of them means the signing key is public knowledge,
# so tokens and OTP hashes derived from it are forgeable.
PUBLIC_JWT_SECRETS = frozenset(
    {
        "",
        "secret",
        "changeme",
        "change-this-secret",
        "replace_with_a_strong_random_secret",
        "bizxusai_live_2026_super_secure_key_948275193746",
    }
)

MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    app_name: str = "BizxusAI API"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    host: str = "0.0.0.0"
    port: int = 8000

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "bizxus_ai"

    jwt_secret_key: str = ""
    report_scheduler_enabled: bool = False
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    default_admin_full_name: str = ""
    default_admin_email: str = ""
    default_admin_phone: str = ""
    default_admin_password: str = ""

    bcrypt_rounds: int = 12

    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_persist_directory: str = "./chroma-data"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    whatsapp_provider: str = "mock"
    whatsapp_log_retention_days: int = 180
    whatsapp_verify_token: str = "bizxus-whatsapp-verify"
    backend_public_url: str = ""
    # Where the Baileys bridge serves its pairing pages. The dashboard turns this into a
    # per-business link the owner clicks to scan their QR, so it must be an address the
    # owner's browser can reach, not the address the API uses.
    whatsapp_bridge_public_url: str = "http://localhost:3005"
    # Shared secret the bridge presents to fetch the businesses it should connect. Without
    # it every new business needs a hand-edited bridge .env and a restart. It hands out
    # per-tenant bridge tokens, so it is operator infrastructure: leave it empty and the
    # discovery endpoint stays disabled.
    whatsapp_bridge_admin_key: str = ""

    sms_provider: str = "mock"
    sms_api_key: str = ""
    sms_http_url: str = ""
    sms_sender_id: str = "BizXusAI"

    otp_code_length: int = 6
    otp_expire_minutes: int = Field(default=10, validation_alias=AliasChoices("OTP_EXPIRE_MINUTES", "OTP_EXPIRY_MINUTES"))
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 30
    otp_demo_code: str = "123456"
    otp_demo_mode: bool = False
    otp_return_code_in_response: bool = True

    email_provider: str = "smtp"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "BizXusAI"

    frontend_base_url: str = "http://localhost:5173"
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_currency: str = "pkr"
    stripe_success_path: str = "/customer/orders/{orderId}?payment=stripe_success"
    stripe_cancel_path: str = "/customer/orders/{orderId}?payment=stripe_cancelled"

    # --- Pakistani payment gateways -------------------------------------------------
    # Both are hosted-checkout gateways: the customer is redirected to the gateway, pays,
    # and is returned to a callback that carries a signed result.
    #
    # `mode` selects where that redirect goes:
    #   simulator - a local page that mimics the gateway, so the whole flow is testable
    #               before merchant onboarding issues real credentials
    #   sandbox   - the gateway's own test environment
    #   live      - production
    # sandbox and live both require real credentials; without them the mode falls back to
    # the simulator rather than sending customers to a gateway that will reject them.
    jazzcash_mode: str = "simulator"
    jazzcash_merchant_id: str = ""
    jazzcash_password: str = ""
    jazzcash_integrity_salt: str = ""

    easypaisa_mode: str = "simulator"
    easypaisa_store_id: str = ""
    easypaisa_hash_key: str = ""
    easypaisa_account_number: str = ""

    # Where a gateway sends the customer back. Must be reachable by their browser, and by
    # the gateway's servers for server-to-server confirmations.
    payment_return_path: str = "/customer/orders/{orderId}?payment={status}"

    local_upload_dir: str = "./uploads"
    temp_upload_dir: str = "./uploads/temp"
    log_dir: str = "../logs"
    log_level: str = "INFO"
    backup_dir: str = "./backups"

    app_version: str = "0.32.0"
    build_label: str = "phase-32-critical-bug-fixes"
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 300
    # Daily ceiling on billed AI replies per tenant; 0 disables the cap.
    ai_daily_message_cap: int = 300

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"false", "0", "no", "off", "release", "production"}:
                return False
        return value

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value):
        normalized = str(value or "development").strip().lower()
        if normalized in {"dev", "development", "local"}:
            return "development"
        if normalized in {"test", "testing"}:
            return "test"
        if normalized in {"prod", "production", "release"}:
            return "production"
        return normalized

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value):
        normalized = str(value or "INFO").strip().upper()
        return normalized if normalized in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"

    @field_validator("jazzcash_mode", "easypaisa_mode", mode="before")
    @classmethod
    def normalize_gateway_mode(cls, value):
        normalized = str(value or "simulator").strip().lower()
        return normalized if normalized in {"simulator", "sandbox", "live"} else "simulator"

    @field_validator("whatsapp_provider", mode="before")
    @classmethod
    def normalize_whatsapp_provider(cls, value):
        normalized = str(value or "mock").strip().lower()
        return normalized if normalized in {"mock", "baileys"} else "mock"

    @field_validator("frontend_base_url", "backend_public_url", "whatsapp_bridge_public_url", mode="before")
    @classmethod
    def normalize_base_url(cls, value):
        return str(value or "").strip().rstrip("/")

    @field_validator("chroma_persist_directory", "local_upload_dir", "temp_upload_dir", "log_dir", "backup_dir", mode="after")
    @classmethod
    def resolve_data_path(cls, value: str) -> str:
        """Anchor data directories to the backend package, not the working directory.

        These defaulted to "./chroma-data" and friends, so starting the API from the repo
        root instead of backend/ silently created a second vector store and upload tree.
        Absolute paths in the environment are respected as-is.
        """
        path = Path(str(value or "").strip())
        if path.is_absolute():
            return str(path)
        backend_root = Path(__file__).resolve().parents[2]
        return str((backend_root / path).resolve())

    @property
    def jazzcash_configured(self) -> bool:
        return bool(self.jazzcash_merchant_id and self.jazzcash_password and self.jazzcash_integrity_salt)

    @property
    def easypaisa_configured(self) -> bool:
        return bool(self.easypaisa_store_id and self.easypaisa_hash_key)

    @property
    def effective_jazzcash_mode(self) -> str:
        """Never send a customer to a gateway that cannot accept the request."""
        if self.jazzcash_mode in {"sandbox", "live"} and not self.jazzcash_configured:
            return "simulator"
        return self.jazzcash_mode

    @property
    def effective_easypaisa_mode(self) -> str:
        if self.easypaisa_mode in {"sandbox", "live"} and not self.easypaisa_configured:
            return "simulator"
        return self.easypaisa_mode

    @property
    def jwt_secret_is_public(self) -> bool:
        """True when the signing key is a known placeholder or too short to be safe."""
        return self.jwt_secret_key in PUBLIC_JWT_SECRETS or len(self.jwt_secret_key) < MIN_JWT_SECRET_LENGTH

    @model_validator(mode="after")
    def enforce_production_safety(self):
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
            if self.jwt_secret_key in PUBLIC_JWT_SECRETS:
                raise ValueError(
                    "JWT_SECRET_KEY is a known placeholder value and is public. Generate a private one, "
                    "for example: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
            if len(self.jwt_secret_key) < MIN_JWT_SECRET_LENGTH:
                raise ValueError(f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters in production.")
            if self.bcrypt_rounds < 12:
                raise ValueError("BCRYPT_ROUNDS must be at least 12 in production.")
            for gateway in ("jazzcash", "easypaisa"):
                if getattr(self, f"{gateway}_mode") == "live" and not getattr(self, f"{gateway}_configured"):
                    raise ValueError(
                        f"{gateway.upper()} is set to live but its credentials are missing, so it would "
                        "silently fall back to the local payment simulator."
                    )
            if not self.stripe_webhook_secret and self.stripe_secret_key:
                raise ValueError("STRIPE_WEBHOOK_SECRET is required in production when Stripe is enabled.")
        return self


def warn_about_insecure_settings() -> None:
    """Log configuration that is tolerable locally but unsafe once reachable.

    Called from application startup rather than at import time, because settings are
    built before logging is configured and a warning emitted then would be discarded.
    """
    if settings.jwt_secret_is_public:
        logger.warning(
            "JWT_SECRET_KEY is a known placeholder or shorter than %s characters. Access tokens and OTP hashes "
            "signed with it can be forged by anyone who has this source. Rotate it with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"',
            MIN_JWT_SECRET_LENGTH,
        )
    if settings.stripe_secret_key and not settings.stripe_webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET is not set, so all Stripe webhooks will be rejected.")
    if settings.rate_limit_enabled is False:
        logger.info("Rate limiting is disabled. Public AI chat and order endpoints are unthrottled.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
