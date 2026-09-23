"""Валидация доказательств, различимые шаблоны и один batch LLM с коррекцией."""
import asyncio
from itertools import permutations
import json
from pathlib import Path
import re

from openai import OpenAIError

from app.config import Settings
from app.llm import DiskCache, LLMClient, cache_key
from app.models import Card, RecommendRequest

PROMPT_VERSION = 'explain-v1-exact-facts'
PROMPT_DIR = Path(__file__).with_name('prompts')
SYSTEM_PROMPT = (PROMPT_DIR / 'explain_system.txt').read_text(encoding='utf-8')
BANNED_PHRASES = tuple((PROMPT_DIR / 'banned_phrases.txt').read_text(encoding='utf-8').splitlines())
CONNECTORS = {'и', 'а', 'но', 'также', 'при', 'этом', 'зато', 'кроме', 'того'}


def words(text: str) -> set[str]:
    """Слова без регистра/пунктуации; ё и е эквивалентны для проверки."""
    return set(re.findall(r'\w+', text.casefold().replace('ё', 'е')))


def jaccard(first: str, second: str) -> float:
    """Доля общих слов; две пустые строки считаются одинаковыми."""
    a, b = words(first), words(second)
    return len(a & b) / len(a | b) if a | b else 1


def numbers(text: str) -> set[str]:
    """Цена 700 000 — одно число; не теряем десятичные часы и состав дат."""
    joined = re.sub(r'(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))', '', text)
    return {n.replace(',', '.') for n in re.findall(r'\d+(?:[.,]\d+)*', joined)}


def _normalized(text: str) -> str:
    return ' '.join(re.findall(r'\w+', text.casefold().replace('ё', 'е')))


def validate_explanations(raw: str, cards: list[Card]) -> tuple[dict[str, str], dict[str, str]]:
    """Проверить ID, факты, числа, длину, общие фразы и сходство карточек.

    Консервативное правило: разрешены только целые факты и связки. Оно ловит
    ненумерические выдумки, которые одной проверкой чисел обнаружить нельзя.
    """
    identities = {card.id for card in cards}
    try:
        payload = json.loads(raw)
        rows = payload['explanations']
        if not isinstance(rows, list) or len(rows) != len(cards):
            raise ValueError
        if {row['id'] for row in rows} != identities or len({row['id'] for row in rows}) != len(rows):
            raise ValueError
        texts = {row['id']: row['text'] for row in rows}
        if any(not isinstance(text, str) for text in texts.values()):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        return {}, {identity: 'Нужен JSON с каждым id ровно один раз' for identity in sorted(identities)}
    errors = {}
    for card in cards:
        text = texts[card.id].strip()
        texts[card.id] = text
        norm = _normalized(text)
        if not text or len(text) > 280 or len(re.findall(r'[.!?](?:\s+|$)', text)) > 2:
            errors[card.id] = 'Нужно 1–2 предложения до 280 символов'
        elif any(_normalized(phrase) in norm for phrase in BANNED_PHRASES):
            errors[card.id] = 'Запрещённая общая фраза'
        elif not numbers(text) or not numbers(text) <= numbers(' '.join(f.text for f in card.facts)):
            errors[card.id] = 'Неизвестное число или отсутствует числовой факт'
        else:
            remaining = norm
            matched = set()
            for fact in sorted(card.facts, key=lambda f: -len(f.text)):
                evidence = _normalized(fact.text)
                if evidence and evidence in remaining:
                    matched.add(fact.type)
                    remaining = remaining.replace(evidence, ' ', 1)
            if len(matched) < 2 or not set(remaining.split()) <= CONNECTORS:
                errors[card.id] = 'Нужны минимум два целых факта без неподтверждённых добавлений'
    for i, card in enumerate(cards):
        for other in cards[:i]:
            if jaccard(texts[card.id], texts[other.id]) >= 0.5:
                errors[card.id] = errors[other.id] = 'Слишком похожие объяснения'
    return {key: text for key, text in texts.items() if key not in errors}, errors


def template_explanations(cards: list[Card], accepted: dict[str, str] | None = None) -> dict[str, str]:
    """Выбрать два наиболее отличающих факта, сохраняя числа и ограничение длины."""
    result = dict(accepted or {})
    for card in cards:
        if card.id in result:
            continue
        candidates = []
        for first, second in permutations(card.facts, 2):
            if first.type == second.type:
                continue
            text = first.text.rstrip('.!?') + '. ' + second.text.rstrip('.!?') + '.'
            if len(text) <= 280 and numbers(text) and not any(_normalized(p) in _normalized(text) for p in BANNED_PHRASES):
                similarity = max((jaccard(text, prev) for prev in result.values()), default=0)
                candidates.append((similarity, text))
                if similarity < 0.5:
                    break
        # Для реальных профилей всегда есть как минимум бюджет и дата.
        result[card.id] = next((text for similarity, text in candidates if similarity < 0.5),
                               min(candidates, key=lambda item: item[0])[1] if candidates else '')
    return result


class Explainer:
    """Повторный запрос возвращает сохранённый текст, включая fallback."""

    def __init__(self, settings: Settings, client: LLMClient) -> None:
        self.settings, self.client = settings, client
        self.cache = DiskCache(settings.cache_dir / 'llm')

    async def explain(self, req: RecommendRequest, cards: list[Card]) -> None:
        """Заполнить только explanation/source; состав и порядок не изменяются."""
        if not cards:
            return
        payload = {'request': req.model_dump(mode='json'), 'cards': [
            {'id': c.id, 'facts': [f.model_dump() for f in c.facts]} for c in cards]}
        key = cache_key([self.settings.llm_provider, self.settings.llm_model, self.settings.llm_seed,
                         PROMPT_VERSION, SYSTEM_PROMPT, BANNED_PHRASES, payload])
        async with self.cache.lock(key):
            cached = self.cache.get(key)
            if self._valid_cache(cached, cards):
                self._apply(cards, cached)
                return
            accepted: dict[str, str] = {}
            if self.client.available:
                async def generate() -> None:
                    nonlocal accepted
                    correction = None
                    for _ in range(2):
                        raw = await self.client.complete(SYSTEM_PROMPT, payload, correction)
                        valid, errors = validate_explanations(raw, cards)
                        # Не смешиваем взаимно непроверенные тексты разных попыток.
                        accepted = valid
                        if not errors:
                            return
                        correction = json.dumps(errors, ensure_ascii=False)
                try:
                    await asyncio.wait_for(generate(), timeout=self.settings.llm_timeout_s)
                except (OpenAIError, TimeoutError, OSError, ValueError, KeyError, TypeError, IndexError):
                    pass
            texts = template_explanations(cards, accepted)
            values = {c.id: {'text': texts[c.id], 'source': 'llm' if c.id in accepted else 'template'} for c in cards}
            self.cache.put(key, values)
            self._apply(cards, values)

    @staticmethod
    def _valid_cache(cached: object, cards: list[Card]) -> bool:
        if not isinstance(cached, dict) or set(cached) != {c.id for c in cards}:
            return False
        if any(not isinstance(v, dict) or v.get('source') not in ('llm', 'template') for v in cached.values()):
            return False
        raw = json.dumps({'explanations': [{'id': key, 'text': v.get('text')} for key, v in cached.items()]})
        _, errors = validate_explanations(raw, cards)
        return not errors

    @staticmethod
    def _apply(cards: list[Card], values: dict) -> None:
        for card in cards:
            card.explanation = values[card.id]['text']
            card.explanation_source = values[card.id]['source']
