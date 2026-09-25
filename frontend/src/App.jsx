import { useEffect, useState } from 'react';
import { Activity, ArrowDownToLine, Circle, Cpu, Radio, RotateCcw, Wifi, Waves } from 'lucide-react';
import { useRadarWebSocket } from './hooks/useRadarWebSocket';
import './App.css';

const labels = { waiting: 'Waiting for sensor', calibrating: 'Learning the room', quiet: 'Signal is stable',
  signal_change: 'Signal change detected', motion_candidate: 'Possible motion', disconnected: 'Sensor disconnected',
  stale: 'Sensor data is stale', offline: 'Server offline' };
const base = import.meta.env.VITE_API_URL || '';

function Trace({ history, field, min, max, label, unit }) {
  const first = history[0]?.at ?? 0;
  const span = Math.max(10000, (history.at(-1)?.at ?? first) - first);
  const points = history.map(p => `${((p.at - first) / span) * 800},${110 - Math.max(0, Math.min(1, (p[field] - min) / (max - min))) * 90}`).join(' ');
  return <div className="trace">
    <div className="trace-heading"><h3>{label}</h3><span>{min} to {max} {unit}</span></div>
    <svg viewBox="0 0 800 130" role="img" aria-label={`${label} over the last ${Math.round(span / 1000)} seconds`} preserveAspectRatio="none">
      {[20, 50, 80, 110].map(y => <line key={y} x1="0" x2="800" y1={y} y2={y} className="chart-grid" />)}
      {points && <polyline points={points} fill="none" className={`trace-line ${field}`} strokeWidth="2" vectorEffect="non-scaling-stroke" />}
    </svg>
    <div className="trace-foot"><span>{history.length ? new Date(first).toLocaleTimeString() : 'Waiting for measurements'}</span><span>NOW</span></div>
  </div>;
}

