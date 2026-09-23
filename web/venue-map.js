import {isVenue, cityViews, mapLocations} from './map-data.mjs';

const el = id => document.getElementById(id);
const form = el('search');
const panel = el('venue-map-panel');
const dialog = el('venue-map-dialog');
const layout = el('venue-results-layout');
const reduceMotion = matchMedia('(prefers-reduced-motion:reduce)');
const price = amount => `${amount.toLocaleString('ru-RU')} ₸`;
let map, tiles, markers, libraryPromise, locationPromise, current, points = [];
let revision = 0, view = 'map', requestBusy = false, dataError = false, tileError = false;
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
    : points.length ? `На карте ${points.length} из ${current?.cards.length || 0} вариантов · цены за мероприятие, «от».`
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
  markers = L.layerGroup().addTo(map);
  map.on('zoomend', () => {
    el('map-zoom-in').disabled = map.getZoom() >= map.getMaxZoom();
    el('map-zoom-out').disabled = map.getZoom() <= map.getMinZoom();
  });
  map.on('popupclose', () => markSelected(null));
  new ResizeObserver(() => {if (!panel.hidden) map.invalidateSize({pan:false});}).observe(el('venue-map'));
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
  return [...el('results').children].find(article => article.dataset.contractorId === id);
}
function markSelected(id) {
  pins.forEach((pin,key) => {
    pin.getElement()?.classList.toggle('is-selected', key === id);
    pin.getElement()?.setAttribute('aria-pressed', String(key === id));
    pin.setZIndexOffset(key === id ? 1000 : 0);
  });
  [...el('results').children].forEach(card => {
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
  body.append(make('h3',point.card.name),make('p',`${point.card.category} · ${point.card.city}`),
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
  el('results').querySelectorAll('.card-map-link').forEach(button => button.remove());
  for (const point of points) {
    const label = make('span',`от ${price(point.card.price_from_kzt)}`);
    const pin = L.marker([point.lat,point.lng], {
      icon:L.divIcon({className:'venue-price-pin',html:label,iconSize:[132,44],iconAnchor:[66,22]}),
      title:`${point.card.name} — от ${price(point.card.price_from_kzt)}${point.demo ? ', условная точка' : ''}`,
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
    link.setAttribute('aria-label',`Показать на карте: ${point.card.name}${point.demo ? ' — условная точка' : ''}`);
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
    : 'По заданным условиям нет совпадений. Попробуйте другую дату или бюджет.';
  status();
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
  const venue = isVenue(form.elements.category.value);
  el('venue-view-tools').hidden = !venue;
  el('venue-list-view').disabled = requestBusy;
  el('venue-map-view').disabled = requestBusy || el('fields').disabled;
  el('venue-list-view').setAttribute('aria-pressed',String(view === 'list'));
  el('venue-map-view').setAttribute('aria-pressed',String(view === 'map'));
}
async function setView(next) {
  view = next;syncTools();
  if (view === 'map') {
    if (current) await render();
    else if (!el('fields').disabled) form.requestSubmit();
  } else {++revision;panel.hidden = true;layout.classList.remove('map-visible');}
}
function clear() {
  ++revision;current = null;points = [];
  if (dialog.open) dialog.close();
  map?.closePopup();markers?.clearLayers();pins.clear();
  el('results').querySelectorAll('.card-map-link').forEach(link => link.remove());
  panel.hidden = true;layout.classList.remove('map-visible');syncTools();
}
document.addEventListener('recommend:start', () => {requestBusy = true;clear();});
document.addEventListener('recommend:success', event => {
  requestBusy = false;current = event.detail;syncTools();render();
});
for (const event of ['recommend:error','recommend:reset','recommend:dirty']) {
  document.addEventListener(event, () => {requestBusy = false;clear();});
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
