import os
import json
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Provider:
    name: str
    api_type: str  # "openai" or "anthropic"
    base_url: str
    api_key: str
    models: list[str] = field(default_factory=list)


class Config:
    TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
    DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "")
    ALLOWED_USER_IDS: list[int] | None = (
        [int(x) for x in os.environ["ALLOWED_USER_IDS"].split(",")]
        if os.environ.get("ALLOWED_USER_IDS")
        else None
    )
    DB_PATH: str = os.environ.get("DB_PATH", "/data/bot.db")
    STREAM_UPDATE_INTERVAL: float = float(
        os.environ.get("STREAM_UPDATE_INTERVAL", "1.0")
    )

    def __init__(self):
        self.providers: dict[str, Provider] = {}
        self._load_providers()

    def _load_providers(self):
        providers_json = os.environ.get("PROVIDERS")
        if providers_json:
            for p in json.loads(providers_json):
                provider = Provider(
                    name=p["name"],
                    api_type=p["api_type"],
                    base_url=p["base_url"],
                    api_key=p["api_key"],
                    models=p.get("models", []),
                )
                self.providers[provider.name] = provider

    def get_provider_for_model(self, model: str) -> Provider | None:
        for provider in self.providers.values():
            if model in provider.models:
                return provider
        return None

    @property
    def all_models(self) -> list[str]:
        models = []
        for provider in self.providers.values():
            models.extend(provider.models)
        return models


config = Config()
