'use strict';
const $ = (id) => document.getElementById(id);
let csrf = '', loggedIn = false;
let folder = '', screenURL = '', refreshTimer, toastTimer, activeTab = 'overview', epoch = 0;
const actionNames = {Lock:'Заблокувати ПК',Sleep:'Перевести ПК у сон',Hibernate:'Увімкнути гібернацію',Logoff:'Вийти із сеансу Windows',Restart:'Перезапустити ПК',Shutdown:'Вимкнути ПК'};

function toast(text, error = false) {
  clearTimeout(toastTimer); $('message').textContent = text; $('message').classList.toggle('error', error); $('message').hidden = false;
  toastTimer = setTimeout(() => { $('message').hidden = true; }, error ? 10000 : 4000);
}
function connection(online) { $('connection').textContent = online ? '● Підключено' : 'Немає з’єднання'; $('connection').classList.toggle('online', online); }
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
  epoch++; csrf = ''; loggedIn = false; clearInterval(refreshTimer);
  if ($('confirm-dialog').open) $('confirm-dialog').close('cancel');
  if (screenURL) URL.revokeObjectURL(screenURL); screenURL = ''; $('screenshot').removeAttribute('src'); $('screenshot').hidden = true; $('screen-placeholder').hidden = false;
  $('screen-time').textContent = 'Знімок з’явиться після оновлення'; $('file-list').replaceChildren(); $('process-list').replaceChildren(); folder = '';
  $('dashboard').hidden = true; $('login').hidden = false; $('password').value = ''; connection(false);
}
function uptime(seconds) { const hours = Math.floor(seconds / 3600); return `${Math.floor(hours / 24)} д ${hours % 24} год ${Math.floor(seconds % 3600 / 60)} хв`; }
async function status() {
  try {
    const s = await json('status'); connection(true);
    $('pc-name').textContent = s.pc; $('pc-detail').textContent = `${s.os} · Працює ${uptime(s.uptime)}`;
    for (const key of ['cpu','ram','disk']) { $(key).textContent = `${Math.round(s[key])}%`; $(key+'-bar').value = s[key]; }
  } catch (error) { connection(false); throw error; }
}
async function connect() {
  await status(); $('password').value = '';
  $('login').hidden = true; $('dashboard').hidden = false;
  if (activeTab === 'files') await files();
  if (activeTab === 'processes') await processes();
  clearInterval(refreshTimer); refreshTimer = setInterval(() => { if (!document.hidden && loggedIn) status().catch(() => {}); },10000);
}
async function screenshot() {
  const response = await api('screenshot'); const blob = await response.blob();
  if (!loggedIn) return;
  if (screenURL) URL.revokeObjectURL(screenURL);
  screenURL = URL.createObjectURL(blob); $('screenshot').src = screenURL; $('screenshot').hidden = false; $('screen-placeholder').hidden = true;
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
  const result = await json('files?path='+encodeURIComponent(folder));
  folder = result.path === '.' ? '' : result.path; $('folder-path').textContent = '/' + folder; $('parent-folder').disabled = !folder;
  const nodes = result.entries.map(entry => {
    const row = element('div', undefined, 'list-item'); const info = element('div', undefined, 'item-info');
    info.append(element('strong',(entry.directory ? '📁 ' : '📄 ') + entry.name),element('small',entry.directory ? 'Папка' : size(entry.size))); row.append(info);
    if (entry.directory) row.append(button('Відкрити', async () => { folder = entry.path; await files(); }));
    else {
      const actions = element('div',undefined,'file-actions');
      actions.append(button('↓',async () => {
        const response = await api('download?path='+encodeURIComponent(entry.path)); const url = URL.createObjectURL(await response.blob());
        const link = element('a'); link.href = url; link.download = entry.name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),30000);
      })); actions.lastChild.setAttribute('aria-label','Зберегти '+entry.name+' на телефон');
      actions.append(button('Видалити',async () => { if (await confirmAction('Видалити файл?',entry.name+' буде видалено з ПК без кошика.','delete',{path:entry.path})) await files(); },'danger'));
      row.append(actions);
    } return row;
  });
  $('file-list').replaceChildren(...(nodes.length ? nodes : [element('p','Папка порожня','empty')]));
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
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => {
  activeTab = b.dataset.tab;
  document.querySelectorAll('[data-tab]').forEach(n => { const active = n === b; n.classList.toggle('active', active); n.setAttribute('aria-selected',String(active)); });
  document.querySelectorAll('.panel').forEach(p => { p.hidden = p.id !== activeTab; });
  if (activeTab === 'files') busy($('refresh-files'), files);
  if (activeTab === 'processes') busy($('refresh-processes'), processes);
}));
$('login-form').addEventListener('submit',e => { e.preventDefault(); busy(e.submitter,async () => {
  epoch++;
  const session = await json('login',{username:$('username').value.trim(),password:$('password').value});
  csrf = session.csrf; loggedIn = true; await connect();
}); });
$('logout').addEventListener('click',() => busy($('logout'),async () => { await json('logout',{}); resetSession(); }));
for (const [id,task] of [['refresh-status',status],['refresh-screen',screenshot],['refresh-files',files],['refresh-processes',processes]]) $(id).addEventListener('click',() => busy($(id),task));
$('parent-folder').addEventListener('click',() => busy($('parent-folder'),async () => { folder = folder.split('/').slice(0,-1).join('/'); await files(); }));
document.querySelectorAll('[data-input]').forEach(b => b.addEventListener('click',() => busy(b,async () => { await json('input',{action:b.dataset.input}); toast('Команду надіслано'); })));
document.querySelectorAll('[data-system]').forEach(b => b.addEventListener('click',() => busy(b,() => confirmAction(actionNames[b.dataset.system]+'?', 'Збережи відкриті документи перед продовженням.','system',{action:b.dataset.system}))));
$('upload-form').addEventListener('submit',e => { e.preventDefault(); busy(e.submitter,async () => {
  const file = $('upload-file').files[0]; if (!file) return;
  if (file.size > 20*1024*1024) throw new Error('Максимальний розмір файлу — 20 МБ');
  const path = (folder ? folder+'/' : '')+file.name;
  await api('upload?path='+encodeURIComponent(path),{method:'POST',body:file}); $('upload-form').reset(); toast('Файл збережено на ПК'); await files();
}); });
window.addEventListener('offline',() => { connection(false); toast('Немає інтернету. Команди не надсилатимуться',true); });
if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
json('session').then(async session => { csrf = session.csrf; loggedIn = true; await connect(); }).catch(() => {});
