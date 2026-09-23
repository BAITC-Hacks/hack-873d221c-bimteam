import {isVenue, cityViews, mapLocations} from './map-data.mjs';

const el = id => document.getElementById(id);
const form = el('search');
const panel = el('venue-map-panel');
const dialog = el('venue-map-dialog');
const layout = el('venue-results-layout');
const reduceMotion = matchMedia('(prefers-reduced-motion:reduce)');
const price = amount => `${amount.toLocaleString('ru-RU')} ₸`;
const venueName = card => card.venue_name || card.name;
let map, tiles, markers, labelLines, libraryPromise, locationPromise, current, points = [];
let revision = 0, view = 'map', requestBusy = false, dataError = false, tileError = false;
let scope = 'recommend', catalogLoading = false;
const pins = new Map();
function make(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function loadLibrary() {
  if (window.L) return Promise.resolve(window.L);
  if (!libraryPromise) libraryPromise = new Promise((resolve,reject) => {
    const script = document.createElement('script');
    const timeout = setTimeout(() => failed(), 10000);
    const failed = () => {clearTimeout(timeout);script.remove();libraryPromise = null;reject(new Error('Карта не загрузилась. Список площадок остаётся доступен.'));};
    script.src = '/web/vendor/leaflet/leaflet.js';
    script.onload = () => {clearTimeout(timeout);resolve(window.L);};
    script.onerror = failed;
    document.head.append(script);
  });
  return libraryPromise;
}
function loadLocations() {
  if (!locationPromise) locationPromise = (async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch('/web/data/venue-locations.json', {signal:controller.signal});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (data.version !== 1 || !data.locations || typeof data.locations !== 'object') throw new Error();
      return data;
    } catch {
      locationPromise = null;
      throw new Error('Не удалось загрузить точки. Список и цены доступны ниже.');
    } finally {clearTimeout(timeout);}
  })();
  return locationPromise;
}
function status() {
  el('map-status').textContent = tileError ? 'Не удалось загрузить фон карты. Можно повторить или выбрать площадку в списке.'
    : points.length ? `На карте ${points.length} из ${current?.cards.length || 0} ${scope === 'catalog' ? 'площадок города' : 'вариантов'} · цены за мероприятие, «от».`
      : 'Нет площадок с координатами для этого запроса.';
  el('map-retry').hidden = !tileError && !dataError;
}
function createMap(L) {
  if (map) return;
  map = L.map(el('venue-map'), {zoomControl:false,scrollWheelZoom:false,minZoom:3,maxZoom:18,
    zoomAnimation:!reduceMotion.matches,fadeAnimation:!reduceMotion.matches,markerZoomAnimation:!reduceMotion.matches});
  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
  tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom:19, attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    keepBuffer:1, updateWhenIdle:true
  });
  tiles.on('tileerror', () => {tileError = true;status();});
  tiles.addTo(map);
  labelLines = L.layerGroup().addTo(map);
  markers = L.layerGroup().addTo(map);
  map.on('moveend resize',arrangeLabels);
  map.on('zoomend', () => {
    el('map-zoom-in').disabled = map.getZoom() >= map.getMaxZoom();
    el('map-zoom-out').disabled = map.getZoom() <= map.getMinZoom();
  });
  map.on('popupclose', () => markSelected(null));
  new ResizeObserver(() => {if (!panel.hidden) map.invalidateSize({pan:false});}).observe(el('venue-map'));
}
function arrangeLabels() {
  if (!map || !labelLines || panel.hidden) return;
  labelLines.clearLayers();
  const size = map.getSize();
  const occupied = [{left:size.x-72,right:size.x,top:0,bottom:222}];
  for (const pin of pins.values()) {
    const label = pin.getElement()?.firstElementChild;
    if (!label) continue;
    label.style.translate = '';
    const origin = map.latLngToContainerPoint(pin.getLatLng());
    if (origin.x < 0 || origin.x > size.x || origin.y < 0 || origin.y > size.y) continue;
    const w = label.offsetWidth + 8, h = label.offsetHeight + 8;
    const candidates = [{x:origin.x,y:origin.y}];
    for (let y=h/2+8;y<=size.y-h/2-26;y+=h+6) {
      for (let x=w/2+8;x<=size.x-w/2-8;x+=w+4) candidates.push({x,y});
    }
    candidates.sort((a,b) => (a.x-origin.x)**2+(a.y-origin.y)**2-((b.x-origin.x)**2+(b.y-origin.y)**2));
    for (const position of candidates) {
      const rect = {left:position.x-w/2,right:position.x+w/2,top:position.y-h/2,bottom:position.y+h/2};
      if (rect.left<4 || rect.right>size.x-4 || rect.top<4 || rect.bottom>size.y-24) continue;
      if (occupied.some(other => rect.left<other.right && rect.right>other.left && rect.top<other.bottom && rect.bottom>other.top)) continue;
      occupied.push(rect);
      const dx = position.x-origin.x, dy = position.y-origin.y;
      label.style.translate = `${dx}px ${dy}px`;
      if (Math.abs(dx)+Math.abs(dy)>8) {
        window.L.polyline([pin.getLatLng(),map.containerPointToLatLng([position.x,position.y])],{interactive:false,color:'var(--muted)',weight:1,opacity:.7}).addTo(labelLines);
        window.L.circleMarker(pin.getLatLng(),{interactive:false,radius:3,color:'var(--accent)',fillOpacity:1,weight:1}).addTo(labelLines);
      }
      break;
    }
  }
}
function fit() {
  if (!map || !current) return;
  map.closePopup();
  map.invalidateSize({pan:false});
  if (points.length) map.fitBounds(points.map(p => [p.lat,p.lng]), {paddingTopLeft:[68,48],paddingBottomRight:[68,48],maxZoom:13,animate:false});
  else {
    const city = cityViews[current.query.city];
    map.setView(city?.center || [30,20], city?.zoom || 3, {animate:false});
  }
}
function cardElement(id) {
  return [...el(scope === 'catalog' ? 'venue-catalog' : 'results').children].find(article => article.dataset.contractorId === id);
}
function markSelected(id) {
  pins.forEach((pin,key) => {
    pin.getElement()?.classList.toggle('is-selected', key === id);
    pin.getElement()?.setAttribute('aria-pressed', String(key === id));
    pin.setZIndexOffset(key === id ? 1000 : 0);
  });
  [...el('results').children,...el('venue-catalog').children].forEach(card => {
    const selected = card.dataset.contractorId === id;
    card.classList.toggle('is-map-selected',selected);
    card.querySelector('.card-map-link')?.setAttribute('aria-pressed',String(selected));
  });
}
function details(id) {
  if (dialog.open) dialog.close();
  const card = cardElement(id);
  if (!card) return;
  const profile = card.querySelector('.profile-details');
  if (profile) profile.open = true;
  requestAnimationFrame(() => {
    card.scrollIntoView({block:'center',behavior:reduceMotion.matches?'instant':'smooth'});
    card.focus({preventScroll:true});
  });
}
function popup(point) {
  const content = make('div');
  const cover = make('div',undefined,'map-popup-cover art-venue');
  cover.append(make('span','Иллюстрация категории'));
  const body = make('div',undefined,'map-popup-body');
  body.append(make('h3',venueName(point.card)),make('p',`${point.card.category} · ${point.card.city}`),
    make('p',`от ${price(point.card.price_from_kzt)}`,'map-popup-price'),
    make('p',point.demo ? 'Условная точка — это не адрес площадки.' : point.address));
  if (point.card.price_imputed) body.append(make('p','Цена проставлена при подготовке данных.'));
  const button = make('button','Подробнее о площадке →');
  button.type = 'button';
  button.addEventListener('click', () => details(point.card.id));
  body.append(button);content.append(cover,body);
  return content;
}
function renderPoints(L) {
  markers.clearLayers();pins.clear();
  document.querySelectorAll('.card-map-link').forEach(button => button.remove());
  for (const point of points) {
    const label = make('span');
    label.append(make('strong',venueName(point.card),'map-pin-name'),make('b',`от ${price(point.card.price_from_kzt)}`,'map-pin-price'));
    const pin = L.marker([point.lat,point.lng], {
      icon:L.divIcon({className:'venue-price-pin',html:label,iconSize:[150,56],iconAnchor:[75,28]}),
      title:`${venueName(point.card)} — от ${price(point.card.price_from_kzt)}${point.demo ? ', условная точка' : ''}`,
      keyboard:true,riseOnHover:true
    }).addTo(markers);
    pin.bindPopup(popup(point), {className:'venue-popup',maxWidth:240,minWidth:240,autoPanPadding:[24,24],closeButton:true});
    pin.on('popupopen', () => {
      markSelected(point.card.id);
      const close = pin.getPopup().getElement()?.querySelector('.leaflet-popup-close-button');
      close?.setAttribute('aria-label','Закрыть карточку площадки');
      close?.setAttribute('title','Закрыть карточку площадки');
    });
    pin.getElement().setAttribute('aria-label', pin.options.title);
    pin.getElement().setAttribute('aria-pressed','false');
    pin.getElement().addEventListener('keydown', event => {
      if (event.key === ' ') {event.preventDefault();pin.openPopup();}
      if (event.key === 'Escape') pin.closePopup();
    });
    pins.set(point.card.id,pin);
    const link = make('button','Показать на карте','card-map-link');
    link.type = 'button';link.setAttribute('aria-pressed','false');
    link.setAttribute('aria-label',`Показать на карте: ${venueName(point.card)}${point.demo ? ' — условная точка' : ''}`);
    link.append(make('small',point.demo ? 'Демо' : 'Адрес указан'));
    link.addEventListener('click', async () => {
      await setView('map');
      panel.scrollIntoView({block:'center',behavior:reduceMotion.matches?'instant':'smooth'});
      pins.get(point.card.id)?.openPopup();pins.get(point.card.id)?.getElement()?.focus({preventScroll:true});
    });
    cardElement(point.card.id)?.append(link);
  }
  const demo = points.some(point => point.demo);
  el('map-mode-label').textContent = demo ? 'ДЕМО-КАРТА' : points.length ? 'КАРТА ПЛОЩАДОК' : cityViews[current.query.city] ? 'ОБЗОР ГОРОДА' : 'НЕТ ТОЧЕК';
  el('map-disclosure-copy').textContent = demo ? 'Расположение демо-точек условное. Цены — из каталога.'
    : points.length ? 'Адреса площадок указаны в карточках. Цены — из каталога.' : 'Для выбранных условий пока нет точек на карте.';
  el('map-empty').hidden = points.length > 0;
  el('map-empty-copy').textContent = current.cards.length ? 'У этих площадок ещё нет координат. Их цены и описания доступны в списке.'
    : scope === 'catalog' ? 'В каталоге пока нет площадок этого города.' : 'По заданным условиям нет совпадений. Попробуйте другую дату или бюджет.';
  arrangeLabels();status();
}
async function render() {
  if (!current || !isVenue(current.query.category) || view !== 'map' || requestBusy) return;
  const token = ++revision;
  panel.hidden = false;layout.classList.add('map-visible');
  el('map-status').textContent = 'Загружаем карту…';
  el('map-retry').hidden = true;
  try {
    const [L, source] = await Promise.all([loadLibrary(),loadLocations()]);
    if (token !== revision || !current) return;
    dataError = false;createMap(L);
    points = mapLocations(current.cards,source,current.query.city);
    fit();
    renderPoints(L);
  } catch (error) {
    if (token !== revision) return;
    dataError = true;
    console.error('Карта площадок:',error);
    el('map-status').textContent = 'Не удалось открыть карту. Попробуйте ещё раз; список площадок доступен.';
    el('map-retry').hidden = false;
  }
}
function syncTools() {
  const venue = scope === 'catalog' || isVenue(form.elements.category.value);
  el('venue-browse').disabled = requestBusy || catalogLoading || el('fields').disabled;
  el('venue-view-tools').hidden = !venue;
  el('venue-list-view').disabled = requestBusy || catalogLoading;
  el('venue-map-view').disabled = requestBusy || catalogLoading || el('fields').disabled;
  el('venue-list-view').setAttribute('aria-pressed',String(view === 'list'));
  el('venue-map-view').setAttribute('aria-pressed',String(view === 'map'));
}
async function setView(next) {
  view = next;syncTools();
  if (view === 'map') {
    if (current) await render();
    else if (scope === 'catalog') browse();
    else if (!el('fields').disabled) form.requestSubmit();
  } else {++revision;panel.hidden = true;layout.classList.remove('map-visible');}
}
function clear() {
  ++revision;current = null;points = [];
  if (dialog.open) dialog.close();
  map?.closePopup();markers?.clearLayers();labelLines?.clearLayers();pins.clear();
  document.querySelectorAll('.card-map-link').forEach(link => link.remove());
  panel.hidden = true;layout.classList.remove('map-visible');syncTools();
}
function setScope(next) {
  scope = next;
  document.querySelector('.results-panel').classList.toggle('browsing-venues',next === 'catalog');
  document.querySelector('.results-panel').setAttribute('aria-labelledby',next === 'catalog' ? 'venue-catalog-title' : 'results-title');
  el('venue-catalog-intro').hidden = next !== 'catalog';
  el('venue-catalog').hidden = next !== 'catalog';
}
function renderCatalog(cards,city) {
  const list = el('venue-catalog');list.replaceChildren();
  const prices = cards.map(card => card.price_from_kzt);
  el('venue-catalog-summary').textContent = cards.length ? `${city} · площадок: ${cards.length} · от ${price(Math.min(...prices))} до ${price(Math.max(...prices))}` : `${city} · площадок пока нет`;
  for (const [index,card] of cards.entries()) {
    const article = make('article',undefined,'venue-catalog-card');
    article.dataset.contractorId = card.id;article.tabIndex = -1;
    const heading = make('div',undefined,'venue-catalog-heading');
    heading.append(make('span',String(index + 1).padStart(2,'0'),'venue-order'),make('h3',card.name));
    article.append(heading,make('p',`${card.categories.join(' · ')} · ${card.city}`,'card-meta'),make('p',`от ${price(card.price_from_kzt)}`,'venue-catalog-price'));
    const budget = Number(form.elements.budget.value);
    if (form.elements.budget.value && Number.isFinite(budget)) article.append(make('p',card.price_from_kzt <= budget ? `Ниже или в пределах бюджета ${price(budget)}` : `Выше бюджета на ${price(card.price_from_kzt - budget)}`,'venue-budget-note'));
    const details = make('details',undefined,'profile-details');
    details.append(make('summary','О площадке'),make('p',card.description,'venue-description'));
    article.append(details,make('p',`Профиль: ${card.profile_name} · ${card.id}${card.synthetic ? ' · синтетический' : ''}`,'venue-data-note'));
    if (card.price_imputed) article.append(make('p','Цена проставлена при подготовке датасета.','venue-data-note'));
    if (card.city_imputed) article.append(make('p','Город проставлен при подготовке датасета.','venue-data-note'));
    list.append(article);
  }
}
async function browse() {
  if (requestBusy || el('fields').disabled) return;
  clear();setScope('catalog');view = 'map';catalogLoading = true;syncTools();
  const token = ++revision;
  const city = form.elements.city.value;
  el('venue-catalog').replaceChildren();
  el('venue-catalog-summary').textContent = `${city} · загружаем площадки…`;
  el('venue-catalog-intro').scrollIntoView({block:'start',behavior:reduceMotion.matches?'instant':'smooth'});
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(),10000);
  try {
    const response = await fetch(`/api/venues?${new URLSearchParams({city})}`,{signal:controller.signal});
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (!Array.isArray(data.venues) || !data.venues.every(card => typeof card.name === 'string' && typeof card.description === 'string' && Array.isArray(card.categories) && Number.isFinite(card.price_from_kzt))) throw new Error();
    if (token !== revision) return;
    renderCatalog(data.venues,city);
    current = {query:{city,category:'Банкетный зал'},cards:data.venues};
    await render();
  } catch {
    if (token !== revision) return;
    el('venue-catalog-summary').textContent = 'Не удалось загрузить обзор. Повторите через кнопку «Все площадки города и цены на карте».';
  } finally {clearTimeout(timeout);catalogLoading = false;syncTools();}
}
el('venue-browse').addEventListener('click',browse);
document.addEventListener('recommend:start', () => {requestBusy = true;setScope('recommend');clear();});
document.addEventListener('recommend:success', event => {
  requestBusy = false;current = event.detail;syncTools();render();
});
for (const event of ['recommend:error','recommend:reset','recommend:dirty']) {
  document.addEventListener(event, () => {requestBusy = false;setScope('recommend');clear();});
}
document.addEventListener('recommend:ready',syncTools);
document.querySelector('[data-preset="venue"]').addEventListener('click', () => {view = 'map';syncTools();});
new MutationObserver(syncTools).observe(el('fields'),{attributes:true,attributeFilter:['disabled']});
el('venue-list-view').addEventListener('click', () => setView('list'));
el('venue-map-view').addEventListener('click', () => setView('map'));
el('map-fit').addEventListener('click',fit);
el('map-zoom-in').addEventListener('click', () => map?.zoomIn());
el('map-zoom-out').addEventListener('click', () => map?.zoomOut());
el('map-retry').addEventListener('click', () => {tileError = false;tiles?.redraw();render();});
el('map-expand').addEventListener('click', () => {
  dialog.append(panel);dialog.showModal();requestAnimationFrame(fit);el('map-close').focus();
});
el('map-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => {
  el('venue-map-home').append(panel);requestAnimationFrame(fit);el('map-expand').focus({preventScroll:true});
});
dialog.addEventListener('click', event => {
  if (event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
});
syncTools();
