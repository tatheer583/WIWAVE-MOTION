import { emptyFrame, normalizeFrame } from './wiwave-data.js';

const el = id => document.getElementById(id);
const show = (id, value) => { const node = el(id); if (node) node.textContent = value ?? '—'; };
const format = (value, suffix = '') => Number.isFinite(value) ? `${value.toFixed(1)}${suffix}` : '—';
async function api(path, method = 'GET') {
  const response = await fetch(path, { method, signal: AbortSignal.timeout(8000) });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

export class WorkspaceControls {
  constructor(observatory) {
    this.obs = observatory;
    this.page = 'operations';
    this.lastUpdate = 0;
    this.requestId = 0;
    el('workspace-btn').onclick = () => this.open();
    el('workspace-close').onclick = () => this.close();
    el('workspace-overlay').onclick = event => { if (event.target === el('workspace-overlay')) this.close(); };
    el('workspace-overlay').onkeydown = event => {
      if (event.key !== 'Tab') return;
      const focusable = [...el('workspace-overlay').querySelectorAll('button:not(:disabled),a,input,select')];
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    el('workspace-tabs').onclick = event => { if (event.target.dataset.page) { this.page = event.target.dataset.page; this.render(); } };
    el('mode-native').onclick = () => this.setMode('native');
    el('mode-demo').onclick = () => this.setMode('demo');
    el('mode-server').onclick = () => {
      this.setMode('ws');
      if (!this.obs._hud.settingsOpen) this.obs._hud.toggleSettings();
      document.querySelector('[data-stab="data"]').click();
      el('opt-ws-url').focus();
    };
    el('playback-exit').onclick = () => this.setMode('native');
    el('playback-pause').onclick = () => { this.obs._paused = !this.obs._paused; };
    el('playback-seek').oninput = event => {
      if (this.replay) this.replay.time = Number(event.target.value);
      this.obs._hud._rssiHistory = [];
    };
    el('playback-speed').onchange = event => { if (this.replay) this.replay.speed = Number(event.target.value); };
  }
  get isOpen() { return !el('workspace-overlay').hidden; }
  setMode(mode) { this.requestId++; this.obs.selectSource(mode); this.obs._hud.saveSettings(); this.render(); }
  open() { this.focusBefore = document.activeElement; el('workspace-overlay').hidden = false; this.render(); el('workspace-close').focus(); }
  close() { el('workspace-overlay').hidden = true; this.focusBefore?.focus(); }
  notice(message) { show('workspace-notice', message); }
  async action(button, path) {
    button.disabled = true;
    let message;
    try { const result = await api(path, 'POST'); message = result.message || 'Done'; }
    catch (error) { message = error.message; }
    finally { button.disabled = false; this.render(); this.notice(message); }
  }
  render() {
    if (!this.isOpen) return;
    this.requestId++;
    this.notice('');
    document.querySelectorAll('[data-page]').forEach(button => button.classList.toggle('active', button.dataset.page === this.page));
    const content = el('workspace-content');
    if (this.page === 'operations') {
      content.innerHTML = `<p class="workspace-intro">Capture a quiet baseline, watch signal changes, and record this computer’s sensor.</p>
        <div class="workspace-metrics"><div>Sensor state<strong id="op-state">—</strong></div><div>Driver reads<strong id="op-rate">—</strong></div><div>Sample age<strong id="op-age">—</strong></div><div>Baseline<strong id="op-progress">—</strong></div></div>
        <div class="workspace-actions"><button id="op-calibrate">Calibrate empty room</button><button id="op-record">Start recording</button><button id="op-stop">Stop recording</button></div>
        <p id="op-recording"></p><p id="op-error" role="status"></p><p class="workspace-muted">Calibration takes about 20 seconds. Stay still and keep doors and furniture unchanged. A signal change can come from movement or radio interference; it does not identify a person.</p>`;
      el('op-calibrate').onclick = event => this.action(event.target, '/api/calibrate');
      el('op-record').onclick = event => this.action(event.target, '/session/start?name=Observatory%20capture');
      el('op-stop').onclick = event => this.action(event.target, '/session/stop');
    } else if (this.page === 'devices') {
      content.innerHTML = '<p class="workspace-intro">Devices reported by the selected stream</p><div id="device-list"></div><p class="workspace-muted">The 3D room and router are a visual template. They do not measure room dimensions, object positions, or sensing range.</p>';
    } else if (this.page === 'sessions') {
      content.innerHTML = '<p class="workspace-intro">Local recordings · original timestamps and source labels are preserved.</p><button id="sessions-refresh">Refresh recordings</button><div id="session-list">Loading…</div>';
      el('sessions-refresh').onclick = () => this.loadSessions();
      this.loadSessions();
    } else if (this.page === 'models') {
      content.innerHTML = `<p class="workspace-intro">Research sources and model connection</p><p>The local backend has a signal-change detector. Human count, pose, falls, and vital signs require a separate compatible CSI sensing engine and validation in your room.</p>
        <p>Connect a RuView server using its WebSocket endpoint in Settings → Data. Valid 17-keypoint model outputs can be displayed; confidence-zero or heuristic person locations do not create skeletons.</p>
        <div class="research-links"><a href="https://github.com/espressif/esp-csi" target="_blank" rel="noreferrer">Espressif · CSI capture & firmware ↗</a><a href="https://github.com/ybhbingo/MMFi_dataset" target="_blank" rel="noreferrer">MM-Fi · pose dataset & official loader ↗</a><a href="https://tns.thss.tsinghua.edu.cn/widar3.0/" target="_blank" rel="noreferrer">Tsinghua Widar 3.0 · gesture dataset ↗</a><a href="https://github.com/xyanchen/WiFi-CSI-Sensing-Benchmark" target="_blank" rel="noreferrer">SenseFi / NTU-Fi · activity benchmarks ↗</a><a href="https://huggingface.co/ruvnet/wifi-densepose-pretrained" target="_blank" rel="noreferrer">RuView · pretrained model card ↗</a></div>
        <p class="workspace-muted">These datasets are research inputs, not proof that a model will work on this laptop’s RSSI. Model weights and training datasets have not been installed. See docs/DATASETS_AND_MODELS.md in the repository.</p>`;
    } else {
      content.innerHTML = `<p class="workspace-intro">Implemented features and hardware dependencies</p><table class="feature-table"><thead><tr><th>Feature</th><th>Status</th></tr></thead><tbody>
        <tr><td>RuView Observatory scene, camera, style presets, rendering settings</td><td>Implemented</td></tr><tr><td>All 12 upstream scenarios</td><td>Explicit synthetic demos</td></tr><tr><td>Windows live RSSI, calibration, signal changes</td><td>Implemented · hardware tested</td></tr><tr><td>Record, CSV export, timed replay, speed and seeking</td><td>Implemented locally</td></tr><tr><td>ESP32 CSV CSI capture</td><td>Implemented · needs hardware test</td></tr><tr><td>RuView WebSocket connection</td><td>Implemented · protocol tested</td></tr><tr><td>Person counts, 17-keypoint pose, vital signs, fall estimates</td><td>Requires compatible CSI engine; unvalidated</td></tr><tr><td>Object identity, measured range, through-wall localization</td><td>Not implemented</td></tr><tr><td>Training, firmware flashing, multi-node provisioning, edge modules</td><td>Use upstream tools; not integrated</td></tr></tbody></table>`;
    }
    this.lastUpdate = 0;
  }
  async loadSessions() {
    const token = ++this.requestId;
    try {
      const sessions = await api('/sessions');
      if (token !== this.requestId || this.page !== 'sessions') return;
      const list = el('session-list'); list.replaceChildren();
      if (!sessions.length) { list.textContent = 'No recordings yet. Start one from Operations while viewing the live sensor.'; return; }
      for (const session of sessions) {
        const row = document.createElement('div'); row.className = 'session-row';
        const title = document.createElement('span'); title.textContent = `${session.name || 'Untitled'} · ${session.start_time} · ${session.end_time ? 'finished' : 'open'}`;
        const csv = document.createElement('a'); csv.href = `/session/${Number(session.id)}/export`; csv.textContent = 'CSV'; csv.download = '';
        const play = document.createElement('button'); play.textContent = 'Replay'; play.onclick = () => this.loadReplay(Number(session.id), play);
        row.append(title, csv, play); list.append(row);
      }
    } catch (error) { if (token === this.requestId) this.notice(error.message); }
  }
  async loadReplay(id, button) {
    const token = ++this.requestId; button.disabled = true;
    try {
      const recording = await api(`/session/${id}/frames`);
      if (token !== this.requestId) return;
      const frames = recording.frames.map(normalizeFrame);
      if (!frames.length) throw new Error('No replayable snapshots. Older recordings may only support CSV export.');
      const start = Date.parse(frames[0].timestamp);
      const times = frames.map((frame, index) => {
        const delta = (Date.parse(frame.timestamp) - start) / 1000;
        return Number.isFinite(delta) ? Math.max(0, delta) : index / 5;
      });
      this.obs.selectSource('replay');
      this.replay = { frames, times, time: 0, speed: Number(el('playback-speed').value), duration: times.at(-1), truncated: recording.truncated };
      el('playback-seek').max = this.replay.duration || 1; el('playback-seek').step = 0.1;
      this.close();
    } catch (error) { this.notice(error.message); }
    finally { button.disabled = false; }
  }
  replayFrame(dt) {
    if (!this.replay) return emptyFrame();
    const replay = this.replay;
    if (!this.obs._paused) replay.time = Math.min(replay.duration, replay.time + dt * replay.speed);
    let index = replay.times.findIndex(time => time > replay.time);
    index = index === -1 ? replay.frames.length - 1 : Math.max(0, index - 1);
    const frame = replay.frames[index];
    return { ...frame, meta: { ...frame.meta, label: 'RECORDED REPLAY', isReplay: true,
      note: `Historical ${frame.source} data. ${replay.truncated ? 'First 10,000 snapshots loaded; full recording available as CSV.' : 'No live detection in replay mode.'}` } };
  }
  update(data) {
    if (performance.now() - this.lastUpdate < 200) return;
    this.lastUpdate = performance.now();
    const mode = this.obs.settings.dataSource, meta = data?.meta || {};
    const badge = el('data-source-badge');
    const label = meta.label || (mode === 'demo' ? 'DEMO · SYNTHETIC' : 'WAITING FOR DATA');
    show('data-source-label', this.obs._paused ? `PAUSED VIEW · ${label}` : label);
    badge.dataset.mode = mode === 'demo' || meta.synthetic ? 'demo' : meta.fresh ? 'live' : 'offline';
    const dot = badge.querySelector('.dot');
    if (dot) dot.className = `dot dot--${meta.fresh && !meta.synthetic ? 'live' : 'demo'}`;
    show('motion-label', meta.local ? 'Change score' : 'Motion');
    show('source-note', `${meta.note || (mode === 'demo' ? 'Generated scenario. People, poses, and vital signs are simulated.' : this.obs._connectionState || 'Waiting for a sensor…')} Room layout is illustrative.`);
    for (const [id, target] of [['mode-native', 'native'], ['mode-demo', 'demo'], ['mode-server', 'ws']]) el(id).classList.toggle('active', mode === target);
    el('playback-bar').hidden = mode !== 'replay';
    if (mode === 'replay' && this.replay) {
      el('playback-seek').value = this.replay.time;
      show('playback-time', `${this.replay.time.toFixed(1)} / ${this.replay.duration.toFixed(1)} s`);
      show('playback-pause', this.obs._paused ? 'Resume' : 'Pause');
    }
    if (!this.isOpen) return;
    if (this.page === 'operations') {
      const local = mode === 'native' ? data.meta?.local : null;
      show('op-state', local?.state || 'Select live sensor'); show('op-rate', format(local?.read_rate_hz, ' Hz'));
      show('op-age', format(local?.sample_age_ms, ' ms')); show('op-progress', format(local?.learning_progress * 100, '%'));
      el('op-calibrate').disabled = !local || !meta.fresh;
      el('op-record').disabled = !local || !meta.fresh || local.recording;
      el('op-stop').disabled = !local?.recording;
      show('op-recording', local?.recording ? `Recording session #${local.session_id}` : 'Not recording this sensor.');
      show('op-error', local?.recording_error || '');
    }
    if (this.page === 'devices') {
      const list = el('device-list'); list.replaceChildren();
      for (const node of data.nodes || []) {
        const row = document.createElement('div'); row.className = 'device-row';
        row.textContent = `${node.name || `Node ${node.node_id}`} · ${format(node.rssi_dbm, ' dBm')} · ${node.subcarrier_count ? `${node.subcarrier_count} subcarriers` : node.channel ? `channel ${node.channel}` : 'channel unavailable'}`;
        list.append(row);
      }
      if (!list.childElementCount) list.textContent = 'No sensor nodes reported by this stream.';
    }
  }
}
