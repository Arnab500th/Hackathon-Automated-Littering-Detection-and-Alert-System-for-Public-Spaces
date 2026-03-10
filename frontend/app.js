// ── Config ────────────────────────────────────────────────────
// Change this if your backend runs on a different host/port
const API = 'http://localhost:8000';

// ── Multi-camera config ───────────────────────────────────────
// Add one entry per camera. id must match CAMERA_ID in each
// camera's config.py. stream_url is the MJPEG endpoint.
// To add cameras during demo: click "+ Add Camera" in Live Feed.
let CAMERAS = [
  { id: 'CAM_01', label: 'Main Entrance', stream_url: `${API}/stream/CAM_01` },
  { id: 'CAM_02', label: 'Parking Lot', stream_url: `${API}/stream/CAM_02` },
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
  if (el) el.classList.add('active');

  if (name === 'incidents') loadIncidents();
  if (name === 'vehicles') loadVehicles();
  if (name === 'stream') renderCameraGrid();
  if (name === 'dashboard') { loadStats(); loadRecentIncidents(); loadHistory(); }
  if (name === 'live-stats') loadLiveStats();
}

// ── Connection status ─────────────────────────────────────────
function setConnected(ok) {
  const label = document.getElementById('connection-label');
  const dot = document.querySelector('.live-dot');
  if (ok) {
    dot.style.background = 'var(--ok)';
    dot.style.animation = 'blink 1.2s ease-in-out infinite';
    label.textContent = 'BACKEND ONLINE';
    label.style.color = 'var(--ok)';
  } else {
    dot.style.background = 'var(--warn)';
    dot.style.animation = 'none';
    label.textContent = 'BACKEND OFFLINE';
    label.style.color = 'var(--warn)';
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
    // Fetch today + all-time in parallel — no added latency
    const [today, allTime] = await Promise.all([
      apiFetch('/stats/today'),
      apiFetch('/stats'),
    ]);
    setConnected(true);

    // Dashboard stat cards — today's figures only
    document.getElementById('stat-total').textContent       = today.total_incidents   ?? '0';
    document.getElementById('stat-total-trash').textContent = today.total_trash       ?? '0';
    document.getElementById('stat-persons').textContent     = today.person_offenders  ?? '0';
    document.getElementById('stat-vehicles').textContent    = today.vehicle_offenders ?? '0';

    // Sub-labels show the actual date for clarity
    const dateLabel = today.date ?? 'today';
    ['stat-total-sub','stat-trash-sub','stat-persons-sub','stat-vehicles-sub']
      .forEach(id => { const el = document.getElementById(id); if (el) el.textContent = dateLabel; });

    // Sidebar totals — all-time
    document.getElementById('sb-trash').textContent    = allTime.total_trash       ?? '0';
    document.getElementById('sb-total').textContent    = allTime.total_incidents   ?? '0';
    document.getElementById('sb-persons').textContent  = allTime.person_offenders  ?? '0';
    document.getElementById('sb-vehicles').textContent = allTime.vehicle_offenders ?? '0';

    // Pie chart — all-time breakdown by trash type
    updatePieChart(today.by_trash_type || {});
    await loadActiveCameras();

    // Toast triggered by all-time count change
    const total = allTime.total_incidents || 0;
    if (lastIncidentCount > 0 && total > lastIncidentCount) {
      showToast('NEW INCIDENT',
        `${total - lastIncidentCount} new litter event(s) detected`);
      loadRecentIncidents();
      loadHistory();
    }
    lastIncidentCount = total;

  } catch (e) {
    setConnected(false);
  }
}

async function loadActiveCameras() {
  try {
    const data = await apiFetch('/cameras/active');
    const cams = data.cameras || [];
    document.getElementById('active-cam-count').textContent = cams.length;

    const list = document.getElementById('active-cam-list');
    if (cams.length === 0) {
      list.innerHTML = '<div class="no-data">No cameras online</div>';
      return;
    }

    list.innerHTML = cams.map(c => `
      <div class="cam-item">
        <div class="cam-dot"></div>
        <div class="cam-info">
          <div class="cam-id">
            ${c.id}
            <span class="priority-badge priority-${(c.priority||'LOW').toLowerCase()}">${c.priority||'LOW'}</span>
            ${c.zone_name ? `<span class="zone-badge">${c.zone_name}</span>` : ''}
          </div>
          <div class="cam-time">pinged ${fmtTime(c.last_ping)}</div>
        </div>
      </div>
    `).join('');
  } catch (e) { /* silent */ }
}

