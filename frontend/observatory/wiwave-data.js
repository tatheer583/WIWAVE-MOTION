// WiWave adapter for local telemetry and RuView SensingUpdate messages.
// Unknown values remain unknown; generated poses are reserved for demo mode.
const finite = value => typeof value === 'number' && Number.isFinite(value);
const bounded = (value, min, max) => finite(value) && value >= min && value <= max ? value : null;
const emptyField = () => ({ grid_size: [20, 1, 20], values: [] });
export const COCO_JOINTS = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder', 'right_shoulder',
  'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist', 'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle'];
export function poseKeypoints(value) {
  if (!Array.isArray(value) || value.length !== 17) return null;
  const points = Array.isArray(value[0]) ? value : COCO_JOINTS.map(name => {
    const point = value.find(p => p?.name === name);
    return point ? [point.x, point.y, point.z, point.confidence] : null;
  });
  return points.every(p => Array.isArray(p) && p.length >= 4 && p.slice(0, 3).every(v => finite(v) && Math.abs(v) <= 100)
    && bounded(p[3], 0.25, 1) !== null) ? points : null;
}

export function emptyFrame(state = 'waiting') {
  return { type: 'sensing_update', source: 'unavailable', timestamp: 0, nodes: [], persons: [],
    features: {}, classification: { presence: null, confidence: null, motion_level: 'unknown' },
    signal_field: emptyField(), vital_signs: null, estimated_persons: null,
    meta: { state, label: 'WAITING FOR DATA', synthetic: false, fresh: false, poseAvailable: false } };
}

export function normalizeFrame(raw) {
  if (!raw || typeof raw !== 'object') throw new Error('Expected a sensor frame');
  if (raw.type === 'radar_update') {
    const fresh = raw.system_status === 'ok';
    return { ...emptyFrame(raw.state), source: raw.source, timestamp: raw.timestamp, tick: raw.sequence,
      features: { mean_rssi: fresh ? bounded(raw.rssi_dbm, -127, 0) : null,
        variance: null, motion_band_power: fresh ? bounded(raw.change_score, 0, 100) : null },
      nodes: raw.adapter ? [{ node_id: 'local', name: raw.adapter, rssi_dbm: raw.rssi_dbm,
        channel: raw.channel, ssid: raw.ssid, connected: fresh }] : [],
      meta: { state: raw.state, label: raw.is_simulation ? 'SIMULATED BACKEND' : fresh ? raw.source === 'esp32_csi' ? 'LIVE CSI' : 'LIVE WI-FI' : 'SENSOR OFFLINE',
        synthetic: Boolean(raw.is_simulation), fresh, poseAvailable: false, local: raw,
        note: raw.error || `${String(raw.state || 'waiting').replaceAll('_', ' ')} · Signal changes only. Person, pose, and vital-sign estimates are unavailable.` } };
  }
  if (raw.type !== 'sensing_update') throw new Error('Unsupported frame type');
  const synthetic = /demo|simulat|synthetic/i.test(String(raw.source));
  const csi = /esp32|csi/i.test(String(raw.source));
  const fresh = (csi || synthetic || raw.source === 'wifi') && raw.source !== 'offline';
  const cls = raw.classification || {};
  const vs = raw.vital_signs || {};
  const candidates = Array.isArray(raw.persons) ? raw.persons.slice(0, 4) : [];
  if (!candidates.some(p => poseKeypoints(p?.keypoints)) && poseKeypoints(raw.pose_keypoints)) candidates.push({ id: 'model-pose', keypoints: raw.pose_keypoints });
  // Upstream persons may be heuristic positions. Never invent skeletons for them.
  const persons = fresh && (csi || synthetic) ? candidates.filter(p => poseKeypoints(p?.keypoints)).slice(0, 4).map((p, i) => {
    const keypoints = poseKeypoints(p.keypoints).map(k => k.slice(0, 3));
    return { id: String(p.id ?? i).slice(0, 80), keypoints, position: keypoints[11], pose: 'model', motion_score: 0 };
  }) : [];
  const advanced = fresh && (csi || synthetic);
  const presence = advanced && typeof cls.presence === 'boolean' ? cls.presence : null;
  return { ...emptyFrame(fresh ? 'streaming' : 'disconnected'), source: raw.source,
    timestamp: raw.timestamp, tick: raw.tick, nodes: fresh && Array.isArray(raw.nodes) ? raw.nodes.filter(n => n && typeof n === 'object').slice(0, 64) : [],
    features: { mean_rssi: fresh ? bounded(raw.features?.mean_rssi, -127, 0) : null,
      variance: fresh ? bounded(raw.features?.variance, 0, 1e9) : null, motion_band_power: fresh ? bounded(raw.features?.motion_band_power, 0, 1e9) : null },
    classification: { presence, confidence: advanced ? bounded(cls.confidence, 0, 1) : null,
      motion_level: advanced ? String(cls.motion_level ?? 'unknown') : 'unknown', fall_detected: advanced && cls.fall_detected === true },
    vital_signs: advanced ? { heart_rate_bpm: bounded(vs.heart_rate_bpm, 1, 250), breathing_rate_bpm: bounded(vs.breathing_rate_bpm, 1, 80) } : null,
    estimated_persons: advanced && Number.isInteger(raw.estimated_persons) ? bounded(raw.estimated_persons, 0, 100) : null,
    persons, model_status: raw.model_status || null,
    signal_field: advanced && Array.isArray(raw.signal_field?.values) ? {
      grid_size: [20, 1, 20], values: raw.signal_field.values.slice(0, 400).map(v => bounded(v, 0, 1) ?? 0),
    } : emptyField(),
    meta: { state: fresh ? 'streaming' : 'disconnected', fresh, synthetic, poseAvailable: persons.length > 0,
      label: synthetic ? 'SIMULATED UPSTREAM' : csi && fresh ? 'LIVE CSI · ESTIMATES' : fresh ? 'LIVE RSSI' : 'SENSOR OFFLINE',
      note: csi ? 'Upstream model estimates; accuracy depends on hardware, models, and room validation.' : 'This stream does not provide measured pose or vital signs.' } };
}

