from app.core.config import Settings, get_settings
from app.services.providers.base import TranslationProvider
from app.services.providers.openai_provider import (
    MockProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
)


def build_provider(settings: Settings | None = None) -> TranslationProvider:
    settings = settings or get_settings()
    if settings.translation_provider == "mock":
        return MockProvider()
    if settings.translation_provider == "openai_compatible":
        if not settings.openai_base_url:
            raise RuntimeError("KHUTBA_OPENAI_BASE_URL is required for openai_compatible")
        return OpenAICompatibleProvider(
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            verifier_model=settings.verifier_model,
            api_key=settings.openai_api_key or "local",
        )
    if not settings.openai_api_key:
        raise RuntimeError("KHUTBA_OPENAI_API_KEY is not configured")
    return OpenAIResponsesProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        verifier_model=settings.verifier_model,
        reasoning_effort=settings.reasoning_effort,
    )