let historyChartInstance = null;
async function loadHistory() {
  try {
    const data = await apiFetch('/stats/history');
    const ctx = document.getElementById('historyBarChart');
    if (!ctx) return;

    if (historyChartInstance) {
      historyChartInstance.data.labels = data.labels;
      historyChartInstance.data.datasets[0].data = data.incidents;
      historyChartInstance.data.datasets[1].data = data.trash;
      historyChartInstance.update();
      return;
    }

    historyChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: 'Confirmed Incidents',
            data: data.incidents,
            backgroundColor: '#ff3366',
            borderRadius: 4,
            minBarLength: 2
          },
          {
            label: 'Total Trash Spotted',
            data: data.trash,
            backgroundColor: '#00d2ff',
            borderRadius: 4,
            minBarLength: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#a1a1aa', font: { family: 'JetBrains Mono' } } }
        },
        scales: {
          y: {
            beginAtZero: true,
            suggestedMax: 1,
            grid: { color: '#27272a' },
            ticks: { color: '#a1a1aa', font: { family: 'JetBrains Mono' }, stepSize: 1 }
          },
          x: {
            grid: { display: false },
            ticks: { color: '#a1a1aa', font: { family: 'JetBrains Mono' } }
          }
        }
      }
    });

  } catch (e) { /* silent */ }
}

// ── Load vehicles ─────────────────────────────────────────────
async function loadVehicles() {
  try {
    const data = await apiFetch('/vehicles');
    const el = document.getElementById('stat-unique-v');
    if (el) el.textContent = data.length ?? '0';
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
  await loadHistory();
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
  const url = `${API}/snapshots/${rel}`;
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

let pieChartInstance = null;

function updatePieChart(byType) {
  const ctx = document.getElementById('trashPieChart');
  if (!ctx) return;

  const labels = Object.keys(byType);
  const data = Object.values(byType);

  if (pieChartInstance) {
    pieChartInstance.data.labels = labels;
    pieChartInstance.data.datasets[0].data = data;
    pieChartInstance.update();
    return;
  }

  pieChartInstance = new Chart(ctx, {
    type: 'pie',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: [
          '#33ff57', '#ff3366', '#ffaa00', '#00ffaa', '#8833ff','#00d2ff','#ff66cc'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#a1a1aa', font: { family: 'JetBrains Mono', size: 11 } }
        }
      }
    }
  });
}

