// Переключение меняет только оформление, не форму, запросы или результаты.
(() => {
  const descriptions = {
    atelier: 'Светлый каталог, тёплые акценты и удобный поиск.',
    signal: 'Графитовый фон, лаймовый акцент, чёткая геометрия.'
  };
  function applyDesign(design) {
    if (!Object.hasOwn(descriptions, design)) design = 'atelier';
    document.documentElement.dataset.design = design;
    document.querySelector('#design-description').textContent = descriptions[design];
    document.querySelectorAll('[data-design-choice]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.designChoice === design));
    });
    document.querySelector('meta[name="theme-color"]').content = design === 'signal' ? '#111720' : '#ffffff';
  }
  let saved = 'atelier';
  try { saved = localStorage.getItem('bimteam.design') || saved; } catch { /* Хранилище необязательно. */ }
  applyDesign(saved);
  document.querySelectorAll('[data-design-choice]').forEach(button => button.addEventListener('click', () => {
    const design = button.dataset.designChoice;
    applyDesign(design);
    try { localStorage.setItem('bimteam.design', design); } catch { /* Оформление всё равно применяется. */ }
  }));
})();
