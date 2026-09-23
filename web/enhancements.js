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
    if(fieldset.disabled) return;
    activeField=field; activeTrigger=trigger;
    title.textContent=field.getAttribute('aria-label');
    if(field.type==='date') renderCalendar(); else renderOptions();
    trigger.setAttribute('aria-expanded','true');
    dialog.showModal();
    if(field.type==='date') content.querySelector('[tabindex="0"]')?.focus();
    else content.querySelector('[aria-pressed="true"]')?.focus();
  }
  if (typeof dialog.showModal === 'function') {
    for(const field of form.querySelectorAll('.search-cell select,.search-cell input[type="date"]')) {
      if(!field.hasAttribute('aria-label')) field.setAttribute('aria-label',field.parentElement.firstChild.textContent.trim());
      const trigger=make('button','Выберите','control-trigger'); trigger.type='button';
      trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-controls','control-dialog');trigger.setAttribute('aria-expanded','false');
      field.classList.add('native-control');field.tabIndex=-1;field.setAttribute('aria-hidden','true');field.after(trigger);triggers.set(field,trigger);
      trigger.addEventListener('click',()=>open(field,trigger));
      field.addEventListener('invalid',event=>{event.preventDefault();if(!dialog.open)open(field,trigger);});
    }
    document.querySelector('#close-control').addEventListener('click',close);
    dialog.addEventListener('close',()=>{activeTrigger?.setAttribute('aria-expanded','false');activeTrigger?.focus();});
    dialog.addEventListener('click',event=>{
      if(event.target!==dialog)return;
      const bounds=dialog.getBoundingClientRect();
      if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)close();
    });
  }
  categoryButtons.forEach(button=>button.addEventListener('click',()=>{
    form.elements.category.value=button.dataset.category;emitChange(form.elements.category);sync();form.requestSubmit();
  }));
  form.addEventListener('input',sync);form.addEventListener('change',sync);
  document.addEventListener('click',()=>queueMicrotask(sync));
  new MutationObserver(sync).observe(fieldset,{attributes:true,attributeFilter:['disabled']});
  sync();
  const header=document.querySelector('.topbar');
  let frame=0;
  addEventListener('scroll',()=>{if(!frame)frame=requestAnimationFrame(()=>{header.classList.toggle('is-scrolled',scrollY>12);frame=0;});},{passive:true});
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
