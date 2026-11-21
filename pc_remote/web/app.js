'use strict';
const $ = (id) => document.getElementById(id);
let csrf = '', loggedIn = false, online = false;
let filesRequest = 0;
let liveViewer=null, liveHls=null, liveHeartbeat=null, fullImageURL='', screenBlob=null, liveRecordId=null;
let captureTimer=null, captureEpoch=0, captureURL='', captureJobTimer=null, captureRequest=null, captureListSignature='';
let fileEntries = [], activeUpload = null, pointerPending = {dx:0,dy:0}, pointerBusy = false, pointerTimer;
let folder = '', screenURL = '', refreshTimer, toastTimer, activeTab = 'overview', epoch = 0;
const actionNames = {Lock:'Заблокувати ПК',Sleep:'Перевести ПК у сон',Hibernate:'Увімкнути гібернацію',Logoff:'Вийти із сеансу Windows',Restart:'Перезапустити ПК',Shutdown:'Вимкнути ПК'};

function toast(text, error = false) {
  $('live-inline-state').textContent=text;
  clearTimeout(toastTimer); $('message').textContent = text; $('message').classList.toggle('error', error); $('message').hidden = false;
  toastTimer = setTimeout(() => { $('message').hidden = true; }, error ? 10000 : 4000);
}
function connection(connected, needsLogin=false) { online = connected; if (!online) pointerPending = {dx:0,dy:0}; $('connection').textContent = connected ? '● Підключено' : (needsLogin?'Потрібен вхід':'Немає з’єднання'); $('connection').classList.toggle('online', connected); }
async function api(path, options = {}) {
  const generation = epoch;
  let response;
  try {
    response = await fetch('/api/' + path, {...options, headers: {...options.headers, ...(options.method === 'POST' && csrf ? {'X-CSRF-Token':csrf} : {})}, credentials:'same-origin', cache:'no-store', signal:AbortSignal.timeout(20000)});
  } catch (_) {
    connection(false);
    throw new Error('Немає зв’язку з ПК. Перевірте інтернет і агент на ПК');
  }
  if (generation !== epoch) throw new Error('Сеанс змінено');
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) resetSession();
    throw new Error(body.error || 'Запит не виконано');
  }
  return response;
}
async function json(path, data) { return (await api(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})).json(); }
async function busy(button, task) {
  if (button.disabled) return;
  button.disabled = true;
  try { await task(); } catch (error) { toast(error.message || 'Перевірте інтернет і агент на ПК', true); }
  finally { button.disabled = false; }
}
function resetSession() {
  stopCapturePreview(); clearInterval(captureJobTimer); captureListSignature=''; $('capture-jobs').replaceChildren();
  closeImageViewer(); screenBlob=null;
  epoch++; csrf = ''; loggedIn = false; clearInterval(refreshTimer); clearTimeout(pointerTimer); pointerPending = {dx:0,dy:0}; if (activeUpload) activeUpload.abort();
  if ($('confirm-dialog').open) $('confirm-dialog').close('cancel');
  if (screenURL) URL.revokeObjectURL(screenURL); screenURL = ''; $('screenshot').removeAttribute('src'); $('screenshot').hidden = true; $('screen-placeholder').hidden = false;
  $('screen-time').textContent = 'Знімок з’явиться після оновлення'; $('file-list').replaceChildren(); $('process-list').replaceChildren(); folder = '';
  $('dashboard').hidden = true; $('login').hidden = false; $('password').value = ''; $('password').type='password'; $('show-password').textContent='Показати пароль'; $('show-password').setAttribute('aria-pressed','false'); connection(false,true);
}
function uptime(seconds) { const hours = Math.floor(seconds / 3600); return `${Math.floor(hours / 24)} д ${hours % 24} год ${Math.floor(seconds % 3600 / 60)} хв`; }
async function status() {
  try {
    const [s, diagnostics] = await Promise.all([json('status'),json('connection')]); connection(true);
    const tunnel = diagnostics.tunnel;
    const labels = {online:'HTTPS-тунель підключено',connecting:'Підключення до HTTPS-тунелю…',retrying:'Тунель недоступний; локальний агент працює. Повторне підключення автоматичне.',local:'Лише локальний доступ. Інтернет-тунель не ввімкнений.',configured:'Використовується налаштована HTTPS-адреса',stopped:'Тунель зупинено'};
    $('tunnel-status').textContent = tunnel.kind==='direct' ? (tunnel.state==='online'?'Прямий HTTPS-доступ налаштовано': 'Підготовка прямого HTTPS-доступу. Перевір порти 80/443 і брандмауер Windows.') : (labels[tunnel.state] || 'Стан тунелю невідомий');
    $('pc-name').textContent = s.pc; $('pc-detail').textContent = `${s.os} · Працює ${uptime(s.uptime)}`;
    for (const key of ['cpu','ram','disk']) { $(key).textContent = `${Math.round(s[key])}%`; $(key+'-bar').value = s[key]; }
  } catch (error) { connection(false); throw error; }
}
async function connect() {
  await status(); $('password').value = '';
  $('login').hidden = true; $('dashboard').hidden = false;
  if (activeTab === 'files') await files();
  if (activeTab === 'processes') await processes();
  if (activeTab === 'media') enterCapture();
  clearInterval(refreshTimer); refreshTimer = setInterval(() => { if (!document.hidden && loggedIn) status().catch(() => {}); },10000);
}
async function screenshot() {
  const response = await api('screenshot'); const blob = await response.blob();
  if (!loggedIn) return;
  if (screenURL) URL.revokeObjectURL(screenURL);
  screenBlob=blob; screenURL = URL.createObjectURL(blob); $('screenshot').src = screenURL; $('screenshot').hidden = false; $('screen-placeholder').hidden = true;
  $('screen-time').textContent = 'Оновлено о ' + new Date().toLocaleTimeString('uk-UA');
}
function element(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function button(text, task, className) { const b = element('button', text, className); b.type='button'; b.addEventListener('click', () => busy(b, task)); return b; }
function size(bytes) { return bytes < 1024 ? `${bytes} Б` : bytes < 1048576 ? `${(bytes/1024).toFixed(1)} КБ` : `${(bytes/1048576).toFixed(1)} МБ`; }
async function confirmAction(title, detail, operation, payload) {
  const dialog = $('confirm-dialog'); if (dialog.open) return false;
  $('confirm-title').textContent = title; $('confirm-detail').textContent = detail; dialog.returnValue = 'cancel';
  const accepted = new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once:true}));
  dialog.showModal(); if (!await accepted) return false;
  const ticket = await json('confirm', {operation,payload});
  await json('execute', {operation,payload,confirmation:ticket.confirmation}); toast('Дію виконано'); return true;
}
async function files() {
  const request = ++filesRequest;
  const result = await json('files?path='+encodeURIComponent(folder));
  if (request !== filesRequest) return;
  folder = result.path === '.' ? '' : result.path; $('folder-path').textContent = '/' + folder; $('parent-folder').disabled = !folder;
  fileEntries = result.entries; renderFiles(); renderBreadcrumbs();
}
function renderFiles() {
  const search = $('file-search').value.trim().toLocaleLowerCase('uk');
  const entries = fileEntries.filter(entry => entry.name.toLocaleLowerCase('uk').includes(search));
  entries.sort((a,b) => Number(b.directory)-Number(a.directory) || ($('file-sort').value === 'size' ? b.size-a.size : a.name.localeCompare(b.name,'uk')));
  const nodes = entries.map(entry => {
    const row = element('div', undefined, 'list-item'); const info = element('div', undefined, 'item-info');
    info.append(element('strong',(entry.directory ? '📁 ' : '📄 ') + entry.name),element('small',entry.directory ? 'Папка' : size(entry.size))); row.append(info);
    if (entry.directory) row.append(button('Відкрити', async () => { openFolder(entry.path); }));
    else {
      const actions = element('div',undefined,'file-actions');
      actions.append(button('Зберегти',async () => {
        const response = await api('download?path='+encodeURIComponent(entry.path)); const url = URL.createObjectURL(await response.blob());
        const link = element('a'); link.href = url; link.download = entry.name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),30000);
      })); actions.lastChild.setAttribute('aria-label','Зберегти '+entry.name+' на телефон');
      actions.append(button('У кошик',async () => { if (await confirmAction('Перемістити файл у кошик?',entry.name+' можна буде відновити через кошик Windows на ПК.','delete',{path:entry.path})) await files(); },'danger'));
      row.append(actions);
    } return row;
  });
  $('file-list').replaceChildren(...(nodes.length ? nodes : [element('p',search ? 'Немає відповідних файлів' : 'Папка порожня','empty')]));
}
async function processes() {
  const result = await json('processes');
  const rows = result.processes.map(proc => {
    const row = element('div',undefined,'list-item'), info = element('div',undefined,'item-info');
    info.append(element('strong',proc.name),element('small',`PID ${proc.pid} · RAM ${proc.ram}%`)); row.append(info);
    row.append(button('Завершити',async () => { if (await confirmAction('Завершити процес?',proc.name+' · PID '+proc.pid+'. Незбережені дані можуть бути втрачені.','terminate',{pid:proc.pid,created:proc.created})) await processes(); },'danger'));
    return row;
  }); $('process-list').replaceChildren(...(rows.length ? rows : [element('p','Процесів немає','empty')]));
}
function selectTab(name, push = true) {
  if (!['overview','control','media','files','processes'].includes(name)) name = 'overview';
  if (name !== 'media') { stopCapturePreview(); clearInterval(captureJobTimer); }
  activeTab = name;
  gesture = null; clearTimeout(pointerTimer); pointerTimer = null;
  if (push) history.pushState({tab:name,folder,depth:(history.state?.depth || 0)+1},'', '#'+name);
  document.querySelectorAll('[data-tab]').forEach(n => { const active = n.dataset.tab === name; n.classList.toggle('active',active); n.setAttribute('aria-pressed',String(active)); });
  document.querySelectorAll('.panel').forEach(p => { p.hidden = p.id !== name; });
  pointerPending = {dx:0,dy:0};
  if (loggedIn && name === 'media') enterCapture();
    if (loggedIn && name === 'files') files().catch(error=>toast(error.message,true));
  if (loggedIn && name === 'processes') busy($('refresh-processes'),processes);
}
function openFolder(path) { folder = path; $('file-search').value = ''; selectTab('files'); }
function renderBreadcrumbs() {
  const crumbs = [button('Спільна папка',async () => openFolder(''))];
  const parts = folder.split('/').filter(Boolean);
  parts.forEach((part,index) => crumbs.push(button(part,async () => openFolder(parts.slice(0,index+1).join('/')))));
  $('folder-path').replaceChildren(...crumbs);
}
history.replaceState({tab:'overview',folder:'',depth:0},'','#overview');
window.addEventListener('popstate',() => { folder = history.state?.folder || ''; selectTab(history.state?.tab || 'overview',false); });
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click',() => selectTab(b.dataset.tab)));
$('go-back').addEventListener('click',() => { if (history.state?.depth) history.back(); else selectTab('overview',false); });
$('file-search').addEventListener('input',renderFiles);
$('file-sort').addEventListener('change',renderFiles);
$('login-form').addEventListener('submit',e => { e.preventDefault(); busy(e.submitter,async () => {
  epoch++;
  const session = await json('login',{username:$('username').value.trim(),password:$('password').value,remember:Boolean($('remember-login').checked)});
  csrf = session.csrf; loggedIn = true; await connect();
}); });
$('logout').addEventListener('click',() => busy($('logout'),async () => { await json('logout',{}); resetSession(); }));
for (const [id,task] of [['refresh-status',status],['refresh-screen',screenshot],['refresh-files',files],['refresh-processes',processes]]) $(id).addEventListener('click',() => busy($(id),task));
$('parent-folder').addEventListener('click',() => openFolder(folder.split('/').slice(0,-1).join('/')));
document.querySelectorAll('[data-input]').forEach(b => b.addEventListener('click',() => busy(b,async () => { await json('input',{action:b.dataset.input}); toast('Команду надіслано'); })));
document.querySelectorAll('[data-system]').forEach(b => b.addEventListener('click',() => busy(b,() => confirmAction(actionNames[b.dataset.system]+'?', 'Збережи відкриті документи перед продовженням.','system',{action:b.dataset.system}))));
$('upload-form').addEventListener('submit',e => { e.preventDefault(); busy(e.submitter,async () => {
  const file = $('upload-file').files[0]; if (!file) return;
  if (file.size > 20*1024*1024) throw new Error('Максимальний розмір файлу — 20 МБ');
  const path = (folder ? folder+'/' : '')+file.name;
  await uploadFile(path,file); $('upload-form').reset(); toast('Файл збережено на ПК'); await files();
}); });
window.addEventListener('offline',() => { connection(false); toast('Немає інтернету. Команди не надсилатимуться',true); });
if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
json('session').then(async session => { csrf = session.csrf; loggedIn = true; await connect(); }).catch(() => {});

