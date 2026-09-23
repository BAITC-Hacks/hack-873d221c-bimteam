// Цены и состав результатов всегда берём из API. Этот файл добавляет только географию.
export const isVenue = category => /^(Банкетный зал|Загородная площадка|Ресторан|Отель)$/.test(category);
export const cityViews = Object.freeze({
  'Алматы': {center:[43.25,76.92], zoom:12},
  'Астана': {center:[51.135,71.43], zoom:12}
});
export function mapLocations(cards, source, city) {
  if (source?.version !== 1 || !source.locations || typeof source.locations !== 'object') return [];
  return cards.flatMap(card => {
    const place = Object.hasOwn(source.locations, card.id) ? source.locations[card.id] : null;
    if (!place || place.city !== city || card.city !== city || !isVenue(card.category)) return [];
    if (!Number.isFinite(place.lat) || Math.abs(place.lat) > 85 || !Number.isFinite(place.lng) || Math.abs(place.lng) > 180) return [];
    if (!Number.isFinite(card.price_from_kzt) || card.price_from_kzt < 0) return [];
    if (place.kind !== 'demo' && !(place.kind === 'verified' && typeof place.address === 'string' && place.address.trim())) return [];
    return [{card, lat:place.lat, lng:place.lng, demo:place.kind === 'demo', address:place.kind === 'verified' ? place.address.trim() : ''}];
  });
}
