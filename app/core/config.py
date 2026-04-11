"""Application configuration using Pydantic Settings."""

import secrets
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Multando API"
    APP_ENV: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/multando"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security — no default secret; must be set via env var in production
    SECRET_KEY: str = secrets.token_urlsafe(64)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    # CORS — configurable via env var
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # AWS S3 / MinIO (for evidence uploads)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""  # MinIO endpoint (e.g. https://minio.example.com)
    S3_BUCKET: str = "multando-evidence"
    STORAGE_BASE_URL: str = "https://storage.multando.com"

    # OAuth Providers
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # Service accounts
    CHATBOT_API_KEY: str = ""  # API key for chatbot service-to-service auth

    # WhatsApp Cloud API
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "multando-verify"
    WHATSAPP_API_VERSION: str = "v18.0"
    WHATSAPP_APP_SECRET: str = ""  # For webhook signature verification

    # Anthropic (Claude AI chatbot)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Custodial Wallet Encryption
    WALLET_MASTER_KEY: str = ""  # Fernet key for dev; leave empty to auto-generate
    AWS_KMS_KEY_ID: str = ""  # KMS key ARN for production
    WALLET_ENCRYPTION_PROVIDER: str = "local"  # "local" or "kms"

    # Solana blockchain
    SOLANA_RPC_URL: str = "https://api.devnet.solana.com"
    SOLANA_PROGRAM_ID: str = ""
    SOLANA_MINT_ADDRESS: str = ""
    SOLANA_REWARD_AUTHORITY_KEY: str = ""  # Base58 encoded private key
    SOLANA_NETWORK: str = "devnet"  # devnet | testnet | mainnet-beta

    # RECORD (Ministerio de Transporte) Integration
    TWOCAPTCHA_API_KEY: str = ""
    RECORD_ENABLED: bool = False  # Enable RECORD auto-submission

    # Withdrawal Limits
    WITHDRAWAL_DAILY_LIMIT: float = 100.0
    WITHDRAWAL_MONTHLY_LIMIT: float = 1000.0
    WITHDRAWAL_VERIFICATION_THRESHOLD: float = 50.0
    WITHDRAWAL_FEE: float = 0.5
    WITHDRAWAL_COOLDOWN_HOURS: int = 24

    # Hot Wallet
    HOT_WALLET_KEYPAIR_PATH: str = ""
    HOT_WALLET_MIN_BALANCE: float = 1000.0

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> str:
        """Ensure DATABASE_URL uses asyncpg driver."""
        if isinstance(v, str):
            if v.startswith("postgresql://") and "+asyncpg" not in v:
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Warn if SECRET_KEY is too short."""
        if len(v) < 32:
            import warnings
            warnings.warn(
                "SECRET_KEY is shorter than 32 characters. "
                "Set a strong SECRET_KEY via environment variable for production.",
                stacklevel=2,
            )
        return v

    @property
    def database_url_sync(self) -> str:
        """Return synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("+asyncpg", "")

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