// ── Live Stats Tab ────────────────────────────────────────────
// Fetches /cameras/active to get the list, then calls
// /stats/camera/{id} for each camera to get today + all-time breakdowns.
async function loadLiveStats() {
  try {
    const data = await apiFetch('/cameras/active');
    const cams = data.cameras || [];
    const container = document.getElementById('live-stats-container');

    if (cams.length === 0) {
      container.innerHTML = '<div class="no-data">No cameras are currently online providing data.</div>';
      return;
    }

    // Show skeleton cards while per-camera data loads
    container.innerHTML = cams.map(c => `
      <div class="panel cam-stat-card" id="cam-card-${c.id}">
        <div class="cam-stat-header">
          <span class="live-dot" style="background:var(--ok)"></span>
          ${c.id}
          <span style="font-size:11px; color:var(--muted); margin-left:8px;">Last ping: ${fmtTime(c.last_ping)}</span>
        </div>
        <div style="color:var(--muted); font-size:12px; padding:12px 0;">Loading camera stats...</div>
      </div>
    `).join('');

    // Fetch all cameras in parallel, then fill each card
    const statResults = await Promise.allSettled(
      cams.map(c => apiFetch(`/stats/camera/${c.id}`))
    );

    statResults.forEach((result, i) => {
      const cam   = cams[i];
      const card  = document.getElementById(`cam-card-${cam.id}`);
      if (!card) return;

      if (result.status === 'rejected') {
        card.innerHTML += `<div style="color:var(--warn);font-size:12px;">Failed to load stats for ${cam.id}</div>`;
        return;
      }

      const s = result.value;
      const t = s.today;
      const a = s.all_time;

      // Build trash-type rows (today)
      const todayTypes = Object.entries(t.by_trash_type || {});
      const trashRows = todayTypes.length
        ? todayTypes.map(([type, cnt]) =>
            `<span style="background:#27272a;border-radius:4px;padding:2px 7px;font-size:11px;font-family:var(--font-mono);">${type}: <b style="color:var(--accent)">${cnt}</b></span>`
          ).join(' ')
        : '<span style="color:var(--muted);font-size:11px;">No trash detected today</span>';

      card.innerHTML = `
        <div class="cam-stat-header" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span class="live-dot" style="background:var(--ok)"></span>
          <span style="font-family:var(--font-mono);font-size:14px;">${cam.id}</span>
          <span class="priority-badge priority-${(cam.priority||'LOW').toLowerCase()}">${cam.priority||'LOW'}</span>
          ${cam.zone_name ? `<span class="zone-badge">${cam.zone_name}</span>` : '<span style="font-size:10px;color:var(--muted);">Standard Area</span>'}
          <span style="font-size:11px;color:var(--muted);">Last ping: ${fmtTime(cam.last_ping)}</span>
          <span style="font-size:11px;color:var(--muted);margin-left:auto;">Date: ${s.date}</span>
        </div>
        <div class="cam-stat-body" style="display:flex;gap:16px;margin-top:12px;flex-wrap:wrap;">

          <!-- Stream thumbnail -->
          <img src="${API}/stream/${cam.id}"
            style="width:210px;height:126px;object-fit:cover;border:1px solid #3f3f46;border-radius:6px;flex-shrink:0;"
            onerror="this.outerHTML='<div style=width:210px;height:126px;display:flex;align-items:center;justify-content:center;border:1px solid #3f3f46;border-radius:6px;color:var(--muted);font-size:12px;>NO SIGNAL</div>'"/>

          <!-- Stats -->
          <div style="flex:1;min-width:260px;">

            <!-- TODAY row -->
            <div style="font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:1px;margin-bottom:6px;">Today — ${s.date}</div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:14px;">
              ${statBox(t.total_incidents,  'INCIDENTS',  'var(--warn)')}
              ${statBox(t.total_trash,      'TRASH',      'var(--accent)')}
              ${statBox(t.total_persons,    'PERSONS',    'var(--ok)')}
              ${statBox(t.total_vehicles,   'VEHICLES',   '#ffaa00')}
            </div>

            <!-- ALL-TIME row -->
            <div style="font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:1px;margin-bottom:6px;">All-time</div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:14px;">
              ${statBox(a.total_incidents,  'INCIDENTS',  'var(--warn)',  true)}
              ${statBox(a.total_trash,      'TRASH',      'var(--accent)', true)}
              ${statBox(a.total_persons,    'PERSONS',    'var(--ok)',    true)}
              ${statBox(a.total_vehicles,   'VEHICLES',   '#ffaa00',     true)}
            </div>

            <!-- Trash types seen today -->
            <div style="font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:1px;margin-bottom:6px;">Trash types today</div>
            <div style="display:flex;flex-wrap:wrap;gap:5px;">${trashRows}</div>
          </div>
        </div>
      `;
    });

  } catch (e) {
    console.error('[loadLiveStats]', e);
  }
}

// Helper: renders a single mini stat box
function statBox(value, label, color, dim = false) {
  const opacity = dim ? 'opacity:0.65;' : '';
  return `
    <div style="background:#18181b;border-radius:6px;padding:8px 4px;text-align:center;${opacity}">
      <div style="font-family:var(--font-mono);font-size:18px;color:${color};">${value ?? 0}</div>
      <div style="font-size:9px;color:var(--muted);margin-top:2px;letter-spacing:0.5px;">${label}</div>
    </div>`;
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
  const slot = document.getElementById('slot-' + id);
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
  const id = prompt('Camera ID (must match CAMERA_ID in config.py):\ne.g. CAM_03');
  if (!id) return;
  const label = prompt('Display label:\ne.g. Back Entrance') || id;
  const host = prompt('Backend host (leave blank for localhost:8000):') || 'localhost:8000';
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
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <div class="toast-title">${title}</div>
    <div class="toast-body">${body}</div>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 6000);
}

// ── Auto-refresh every 5 seconds ──────────────────────────────
setInterval(() => {
  loadStats();
  loadRecentIncidents();
  // We don't poll loadHistory() every 5s since it's a 7-day view, updated on new incident

  const activePage = document.querySelector('.page.active');
  if (activePage && activePage.id === 'page-live-stats') {
    loadLiveStats();
  }
}, 5000);

// ── Init ──────────────────────────────────────────────────────
loadAll();