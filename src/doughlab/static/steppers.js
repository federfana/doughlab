/* Frecce ± fuori dal campo per ogni input numerico (su iPhone i campi numerici non hanno frecce proprie).
   Funziona anche sui campi creati dopo (schede delle fasi, moduli caricati da HTMX, template di Alpine).
   I campi che hanno già le loro frecce (.number-stepper) non vengono toccati. */
(function () {
  // Quanto cambia ogni pressione. Per nome del campo, poi per classe; altrimenti `data-increment`, `step` o 1.
  const BY_NAME = {
    n_panetti: 1, panetto_g: 5, hydration_pct: 1, salt_pct: 0.5, oil_pct: 1, sugar_pct: 1,
    preferment_pct: 5, preferment_hydration_pct: 1, preferment_yeast_pct: 5,
    initial_dough_c: 1, flour_c: 1, room_c: 1, fridge_c: 1,
    hydration: 1, flour_w: 10, protein: 0.5, dough_ball_count: 1, dough_ball_weight: 5,
    cold_hours: 1, room_hours: 1, dough_temp: 1, bake_temp: 10,
    w: 10, pl: 0.05, hydration_min: 1, hydration_max: 1, stock_g: 100,
  };
  const BY_CLASS = { 'dur-h': 1, 'dur-m': 5 };

  function stepFor(input) {
    if (input.dataset.increment) return Number(input.dataset.increment);
    if (BY_NAME[input.name] !== undefined) return BY_NAME[input.name];
    if (/^flour_pct_\d+$/.test(input.name) || /percentuale della farina/i.test(input.getAttribute('aria-label') || '')) return 5;
    if (/^phase_ambient_/.test(input.name)) return 1;
    for (const cls of Object.keys(BY_CLASS)) if (input.classList.contains(cls)) return BY_CLASS[cls];
    const declared = Number(input.getAttribute('step'));
    return declared > 0 ? declared : 1;
  }

  function labelFor(input) {
    const own = input.getAttribute('aria-label');
    if (own) return own.charAt(0).toLowerCase() + own.slice(1);
    const lab = input.closest('label')?.querySelector('.lab');
    return (lab ? lab.textContent : input.placeholder || 'valore').trim().toLowerCase();
  }

  const format = (n) => String(n).replace('.', ',');

  // Campi con direttive di Alpine: spostarli dopo che Alpine li ha inizializzati li romperebbe, quindi si
  // sistemano solo prima (pagina appena caricata, contenuto di HTMX appena inserito) o a mano nel template.
  const hasAlpine = (input) => [...input.attributes].some((a) => /^(x-|:|@)/.test(a.name));

  function enhance(input, early) {
    if (input.closest('.number-stepper') || input.dataset.noStepper !== undefined) return;
    if (!early && hasAlpine(input)) return;
    if (input.disabled || input.readOnly) return;
    const step = stepFor(input);
    const wrapper = document.createElement('span');
    wrapper.className = 'number-stepper';
    const controls = document.createElement('span');
    controls.className = 'number-stepper-controls';
    const name = labelFor(input);
    for (const [sign, arrow, verb] of [[1, '↑', 'Aumenta'], [-1, '↓', 'Riduci']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = arrow;
      button.dataset.delta = String(sign * step);
      button.setAttribute('aria-label', `${verb} ${name} di ${format(step)}`);
      button.title = `${verb} di ${format(step)}`;
      controls.append(button);
    }
    input.before(wrapper);
    wrapper.append(input, controls);
    input.dataset.stepperStep = String(step);
  }

  function adjust(input, delta) {
    const min = input.min === '' ? -Infinity : Number(input.min);
    const max = input.max === '' ? Infinity : Number(input.max);
    const current = Number(String(input.value).replace(',', '.')) || 0;
    const next = Math.min(max, Math.max(min, current + delta));
    input.value = String(Number(next.toFixed(3)));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    // Le durate si normalizzano al `change` (60 min diventano 1 h).
    if (input.getAttribute('onchange') || input.dataset.change) input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function enhanceAll(root, early) {
    if (root.matches && root.matches('input[type="number"]')) enhance(root, early);
    if (root.querySelectorAll) root.querySelectorAll('input[type="number"]').forEach((input) => enhance(input, early));
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('.number-stepper-controls button[data-delta]');
    if (!button) return;
    const input = button.closest('.number-stepper').querySelector('input');
    if (input) adjust(input, Number(button.dataset.delta));
  });
  document.addEventListener('keydown', (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.dataset.stepperStep) return;
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    adjust(input, (event.key === 'ArrowUp' ? 1 : -1) * Number(input.dataset.stepperStep));
  });

  enhanceAll(document, true);
  // HTMX avvisa di ogni elemento nuovo (`htmx:load`) subito dopo averlo inserito, prima che Alpine lo elabori.
  document.body.addEventListener('htmx:load', (event) => event.target && enhanceAll(event.target, true));
  new MutationObserver((mutations) => {
    for (const mutation of mutations) mutation.addedNodes.forEach((node) => { if (node.nodeType === 1) enhanceAll(node, false); });
  }).observe(document.body, { childList: true, subtree: true });
})();
