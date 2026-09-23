// Рустем: интерфейс. Все данные приходят из API; ключей здесь нет.
const form = document.querySelector('#search');
const status = document.querySelector('#status');
const results = document.querySelector('#results');
const button = form.querySelector('button');
function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text; // Данные каталога никогда не вставляем как HTML.
  return node;
}
async function init() {
  try {
    const response = await fetch('/api/options');
    if (!response.ok) throw new Error('Не удалось загрузить каталог. Обновите страницу.');
    const options = await response.json();
    for (const [field, source] of Object.entries({city:'cities',category:'categories',event_format:'event_formats',language:'languages'})) {
      for (const value of options[source]) form.elements[field].add(new Option(value, value));
    }
    form.elements.category.value = 'Ведущий';
    form.elements.event_format.value = 'корпоратив';
    status.textContent = 'Выберите условия мероприятия.';
    button.disabled = false;
  } catch (error) { status.textContent = error.message; }
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  button.disabled = true; results.replaceChildren(); status.textContent = 'Подбираем подрядчиков…';
  const payload = Object.fromEntries(new FormData(form));
  payload.budget = Number(payload.budget);
  payload.duration_hours = payload.duration_hours ? Number(payload.duration_hours) : null;
  payload.language = payload.language || null;
  try {
    const response = await fetch('/api/recommend', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || 'Сервис временно недоступен. Попробуйте ещё раз.');
    status.textContent = data.message;
    for (const card of data.results) {
      const article = document.createElement('article');
      article.append(element('h2', card.name), element('p', `${card.category} · ${card.city}`),
        element('h3', `от ${card.price_from_kzt.toLocaleString('ru-RU')} ₸`),
        element('p', card.explanation), element('blockquote', `Из профиля: «${card.profile_excerpt}»`),
        element('small', card.synthetic ? 'Синтетический профиль' : 'Профиль из исходных данных, имя изменено'));
      if (card.price_imputed) article.append(element('small', 'Цена проставлена при подготовке датасета.'));
      if (card.city_imputed) article.append(element('small', 'Город проставлен при подготовке датасета.'));
      results.append(article);
    }
  } catch(error) { status.textContent = error.message || 'Ошибка соединения. Проверьте запуск сервера.'; }
  finally {button.disabled = false;}
});
init();
