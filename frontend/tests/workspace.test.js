import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
import { WorkspaceControls } from '../observatory/wiwave-controls.js';
import { HudController, DEFAULTS } from '../observatory/js/hud-controller.js';
import { normalizeFrame } from '../observatory/wiwave-data.js';

test('actual Observatory markup supports source switching, settings, controls and timed replay', async t => {
  const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'), { url: 'http://localhost:8000' });
  const original = { document: globalThis.document, localStorage: globalThis.localStorage, fetch: globalThis.fetch };
  globalThis.document = dom.window.document;
  globalThis.localStorage = dom.window.localStorage;
  dom.window.HTMLCanvasElement.prototype.getContext = () => null;
  const calls = [];
  const payload = { type: 'radar_update', source: 'native_rssi', system_status: 'ok', state: 'quiet', sequence: 1,
    timestamp: '2026-09-25T00:00:00Z', rssi_dbm: -45, read_rate_hz: 10, sample_age_ms: 50, learning_progress: 1 };
  globalThis.fetch = async (path, options) => {
    calls.push([path, options.method]);
    const result = path === '/sessions' ? [{ id: 5, name: '<script>unsafe</script>', start_time: payload.timestamp, end_time: payload.timestamp }]
      : path.includes('/frames') ? { frames: [payload, { ...payload, sequence: 2, timestamp: '2026-09-25T00:00:01Z' }], truncated: false }
      : { message: 'Completed' };
    return { ok: true, json: async () => result };
  };
  t.after(() => { Object.assign(globalThis, original); dom.window.close(); });
  const obs = { settings: { ...DEFAULTS }, _paused: false, _connectionState: 'connected',
    _grid: {}, _roomWire: {}, _demoData: { setScenario() {}, currentScenario: 'empty_room', _autoMode: true },
    selectSource(mode) { this.settings.dataSource = mode; this._paused = false; } };
  obs._hud = new HudController(obs);
  obs._hud.initSettings(); obs._hud.initQuickSelect();
  const workspace = new WorkspaceControls(obs);
  const get = id => document.getElementById(id);
  workspace.open(); workspace.update(normalizeFrame(payload));
  assert.equal(get('op-rate').textContent, '10.0 Hz');
  assert.equal(get('op-calibrate').disabled, false);
  await workspace.action(get('op-calibrate'), '/api/calibrate');
  assert.ok(calls.some(([path, method]) => path === '/api/calibrate' && method === 'POST'));
  workspace.close();
  get('mode-demo').click();
  workspace.open(); workspace.lastUpdate = 0;
  workspace.update({ meta: { synthetic: true, fresh: true, label: 'DEMO · SYNTHETIC' } });
  assert.equal(get('op-record').disabled, true);
  assert.match(get('data-source-label').textContent, /SYNTHETIC/);
  // The badge children must survive rendering so settings can still update them.
  assert.doesNotThrow(() => obs._hud.updateSourceBadge('native', null));
  get('mode-native').click();
  assert.equal(obs.settings.dataSource, 'native');
  workspace.page = 'sessions'; workspace.render(); await new Promise(resolve => setImmediate(resolve));
  assert.match(get('session-list').textContent, /<script>unsafe/);
  assert.equal(get('session-list').querySelector('script'), null);
  const play = get('session-list').querySelector('button');
  await workspace.loadReplay(5, play);
  assert.equal(obs.settings.dataSource, 'replay');
  const frame = workspace.replayFrame(.5);
  assert.equal(frame.meta.isReplay, true); assert.equal(frame.timestamp, payload.timestamp);
  assert.equal(workspace.replayFrame(.6).tick, 2);
  obs._paused = true; workspace.replayFrame(1); assert.equal(workspace.replay.time, 1);
  get('playback-exit').click(); assert.equal(obs.settings.dataSource, 'native');
  for (const page of ['operations', 'devices', 'models', 'features']) {
    workspace.page = page; workspace.open(); workspace.update(normalizeFrame(payload));
    assert.ok(get('workspace-content').textContent.length > 20);
  }
});
