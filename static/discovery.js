(() => {
  'use strict';
  const root = document.querySelector('[data-discovery]');
  if (!root) return;
  const cards = [...root.querySelectorAll('[data-card]')];
  const navigation = root.querySelector('[data-deck-controls]');
  const controls = root.querySelector('[data-view-controls]');
  let index = 0;
  let view = 'deck';
  function render(focus = false) {
    cards.forEach((card, position) => {
      card.hidden = view === 'deck' && position !== index;
      card.tabIndex = -1;
    });
    navigation.hidden = view === 'list';
    navigation.querySelector('[data-previous]').disabled = index === 0;
    navigation.querySelector('[data-next]').disabled = index === cards.length - 1;
    navigation.querySelector('[data-card-status]').textContent = `${index + 1} de ${cards.length} en esta página`;
    controls.querySelectorAll('[data-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === view)));
    if (focus && cards[index]) cards[index].focus({preventScroll: true});
  }
  function move(delta, focus = false) {
    index = Math.max(0, Math.min(cards.length - 1, index + delta));
    render(focus);
  }
  if (cards.length && navigation && controls) {
    controls.hidden = false;
    navigation.querySelector('[data-previous]').addEventListener('click', () => move(-1, true));
    navigation.querySelector('[data-next]').addEventListener('click', () => move(1, true));
    controls.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
      view = button.dataset.view;
      render();
    }));
    root.addEventListener('keydown', event => {
      if (view !== 'deck' || !event.target.matches('[data-card]')) return;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault();
        move(event.key === 'ArrowRight' ? 1 : -1, true);
      }
    });
    render();
  }
  const dialog = document.querySelector('[data-invite-dialog]');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  let origin = null;
  let content = null;
  root.querySelectorAll('[data-invite]').forEach(details => {
    details.querySelector('summary').addEventListener('click', event => {
      event.preventDefault();
      origin = details;
      content = details.querySelector('[data-invite-content]');
      dialog.querySelector('[data-dialog-body]').append(content);
      dialog.showModal();
      dialog.querySelector('[data-close-dialog]').focus();
    });
  });
  dialog.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => {
    if (origin && content) {
      origin.append(content);
      origin.querySelector('summary').focus();
    }
    origin = null;
    content = null;
  });
})();
