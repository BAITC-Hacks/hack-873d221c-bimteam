# Контракт сервера и интерфейса

Сервер и страница работают по одному адресу. Рустем открывает `/`, не HTML двойным кликом. Полная схема обоих контрактов и интерактивные запросы: [/docs](http://127.0.0.1:8000/docs).

## Новый контракт

`POST /api/recommend`, Content-Type: application/json:

```json
{"city":"Алматы","date":"2026-10-10","event_type":"конференция","category":"Ведущий","budget_kzt":1300000}
```

Необязательны `language` (строка или null), `duration_hours` (0 < число ≤100 или null), `wishes` (до 1000 символов или null). Пожелания влияют только на необязательную семантику и выбор цитаты/фактов для объяснения. Бюджет — положительное целое число тенге до 1 000 000 000; дата — ISO, с 23.09.2026 по 31.12.2026 включительно.

Город, категория, формат и непустой язык берутся из `/api/options`. Категория проверяется по любому элементу списка профиля, а не только первому. Цена ровно по бюджету проходит. Пустой max_hours не означает ноль часов.

| Поле ответа | Смысл |
| --- | --- |
| status | found / no_category / all_filtered |
| message | Готовое русское резюме |
| cards | До 3 карточек; готовый порядок, не пересортировывать |
| shortfall_reason | Почему меньше трёх; null при трёх |
| funnel | Последовательные step/label/before/after/rejected_ids |
| hints | До 2 проверенных изменений одного условия |
| elapsed_ms | Время серверного пайплайна, не сетевой round-trip |

Карточка: rank, id, name, category, categories, city, price_from_kzt, price_imputed, city_imputed, synthetic, languages, max_hours, explanation, facts=[{type,text}], explanation_source=llm/template, profile_excerpt.

Факт занятости использует знаменатель всей группы «категория+город». Воронка даты проверяет уже прошедших формат: это разные группы, не ошибка счётчиков.

## Совместимость существующего web/

Старый запрос сохранён без правок интерфейса:

```json
{"city":"Алматы","date":"2026-10-10","event_format":"корпоратив","category":"Ведущий","budget":1000000,"duration_hours":null,"language":null}
```

Наличие старых названий определяет legacy-контракт:

| Новый | Старый |
| --- | --- |
| event_type | event_format |
| budget_kzt > 0 | budget ≥ 0 |
| status=found | status=ok |
| status=no_category | status=no_category_in_city |
| status=all_filtered | status=no_matches |
| cards | results |

Также возвращаются candidate_count (после категории+города), eligible_count (после всех условий) и rejection_summary с ключами busy/budget/format/language/duration. **Теперь счётчики не пересекаются:** один профиль учитывается на первом не пройденном шаге.

Нулевой budget разрешён только для legacy-кнопки пустого примера. Смешивать старые/новые поля нельзя — HTTP 422. Ошибочные имена полей в legacy-ответе соответствуют форме. explanation_source больше не rules/nvidia_quote/openai_quote, а template/llm; web/ это поле не анализирует.

Показывайте price_from_kzt с пометкой «от», сохраняйте подписи synthetic/imputed. Профильные тексты вставлять через textContent. Не исполнять содержимое description, facts или ответа модели как HTML. Нынешний web/ показывает карточки и message, но не новую полную воронку и hints.

## Служебные маршруты

- GET /api/options: cities, categories, event_types и совместимый event_formats, languages, date_min, date_max; массивы отсортированы.
- GET /api/demo: пять реальных запросов и шаблонные снимки ответов без elapsed_ms. После генерации файла перезапустите сервер.
- GET /api/health: ok, настроенный llm_provider, profiles. Это не проверка ключа модели.
- GET /health: совместимый старый ответ {"status":"готов"}.
- GET /: web/index.html; /web/ содержит только файлы интерфейса, не .env или cache.
- GET /docs и /openapi.json: схема API.
- HTTP 422: {"message":"Проверьте ...","fields":["..."]}. Ошибка ввода отличается от нормального пустого результата HTTP 200.

При переносе фронтенда на отдельный домен согласуйте CORS/proxy. В локальном однопроцессном демо сервер запускается через uvicorn app.main:app --no-access-log; старый api.main:app оставлен как alias.
