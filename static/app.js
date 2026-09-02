const root = document.documentElement;
const THEME_ORDER = ['system', 'light', 'dark'];

function themeLabel(theme) {
  return theme.charAt(0).toUpperCase() + theme.slice(1);
}

function syncThemeControls(theme) {
  const switchButton = document.querySelector('.theme-switch');
  const modeButton = document.querySelector('.mode-button');
  if (switchButton) {
    const label = switchButton.querySelector('b');
    if (label) label.textContent = themeLabel(theme);
    const icon = switchButton.querySelector('.theme-icon');
    if (icon) icon.textContent = theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '☼';
  }
  if (modeButton) {
    const next = theme === 'dark' ? 'light' : 'dark';
    modeButton.textContent = next === 'dark' ? '☾' : '☀';
    modeButton.title = `Switch to ${next} mode`;
    modeButton.setAttribute('aria-label', `Switch to ${next} mode`);
  }
}

function persistTheme(theme) {
  try { localStorage.setItem('fileflow-theme', theme); } catch (_) {}
  fetch('/theme', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
    body: 'theme=' + encodeURIComponent(theme),
    keepalive: true
  }).catch(() => {});
}

function setTheme(theme) {
  if (!THEME_ORDER.includes(theme)) theme = 'system';
  // Apply first, persist second. The UI never waits for Flask/network I/O.
  root.dataset.theme = theme;
  syncThemeControls(theme);
  persistTheme(theme);
}

function cycleTheme() {
  const current = root.dataset.theme || 'system';
  const index = Math.max(0, THEME_ORDER.indexOf(current));
  setTheme(THEME_ORDER[(index + 1) % THEME_ORDER.length]);
}

function toggleMode() {
  const current = root.dataset.theme || 'system';
  setTheme(current === 'dark' ? 'light' : 'dark');
}

// Restore a local preference immediately, then the server remains the source
// of truth on the next page load.
try {
  const saved = localStorage.getItem('fileflow-theme');
  if (saved && THEME_ORDER.includes(saved)) root.dataset.theme = saved;
} catch (_) {}
syncThemeControls(root.dataset.theme || 'system');

document.querySelector('.theme-switch')?.addEventListener('click', cycleTheme);
document.querySelector('.mode-button')?.addEventListener('click', toggleMode);

setTimeout(() => document.querySelectorAll('.toast').forEach(x => x.classList.add('hide')), 4200);

function rows() { return [...document.querySelectorAll('#fileRows tr[data-name]')]; }
function selectedBoxes() { return [...document.querySelectorAll('input[name="selected"]')]; }

function updateSelection() {
  const boxes = selectedBoxes();
  const selected = boxes.filter(x => x.checked).length;
  const label = document.getElementById('selectedCount');
  if (label) label.textContent = selected;
  const sl = document.getElementById('selectionLabel');
  if (sl) sl.textContent = `${selected} selected`;
  const oc = document.getElementById('organizeCount');
  if (oc) oc.textContent = selected;
  const ob = document.getElementById('organizeButton');
  if (ob) ob.disabled = selected === 0;
  const master = document.getElementById('masterCheck');
  if (master) {
    master.checked = boxes.length > 0 && selected === boxes.length;
    master.indeterminate = selected > 0 && selected < boxes.length;
  }
}

function toggleAll(value) { selectedBoxes().forEach(x => x.checked = value); updateSelection(); }

function removeFile(btn) {
  const row = btn.closest('tr');
  if (!row) return;
  const box = row.querySelector('input[name="selected"]');
  if (box) box.checked = false;
  row.remove();
  const n = document.getElementById('removedCount');
  if (n) n.textContent = Number(n.textContent || 0) + 1;
  const total = document.getElementById('totalCount');
  if (total) total.textContent = rows().length;
  updateSelection();
  showToast('File removed from this organization preview. The file was not deleted.');
}

function showToast(message, kind='success') {
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.innerHTML = `<span>●</span>${message}<button type="button" aria-label="Dismiss">×</button>`;
  t.querySelector('button').onclick = () => t.remove();
  document.body.appendChild(t);
  setTimeout(() => t.classList.add('hide'), 3500);
}

function focusSearch() { document.getElementById('fileSearch')?.focus(); }

function applyFilters() {
  const q = (document.getElementById('fileSearch')?.value || '').toLowerCase();
  const type = (document.getElementById('typeFilter')?.value || '').toLowerCase();
  const status = (document.getElementById('statusFilter')?.value || '').toLowerCase();
  rows().forEach(r => {
    r.hidden = !!((q && !r.dataset.name.includes(q)) || (type && r.dataset.type !== type) || (status && r.dataset.status !== status));
  });
}

['fileSearch', 'typeFilter', 'statusFilter'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', applyFilters);
  document.getElementById(id)?.addEventListener('change', applyFilters);
});

async function chooseFolder() {
  const drop = document.getElementById('drop');
  if (!drop) return;
  const original = drop.innerHTML;
  drop.classList.add('loading');
  drop.setAttribute('aria-busy', 'true');
  drop.innerHTML = '<span class="picker-spinner" aria-hidden="true">◌</span><b>Opening folder picker…</b><span>Please choose a workspace folder.</span>';
  try {
    const response = await fetch('/pick-folder', {method: 'GET'});
    const data = await response.json();
    if (data.ok) {
      showToast('Workspace connected. Scanning folder…');
      window.location.reload();
    } else if (!data.cancelled) {
      showToast(data.error || 'Could not open the folder picker.', 'error');
      drop.innerHTML = original;
    } else {
      drop.innerHTML = original;
    }
  } catch (_) {
    showToast('Could not reach the local folder picker.', 'error');
    drop.innerHTML = original;
  } finally {
    drop.classList.remove('loading');
    drop.removeAttribute('aria-busy');
  }
}

const d = document.getElementById('drop');
if (d) {
  d.setAttribute('role', 'button');
  d.setAttribute('tabindex', '0');
  d.addEventListener('click', chooseFolder);
  d.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); chooseFolder(); } });
  ['dragenter', 'dragover'].forEach(e => d.addEventListener(e, x => { x.preventDefault(); d.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(e => d.addEventListener(e, x => { x.preventDefault(); d.classList.remove('drag'); }));
  d.addEventListener('drop', () => { showToast('Use the folder picker to choose a workspace. File drops cannot expose a local folder path to the server.', 'info'); });
}

const folderPickerButton = document.getElementById('folderPickerButton');
folderPickerButton?.addEventListener('click', chooseFolder);

updateSelection();
