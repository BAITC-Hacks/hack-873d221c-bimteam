"""Проверяемые настройки; секреты читаются только из локального .env."""
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

ROOT = Path(__file__).resolve().parents[1]
DATE_MIN = date(2026, 9, 23)
DATE_MAX = date(2026, 12, 31)


class Settings(BaseSettings):
    """Пути относительно корня проекта, независимо от текущей директории."""

    model_config = SettingsConfigDict(env_file=ROOT / '.env', env_file_encoding='utf-8', extra='ignore')
    llm_provider: Literal['openai', 'nvidia', 'none'] = 'none'
    openai_api_key: SecretStr = SecretStr('')
    nvidia_api_key: SecretStr = SecretStr('')
    openai_model: str = ''
    nvidia_model: str = ''
    llm_timeout_s: float = Field(default=8, gt=0, le=8)
    llm_seed: int | None = None
    embedding_provider: Literal['openai', 'nvidia', 'none'] = 'none'
    embedding_model: str = ''
    embedding_timeout_s: float = Field(default=1, gt=0, le=1)
    data_path: Path = ROOT / 'data/contractors.csv'
    extra_data_path: Path = ROOT / 'data/contractors_extra.csv'
    embeddings_path: Path = ROOT / 'data/embeddings.npy'
    embeddings_ids_path: Path = ROOT / 'data/embeddings_ids.json'
    demo_path: Path = ROOT / 'data/demo_queries.json'
    cache_dir: Path = ROOT / 'cache'

    @classmethod
    def settings_customise_sources(cls, settings_cls: type[BaseSettings],
                                   init_settings: PydanticBaseSettingsSource,
                                   env_settings: PydanticBaseSettingsSource,
                                   dotenv_settings: PydanticBaseSettingsSource,
                                   file_secret_settings: PydanticBaseSettingsSource
                                   ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Не брать случайные API-ключи из окружения машины; init нужен для тестов."""
        return init_settings, dotenv_settings

    @field_validator('data_path', 'extra_data_path', 'embeddings_path',
                     'embeddings_ids_path', 'demo_path', 'cache_dir', mode='after')
    @classmethod
    def rooted_path(cls, value: Path) -> Path:
        """Разрешить пользовательский относительный путь от корня репозитория."""
        return value if value.is_absolute() else ROOT / value

    def api_key(self, provider: str) -> str:
        """Вернуть секрет только для создания SDK-клиента, не для журналирования."""
        return (self.openai_api_key if provider == 'openai' else self.nvidia_api_key).get_secret_value()

    @property
    def llm_model(self) -> str:
        """Модель выбранного провайдера; пустое имя означает шаблонный режим."""
        return self.openai_model if self.llm_provider == 'openai' else self.nvidia_model