export default function App() {
  const { data, history, events, connection } = useRadarWebSocket();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [sessions, setSessions] = useState([]);
  const available = data.system_status === 'ok';
  const isCsi = data.source === 'esp32_csi';
  const sourceName = data.is_simulation ? 'Synthetic demo' : isCsi ? 'ESP32 · CSI' : 'Laptop · RSSI';
  const title = labels[data.state] || 'Waiting for sensor';
  const loadSessions = async () => {
    try {
      const response = await fetch(`${base}/sessions`);
      if (response.ok) setSessions(await response.json());
    } catch { /* Current sensor status carries connection failures. */ }
  };
  useEffect(() => {
    let active = true;
    fetch(`${base}/sessions`).then(response => response.ok ? response.json() : [])
      .then(rows => { if (active) setSessions(rows); }).catch(() => {});
    return () => { active = false; };
  }, [data.recording]);
  const action = async path => {
    setBusy(true);
    setNotice('');
    try {
      const response = await fetch(`${base}${path}`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Request failed');
      setNotice(result.message);
      await loadSessions();
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Open WiWave Observatory"><Waves size={29} /><span>wiwave<span className="brand-dot">.</span></span></a>
      <div className="workspace-label">SENSING WORKSPACE <span>05</span></div>
      <div className="nav-active"><Radio size={18} /> Live monitor <span className="live-dot" /></div>
      <div className="sidebar-section"><p className="eyebrow">CONNECTED SOURCE</p><div className="source-icon"><Wifi size={22} /></div>
        <h3>{sourceName}</h3><p className="muted">{data.adapter || 'Connecting to your receiver…'}</p>
        <dl className="source-details"><div><dt>Network</dt><dd>{data.ssid || (isCsi ? 'CSI receiver' : '—')}</dd></div>
          <div><dt>Channel</dt><dd>{data.channel ?? '—'}</dd></div><div><dt>Transport</dt><dd>{connection}</dd></div></dl>
      </div>
      <div className="sidebar-section capability-list"><p className="eyebrow">MEASUREMENT CAPABILITIES</p>
        <div><span className="cap-dot enabled" /> Live signal strength</div>
        <div><span className={`cap-dot ${isCsi ? 'enabled' : ''}`} /> CSI amplitude {isCsi ? 'connected' : 'requires receiver'}</div>
        <div><span className="cap-dot" /> People & object identification</div>
        <div><span className="cap-dot" /> Position & distance</div>
        <p className="muted small">Unmeasured capabilities remain unavailable.</p>
      </div>
      <div className="sidebar-bottom"><span className="tiny-square" /> LOCAL-FIRST SENSING<span>v5.0</span></div>
    </aside>

    <main className="main-content">
      <header className="topbar"><div><p className="eyebrow">WORKSPACE / LIVE MONITOR</p><h1>Read the room.</h1><p className="subtitle">Live Wi-Fi measurements. A clearer view of signal changes.</p></div>
        <div className={`source-badge ${data.is_simulation ? 'demo' : available ? 'online' : ''}`}><span className="live-dot" />{data.is_simulation ? 'SIMULATED DATA' : available ? 'LIVE HARDWARE' : 'AWAITING SENSOR'}</div>
      </header>

      <section className="metric-grid" aria-label="Live measurements">
        <article className="metric"><div><span>RECEIVED SIGNAL</span><Wifi size={16} /></div><strong>{data.rssi_dbm == null ? '—' : data.rssi_dbm.toFixed(1)}<small>dBm</small></strong><p>Measured at the receiver</p></article>
        <article className="metric"><div><span>CHANGE SCORE</span><Activity size={16} /></div><strong>{available ? Math.round(data.change_score) : '—'}<small>/ 100</small></strong><p>Baseline deviation · not probability</p></article>
        <article className="metric"><div><span>READ RATE</span><Cpu size={16} /></div><strong>{available ? data.read_rate_hz.toFixed(1) : '—'}<small>Hz</small></strong><p>{isCsi ? 'Received CSI frames' : 'Driver reads · update rate may vary'}</p></article>
        <article className="metric"><div><span>DATA AGE</span><Radio size={16} /></div><strong>{data.sample_age_ms == null || connection === 'offline' ? '—' : data.sample_age_ms}<small>ms</small></strong><p>{available ? 'Sensor stream is current' : 'Waiting for fresh measurements'}</p></article>
      </section>

      <div className="monitor-grid">
        <section className="panel field-panel"><div className="panel-heading"><div><p className="eyebrow">SIGNAL FIELD</p><h2>Environmental activity</h2></div><span className="tag">{isCsi ? 'CSI AMPLITUDE' : 'RSSI MONITOR'}</span></div>
          <div className={`field ${available ? 'running' : ''} ${data.motion_detected ? 'changed' : ''}`} aria-label="Signal activity illustration; no measured positions">
            <div className="field-grid" /><div className="ring ring-one" /><div className="ring ring-two" /><div className="ring ring-three" />
            <div className="field-cross horizontal" /><div className="field-cross vertical" /><div className="sweep" />
            <span className="field-label top">SIGNAL ENVIRONMENT</span><span className="field-label bottom">ACTIVITY VIEW · NO POSITION DATA</span>
            <div className="receiver"><Waves size={35} /><span>RECEIVER</span></div>
          </div>
          <div className="field-caption"><span className={`live-dot ${available ? '' : 'inactive'}`} />{data.is_simulation ? 'Demo visualization using synthetic measurements' : 'Activity illustration driven by live measurements'}<span>NO TARGETS INFERRED</span></div>
        </section>

        <section className="panel detection-panel"><p className="eyebrow">DETECTION STATE</p><div className={`state-symbol ${data.motion_detected ? 'changed' : ''}`}><Activity size={27} /></div>
          <h2 aria-live="polite">{title}</h2><p className="state-description">{data.error || (data.state === 'calibrating' ? 'Keep the room quiet and your laptop and router stationary while the baseline is learned.' : data.motion_detected ? (isCsi ? 'Channel changes may indicate movement. Human presence has not been verified.' : 'The Wi-Fi link changed. Movement, interference, or receiver changes can cause this.') : available ? 'Monitoring changes relative to your quiet-room baseline. A stable signal does not prove the room is empty.' : 'Connect your Wi-Fi adapter or configured CSI receiver to resume live monitoring.')}</p>
          <div className="meter-label"><span>{data.state === 'calibrating' ? 'Calibration' : 'Signal change score'}</span><strong>{data.state === 'calibrating' ? `${Math.round(data.learning_progress * 100)}%` : `${Math.round(data.change_score)} / 100`}</strong></div>
          <div className="meter"><div style={{ width: `${data.state === 'calibrating' ? data.learning_progress * 100 : data.change_score}%` }} /></div>
          <button className="button calibrate" disabled={busy || !available} onClick={() => action('/api/calibrate')}><RotateCcw size={15} /> Calibrate quiet room</button>
          <div className="unavailable-metrics"><div><span>PEOPLE</span><strong>—</strong></div><div><span>RANGE</span><strong>—</strong></div><div><span>EVENTS</span><strong>{data.event_count}</strong></div></div>
          <p className="small muted">{isCsi ? 'CSI motion detection is experimental and needs testing in this room.' : 'Add an ESP32 CSI receiver for richer motion measurements.'}</p>
        </section>
      </div>

      <section className="panel telemetry-panel"><div className="panel-heading"><div><p className="eyebrow">LIVE TELEMETRY</p><h2>The signal, over time</h2></div><span className="legend"><span className="live-dot" /> RSSI <i /> Change score</span></div>
        <div className="charts"><Trace history={history} field="rssi" min={-100} max={-20} label="Signal strength" unit="dBm" /><Trace history={history} field="score" min={0} max={100} label="Baseline deviation" unit="" /></div>
      </section>

      <div className="bottom-grid"><section className="panel events-panel"><div className="panel-heading"><h2>Activity log</h2><span className="tag">THIS CONNECTION</span></div>
        {events.length ? <ul className="event-list">{events.map((event, i) => <li key={`${event.at}-${i}`}><span className="event-marker" /><span>{labels[event.state] || event.state}</span><time>{event.at}</time></li>)}</ul> : <p className="muted">Sensor transitions will appear here.</p>}
      </section><section className="panel sessions-panel"><div className="panel-heading"><h2>Recorded sessions</h2><button className={`button ${data.recording ? 'recording' : ''}`} disabled={busy || (!data.recording && !available)} onClick={() => action(data.recording ? '/session/stop' : '/session/start')}><Circle size={12} fill={data.recording ? 'currentColor' : 'none'} />{data.recording ? 'Stop recording' : 'Record session'}</button></div>
        {sessions.length ? <ul className="session-list">{sessions.slice(0, 4).map(session => <li key={session.id}><div><strong>{session.name}</strong><span>{new Date(session.start_time).toLocaleString()}{data.session_id === session.id ? ' · Recording' : ''}</span></div><a href={`${base}/session/${session.id}/export`} aria-label={`Export ${session.name}`} title="Export CSV"><ArrowDownToLine size={17} /></a></li>)}</ul> : <p className="muted">Record live measurements to compare a quiet room with a walk-through. Export sessions as CSV.</p>}
        {data.recording_error && <p className="error-text">Recording failed: {data.recording_error}</p>}
      </section></div>
      {notice && <div className="notice" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}
      <footer className="page-footer">WiWave / Experimental environmental sensing<span>RSSI and untrained CSI do not identify humans or objects.</span></footer>
    </main>
  </div>;
}
