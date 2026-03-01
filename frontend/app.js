// ── Config ────────────────────────────────────────────────────
// Change this if your backend runs on a different host/port
const API = 'http://localhost:8000';

// ── Multi-camera config ───────────────────────────────────────
// Add one entry per camera. id must match CAMERA_ID in each
// camera's config.py. stream_url is the MJPEG endpoint.
// To add cameras during demo: click "+ Add Camera" in Live Feed.
let CAMERAS = [
  { id: 'CAM_01', label: 'Main Entrance',  stream_url: `${API}/stream/CAM_01` },
  { id: 'CAM_02', label: 'Parking Lot',    stream_url: `${API}/stream/CAM_02` },
];

// ── State ─────────────────────────────────────────────────────
let lastIncidentCount = 0;

// ── Clock ─────────────────────────────────────────────────────
function updateClock() {
  document.getElementById('clock').textContent =
    new Date().toLocaleTimeString('en-GB', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ── Page navigation ───────────────────────────────────────────
function showPage(name, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  el.classList.add('active');

  if (name === 'incidents') loadIncidents();
  if (name === 'vehicles')  loadVehicles();
  if (name === 'stream')    renderCameraGrid();
}

// ── Connection status ─────────────────────────────────────────
function setConnected(ok) {
  const label = document.getElementById('connection-label');
  const dot   = document.querySelector('.live-dot');
  if (ok) {
    dot.style.background  = 'var(--ok)';
    dot.style.animation   = 'blink 1.2s ease-in-out infinite';
    label.textContent     = 'BACKEND ONLINE';
    label.style.color     = 'var(--ok)';
  } else {
    dot.style.background  = 'var(--warn)';
    dot.style.animation   = 'none';
    label.textContent     = 'BACKEND OFFLINE';
    label.style.color     = 'var(--warn)';
  }
}

// ── API helpers ───────────────────────────────────────────────
async function apiFetch(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Load stats ────────────────────────────────────────────────
async function loadStats() {
  try {
    const data = await apiFetch('/stats');
    setConnected(true);

    document.getElementById('stat-total').textContent    = data.total_incidents   ?? '0';
    document.getElementById('stat-persons').textContent  = data.person_offenders  ?? '0';
    document.getElementById('stat-vehicles').textContent = data.vehicle_offenders ?? '0';
    document.getElementById('sb-total').textContent      = data.total_incidents   ?? '0';
    document.getElementById('sb-persons').textContent    = data.person_offenders  ?? '0';
    document.getElementById('sb-vehicles').textContent   = data.vehicle_offenders ?? '0';

    renderTrashBars(data.by_trash_type || {});
    renderZoneHeatmap(data.by_camera   || {});

    // New incident toast
    const total = data.total_incidents || 0;
    if (lastIncidentCount > 0 && total > lastIncidentCount) {
      showToast('⚠ NEW INCIDENT',
        `${total - lastIncidentCount} new litter event(s) detected`);
      loadRecentIncidents();
    }
    lastIncidentCount = total;

  } catch (e) {
    setConnected(false);
  }
}

// ── Load vehicles ─────────────────────────────────────────────
async function loadVehicles() {
  try {
    const data = await apiFetch('/vehicles');
    document.getElementById('stat-unique-v').textContent = data.length ?? '0';
    renderVehiclesTable(data);
  } catch (e) {
    document.getElementById('vehicles-tbody').innerHTML =
      `<tr><td colspan="4" class="empty-cell">Backend offline or no vehicles yet</td></tr>`;
  }
}

// ── Load recent incidents (dashboard tab) ─────────────────────
async function loadRecentIncidents() {
  try {
    const data = await apiFetch('/incidents/recent?limit=8');
    renderRecentTable(data);
  } catch (e) { /* silent */ }
}

// ── Load all incidents (incidents tab) ────────────────────────
async function loadIncidents() {
  try {
    const data = await apiFetch('/incidents');
    renderAllTable(data);
  } catch (e) {
    document.getElementById('all-tbody').innerHTML =
      `<tr><td colspan="9" class="empty-cell">Backend offline</td></tr>`;
  }
}

// ── Load everything ───────────────────────────────────────────
async function loadAll() {
  await loadStats();
  await loadRecentIncidents();
  await loadVehicles();
}

// ── Render helpers ─────────────────────────────────────────────
function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
}

function offenderBadge(type) {
  if (!type) return '<span class="badge badge-unknown">?</span>';
  return type.toLowerCase() === 'vehicle'
    ? '<span class="badge badge-vehicle">VEHICLE</span>'
    : '<span class="badge badge-person">PERSON</span>';
}

function thumbCell(path) {
  if (!path) return '<div class="no-img">N/A</div>';
  // Strip absolute path, keep relative part after snapshots/
  const rel = path.replace(/^.*snapshots[/\\]/, '');
  const url  = `${API}/snapshots/${rel}`;
  return `<img class="thumb" src="${url}"
    onclick="openLightbox('${url}')"
    title="Click to enlarge"
    onerror="this.outerHTML='<div class=no-img>ERR</div>'"/>`;
}

function renderRecentTable(rows) {
  const tbody = document.getElementById('recent-tbody');
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No incidents yet</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td style="font-family:var(--font-mono);color:var(--muted)">${r.id}</td>
      <td style="font-family:var(--font-mono);font-size:11px">${fmtTime(r.timestamp)}</td>
      <td>${r.trash_type || '—'}</td>
      <td>${offenderBadge(r.offender_type)}</td>
      <td>${r.license_plate
            ? `<span class="badge badge-plate">${r.license_plate}</span>`
            : '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
      <td style="font-family:var(--font-mono);color:var(--accent)">
        ${r.trash_confidence ? (r.trash_confidence * 100).toFixed(0) + '%' : '—'}
      </td>
      <td>${thumbCell(r.person_image_path || r.vehicle_image_path)}</td>
    </tr>
  `).join('');
}

function renderAllTable(rows) {
  const tbody = document.getElementById('all-tbody');
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">No incidents</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td style="font-family:var(--font-mono);color:var(--muted)">${r.id}</td>
      <td style="font-family:var(--font-mono);font-size:11px">${fmtTime(r.timestamp)}</td>
      <td style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">${r.camera_id || '—'}</td>
      <td>${r.trash_type || '—'}</td>
      <td style="font-family:var(--font-mono);color:var(--accent)">
        ${r.trash_confidence ? (r.trash_confidence * 100).toFixed(0) + '%' : '—'}
      </td>
      <td>${offenderBadge(r.offender_type)}</td>
      <td>${r.license_plate
            ? `<span class="badge badge-plate">${r.license_plate}</span>`
            : '—'}</td>
      <td style="font-family:var(--font-mono);color:${r.alert_sent ? 'var(--ok)' : 'var(--muted)'}">
        ${r.alert_sent ? 'YES' : 'NO'}
      </td>
      <td>${thumbCell(r.full_frame_path || r.person_image_path || r.vehicle_image_path)}</td>
    </tr>
  `).join('');
}

function renderVehiclesTable(rows) {
  const tbody = document.getElementById('vehicles-tbody');
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">No vehicles recorded</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td style="font-family:var(--font-mono);color:var(--ok);letter-spacing:2px">
        ${r.license_plate || '—'}
      </td>
      <td style="font-family:var(--font-mono);font-size:11px">${fmtTime(r.first_seen)}</td>
      <td style="font-family:var(--font-mono);font-size:11px">${fmtTime(r.last_seen)}</td>
      <td><span class="repeat-badge">${r.incident_count}</span></td>
    </tr>
  `).join('');
}

function renderTrashBars(byType) {
  const el      = document.getElementById('trash-bars');
  const entries = Object.entries(byType).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    el.innerHTML = '<div class="no-data">No data yet</div>';
    return;
  }
  const max = Math.max(...entries.map(e => e[1]));
  el.innerHTML = entries.map(([label, count]) => `
    <div class="bar-row">
      <div class="bar-label-row">
        <span>${label}</span><span>${count}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${(count / max * 100).toFixed(1)}%"></div>
      </div>
    </div>
  `).join('');
}

function renderZoneHeatmap(byCamera) {
  const el    = document.getElementById('zone-grid');
  const zones = [
    'Top-Left', 'Top-Center', 'Top-Right',
    'Bot-Left', 'Bot-Center', 'Bot-Right'
  ];
  // Wire to real zone data if /scene endpoint added later
  // For now renders camera breakdown remapped to zones
  const keys   = Object.keys(byCamera);
  const counts = zones.reduce((acc, z, i) => {
    const cam = keys[i];
    acc[z] = cam ? (byCamera[cam] || 0) : 0;
    return acc;
  }, {});
  const max = Math.max(...Object.values(counts), 1);

  el.innerHTML = zones.map(z => {
    const c    = counts[z];
    const heat = c >= max * 0.7 ? 'hot' : c >= max * 0.3 ? 'med' : '';
    return `
      <div class="zone-cell ${heat}">
        <span class="zone-name">${z}</span>
        <span class="zone-count ${heat}">${c}</span>
      </div>
    `;
  }).join('');
}

// ── Multi-camera stream ───────────────────────────────────────
// Each camera gets its own <div class="cam-slot"> with an <img>
// pointing to /stream/<camera_id>. The MJPEG stream is just an
// img src — browser handles it natively, no JS needed for decoding.

function renderCameraGrid() {
  const grid = document.getElementById('camera-grid');
  grid.innerHTML = CAMERAS.map(cam => `
    <div class="cam-slot" id="slot-${cam.id}">
      <img
        src="${cam.stream_url}"
        alt="${cam.label}"
        onerror="camError('${cam.id}')"
        onload="camOk('${cam.id}')"
      />
      <span class="cam-label">${cam.id} ● ${cam.label.toUpperCase()}</span>
    </div>
  `).join('');
}

function camOk(id) {
  const slot  = document.getElementById('slot-' + id);
  const label = slot ? slot.querySelector('.cam-label') : null;
  if (label) {
    label.style.color = 'var(--ok)';
    setTimeout(() => { label.style.color = 'var(--accent)'; }, 2000);
  }
}

function camError(id) {
  const slot = document.getElementById('slot-' + id);
  if (!slot) return;
  const cam = CAMERAS.find(c => c.id === id);
  // Replace the broken img with an offline placeholder
  slot.innerHTML = `
    <div class="cam-offline">
      <span>[ NO SIGNAL ]</span>
      <small>${cam ? cam.label : id}</small>
      <small style="color:var(--muted)">${cam ? cam.stream_url : ''}</small>
    </div>
    <span class="cam-label" style="color:var(--muted)">${id} ● OFFLINE</span>
  `;
}

function refreshStreams() {
  // Force reload all streams by re-rendering the grid
  renderCameraGrid();
}

function addCameraPrompt() {
  const id    = prompt('Camera ID (must match CAMERA_ID in config.py):\ne.g. CAM_03');
  if (!id) return;
  const label = prompt('Display label:\ne.g. Back Entrance') || id;
  const host  = prompt('Backend host (leave blank for localhost:8000):') || 'localhost:8000';
  CAMERAS.push({
    id,
    label,
    stream_url: `http://${host}/stream/${id}`
  });
  renderCameraGrid();
}

// ── Lightbox ──────────────────────────────────────────────────
function openLightbox(url) {
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox').classList.add('open');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
}
// Close on Escape key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeLightbox();
});

// ── Toast ─────────────────────────────────────────────────────
function showToast(title, body) {
  const container = document.getElementById('toasts');
  const toast     = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <div class="toast-title">${title}</div>
    <div class="toast-body">${body}</div>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 6000);
}

// ── Auto-refresh every 5 seconds ──────────────────────────────
setInterval(loadStats,          5000);
setInterval(loadRecentIncidents, 5000);

// ── Init ──────────────────────────────────────────────────────
loadAll();