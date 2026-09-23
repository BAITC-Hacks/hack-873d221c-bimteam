// Прогрессивное улучшение: исходные поля и события остаются контрактом формы.
(() => {
  const form = document.querySelector('#search');
  const fieldset = document.querySelector('#fields');
  const budget = form.elements.namedItem('budget');
  const wrapper = document.createElement('span');
  wrapper.className = 'budget-wrap'; budget.before(wrapper); wrapper.append(budget);
  const display = document.createElement('span');
  display.className = 'budget-display'; display.setAttribute('aria-hidden','true'); wrapper.append(display);
  const mobile = document.querySelector('#mobile-submit');
  const dialog = document.querySelector('#control-dialog');
  const content = document.querySelector('#control-content');
  const title = document.querySelector('#control-title');
  const triggers = new Map();
  const categoryButtons = [...document.querySelectorAll('[data-category]')];
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let activeField = null;
  let activeTrigger = null;
  const dateText = value => value ? new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z')) : 'Выберите дату';
  const emitChange = field => {
    field.dispatchEvent(new Event('input',{bubbles:true}));
    field.dispatchEvent(new Event('change',{bubbles:true}));
  };
  function sync() {
    display.textContent = budget.value === '' ? '' : `${Number(budget.value).toLocaleString('ru-RU')} ₸`;
    mobile.disabled = fieldset.disabled;
    mobile.firstElementChild.textContent = document.querySelector('#submit span').textContent;
    for (const [field,button] of triggers) {
      const value = field.type === 'date' ? dateText(field.value) : field.selectedOptions[0]?.textContent || 'Выберите';
      button.textContent = value;
      button.setAttribute('aria-label',`${field.getAttribute('aria-label')}: ${value}`);
    }
    categoryButtons.forEach(button => {
      const available = [...form.elements.category.options].some(option => option.value === button.dataset.category);
      button.disabled = fieldset.disabled || !available;
      button.setAttribute('aria-pressed',String(button.dataset.category === form.elements.category.value));
    });
  }
  const make = (tag,text,classes) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (classes) item.className = classes;
    return item;
  };
  function close() { dialog.close(); }
  function choose(value) {
    activeField.value = value;
    emitChange(activeField); sync(); close();
  }
  const cityDescriptions = {
    'Алматы': 'Подрядчики для вашего события в Алматы',
    'Астана': 'Подрядчики для вашего события в Астане',
    'Зарубежье': 'Мероприятия за пределами Казахстана'
  };
  function cityIcon(city) {
    const icon = document.createElementNS('http://www.w3.org/2000/svg','svg');
    icon.setAttribute('viewBox','0 0 32 32'); icon.setAttribute('aria-hidden','true');
    const paths = city === 'Алматы'
      ? ['M3 27h26M4 21 12 8l8 13M10 11l2 3 3-1M18 16l5-8 6 11','M11 27v-7h10v7M14 23h4']
      : city === 'Астана'
      ? ['M3 27h26M14 24l-2-12m6 12 2-12M11 24h10','M21 8a5 5 0 1 1-10 0 5 5 0 0 1 10 0ZM5 24V14h4v10m14 0V17h4v7']
      : ['M28 16a12 12 0 1 1-24 0 12 12 0 0 1 24 0ZM4 16h24','M16 4c-7 6-7 18 0 24 7-6 7-18 0-24ZM7 9h18M7 23h18'];
    for (const data of paths) {
      const path = document.createElementNS('http://www.w3.org/2000/svg','path');
      path.setAttribute('d',data); icon.append(path);
    }
    return icon;
  }
  function renderCities() {
    const label = make('label','Поиск города','city-search-label');
    const search = make('input'); search.type='search'; search.placeholder='Введите город';
    search.id='city-search'; search.autocomplete='off'; search.setAttribute('aria-controls','city-options');
    label.append(search);
    const caption = make('p','Города в каталоге','city-list-caption');
    const list = make('div',undefined,'city-options'); list.id='city-options';
    const empty = make('p','Такого города пока нет в каталоге. Попробуйте другое название.','city-no-results');
    empty.hidden=true; empty.setAttribute('role','status');
    const normalize = value => value.normalize('NFKC').trim().toLocaleLowerCase('ru-RU').replace(/ё/g,'е');
    for (const option of activeField.options) {
      const button = make('button',undefined,'city-option'); button.type='button'; button.disabled=option.disabled;
      button.setAttribute('aria-pressed',String(option.selected)); button.setAttribute('aria-label',option.textContent);
      button.dataset.search = normalize(option.textContent);
      const tone = option.value === 'Алматы' ? 'mountain' : option.value === 'Астана' ? 'capital' : 'world';
      const icon = make('span',undefined,`city-icon city-icon-${tone}`); icon.append(cityIcon(option.value));
      const copy = make('span',undefined,'city-option-copy');
      copy.append(make('strong',option.textContent),make('span',cityDescriptions[option.value] || 'Подрядчики для вашего события'));
      const check = make('span',option.selected ? '✓' : '', 'city-option-check'); check.setAttribute('aria-hidden','true');
      button.append(icon,copy,check); button.addEventListener('click',()=>choose(option.value)); list.append(button);
    }
    const available = () => [...list.querySelectorAll('button:not([hidden]):not(:disabled)')];
    search.addEventListener('input',()=>{
      const query=normalize(search.value);
      for (const button of list.children) button.hidden=!button.dataset.search.includes(query);
      empty.hidden=available().length>0;
      positionCityPicker();
    });
    search.addEventListener('keydown',event=>{
      if (event.key==='ArrowDown') {event.preventDefault();available()[0]?.focus();}
      if (event.key==='ArrowUp') {event.preventDefault();available().at(-1)?.focus();}
      if (event.key==='Enter') {event.preventDefault();const options=available();if(options.length===1)options[0].click();}
    });
    list.addEventListener('keydown',event=>{
      const options=available(), index=options.indexOf(document.activeElement);
      if(index<0)return;
      if(event.key==='ArrowDown'||event.key==='ArrowUp') {
        event.preventDefault();const next=index+(event.key==='ArrowDown'?1:-1);
        if(next<0)search.focus();else options[Math.min(next,options.length-1)]?.focus();
      } else if(event.key==='Home'||event.key==='End') {
        event.preventDefault();(event.key==='Home'?options[0]:options.at(-1))?.focus();
      }
    });
    content.replaceChildren(label,caption,list,empty);
  }
  function positionCityPicker() {
    if(!dialog.open || !dialog.classList.contains('city-picker'))return;
    if(matchMedia('(max-width:600px)').matches)return;
    const anchor=activeTrigger.closest('.search-cell').getBoundingClientRect();
    const width=Math.min(480,innerWidth-32), safeTop=96, gap=12;
    const below=innerHeight-anchor.bottom-gap-16, above=anchor.top-gap-safeTop;
    const openAbove=below<280 && above>below;
    const maxHeight=Math.max(140,Math.min(560,openAbove?above:below));
    dialog.style.setProperty('--city-width',`${width}px`);
    dialog.style.setProperty('--city-left',`${Math.max(16,Math.min(anchor.left,innerWidth-width-16))}px`);
    dialog.style.setProperty('--city-max-height',`${maxHeight}px`);
    const top=openAbove ? anchor.top-gap-Math.min(dialog.scrollHeight,maxHeight) : anchor.bottom+gap;
    dialog.style.setProperty('--city-top',`${Math.max(safeTop,Math.min(top,innerHeight-156))}px`);
  }
  function renderOptions() {
    const list = make('div',undefined,'control-options');
    for (const option of activeField.options) {
      const button = make('button',option.textContent);
      button.type = 'button'; button.disabled = option.disabled;
      button.setAttribute('aria-pressed',String(option.selected));
      button.addEventListener('click',()=>choose(option.value));
      list.append(button);
    }
    content.replaceChildren(list);
  }
  const iso = date => date.toISOString().slice(0,10);
  const parseDate = value => new Date(value+'T12:00:00Z');
  function renderCalendar(focusedValue = activeField.value || activeField.min, focusDay = false) {
    const focused = parseDate(focusedValue);
    const year = focused.getUTCFullYear(), month = focused.getUTCMonth();
    const first = new Date(Date.UTC(year,month,1,12));
    const last = new Date(Date.UTC(year,month+1,0,12));
    const nav = make('div',undefined,'calendar-nav');
    const previous = make('button','←'); previous.type='button'; previous.setAttribute('aria-label','Предыдущий месяц');
    const next = make('button','→'); next.type='button'; next.setAttribute('aria-label','Следующий месяц');
    previous.disabled = iso(first) <= activeField.min;
    next.disabled = iso(last) >= activeField.max;
    const monthTitle = make('strong',new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'}).format(first));
    monthTitle.setAttribute('aria-live','polite');
    nav.append(previous,monthTitle,next);
    const clamp = value => value < activeField.min ? activeField.min : value > activeField.max ? activeField.max : value;
    const moveMonth = amount => {
      const newDate = new Date(Date.UTC(year,month+amount,1,12));
      renderCalendar(clamp(iso(newDate)),true);
    };
    previous.addEventListener('click',()=>moveMonth(-1)); next.addEventListener('click',()=>moveMonth(1));
    const grid = make('div',undefined,'calendar-grid');
    grid.setAttribute('role','group'); grid.setAttribute('aria-label','Дни месяца');
    for (const day of ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']) grid.append(make('span',day));
    for(let i=0;i<(first.getUTCDay()+6)%7;i++) { const spacer=make('span');spacer.setAttribute('aria-hidden','true');grid.append(spacer); }
    for(let day=1;day<=last.getUTCDate();day++) {
      const date = new Date(Date.UTC(year,month,day,12));
      const value = iso(date), button = make('button',String(day)); button.type='button';
      button.disabled = value < activeField.min || value > activeField.max;
      button.dataset.date=value;
      button.tabIndex = value === focusedValue ? 0 : -1;
      button.setAttribute('aria-label',new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',weekday:'long',timeZone:'UTC'}).format(date));
      button.setAttribute('aria-pressed',String(value===activeField.value));
      button.addEventListener('click',()=>choose(value));
      button.addEventListener('keydown',event=>{
        const offset = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};
        if (Object.hasOwn(offset,event.key)) {
          event.preventDefault(); const target=parseDate(value); target.setUTCDate(target.getUTCDate()+offset[event.key]);
          renderCalendar(clamp(iso(target)),true);
        } else if(event.key==='Home'||event.key==='End') {
          event.preventDefault(); renderCalendar(clamp(iso(event.key==='Home'?first:last)),true);
        } else if(event.key==='PageUp'||event.key==='PageDown') {
          event.preventDefault(); moveMonth(event.key==='PageUp'?-1:1);
        }
      });
      grid.append(button);
    }
    const help=make('p',`Календарь каталога: ${activeField.min.split('-').reverse().join('.')} — ${activeField.max.split('-').reverse().join('.')}. Стрелки — выбор дня, Enter — подтвердить, Escape — закрыть.`,'calendar-help');
    content.replaceChildren(nav,grid,help);
    if(focusDay) grid.querySelector('[tabindex="0"]')?.focus();
  }
  function open(field,trigger) {
    if(fieldset.disabled || dialog.open) return;
    activeField=field; activeTrigger=trigger;
    const isCity=field.name==='city';
    dialog.classList.toggle('city-picker',isCity);
    trigger.closest('.search-cell').classList.toggle('is-selecting-city',isCity);
    title.textContent=isCity ? 'Где пройдёт событие?' : field.getAttribute('aria-label');
    if(isCity)renderCities();else if(field.type==='date') renderCalendar(); else renderOptions();
    trigger.setAttribute('aria-expanded','true');
    dialog.showModal();
    positionCityPicker();
    if(isCity)content.querySelector('#city-search')?.focus({preventScroll:true});
    else if(field.type==='date') content.querySelector('[tabindex="0"]')?.focus();
    else content.querySelector('[aria-pressed="true"]')?.focus();
    if(isCity)requestAnimationFrame(positionCityPicker);
  }
  if (typeof dialog.showModal === 'function') {
    for(const field of form.querySelectorAll('.search-cell select,.search-cell input[type="date"]')) {
      if(!field.hasAttribute('aria-label')) field.setAttribute('aria-label',field.parentElement.firstChild.textContent.trim());
      const trigger=make('button','Выберите','control-trigger'); trigger.type='button';
      trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-controls','control-dialog');trigger.setAttribute('aria-expanded','false');
      field.classList.add('native-control');field.tabIndex=-1;field.setAttribute('aria-hidden','true');field.after(trigger);triggers.set(field,trigger);
      trigger.addEventListener('click',()=>open(field,trigger));
      const cell = field.closest('.search-cell');
      cell.classList.add('search-cell-selectable');
      cell.addEventListener('click',event=>{
        if(trigger.contains(event.target))return;
        // Не передаём клик label скрытому нативному полю.
        event.preventDefault();
        open(field,trigger);
      });
      field.addEventListener('invalid',event=>{event.preventDefault();if(!dialog.open)open(field,trigger);});
    }
    document.querySelector('#close-control').addEventListener('click',close);
    dialog.addEventListener('close',()=>{
      activeTrigger?.setAttribute('aria-expanded','false');
      activeTrigger?.closest('.search-cell').classList.remove('is-selecting-city');
      activeTrigger?.focus({preventScroll:true});
      dialog.classList.remove('city-picker');
    });
    dialog.addEventListener('click',event=>{
      if(event.target!==dialog)return;
      const bounds=dialog.getBoundingClientRect();
      if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)close();
    });
  }
  addEventListener('resize',positionCityPicker);
  document.querySelector('.search-panel').addEventListener('transitionend',positionCityPicker);
  categoryButtons.forEach(button=>button.addEventListener('click',()=>{
    form.elements.category.value=button.dataset.category;emitChange(form.elements.category);sync();form.requestSubmit();
  }));
  form.addEventListener('input',sync);form.addEventListener('change',sync);
  document.addEventListener('click',()=>queueMicrotask(sync));
  new MutationObserver(sync).observe(fieldset,{attributes:true,attributeFilter:['disabled']});
  sync();
  const header=document.querySelector('.topbar');
  let frame=0;
  addEventListener('scroll',()=>{if(!frame)frame=requestAnimationFrame(()=>{header.classList.toggle('is-scrolled',scrollY>12);positionCityPicker();frame=0;});},{passive:true});
  if('IntersectionObserver' in window&&!reducedMotion.matches){
    const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.replace('reveal-pending','reveal-ready');observer.unobserve(entry.target);}}),{threshold:.05});
    document.querySelectorAll('.intro,.search-panel,.how-it-works').forEach(item=>{item.classList.add('reveal-pending');observer.observe(item);});
  }
  const panel=document.querySelector('.results-panel');
  let wasBusy=false;
  new MutationObserver(()=>{
    const busy=panel.getAttribute('aria-busy')==='true';
    if(wasBusy&&!busy&&matchMedia('(max-width:600px)').matches)panel.scrollIntoView({behavior:reducedMotion.matches?'instant':'smooth',block:'start'});
    wasBusy=busy;
  }).observe(panel,{attributes:true,attributeFilter:['aria-busy']});
})();
