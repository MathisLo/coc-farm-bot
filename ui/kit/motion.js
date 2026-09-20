/* UI-only helpers. Values must come from the real backend. No automatic polling. */
(function (global) {
  'use strict';
  const states = new WeakMap();
  const toastClosers = new WeakMap();
  const format = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
  const reduced = () => Boolean(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);

  function countTo(element, value, options = {}) {
    if (!element || typeof element.textContent === 'undefined') throw new TypeError('A DOM element is required');
    if (!Number.isSafeInteger(value) || value < 0) throw new TypeError('Value must be a non-negative safe integer');
    let state = states.get(element);
    if (state && state.frame) global.cancelAnimationFrame(state.frame);
    const from = state ? state.value : value;
    const duration = Number.isFinite(options.duration) ? Math.max(0, Math.min(600, options.duration)) : 320;
    state = { value: from, frame: null };
    states.set(element, state);
    const render = (n) => { state.value = n; element.textContent = format.format(Math.round(n)); };
    // First value, reset, hidden document and reduced motion: show the true value immediately.
    if (from >= value || duration === 0 || reduced() || document.hidden) { render(value); return; }
    const start = global.performance.now();
    function step(now) {
      if (!element.isConnected || document.hidden || reduced()) { state.frame = null; render(value); return; }
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      render(from + (value - from) * (1 - Math.pow(1 - t, 3)));
      if (t < 1) state.frame = global.requestAnimationFrame(step);
      else { state.frame = null; render(value); }
    }
    state.frame = global.requestAnimationFrame(step);
  }

  function toast(host, message, { level = 'info', duration } = {}) {
    if (!host || typeof message !== 'string') throw new TypeError('A host and a text message are required');
    if (!['info', 'success', 'warning', 'error'].includes(level)) throw new TypeError('Unknown notification level');
    host.classList.add('coc-toast-host');
    const item = document.createElement('div');
    item.className = 'coc-toast'; item.dataset.level = level;
    item.setAttribute('role', level === 'error' ? 'alert' : 'status');
    const text = document.createElement('span'); text.textContent = message;
    const close = document.createElement('button'); close.type = 'button'; close.className = 'coc-toast__close';
    close.setAttribute('aria-label', 'Fermer la notification'); close.textContent = '\u00D7';
    let timer;
    const dismiss = () => { global.clearTimeout(timer); toastClosers.delete(item); item.remove(); };
    toastClosers.set(item, dismiss);
    close.addEventListener('click', dismiss, { once: true });
    item.append(text, close); host.appendChild(item);
    // Keep the stack bounded. Important errors also stay in the application's persistent logs.
    while (host.children.length > 4) {
      const first = host.firstElementChild;
      const remove = toastClosers.get(first);
      if (remove) remove(); else first.remove();
    }
    const delay = duration === undefined ? (level === 'error' ? 0 : 4500) : duration;
    if (Number.isFinite(delay) && delay > 0) timer = global.setTimeout(dismiss, delay);
    return dismiss;
  }

  function setBusy(button, busy) {
    if (!button || button.tagName !== 'BUTTON') throw new TypeError('A button is required');
    button.dataset.busy = String(Boolean(busy));
    button.setAttribute('aria-busy', String(Boolean(busy)));
    // Never decide whether Stop or Launch is allowed here: the real controller owns disabled states.
  }

  global.CoCUI = Object.freeze({ countTo, toast, setBusy });
})(window);
