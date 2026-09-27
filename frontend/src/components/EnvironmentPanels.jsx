import { useCallback, useEffect, useState } from 'react';
import { Bell, BellOff, Waves } from 'lucide-react';
import CsiWaterfall from './CsiWaterfall';

const bands = [
  ['slow_oscillation', 'Slow oscillation', '0.1–0.5 Hz'],
  ['mid_activity', 'Mid activity', '0.5–2 Hz'],
  ['fast_activity', 'Fast activity', '2–4 Hz'],
];

export function LinksPanel({ links }) {
  return <section className="panel links-panel"><div className="panel-heading">
    <div><p className="eyebrow">MEASURED LINKS</p><h2>Every channel the room exposes</h2></div>
    <span className="tag">{links?.length ? `${links.length + 1} LINKS` : '1 LINK'}</span></div>
    <ul className="link-list">
      <li className="link-row primary"><span className="link-name">Your router (primary)</span>
        <span className="link-note">fast channel · per-sample updates</span></li>
      {(links || []).map(link => <li key={link.bssid} className="link-row">
        <span className="link-name">{link.ssid || 'Hidden network'}</span>
        <span className="link-strength"><i style={{ width: `${Math.max(4, Math.min(100, link.signal ?? 0))}%` }} /></span>
        <span className="link-meta">{link.rssi_dbm == null ? '—' : `${link.rssi_dbm} dBm`} · ch {link.channel ?? '—'} · age {link.age_s ?? '—'}s</span>
      </li>)}
    </ul>
    {(!links || !links.length) && <p className="muted small">Neighbor links appear here when your driver's scan cache lists them; they are slow channels and may be empty.</p>}
    <p className="muted small">Neighbor telemetry refreshes on the driver's scan cadence — it reflects the environment, not per-sample motion.</p>
  </section>;
}

export function SpectralPanel({ spectral }) {
  return <section className="panel spectral-panel"><div className="panel-heading">
    <div><p className="eyebrow">SPECTRAL VIEW</p><h2>Oscillations in the link</h2></div>
    <span className="tag">{spectral ? `${spectral.window_s}s WINDOW` : 'COLLECTING'}</span></div>
    {spectral ? <div>
      {bands.map(([key, label, range]) => <div key={key} className="band-row">
        <span className="band-label">{label}<small>{range}</small></span>
        <span className="band-bar"><i style={{ width: `${Math.round((spectral[key] ?? 0) * 100)}%` }} /></span>
        <span className="band-value">{Math.round((spectral[key] ?? 0) * 100)}%</span>
      </div>)}
      <dl className="spectral-meta">
        <div><dt>Dominant frequency</dt><dd>{spectral.dominant_hz?.toFixed(2)} Hz</dd></div>
        <div><dt>Spectral entropy</dt><dd>{spectral.spectral_entropy?.toFixed(2)}</dd></div>
      </dl>
      <p className="muted small">Descriptive statistics of the measured signal. Band energy does not mean breathing, footsteps, or people.</p>
    </div> : <p className="muted">Building a 30-second uniform window of samples…</p>}
  </section>;
}

export function EventsJournal({ base = '', refreshKey = 0 }) {
  const [events, setEvents] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [detail, setDetail] = useState(null);
  const fetchEvents = useCallback((signal) => fetch(`${base}/api/events?limit=8`, { signal })
    .then(response => response.ok ? response.json() : { events: [] })
    .then(data => setEvents(data.events))
    .catch(() => { /* the live status already carries connection failures */ }), [base]);
  useEffect(() => {
    const controller = new AbortController();
    fetchEvents(controller.signal);
    return () => controller.abort();
  }, [fetchEvents, refreshKey]);
  const load = () => { fetchEvents(); };
  const open = async id => {
    if (openId === id) { setOpenId(null); setDetail(null); return; }
    setOpenId(id); setDetail(null);
    try {
      const response = await fetch(`${base}/api/events/${id}`);
      if (response.ok) setDetail(await response.json());
    } catch { setDetail(null); }
  };
  return <section className="panel journal-panel"><div className="panel-heading">
    <div><p className="eyebrow">EVENT JOURNAL</p><h2>What changed, and when</h2></div>
    <button className="button small" onClick={load}>Refresh</button></div>
    {events.length ? <ul className="journal-list">{events.map(event => <li key={event.id}>
      <button className="journal-row" onClick={() => open(event.id)}>
        <span className="journal-time">{new Date(event.started_at).toLocaleString()}</span>
        <span className="journal-meta">{event.duration_s != null ? `${event.duration_s}s` : 'ongoing'} · peak {Math.round(event.peak_change_score)}/100{event.stop_reason ? ` · ${event.stop_reason.replace('_', ' ')}` : ''}</span>
      </button>
      {openId === event.id && <div className="journal-detail">
        {detail ? <div>
          <p className="small">{detail.pre_frames.length} frames before · {detail.post_frames.length} frames during/after · peak change {Math.round(detail.peak_change_score)}/100 · baseline {detail.baseline_dbm ?? '—'} dBm · {detail.neighbor_links ?? 0} neighbor links</p>
          <Sparkline frames={detail.pre_frames} label="Before the trigger" />
          <Sparkline frames={detail.post_frames} label="Triggered period" />
        </div> : <p className="muted small">Loading detail…</p>}
      </div>}
    </li>)}</ul>
      : <p className="muted">Sustained signal changes will be journaled here with their before/after context.</p>}
    <p className="muted small">Events record signal statistics only — never identities, positions, or people.</p>
  </section>;
}

function Sparkline({ frames, label }) {
  if (!frames?.length) return null;
  const values = frames.map(frame => frame.s ?? 0);
  const max = Math.max(...values, 1);
  const points = values.map((value, i) => `${(i / Math.max(1, values.length - 1)) * 300},${40 - (value / max) * 36}`).join(' ');
  return <div className="sparkline"><span className="sparkline-label">{label}</span>
    <svg viewBox="0 0 300 44" preserveAspectRatio="none" aria-hidden="true"><polyline points={points} fill="none" strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg></div>;
}

export function AlertsToggle({ enabled, busy, onToggle }) {
  return <button className="button alerts" disabled={busy} onClick={onToggle} title="Optional local Windows notification on sustained signal changes">
    {enabled ? <BellOff size={15} /> : <Bell size={15} />}{enabled ? 'Disable alerts' : 'Alert me on changes'}
  </button>;
}

export function WaterfallPanel({ data }) {
  const isDemo = data.is_simulation;
  return <section className="panel csi-panel"><div className="panel-heading">
    <div><p className="eyebrow">CSI SPECTRUM</p><h2>Subcarrier waterfall</h2></div>
    <span className="tag">{isDemo ? 'SYNTHETIC DEMO' : 'LIVE CSI'}</span></div>
    <CsiWaterfall preview={data.csi_preview} />
    <p className="muted small"><Waves size={12} /> CSI amplitude capture {isDemo ? 'is simulated for demonstration' : 'from the connected receiver'}. CSI is richer than RSSI but still not a people detector.</p>
  </section>;
}

