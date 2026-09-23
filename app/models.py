"""Публичные контракты API и явный адаптер старой формы."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.config import DATE_MIN, DATE_MAX


class RecommendRequest(BaseModel):
    """Новый контракт: бюджет положительный, пожелания не являются фильтром."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    city: str = Field(min_length=1, max_length=80)
    date: date
    event_type: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    budget_kzt: int = Field(gt=0, le=1_000_000_000)
    duration_hours: float | None = Field(default=None, gt=0, le=100)
    language: str | None = Field(default=None, min_length=1, max_length=50)
    wishes: str | None = Field(default=None, max_length=1000)

    @field_validator('date')
    @classmethod
    def calendar_window(cls, value: date) -> date:
        """За пределами календаря доступность неизвестна, а не свободна."""
        if not DATE_MIN <= value <= DATE_MAX:
            raise ValueError('Дата должна быть с 23.09.2026 по 31.12.2026')
        return value

    @field_validator('wishes')
    @classmethod
    def normalize_wishes(cls, value: str | None) -> str | None:
        """Пустые пожелания равнозначны отсутствующим."""
        return ' '.join(value.split()) or None if value is not None else None


class LegacyRequest(RecommendRequest):
    """Только старый web-клиент может прислать нулевой бюджет для пустого демо."""

    event_type: str = Field(alias='event_format', min_length=1, max_length=80)
    budget_kzt: int = Field(alias='budget', ge=0, le=1_000_000_000)


class Fact(BaseModel):
    """Проверяемое утверждение, вычисленное кодом, не моделью."""
    type: str
    text: str


class Card(BaseModel):
    """Один отобранный подрядчик с происхождением данных."""
    rank: int
    id: str
    name: str
    category: str
    categories: list[str]
    city: str
    price_from_kzt: int
    price_imputed: bool
    city_imputed: bool
    synthetic: bool
    languages: list[str]
    max_hours: float | None
    explanation: str = ''
    facts: list[Fact]
    explanation_source: Literal['llm', 'template'] = 'template'
    profile_excerpt: str = ''


class Funnel(BaseModel):
    """Один последовательный шаг: причины отсева не пересекаются."""
    step: str
    label: str
    before: int
    after: int
    rejected_ids: list[str]


class RecommendResponse(BaseModel):
    """Канонический ответ; elapsed_ms не участвует в сравнении детерминизма."""
    status: Literal['found', 'no_category', 'all_filtered']
    message: str
    cards: list[Card]
    shortfall_reason: str | None
    funnel: list[Funnel]
    hints: list[str]
    elapsed_ms: int