function uploadFile(path, file) {
  return new Promise((resolve,reject) => {
    const xhr = new XMLHttpRequest(), generation = epoch;
    activeUpload = xhr; $('upload-progress').hidden = false; $('upload-progress').value = 0; $('cancel-upload').hidden = false;
    xhr.open('POST','/api/upload?path='+encodeURIComponent(path)); xhr.setRequestHeader('X-CSRF-Token',csrf); xhr.timeout = 120000;
    xhr.upload.onprogress = e => { if (e.lengthComputable) $('upload-progress').value = Math.round(e.loaded/e.total*100); };
    xhr.onload = () => {
      if (generation !== epoch) return reject(new Error('Сеанс змінено'));
      if (xhr.status === 401) resetSession();
      let response = {}; try { response = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(); else reject(new Error(response.error || 'Передавання не вдалося'));
    };
    xhr.onerror = xhr.ontimeout = () => { connection(false); reject(new Error('Немає зв’язку з ПК. Онови список перед повторною спробою')); };
    xhr.onabort = () => reject(new Error('Передавання перервано. Онови список файлів'));
    xhr.onloadend = () => { if (activeUpload === xhr) activeUpload = null; $('upload-progress').hidden = true; $('cancel-upload').hidden = true; };
    xhr.send(file);
  });
}
$('cancel-upload').addEventListener('click',() => activeUpload?.abort());
async function flushPointer() {
  clearTimeout(pointerTimer); pointerTimer=null;
  if (!loggedIn || !online || activeTab !== 'control' || document.hidden) { pointerPending = {dx:0,dy:0}; return; }
  if (pointerBusy) { pointerTimer = setTimeout(flushPointer,60); return; }
  const dx = Math.max(-500,Math.min(500,Math.round(pointerPending.dx))), dy = Math.max(-500,Math.min(500,Math.round(pointerPending.dy)));
  pointerPending = {dx:0,dy:0}; if (!dx && !dy) return;
  pointerBusy = true;
  try { await json('pointer',{dx,dy}); } catch (error) { pointerPending = {dx:0,dy:0}; toast(error.message,true); }
  finally { pointerBusy = false; }
}
let gesture = null;
$('touchpad').addEventListener('pointerdown',e => { if (!online || gesture) return; e.preventDefault(); gesture = {id:e.pointerId,x:e.clientX,y:e.clientY,travel:0,time:Date.now()}; $('touchpad').setPointerCapture(e.pointerId); });
$('touchpad').addEventListener('pointermove',e => {
  if (!gesture || gesture.id !== e.pointerId) return;
  const dx = e.clientX-gesture.x, dy = e.clientY-gesture.y;
  gesture.travel += Math.abs(dx)+Math.abs(dy); gesture.x=e.clientX; gesture.y=e.clientY;
  pointerPending.dx += dx*1.5; pointerPending.dy += dy*1.5;
  if (!pointerTimer) pointerTimer = setTimeout(() => { pointerTimer=null; flushPointer(); },60);
});
$('touchpad').addEventListener('pointerup',e => {
  if (!gesture || gesture.id !== e.pointerId) return;
  const tap = gesture.travel < 6 && Date.now()-gesture.time < 350; gesture = null;
  if (tap) { pointerPending={dx:0,dy:0}; json('pointer',{button:'left'}).catch(error=>toast(error.message,true)); } else flushPointer();
});
$('touchpad').addEventListener('pointercancel',() => { gesture=null; pointerPending={dx:0,dy:0}; clearTimeout(pointerTimer); pointerTimer=null; });
document.addEventListener('visibilitychange',() => { if (document.hidden) { gesture=null; pointerPending={dx:0,dy:0}; } });
document.querySelectorAll('[data-pointer]').forEach(b => b.addEventListener('click',() => busy(b,() => json('pointer',{button:b.dataset.pointer}))));
document.querySelectorAll('[data-scroll]').forEach(b => b.addEventListener('click',() => busy(b,() => json('pointer',{scroll:Number(b.dataset.scroll)}))));

$('show-password').addEventListener('click',() => { const visible=$('password').type==='password'; $('password').type=visible?'text':'password'; $('show-password').textContent=visible?'Приховати пароль':'Показати пароль'; $('show-password').setAttribute('aria-pressed',String(visible)); });

function stopCapturePreview() {
  captureEpoch++; clearTimeout(captureTimer); captureTimer=null;
  clearInterval(liveHeartbeat); liveHeartbeat=null;
  if(liveHls){liveHls.destroy();liveHls=null;}
  const video=$('live-video'); video.pause?.();video.removeAttribute('src');video.load?.();video.hidden=true;
  if(liveViewer && csrf)fetch('/api/media/live/stop',{method:'POST',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({id:liveViewer.id})}).catch(()=>{});
  liveViewer=null;
  closePlayerFullscreen($('capture-player'));
  if (captureURL) URL.revokeObjectURL(captureURL); captureURL='';
  $('capture-preview').hidden=true; $('capture-preview').removeAttribute('src');
  $('capture-preview-state').textContent='Трансляцію вимкнено';
}
async function captureDevices() {
  const devices=await json('media/devices');
  const previous=$('capture-camera').value;
  $('capture-camera').replaceChildren(...devices.cameras.map(d=>{const option=element('option',d.name);option.value=String(d.id);return option;}));
  if (devices.cameras.some(d=>String(d.id)===previous)) $('capture-camera').value=previous;
  if (!devices.cameras.length) {const option=element('option','Камеру не знайдено');option.value='0';$('capture-camera').append(option);}
  const silent=element('option','Без звуку');silent.value='';
  $('capture-mic').replaceChildren(silent,...devices.microphones.map(d=>{const option=element('option',d.name);option.value=String(d.id);return option;}));
}
function enterCapture() {
  captureDevices().catch(error=>toast(error.message,true));
  captureJobs().catch(error=>toast(error.message,true));
  clearInterval(captureJobTimer);captureJobTimer=setInterval(()=>{if(loggedIn && activeTab==='media' && !document.hidden)captureJobs().catch(()=>{});},2000);
}
async function capturePreview() {
  stopCapturePreview();
  const source=$('capture-source').value, camera=Number($('capture-camera').value||0);
  if(source==='audio')return toast('Для мікрофона обери запис',true);
  const generation=captureEpoch;
  $('capture-preview-state').textContent='Підключення відео…';
  const viewer=await json('media/live/start',{source,camera});
  if(generation!==captureEpoch || !loggedIn || activeTab!=='media' || document.hidden){json('media/live/stop',{id:viewer.id}).catch(()=>{});return;}
  liveViewer=viewer;
  const video=$('live-video');video.hidden=false;video.muted=true;
  liveHeartbeat=setInterval(()=>json('media/live/keepalive',{id:viewer.id}).catch(error=>{stopCapturePreview();toast(error.message,true);}),10000);
  try {
    const nativeHls=/Apple/.test(navigator.vendor||'') && video.canPlayType('application/vnd.apple.mpegurl');
    if(window.Hls?.isSupported() && !nativeHls) {
      liveHls=new window.Hls({enableWorker:false,liveSyncDurationCount:2,liveMaxLatencyDurationCount:6,maxBufferLength:6,backBufferLength:3});
      liveHls.on(window.Hls.Events.ERROR,(_event,data)=>{if(data.fatal && generation===captureEpoch){stopCapturePreview();toast('Відеозв’язок перервано. Запусти трансляцію знову.',true);}});
      liveHls.on(window.Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>toast('Натисни ▶ у відеоплеєрі, щоб почати перегляд')));
      liveHls.loadSource(viewer.url);liveHls.attachMedia(video);
    } else if(video.canPlayType('application/vnd.apple.mpegurl')){video.src=viewer.url;video.play().catch(()=>toast('Натисни ▶ у відеоплеєрі'));}
    else throw new Error('Цей браузер не підтримує HLS-відео. Використай оновлений Chrome, Edge, Firefox або Safari.');
    $('capture-preview-state').textContent='Буферизація відео…';
  } catch(error){stopCapturePreview();throw error;}
}
async function captureJobs() {
  const generation=epoch, result=await json('media/jobs');
  if(generation!==epoch || !loggedIn)return;
  const current=result.jobs.find(job=>job.status==='recording' && job.source===$('capture-source').value && (job.source!=='camera' || job.camera===Number($('capture-camera').value||0)));
  liveRecordId=current?.id || null;$('live-record-stop').hidden=!liveRecordId;
  const root=$('capture-jobs'), signature=JSON.stringify(result.jobs.map(job=>[job.id,job.status,job.size,job.error]));
  if(signature===captureListSignature || root.querySelector('.expanded') || (document.fullscreenElement && root.contains?.(document.fullscreenElement)))return;
  // Preserve an actively playing clip while refreshing job statuses.
  if(root.querySelector('video:not([paused]),audio:not([paused])')) {
    const playing=[...root.querySelectorAll('video,audio')].some(player=>!player.paused);
    if(playing)return;
  }
  captureListSignature=signature;root.replaceChildren();
  if(!result.jobs.length){root.append(element('p','Записів ще немає','hint'));return;}
  for(const job of result.jobs) {
    const card=element('article',undefined,'card');
    const names={screen:'Екран',camera:'Камера',audio:'Мікрофон'};
    card.append(element('h3',(names[job.source]||'Запис')+' · '+new Date(job.created*1000).toLocaleString('uk-UA')));
    card.append(element('p',job.status==='recording'?'🔴 Запис триває · до '+job.seconds+' с':job.status==='ready'?'Готово · '+size(job.size):(job.error||'Помилка запису')));
    if(job.status==='recording')card.append(button('⏹ Зупинити та зберегти',async()=>{await json('media/stop',{id:job.id});await captureJobs();}));
    else {
      if(job.status==='ready') {
        const url='/api/media/file?id='+encodeURIComponent(job.id),player=element(job.source==='audio'?'audio':'video');
        player.controls=true;player.preload='none';player.playsInline=true;player.src=url;
        const frame=element('div',undefined,'fullscreen-player');frame.append(player);
        if(job.source!=='audio'){const tools=element('div',undefined,'live-toolbar');tools.append(button('⛶ На весь екран',()=>playerFullscreen(frame)));tools.append(button('✕ Згорнути',()=>closePlayerFullscreen(frame),'exit-full'));frame.append(tools);}
        card.append(frame);
        const link=element('a','Завантажити');link.href=url;link.download=job.source+'-'+job.id+(job.source==='audio'?'.mp3':'.mp4');card.append(link);
      }
      card.append(button('До кошика',async()=>{if(!window.confirm('Перемістити запис до кошика Windows?'))return;await json('media/delete',{id:job.id});await captureJobs();},'quiet'));
    }
    root.append(card);
  }
}
$('capture-devices').addEventListener('click',()=>busy($('capture-devices'),captureDevices));
$('capture-view').addEventListener('click',()=>busy($('capture-view'),capturePreview));
$('capture-hide').addEventListener('click',stopCapturePreview);
$('capture-source').addEventListener('change',stopCapturePreview);
$('capture-camera').addEventListener('change',stopCapturePreview);
$('capture-refresh').addEventListener('click',()=>busy($('capture-refresh'),captureJobs));
async function startCaptureRecording() {
  if($('capture-source').value!=='audio' && !liveViewer)await capturePreview();
  const job=await json('media/start',{source:$('capture-source').value,seconds:Number($('capture-seconds').value),camera:Number($('capture-camera').value||0),microphone:$('capture-mic').value===''?null:Number($('capture-mic').value)});
  liveRecordId=job.id;$('live-record-stop').hidden=false;
  toast('Запис розпочато. Трансляція продовжується.');await captureJobs();
}
$('capture-record').addEventListener('click',()=>busy($('capture-record'),startCaptureRecording));
$('live-record').addEventListener('click',()=>busy($('live-record'),startCaptureRecording));
$('live-record-stop').addEventListener('click',()=>busy($('live-record-stop'),async()=>{if(liveRecordId)await json('media/stop',{id:liveRecordId});await captureJobs();}));
async function closePlayerFullscreen(frame) {
  frame.classList.toggle('expanded',false);document.body?.classList.toggle('viewer-expanded',false);
  if(document.fullscreenElement===frame){try{await document.exitFullscreen();}catch(_){}}
}
async function playerFullscreen(frame) {
  if(document.fullscreenElement===frame || frame.classList.contains?.('expanded'))return closePlayerFullscreen(frame);
  if(frame.requestFullscreen){try{await frame.requestFullscreen();return;}catch(_){}}
  frame.classList.toggle('expanded',true);document.body?.classList.toggle('viewer-expanded',true);
}
function closeImageViewer() {
  closePlayerFullscreen($('image-full-wrapper'));
  if($('image-viewer').open)$('image-viewer').close();
  if(fullImageURL)URL.revokeObjectURL(fullImageURL);fullImageURL='';$('full-image').removeAttribute('src');
}
function showImage(blob) {
  closeImageViewer();fullImageURL=URL.createObjectURL(blob);$('full-image').src=fullImageURL;
  $('image-download').href=fullImageURL;$('image-download').download='pc-helper-'+Date.now()+(blob.type==='image/png'?'.png':'.jpg');
  $('image-viewer').showModal();
}
$('live-fullscreen').addEventListener('click',()=>playerFullscreen($('capture-player')));
$('live-close-full').addEventListener('click',()=>closePlayerFullscreen($('capture-player')));
$('live-snapshot').addEventListener('click',()=>busy($('live-snapshot'),async()=>{const response=await api('media/frame?source='+$('capture-source').value+'&camera='+encodeURIComponent($('capture-camera').value||0));showImage(await response.blob());}));
$('screen-full').addEventListener('click',()=>busy($('screen-full'),async()=>{if(!screenBlob)await screenshot();showImage(screenBlob);}));
$('screenshot').addEventListener('click',()=>{if(screenBlob)showImage(screenBlob);});
$('image-close').addEventListener('click',closeImageViewer);
$('image-full').addEventListener('click',()=>playerFullscreen($('image-full-wrapper')));
$('image-viewer').addEventListener('close',()=>{if(fullImageURL)URL.revokeObjectURL(fullImageURL);fullImageURL='';});
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.expanded').forEach(closePlayerFullscreen);});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCapturePreview();});
window.addEventListener('offline',stopCapturePreview);

$('live-video').addEventListener('playing',()=>{if(liveViewer)$('capture-preview-state').textContent='● LIVE · до 15 кадрів/с · запис доступний під час перегляду';});
$('live-video').addEventListener('error',()=>{if(liveViewer){stopCapturePreview();toast('Браузер не зміг відтворити відео. Спробуй оновити його або відкрити панель у Chrome / Edge / Safari.',true);}});
window.addEventListener('pagehide',stopCapturePreview);