export class LiveConnection {
  constructor(onFrame, onStatus) { this.onFrame = onFrame; this.onStatus = onStatus; }
  connect(url) {
    this.close();
    const parsed = new URL(url, window.location.href);
    if (!['ws:', 'wss:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error('Enter a ws:// or wss:// endpoint without embedded credentials');
    this.url = parsed.href;
    this.closed = false;
    this.open();
    this.watchdog = setInterval(() => {
      if (this.receivedAt && Date.now() - this.receivedAt > 3000) {
        this.onFrame(emptyFrame('stale'));
        this.onStatus('stale');
        this.socket?.close();
        this.receivedAt = 0;
      }
    }, 500);
  }
  open() {
    if (this.closed) return;
    this.onStatus('connecting');
    const socket = this.socket = new WebSocket(this.url);
    this.connectTimeout = setTimeout(() => socket.close(), 4000);
    socket.onopen = () => { if (this.closed || this.socket !== socket) return; clearTimeout(this.connectTimeout); this.lastKey = null; this.receivedAt = Date.now(); this.onStatus('connected'); };
    socket.onmessage = event => {
      if (this.closed || this.socket !== socket) return;
      try {
        if (typeof event.data !== 'string' || event.data.length > 1000000) throw new Error('Frame too large');
        const frame = normalizeFrame(JSON.parse(event.data));
        const key = frame.tick ?? frame.timestamp;
        if (key == null || key !== this.lastKey) this.receivedAt = Date.now();
        this.lastKey = key;
        this.onFrame(frame);
      } catch (error) { this.onStatus(error.message); }
    };
    socket.onclose = () => {
      clearTimeout(this.connectTimeout);
      if (this.closed || this.socket !== socket) return;
      socket.onmessage = null;
      this.onFrame(emptyFrame('disconnected'));
      this.onStatus('disconnected');
      this.retry = setTimeout(() => this.open(), 2000);
    };
    socket.onerror = () => socket.close();
  }
  close() {
    this.closed = true;
    clearTimeout(this.retry); clearTimeout(this.connectTimeout); clearInterval(this.watchdog);
    if (this.socket) { this.socket.onclose = null; this.socket.close(); }
    this.socket = null; this.receivedAt = 0;
  }
}
