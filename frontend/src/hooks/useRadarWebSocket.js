import { useEffect, useState } from 'react';

export const initialData = {
  state: 'waiting', source: 'native_rssi', system_status: 'waiting', sequence: 0,
  signal: null, rssi_dbm: null, change_score: 0, learning_progress: 0,
  read_rate_hz: 0, motion_detected: false, event_count: 0, recording: false,
};

// One socket, one fallback poll, bounded history, and complete unmount cleanup.
export function useRadarWebSocket() {
  const [view, setView] = useState({ data: initialData, history: [], events: [], connection: 'connecting' });
  useEffect(() => {
    let disposed = false, socket, reconnectTimer, connectTimer, pollTimer, controller;
    let attempts = 0, lastMessageAt = 0, lastSequence = -1, serverTimestamp = null;
    const base = import.meta.env.VITE_API_URL || window.location.origin;
    const wsUrl = import.meta.env.VITE_WS_URL || `${base.replace(/^http/, 'ws')}/ws/radar`;
    const accept = (data, transport) => {
      if (disposed || data.type !== 'radar_update') return;
      lastMessageAt = Date.now();
      const newSample = data.sequence !== lastSequence || data.timestamp !== serverTimestamp;
      lastSequence = data.sequence;
      serverTimestamp = data.timestamp;
      setView(prev => {
        const transition = prev.data.state !== data.state;
        const history = newSample && data.system_status === 'ok' && Number.isFinite(data.rssi_dbm)
          ? [...prev.history, { at: Date.parse(data.timestamp), rssi: data.rssi_dbm, score: data.change_score }].slice(-600)
          : prev.history;
        return { data, connection: transport, history,
          events: transition ? [{ state: data.state, at: new Date().toLocaleTimeString() }, ...prev.events].slice(0, 8) : prev.events };
      });
    };
    const markOffline = () => {
      if (!disposed) setView(prev => ({ ...prev, connection: 'offline',
        data: { ...prev.data, state: 'offline', system_status: 'offline', motion_detected: false, change_score: 0, rssi_dbm: null } }));
    };
    const poll = async () => {
      if (disposed) return;
      if (socket?.readyState === WebSocket.OPEN) {
        pollTimer = setTimeout(poll, 1000);
        return;
      }
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 2500);
      try {
        const response = await fetch(`${base}/api/poll`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error('Polling unavailable');
        const data = await response.json();
        if (socket?.readyState !== WebSocket.OPEN) accept(data, 'polling');
      } catch { if (socket?.readyState !== WebSocket.OPEN) markOffline(); }
      finally {
        clearTimeout(timeout);
        if (!disposed) pollTimer = setTimeout(poll, 1000);
      }
    };
    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(wsUrl);
      const current = socket;
      connectTimer = setTimeout(() => { if (current.readyState === WebSocket.CONNECTING) current.close(); }, 4000);
      current.onopen = () => {
        if (disposed) return current.close();
        attempts = 0;
        clearTimeout(connectTimer);
        controller?.abort();
        lastMessageAt = Date.now();
      };
      current.onmessage = event => {
        try { accept(JSON.parse(event.data), 'websocket'); } catch { /* Ignore malformed frames. */ }
      };
      current.onerror = () => current.close();
      current.onclose = () => {
        if (disposed || socket !== current) return;
        clearTimeout(connectTimer);
        reconnectTimer = setTimeout(connect, Math.min(10000, 1000 * 2 ** attempts++));
      };
    };
    connect();
    poll();
    const watchdog = setInterval(() => {
      if (lastMessageAt && Date.now() - lastMessageAt > 4000) {
        markOffline();
        if (socket?.readyState === WebSocket.OPEN) socket.close();
      }
    }, 1000);
    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      clearTimeout(connectTimer);
      clearTimeout(pollTimer);
      clearInterval(watchdog);
      controller?.abort();
      socket?.close();
    };
  }, []);
  return view;
}
