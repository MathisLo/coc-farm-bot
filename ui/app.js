(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const all = (selector, root=document) => [...root.querySelectorAll(selector)];
  const format = value => Number.isFinite(Number(value)) ? new Intl.NumberFormat('fr-FR').format(Number(value)) : '—';
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const fields = ['window_title','min_gold','min_elixir','loot_margin','electrodragon_count','dragon_count','rage_count','hero_count','delay_between_dragons','and_rule','dry_run','upgrade_wall','upgrade_recommended','upgrade_heroes','chain_attacks'];
  const pageTitles = {
    console:['CONSOLE','Pilote de raid','Automatisez vos raids, maximisez vos ressources'],
    statistics:['STATISTIQUES','Statistiques','Suivez les résultats de vos raids'],
    profiles:['PROFILS','Profils','Consultez le compte actif'],
    tools:['OUTILS','Outils','Lecture, calibrage et diagnostic'],
    parameters:['PARAMÈTRES','Paramètres','Gérez les réglages du bot']
  };
  const state = {
    connected:false, dirty:false, busy:false, page:'console', savedValues:{}, stats:null,
    profile:null, profileKey:'', logSeq:-1, previewRevision:-1, pendingJob:null,
    windowsKey:'', calibration:null, calibrationImageRevision:-1, pollTimer:null,
    lastConnectionErrorAt:0
  };

  CoCIcons.hydrate();

  function toast(message, kind='success') {
    CoCUI.toast($('toast-region'),message,{level:kind});
  }

  async function api(name,payload={}) {
    try {
      const result=await window.pywebview.api.call(name,payload);
      if (!result || typeof result!=='object') throw new Error('Réponse invalide du moteur');
      return result;
    } catch (error) {
      console.error('Backend',name,error);
      const uncertain=error?.name==='TimeoutError' || /timed?\s*out|timeout/i.test(String(error));
      if (Date.now()-state.lastConnectionErrorAt>10000) {
        toast(uncertain?'Confirmation en attente. Synchronisation avec le moteur…':'Erreur de communication avec le moteur Python.',uncertain?'warning':'error');
        state.lastConnectionErrorAt=Date.now();
      }
      return {ok:false,uncertain,notified:true,error:uncertain?'Confirmation en attente.':'Erreur de communication avec le moteur Python.'};
    }
  }

  function setLoading(button,on,text=null) {
    if (!button) return;
    if (on) {
      if (!button.dataset.originalHtml) button.dataset.originalHtml=button.innerHTML;
      button.classList.add('is-loading');
      button.disabled=true;
      if (text) button.innerHTML=`${CoCIcons.icon('refresh')}<span>${text}</span>`;
    } else {
      button.classList.remove('is-loading');
      if (button.dataset.originalHtml) {button.innerHTML=button.dataset.originalHtml;delete button.dataset.originalHtml;}
      button.disabled=false;
    }
  }

  function values() {
    const result={};
    for (const name of fields) {
      const input=document.querySelector(`[data-field="${name}"]`);
      result[name]=input.type==='checkbox'?input.checked:input.value;
    }
    return result;
  }

  function validateFields() {
    for (const name of fields) {
      const input=document.querySelector(`[data-field="${name}"]`);
      if (input.type==='number' && (!input.value.trim() || !input.checkValidity())) {
        input.focus();
        showPage('console');
        activateTab(document.querySelector('[data-tabs="settings"]'),input.closest('[data-panel]').dataset.panel);
        toast('Corrigez la valeur indiquée avant de continuer.','warning');
        return false;
      }
    }
    return true;
  }

  function fillFields(saved) {
    for (const name of fields) {
      if (name==='window_title') continue;
      const input=document.querySelector(`[data-field="${name}"]`);
      if (!input || (state.dirty && state.connected)) continue;
      if (input.type==='checkbox') input.checked=Boolean(saved[name]);
      else input.value=saved[name] ?? '';
    }
  }

  function updateWindows(list,selected) {
    const select=$('window_title');
    const current=select.value;
    const display=[...list];
    const key=JSON.stringify(display);
    if (key!==state.windowsKey) {
      state.windowsKey=key;
      select.replaceChildren();
      if (!display.length) {
        const opt=new Option('Aucune fenêtre Clash détectée','');select.add(opt);
      } else display.forEach(title=>select.add(new Option(title,title)));
    }
    if (state.dirty && display.includes(current)) select.value=current;
    else if (selected && display.includes(selected)) select.value=selected;
    else if (display.length) select.value=display[0];
  }

  function animateValue(element,from,to) {
    if (!Number.isSafeInteger(to) || to<0) {element.textContent='—';return;}
    CoCUI.countTo(element,to,{duration:from===null?0:320});
  }

  function updateStats(stats,pending) {
    for (const key of ['gold','elixir','dark_elixir']) {
      const previous=state.stats?.[key] ?? null;
      animateValue($(`stat-${key}`),previous,stats[key]);
      if (previous!==null && stats[key]>previous) {
        const card=document.querySelector(`[data-resource="${key}"]`);
        card.classList.remove('is-gaining');void card.offsetWidth;card.classList.add('is-gaining');
        setTimeout(()=>card.classList.remove('is-gaining'),600);
      }
    }
    document.querySelector('[data-stat="battles"]').textContent=format(stats.battles);
    for (const key of ['gold','elixir','dark_elixir']) {
      document.querySelector(`[data-average="${key}"]`).textContent=stats.battles?format(Math.round(stats[key]/stats.battles)):'—';
    }
    $('battle-summary').textContent=`${format(stats.battles)} combat(s) comptabilisé(s) · cumul sauvegardé`;
    $('pending-battle').hidden=!pending;
    state.stats=stats;
  }

  function updateProfile(profile) {
    const key=JSON.stringify(profile);
    if (key===state.profileKey) return;
    state.profileKey=key;state.profile=profile;
    $('profile-empty').hidden=Boolean(profile);
    $('profile-detail').hidden=!profile;
    if (!profile) return;
    for (const el of all('[data-profile]')) {
      const name=el.dataset.profile,value=profile[name];
      if (name==='captured_at') el.textContent=Number.isFinite(Number(value))?new Date(Number(value)*1000).toLocaleString('fr-FR'):'—';
      else if (typeof value==='number') el.textContent=format(value);
      else el.textContent=value || '—';
    }
  }

  function updateLogs(logs,seq) {
    if (seq===state.logSeq || !Array.isArray(logs)) return;
    const oldSeq=state.logSeq;state.logSeq=seq;
    const host=$('journal');
    const follow=oldSeq<0 || host.scrollHeight-host.scrollTop-host.clientHeight<32;
    const previousScroll=host.scrollTop;
    host.replaceChildren();
    if (!logs.length) {
      const empty=document.createElement('div');empty.className='empty-journal';empty.textContent='Aucun événement pour cette session.';host.append(empty);return;
    }
    logs.forEach((entry,index)=>{
      const row=document.createElement('div');row.className='log-entry';row.dataset.level=entry.level || 'info';
      if (oldSeq>=0 && index===logs.length-1) row.classList.add('is-new');
      const time=document.createElement('time');time.className='log-time';
      const parsed=new Date(entry.time);time.textContent=Number.isNaN(parsed.valueOf())?'—':parsed.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
      const kind=document.createElement('span');kind.className='log-type';kind.textContent=entry.type || 'INFO';
      const message=document.createElement('span');message.textContent=entry.message || '';
      row.append(time,kind,message);host.append(row);
    });
    host.scrollTop=follow?host.scrollHeight:previousScroll;
  }

  function updatePreview(data,revision) {
    if (!data || revision===state.previewRevision) return;
    state.previewRevision=revision;
    const image=new Image();image.alt='Dernière capture du jeu';image.style.opacity='0';
    image.onload=()=>{
      const host=$('preview-area');
      const previous=host.querySelector('img');
      if (previous) previous.classList.add('preview-old');
      else host.replaceChildren();
      image.className='preview-current';host.append(image);
      requestAnimationFrame(()=>{image.style.opacity='1';if (previous) previous.style.opacity='0';});
      if (previous) setTimeout(()=>previous.remove(),200);
      if (state.calibration && $('calibration-dialog').open && revision!==state.calibrationImageRevision) {
        state.calibrationImageRevision=revision;
        setCalibrationImage(data);
      }
    };
    image.src=data;
  }

  function updateSummaries(v) {
    $('summary-loot').textContent=`Or ${format(v.min_gold)} · Élixir ${format(v.min_elixir)} · marge ${v.loot_margin} % · ${v.and_rule?'deux ressources':'une ressource'}`;
    $('summary-army').textContent=`${v.electrodragon_count} électrodragons · ${v.dragon_count} dragons · ${v.rage_count} Rage · ${v.hero_count} héros · ${v.delay_between_dragons} ms`;
    const flags=[];
    if (v.chain_attacks) flags.push('attaques enchaînées');
    if (v.upgrade_recommended) flags.push('bâtiments');
    if (v.upgrade_recommended && v.upgrade_heroes) flags.push('héros');
    if (v.upgrade_wall) flags.push('remparts');
    if (v.dry_run) flags.push('simulation');
    $('summary-cycle').textContent=flags.length?flags.join(' · '):'Aucune action automatique supplémentaire';
  }

  function updateRunningUi(snapshot) {
    const running=snapshot.busy;
    state.busy=running;
    const badge=$('run-state');badge.textContent=snapshot.run_state;
    const stateName=({'PRÊT':'ready','EN COURS':'running','LECTURE':'reading','ARRÊT':'stopped','ERREUR':'error'})[snapshot.run_state] || 'ready';
    badge.dataset.state=stateName;
    $('status-text').textContent=snapshot.status;
    document.querySelector('.command-status').dataset.state=stateName;
    for (const button of all('[data-action]')) {
      const action=button.dataset.action;
      if (action==='export') continue;
      if (action==='stop') button.disabled=!running;
      else if (!button.classList.contains('is-loading')) button.disabled=running;
    }
    const start=document.querySelector('.command-actions [data-action="start"]');
    if (!start.classList.contains('is-loading')) {
      start.innerHTML=CoCIcons.icon('play')+`<span>${running&&stateName==='running'?'Cycle en cours':'Lancer le cycle'}</span>`;
    }
  }

  function finishPending(snapshot) {
    const job=state.pendingJob;
    if (!job) return;
    if (snapshot.busy) {job.seenBusy=true;return;}
    if (!job.seenBusy && Date.now()-job.started<1200) return;
    if (job.name==='stop') {
      toast(snapshot.run_state==='ERREUR'?'Le cycle s’est arrêté avec une erreur.':'Opération arrêtée.',snapshot.run_state==='ERREUR'?'error':'success');
    } else if (snapshot.run_state==='ERREUR') {
      toast('L’opération a échoué. Exportez le diagnostic pour le détail.','error');
    } else if (job.name==='profile') {
      const changed=snapshot.profile?.captured_at!==job.profileTime && snapshot.profile?.captured_at;
      toast(changed?'Profil relevé.':'Aucun nouveau profil relevé.',changed?'success':'warning');
    } else if (job.name==='inspect' || job.name==='calibration_capture') {
      const changed=snapshot.preview_revision>job.previewRevision;
      toast(changed?'Capture actualisée.':'Aucune nouvelle capture disponible.',changed?'success':'warning');
    }
    const button=document.querySelector(`[data-action="${job.name}"]`);
    if (button) setLoading(button,false);
    state.pendingJob=null;
  }

  function render(snapshot) {
    if (snapshot.ok===false) {
      if (!snapshot.notified && Date.now()-state.lastConnectionErrorAt>10000) {
        toast(snapshot.error||'Erreur de communication avec le moteur Python.','error');
        state.lastConnectionErrorAt=Date.now();
      }
      return;
    }
    for (const el of all('[data-version]')) el.textContent=`v${snapshot.version}`;
    updateWindows(snapshot.windows,snapshot.values.window_title);
    fillFields(snapshot.values);
    state.savedValues=snapshot.values;
    updateStats(snapshot.stats,snapshot.pending_battle);
    updateProfile(snapshot.profile);
    updateLogs(snapshot.logs,snapshot.log_seq);
    updatePreview(snapshot.preview,snapshot.preview_revision);
    updateSummaries(snapshot.values);
    $('calibration-count').textContent=format(snapshot.calibration_count);
    updateRunningUi(snapshot);
    finishPending(snapshot);
    state.connected=true;
  }

  async function pollOnce() {
    const snapshot=await api('snapshot',{log_seq:state.logSeq,preview_revision:state.previewRevision});
    render(snapshot);
    return snapshot;
  }
  async function poll() {
    await pollOnce();
    state.pollTimer=setTimeout(poll,1000);
  }

  function updateIndicator(group) {
    const active=group.querySelector('.tab.is-active'),indicator=group.querySelector('.tab-indicator');
    if (!active || !indicator) return;
    indicator.style.width=`${active.offsetWidth}px`;
    indicator.style.transform=`translateX(${active.offsetLeft}px)`;
  }
  function activateTab(group,name) {
    for (const button of all('.tab',group)) {
      const active=button.dataset.tab===name;
      button.classList.toggle('is-active',active);
      button.setAttribute('aria-selected',String(active));
    }
    updateIndicator(group);
    if (group.dataset.tabs==='settings') {
      for (const panel of all('[data-panel]')) {const active=panel.dataset.panel===name;panel.hidden=!active;panel.classList.toggle('is-active',active);}
    } else {
      for (const panel of all('[data-activity]')) {const active=panel.dataset.activity===name;panel.hidden=!active;panel.classList.toggle('is-active',active);}
      $('activity-caption').textContent=({journal:'Événements du cycle',preview:'Dernière capture du jeu',actions:'Actions ponctuelles'})[name];
    }
  }

  function showPage(name) {
    if (!pageTitles[name]) return;
    state.page=name;
    for (const nav of all('.nav-link')) {
      const active=nav.dataset.page===name;
      nav.classList.toggle('is-active',active);
      if (active) nav.setAttribute('aria-current','page');else nav.removeAttribute('aria-current');
    }
    for (const page of all('.page-view')) {
      const active=page.id===`page-${name}`;
      page.hidden=!active;page.classList.toggle('is-active',active);
    }
    const title=pageTitles[name];
    $('breadcrumb-page').textContent=title[0];$('page-title').textContent=title[1];$('page-subtitle').textContent=title[2];
    requestAnimationFrame(()=>all('.tabs').forEach(updateIndicator));
  }

  async function perform(name,button) {
    if (name==='calibrate') {await openCalibration();return;}
    if (name==='reset') {$('reset-dialog').showModal();return;}
    if (name==='stop' && !state.busy) return;
    if (state.busy && !['stop','export'].includes(name)) return;
    const needsValues=['save','start','walls','attack','buildings'].includes(name);
    if (needsValues && !validateFields()) return;
    const payload=needsValues?{values:values()}:{};
    const labels={refresh:'Recherche…',save:'Enregistrement…',start:'Lancement…',stop:'Arrêt…',inspect:'Lecture…',profile:'Analyse…',calibration_capture:'Capture…',export:'Export…'};
    setLoading(button,true,labels[name]||'Exécution…');
    if (name==='inspect') activateTab(document.querySelector('[data-tabs="activity"]'),'preview');
    const before={previewRevision:state.previewRevision,profileTime:state.profile?.captured_at || null};
    const response=await api(name,payload);
    if (!response.ok) {
      setLoading(button,false);
      if (!response.cancelled && !response.uncertain && !response.notified) toast(response.error||'Action impossible. Consultez le diagnostic.','error');
      await pollOnce();return;
    }
    if (needsValues) state.dirty=false;
    if (name==='refresh') toast(response.count?`${response.count} fenêtre(s) Clash détectée(s).`:'Aucune fenêtre Clash détectée.',response.count?'success':'warning');
    else if (name==='save') toast('Configuration enregistrée.');
    else if (name==='start') toast('Cycle lancé.');
    else if (name==='walls') toast('Amélioration des remparts lancée.');
    else if (name==='attack') toast('Attaque ponctuelle lancée.');
    else if (name==='buildings') toast('Amélioration des bâtiments lancée.');
    else if (name==='export') toast('Diagnostic exporté.');
    if (['profile','inspect','calibration_capture','stop'].includes(name)) {
      state.pendingJob={name,started:Date.now(),seenBusy:name==='stop',...before};
    } else setLoading(button,false);
    await pollOnce();
  }

  function closeDialog(dialog) {if (dialog?.open) dialog.close();}
  async function openCalibration() {
    const info=await api('calibration_info');
    if (!info.ok) {toast(info.error||'Calibrage indisponible.','error');return;}
    state.calibration={defaults:info.defaults,labels:info.labels,overrides:structuredClone(info.overrides),ratio:info.ratio};
    const select=$('calibration-key');select.replaceChildren();
    for (const key of Object.keys(info.defaults)) select.add(new Option(info.labels[key]||key,key));
    state.calibrationImageRevision=info.preview_revision;
    if (info.preview) setCalibrationImage(info.preview);
    else {$('calibration-image-wrap').hidden=true;$('calibration-preview').querySelector('.empty-state').hidden=false;}
    updateCalibrationMarker();
    $('calibration-dialog').showModal();
  }

  function setCalibrationImage(source) {
    const image=$('calibration-image');
    image.onload=()=>{
      $('calibration-image-wrap').hidden=false;
      $('calibration-preview').querySelector('.empty-state').hidden=true;
      state.calibration.ratio=image.naturalWidth/image.naturalHeight;
      updateCalibrationMarker();
    };
    image.src=source;
  }

  function updateCalibrationMarker(draft=null) {
    if (!state.calibration) return;
    const key=$('calibration-key').value;
    const values=draft||state.calibration.overrides[key]||state.calibration.defaults[key];
    if (!values) return;
    const overlay=$('calibration-overlay');overlay.replaceChildren();
    const namespace='http://www.w3.org/2000/svg';
    const element=document.createElementNS(namespace,values.length===2?'circle':'rect');
    if (values.length===2) {
      element.setAttribute('cx',values[0]);element.setAttribute('cy',values[1]);element.setAttribute('r','1.2');
    } else {
      element.setAttribute('x',values[0]);element.setAttribute('y',values[1]);
      element.setAttribute('width',Math.max(.1,values[2]-values[0]));element.setAttribute('height',Math.max(.1,values[3]-values[1]));
    }
    element.setAttribute('stroke','#f6c244');element.setAttribute('stroke-width','.45');element.setAttribute('fill','#f6c24420');
    element.setAttribute('vector-effect','non-scaling-stroke');overlay.append(element);
    $('calibration-coordinates').textContent=values.map(v=>`${Number(v).toFixed(2)} %`).join('  /  ');
    $('calibration-instruction').textContent=values.length===2?'Cliquez sur le nouveau point de clic.':'Tracez un rectangle autour de la zone à lire.';
  }

  function positionFromEvent(event) {
    const rect=$('calibration-overlay').getBoundingClientRect();
    return [Math.min(100,Math.max(0,(event.clientX-rect.left)*100/rect.width)),
            Math.min(100,Math.max(0,(event.clientY-rect.top)*100/rect.height))];
  }
  let dragStart=null;
  const overlay=$('calibration-overlay');
  overlay.addEventListener('pointerdown',event=>{if (!state.calibration) return;dragStart=positionFromEvent(event);overlay.setPointerCapture(event.pointerId);event.preventDefault();});
  overlay.addEventListener('pointermove',event=>{
    if (!dragStart || !state.calibration) return;
    const key=$('calibration-key').value;
    if (state.calibration.defaults[key].length!==4) return;
    const end=positionFromEvent(event);
    updateCalibrationMarker([Math.min(dragStart[0],end[0]),Math.min(dragStart[1],end[1]),Math.max(dragStart[0],end[0]),Math.max(dragStart[1],end[1])]);
  });
  overlay.addEventListener('pointerup',event=>{
    if (!dragStart || !state.calibration) return;
    const key=$('calibration-key').value,end=positionFromEvent(event),first=dragStart;dragStart=null;
    const values=state.calibration.defaults[key].length===2?end:
      [Math.min(first[0],end[0]),Math.min(first[1],end[1]),Math.max(first[0],end[0]),Math.max(first[1],end[1])];
    if (values.length===4 && (values[2]-values[0]<.05 || values[3]-values[1]<.05)) {updateCalibrationMarker();return;}
    state.calibration.overrides[key]=values;updateCalibrationMarker();
  });
  $('calibration-key').addEventListener('change',()=>updateCalibrationMarker());
  $('calibration-reset').addEventListener('click',()=>{
    if (!state.calibration) return;
    delete state.calibration.overrides[$('calibration-key').value];updateCalibrationMarker();
  });
  $('calibration-file').addEventListener('change',event=>{
    const file=event.target.files?.[0];if (!file || !state.calibration) return;
    if (!['image/png','image/jpeg'].includes(file.type)) {toast('Choisissez une capture PNG ou JPEG.','warning');return;}
    const reader=new FileReader();reader.onload=()=>setCalibrationImage(reader.result);reader.readAsDataURL(file);
  });
  $('calibration-save').addEventListener('click',async()=>{
    if (!state.calibration || $('calibration-image-wrap').hidden) {toast('Chargez une capture avant d’enregistrer.','warning');return;}
    const button=$('calibration-save');setLoading(button,true,'Enregistrement…');
    const result=await api('save_calibration',{overrides:state.calibration.overrides,ratio:state.calibration.ratio});
    setLoading(button,false);
    if (result.ok) {closeDialog($('calibration-dialog'));toast('Calibrage enregistré.');await pollOnce();}
    else toast(result.error||'Calibrage non enregistré.','error');
  });

  all('[data-close-modal]').forEach(button=>button.addEventListener('click',()=>closeDialog(button.closest('dialog'))));
  $('confirm-reset').addEventListener('click',async()=>{
    const button=$('confirm-reset');setLoading(button,true,'Effacement…');
    const result=await api('reset');
    if (!result.ok) {setLoading(button,false);closeDialog($('reset-dialog'));toast(result.error||'Effacement impossible.','error');}
  });
  all('[data-field]').forEach(input=>input.addEventListener('input',()=>{state.dirty=true;}));
  all('.nav-link').forEach(button=>button.addEventListener('click',()=>showPage(button.dataset.page)));
  all('[data-edit-tab]').forEach(button=>button.addEventListener('click',()=>{
    showPage('console');activateTab(document.querySelector('[data-tabs="settings"]'),button.dataset.editTab);
  }));
  all('.tabs').forEach(group=>group.addEventListener('click',event=>{
    const button=event.target.closest('.tab');if (button) activateTab(group,button.dataset.tab);
  }));
  all('.tabs').forEach(group=>group.addEventListener('keydown',event=>{
    const buttons=all('.tab',group),index=buttons.indexOf(document.activeElement);
    if (index<0) return;
    let next=index;
    if (event.key==='ArrowRight') next=(index+1)%buttons.length;
    else if (event.key==='ArrowLeft') next=(index+buttons.length-1)%buttons.length;
    else if (event.key==='Home') next=0;
    else if (event.key==='End') next=buttons.length-1;
    else return;
    event.preventDefault();buttons[next].focus();activateTab(group,buttons[next].dataset.tab);
  }));
  all('[data-action]').forEach(button=>button.addEventListener('click',()=>perform(button.dataset.action,button)));
  window.addEventListener('resize',()=>all('.tabs').forEach(updateIndicator));
  requestAnimationFrame(()=>all('.tabs').forEach(updateIndicator));
  window.addEventListener('pywebviewready',()=>poll());
})();
