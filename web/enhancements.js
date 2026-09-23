// Улучшения представления. Значения полей и контракт API остаются прежними.
(() => {
  const form = document.querySelector('#search');
  const budget = form.elements.namedItem('budget');
  const wrapper = document.createElement('span');
  wrapper.className = 'budget-wrap';
  budget.before(wrapper); wrapper.append(budget);
  const display = document.createElement('span');
  display.className = 'budget-display'; display.setAttribute('aria-hidden', 'true');
  wrapper.append(display);
  const mobile = document.querySelector('#mobile-submit');
  function sync() {
    display.textContent = budget.value === '' ? '' : `${Number(budget.value).toLocaleString('ru-RU')} ₸`;
    mobile.disabled = document.querySelector('#fields').disabled;
    mobile.firstElementChild.textContent = document.querySelector('#submit span').textContent;
  }
  form.addEventListener('input', sync);
  form.addEventListener('change', sync);
  document.addEventListener('click', () => queueMicrotask(sync));
  new MutationObserver(sync).observe(document.querySelector('#fields'), {attributes:true, attributeFilter:['disabled']});
  sync();
  if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.replace('reveal-pending','reveal-ready');
      observer.unobserve(entry.target);
    }), {threshold:0.06});
    document.querySelectorAll('.intro,.trust-strip,.search-panel,.results-panel').forEach(item => {
      item.classList.add('reveal-pending'); observer.observe(item);
    });
  }
})();
