/* Functional icons use the SVG sprite supplied with the official asset kit. */
(() => {
  const names = new Set(['console','chart','profiles','user','settings','tools','activity','refresh','play','stop','pause','save','capture','crosshair','export','file','chevron-down','chevron-right','check','close','info','warning','error','wall','search','copy','clock','folder','shield','zoom']);
  const aliases = {
    'shield-swords':'shield', hexagon:'shield', swords:'wall', wrench:'tools',
    'user-round-search':'profiles', 'file-down':'export', monitor:'capture',
    'arrow-right':'chevron-right', hammer:'tools', castle:'wall', repeat:'refresh',
    square:'stop', trash:'error', upload:'folder', 'rotate-ccw':'refresh',
    x:'close', 'triangle-alert':'warning', coins:'chart', 'alert-circle':'error',
    'check-circle':'check'
  };
  function icon(name) {
    const resolved=aliases[name] || name;
    const id=names.has(resolved)?resolved:'info';
    return `<img class="icon" src="assets/kit/icons-ui/${id}.svg" alt="" aria-hidden="true">`;
  }
  function hydrate(root=document) {
    root.querySelectorAll('[data-icon]').forEach(element=>{element.innerHTML=icon(element.dataset.icon);});
  }
  window.CoCIcons=Object.freeze({icon,hydrate});
})();
