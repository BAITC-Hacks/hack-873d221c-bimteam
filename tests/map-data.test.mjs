import test from 'node:test';
import assert from 'node:assert/strict';
import {mapLocations,isVenue} from '../web/map-data.mjs';

const card = {id:'one',name:'Площадка',city:'Алматы',category:'Банкетный зал',price_from_kzt:2500000};
const place = {city:'Алматы',lat:43.24,lng:76.92,kind:'demo'};
const source = locations => ({version:1,locations});

test('Карта показывает только результат подбора, сохраняя цену и порядок API', () => {
  const second = {...card,id:'two',price_from_kzt:3000000};
  const data = source({one:{...place,price_from_kzt:1},two:place,excluded:place});
  const points = mapLocations([second,card],data,'Алматы');
  assert.deepEqual(points.map(p => p.card.id),['two','one']);
  assert.deepEqual(points.map(p => p.card.price_from_kzt),[3000000,2500000]);
  assert.equal(mapLocations([],data,'Алматы').length,0);
});

test('Демо явно помечено, проверенное расположение требует адреса', () => {
  assert.equal(mapLocations([card],source({one:place}),'Алматы')[0].demo,true);
  for (const value of [{...place,kind:undefined},{...place,kind:'verified'},{...place,kind:'verified',address:' '}]) {
    assert.equal(mapLocations([card],source({one:value}),'Алматы').length,0);
  }
  const verified = {...place,kind:'verified',address:'  Тестовый адрес  '};
  const [point] = mapLocations([card],source({one:verified}),'Алматы');
  assert.equal(point.demo,false);assert.equal(point.address,'Тестовый адрес');
});

test('Нет координат — нет выдуманной точки в центре города', () => {
  for (const data of [null,{},source({}),{version:2,locations:{one:place}}]) {
    assert.deepEqual(mapLocations([card],data,'Алматы'),[]);
  }
});

test('Неверные координаты и другой город не попадают на карту', () => {
  const changes = [{lat:NaN},{lat:Infinity},{lat:'43.24'},{lat:null},{lat:86},{lng:-181},{lng:undefined},{city:'Астана'}];
  for (const change of changes) assert.equal(mapLocations([card],source({one:{...place,...change}}),'Алматы').length,0);
  assert.equal(mapLocations([card],source({one:place}),'Астана').length,0);
  assert.equal(mapLocations([{...card,city:'Астана'}],source({one:place}),'Алматы').length,0);
});

test('Карта относится к площадкам; отрицательная цена не отображается', () => {
  for (const category of ['Банкетный зал','Ресторан','Отель','Загородная площадка']) assert.equal(isVenue(category),true);
  for (const category of ['Ведущий','Флорист','Фотограф','']) assert.equal(isVenue(category),false);
  assert.deepEqual(mapLocations([{...card,category:'Ведущий'}],source({one:place}),'Алматы'),[]);
  assert.deepEqual(mapLocations([{...card,price_from_kzt:-1}],source({one:place}),'Алматы'),[]);
});
