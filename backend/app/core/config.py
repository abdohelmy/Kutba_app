from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GLOSSARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "islamic_khutbah_649_verified_variations_contexts.csv"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KHUTBA_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Khutba API"
    api_prefix: str = "/api/v1"
    secret_key: str = "dev-only-change-me-before-production-123456"
    database_url: str = "sqlite:///./khutba.db"
    storage_dir: Path = Path("./data")
    glossary_path: Path = DEFAULT_GLOSSARY_PATH
    access_token_minutes: int = 60
    mosque_registration_password: SecretStr = SecretStr("01082025")
    max_document_bytes: int = 15 * 1024 * 1024
    ocr_enabled: bool = True
    pdftoppm_command: str = "pdftoppm"
    tesseract_command: str = "tesseract"
    ocr_languages: str = "ara"
    ocr_dpi: int = Field(default=300, ge=150, le=400)
    max_ocr_pages: int = Field(default=30, ge=1, le=100)
    ocr_timeout_seconds: int = Field(default=120, ge=10, le=600)
    ocr_page_segmentation_mode: int = Field(default=3, ge=1, le=13)

    canonical_sources_enabled: bool = True
    canonical_source_timeout_seconds: int = Field(default=30, ge=5, le=120)
    quran_api_mode: str = Field(default="legacy", pattern="^(legacy|oauth)$")
    quran_legacy_api_base_url: str = "https://api.quran.com/api/v4"
    quran_translation_id: int = Field(default=20, ge=1)
    quran_transliteration_id: int = Field(default=57, ge=1)
    quran_foundation_environment: str = Field(
        default="production", pattern="^(prelive|production)$"
    )
    quran_foundation_client_id: str | None = None
    quran_foundation_client_secret: str | None = None
    sunnah_api_base_url: str = "https://api.sunnah.com/v1"
    sunnah_api_key: str | None = None
    sunnah_web_search_fallback_enabled: bool = True
    sunnah_web_search_concurrency: int = Field(default=3, ge=1, le=8)

    translation_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    verifier_model: str | None = None
    openai_base_url: str | None = None
    reasoning_effort: str = Field(default="high", pattern="^(none|low|medium|high|xhigh|max)$")

    @model_validator(mode="after")
    def validate_provider(self) -> "Settings":
        supported = {"openai", "openai_compatible", "mock"}
        if self.translation_provider not in supported:
            raise ValueError(f"translation_provider must be one of {sorted(supported)}")
        if self.translation_provider == "openai" and not self.openai_api_key:
            # Startup remains possible for local development; a translation request fails clearly.
            return self
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
