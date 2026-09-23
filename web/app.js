// Контракт: docs/API.md. Данные каталога вставляются только через textContent.
const $ = selector => document.querySelector(selector);
const form = $('#search');
const fields = $('#fields');
const statusNode = $('#status');
const results = $('#results');
const presets = [...document.querySelectorAll('[data-preset]')];
const money = value => Number(value).toLocaleString('ru-RU');
const dateLabel = value => value.split('-').reverse().join('.');
let ready = false;
let busy = false;
const storageKey = 'bimteam.search.v1';
const savedFields = ['city','category','event_format','date','budget','duration_hours','language'];
let defaults = {};
function values() {
  return Object.fromEntries(savedFields.map(key => [key, form.elements.namedItem(key).value]));
}
function saveConditions() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(values()));
    $('#saved-note').textContent = 'Условия сохранены в этом браузере.';
  } catch { $('#saved-note').textContent = 'Сохранение недоступно. Подбор продолжает работать.'; }
}
function restoreConditions() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return false;
    let restored = false;
    for (const key of savedFields) {
      const input = form.elements.namedItem(key);
      const value = saved[key];
      if (typeof value !== 'string') continue;
      if (input instanceof HTMLSelectElement && ![...input.options].some(option => option.value === value)) continue;
      if (key === 'date' && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < input.min || value > input.max || Number.isNaN(Date.parse(value)) || new Date(value).toISOString().slice(0,10) !== value)) continue;
      if (key === 'budget' && (!/^\d+$/.test(value) || Number(value) > 1000000000)) continue;
      if (key === 'duration_hours' && value !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0.1 || Number(value) > 100)) continue;
      input.value = value;
      restored = true;
    }
    $('.extra-fields').open = Boolean(form.elements.language.value || form.elements.duration_hours.value);
    return restored;
  } catch { return false; }
}
function updateDateButtons() {
  const date = form.elements.namedItem('date');
  const valid = date.value && date.value >= date.min && date.value <= date.max;
  $('#previous-day').disabled = busy || !ready || !valid || date.value <= date.min;
  $('#next-day').disabled = busy || !ready || !valid || date.value >= date.max;
}
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function message(text, type = '') { statusNode.textContent = text; statusNode.className = type; }
function waiting(value) {
  busy = value;
  fields.disabled = value || !ready;
  presets.forEach(button => { button.disabled = value || !ready; });
  $('.results-panel').setAttribute('aria-busy', String(value));
  $('#submit span').textContent = value ? 'Проверяем совпадения…' : 'Подобрать подрядчиков';
  updateDateButtons();
}
function empty(title, copy) {
  $('#empty-state').hidden = false;
  $('#empty-title').textContent = title;
  $('#empty-copy').textContent = copy;
  $('.steps').hidden = true;
}
async function request(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    let data;
    try { data = await response.json(); } catch { throw new Error('Сервер вернул неожиданный ответ. Попробуйте ещё раз.'); }
    if (!response.ok) {
      if (response.status === 422 && Array.isArray(data.fields)) {
        data.fields.forEach(key => form.elements.namedItem(key)?.setAttribute('aria-invalid', 'true'));
      }
      throw new Error(data.message || 'Сервис временно недоступен. Попробуйте ещё раз.');
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Сервис не ответил за 15 секунд. Повторите подбор.');
    if (error instanceof TypeError) throw new Error('Нет связи с сервером. Проверьте подключение и повторите попытку.');
    throw error;
  } finally { clearTimeout(timer); }
}
async function init() {
  ready = false; waiting(false); $('#reload').hidden = true;
  message('Загружаем доступные параметры…', 'loading');
  try {
    const data = await request('/api/options');
    for (const [field, source] of Object.entries({city:'cities', category:'categories', event_format:'event_formats', language:'languages'})) {
      if (!Array.isArray(data[source]) || !data[source].every(value => typeof value === 'string')) throw new Error('Не удалось прочитать параметры каталога. Повторите загрузку.');
      const select = form.elements.namedItem(field);
      select.replaceChildren();
      if (field === 'language') select.add(new Option('Не важен', ''));
      data[source].forEach(value => select.add(new Option(value, value)));
    }
    if (!data.cities.length || !data.categories.length || !data.event_formats.length || !/^\d{4}-\d{2}-\d{2}$/.test(data.date_min) || !/^\d{4}-\d{2}-\d{2}$/.test(data.date_max)) throw new Error('В каталоге пока нет параметров для подбора. Повторите загрузку позднее.');
    for (const [key,value] of Object.entries({city:'Алматы', category:'Ведущий', event_format:'корпоратив'})) {
      if ([...form.elements.namedItem(key).options].some(option => option.value === value)) form.elements.namedItem(key).value = value;
    }
    const date = form.elements.namedItem('date');
    date.min = data.date_min; date.max = data.date_max;
    date.value = '2026-10-10' >= data.date_min && '2026-10-10' <= data.date_max ? '2026-10-10' : data.date_min;
    $('#catalog-note').textContent = `Календарь: ${dateLabel(data.date_min)} — ${dateLabel(data.date_max)}`;
    defaults = values();
    const restored = restoreConditions();
    ready = true;
    message(restored ? 'Условия восстановлены. Нажмите «Подобрать подрядчиков», чтобы проверить актуальный результат.' : 'Задайте условия или начните с примера.');
  } catch(error) {
    message(error.message, 'error');
    $('#catalog-note').textContent = 'Параметры каталога недоступны.';
    $('#reload').hidden = false;
  } finally { waiting(false); document.dispatchEvent(new CustomEvent('recommend:ready')); }
}
function renderCard(card, index, query) {
  const article = node('article', undefined, 'card');
  article.dataset.contractorId = card.id;
  article.tabIndex = -1;
  const art = /флор|декорат/i.test(card.category) ? 'florist' : /фото|видео/i.test(card.category) ? 'photo' : /зал|площад|ресторан|отель/i.test(card.category) ? 'venue' : 'host';
  const cover = node('div', undefined, `card-cover art-${art}`);
  cover.append(node('span','Подходит по условиям','cover-label'),node('span','Иллюстрация категории','cover-caption'));
  article.append(cover);
  const header = node('div', undefined, 'card-head');
  const avatar = node('div', card.name.split(/\s+/).filter(Boolean).slice(0,2).map(part=>part[0]).join(''), 'avatar');
  avatar.setAttribute('aria-hidden','true');
  const title = node('div', undefined, 'card-title');
  title.append(node('h3',card.name),node('p',`${card.category} · ${card.city}`,'card-meta'));
  header.append(avatar,title,node('span',String(index+1).padStart(2,'0'),'rank'));
  const priceRow = node('div',undefined,'price-row');
  const price = node('div',undefined,'price');
  price.append(node('small','от '),document.createTextNode(`${money(card.price_from_kzt)} ₸`));
  priceRow.append(price,node('span',`Свободен ${dateLabel(query.date)}`,'date-badge'));
  article.append(header,priceRow,node('p','Подходит по заданным условиям','match-badge'),node('p','ПОЧЕМУ ПОДХОДИТ','explanation-title'),node('p',card.explanation,'explanation'));
  const facts = node('ul', undefined, 'card-facts');
  const budgetFact = card.price_from_kzt <= query.budget
    ? `Цена от ${money(card.price_from_kzt)} ₸ при бюджете ${money(query.budget)} ₸`
    : 'Итоговую стоимость нужно уточнить';
  for (const text of [budgetFact, `Формат: ${query.event_format}${query.language ? ' · язык: '+query.language : ''}`]) {
    const fact = node('li');
    const icon = document.createElementNS('http://www.w3.org/2000/svg','svg');
    icon.setAttribute('viewBox','0 0 24 24'); icon.setAttribute('class','line-icon');
    icon.setAttribute('fill','none'); icon.setAttribute('stroke','currentColor');
    icon.setAttribute('stroke-width','1.5'); icon.setAttribute('aria-hidden','true');
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d','m5 12 4 4L19 6'); icon.append(path);
    fact.append(icon,node('span',text)); facts.append(fact);
  }
  article.append(facts);
  if(card.profile_excerpt) {
    const quote = node('blockquote',undefined,'profile-quote');
    quote.append(node('strong','ИЗ ПРОФИЛЯ'),document.createTextNode(card.profile_excerpt));
    const details = node('details', undefined, 'profile-details');
    const summary = node('summary','Подробнее — выдержка из профиля');
    summary.setAttribute('aria-label', `Профиль ${card.name}: подробнее`);
    details.append(summary,quote); article.append(details);
  }
  const notes = node('div',undefined,'data-notes');
  notes.append(node('span',card.synthetic ? 'Синтетический профиль' : 'Исходный профиль · имя изменено',card.synthetic ? 'synthetic' : ''));
  if(card.price_imputed) notes.append(node('span','Цена проставлена при подготовке данных'));
  if(card.city_imputed) notes.append(node('span','Город проставлен при подготовке данных'));
  article.append(notes);
  return article;
}
const reasonNames = {busy:'Заняты на дату',budget:'Дороже бюджета',format:'Другой формат',duration:'Не хватает часов',language:'Нет нужного языка'};
form.addEventListener('submit',async event=>{
  event.preventDefault();
  if(busy || !ready || !form.reportValidity()) return;
  saveConditions();
  const payload = Object.fromEntries(new FormData(form));
  payload.budget = Number(payload.budget);
  payload.duration_hours = payload.duration_hours ? Number(payload.duration_hours) : null;
  payload.language = payload.language || null;
  form.querySelectorAll('[aria-invalid]').forEach(input=>input.removeAttribute('aria-invalid'));
  results.replaceChildren(); $('#rejections').hidden = true; $('#empty-state').hidden = true;
  $('#result-count').textContent = 'Ищем…';
  $('#query-summary').textContent = `${payload.city} · ${payload.category} · ${payload.event_format} · ${dateLabel(payload.date)} · до ${money(payload.budget)} ₸${payload.language ? ' · '+payload.language : ''}${payload.duration_hours ? ' · '+payload.duration_hours+' ч' : ''}`;
  $('#query-summary').hidden = false;
  waiting(true); message('Проверяем календарь, бюджет и остальные условия…','loading');
  document.dispatchEvent(new CustomEvent('recommend:start', {detail:{query:payload}}));
  try {
    const data = await request('/api/recommend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!['ok','no_matches','no_category_in_city'].includes(data.status) || typeof data.message !== 'string' || !Array.isArray(data.results) || data.results.length>3 || (data.status==='ok') !== (data.results.length>0) || !data.results.every(card=>typeof card.name==='string' && typeof card.explanation==='string' && Number.isFinite(card.price_from_kzt))) throw new Error('Не удалось прочитать результат подбора. Повторите запрос.');
    message(data.message);
    $('#result-count').textContent = `Показано: ${data.results.length}${Number.isInteger(data.eligible_count) ? ' из '+data.eligible_count : ''}`;
    data.results.forEach((card,index)=>results.append(renderCard(card,index,payload)));
    if(data.status==='no_category_in_city') empty('Такой категории в городе нет','Попробуйте другой город или категорию. В текущем каталоге нет профилей для этого сочетания.');
    if(data.status==='no_matches') empty('Условия не совпали','Подрядчики есть, но не проходят все ограничения. Попробуйте другую дату, увеличьте бюджет или измените дополнительные условия.');
    const reasons = $('#reason-list'); reasons.replaceChildren();
    for(const [key,label] of Object.entries(reasonNames)) {
      const count = data.rejection_summary?.[key];
      if(Number.isInteger(count) && count>0) reasons.append(node('span',`${label} · ${count}`));
    }
    $('#rejections').hidden = !reasons.childElementCount;
    document.dispatchEvent(new CustomEvent('recommend:success', {detail:{query:payload, cards:data.results}}));
  } catch(error) {
    results.replaceChildren(); $('#result-count').textContent = 'Нет ответа';
    message(error.message,'error');
    empty('Не удалось завершить подбор','Ваши условия сохранены. Нажмите «Подобрать подрядчиков», чтобы повторить запрос.');
    document.dispatchEvent(new CustomEvent('recommend:error'));
  } finally { waiting(false); }
});
form.addEventListener('input',event=>{
  event.target.removeAttribute('aria-invalid');
  saveConditions(); updateDateButtons();
  if(!$('#query-summary').hidden && !busy) message('Условия изменены. Нажмите «Подобрать подрядчиков», чтобы обновить результат.');
  document.dispatchEvent(new CustomEvent('recommend:dirty'));
});
function shiftDate(days) {
  if (busy || !ready) return;
  const input = form.elements.namedItem('date');
  if (!input.value || !input.checkValidity()) { input.reportValidity(); return; }
  const date = new Date(input.value + 'T00:00:00Z');
  date.setUTCDate(date.getUTCDate() + days);
  const next = date.toISOString().slice(0,10);
  if (next < input.min || next > input.max) return;
  input.value = next;
  saveConditions(); updateDateButtons();
  // Новая дата — новый запрос. Остальные ограничения сохраняются.
  form.requestSubmit();
}
$('#previous-day').addEventListener('click', () => shiftDate(-1));
$('#next-day').addEventListener('click', () => shiftDate(1));
$('#reset-filters').addEventListener('click', () => {
  if (busy || !ready) return;
  Object.entries(defaults).forEach(([key,value]) => { form.elements.namedItem(key).value = value; });
  form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
  $('.extra-fields').open = false;
  results.replaceChildren(); $('#rejections').hidden = true; $('#query-summary').hidden = true;
  $('#result-count').textContent = 'до 3 вариантов';
  empty('Найдём тех, кто подходит','Выберите условия. Здесь появится короткий список с конкретными причинами — почему именно эти подрядчики.');
  $('.steps').hidden = false;
  message('Условия сброшены. Можно начать новый подбор.');
  try { localStorage.removeItem(storageKey); $('#saved-note').textContent = 'Сохранённые условия удалены.'; }
  catch { $('#saved-note').textContent = 'Условия сброшены в форме. Хранилище браузера недоступно.'; }
  updateDateButtons();
  document.dispatchEvent(new CustomEvent('recommend:reset'));
});
presets.forEach(button=>button.addEventListener('click',()=>{
  if(busy || !ready) return;
  const venue = button.dataset.preset === 'venue';
  const values = {city:'Алматы',category:venue?'Банкетный зал':button.dataset.preset==='florist'?'Флорист':'Ведущий',event_format:venue?'свадьба':'корпоратив',date:'2026-10-10',budget:venue?'6000000':button.dataset.preset==='empty'?'0':'1000000',language:'',duration_hours:''};
  for(const [field,value] of Object.entries(values)) {
    const input = form.elements.namedItem(field);
    if(input instanceof HTMLSelectElement && ![...input.options].some(option=>option.value===value)) { message('Этот пример недоступен в текущем каталоге. Выберите условия вручную.','error'); return; }
  }
  Object.entries(values).forEach(([field,value])=>{form.elements.namedItem(field).value=value;});
  form.requestSubmit();
}));
$('#reload').addEventListener('click',init);
init();
