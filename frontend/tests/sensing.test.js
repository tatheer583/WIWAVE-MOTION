import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeFrame, emptyFrame, poseKeypoints, COCO_JOINTS, LiveConnection } from '../observatory/wiwave-data.js';
import { DemoDataGenerator } from '../observatory/js/demo-data.js';
import { FigurePool } from '../observatory/js/figure-pool.js';
import { PoseSystem } from '../observatory/js/pose-system.js';
import { DEFAULTS } from '../observatory/js/hud-controller.js';
import * as THREE from 'three';

test('real RSSI cannot claim people, vitals, or skeletons even with misleading legacy fields', () => {
  const frame = normalizeFrame({ type: 'radar_update', system_status: 'ok', source: 'native_rssi', sequence: 3,
    rssi_dbm: -47, person_count: 2, persons: [{ position: [1, 1, 1] }], bpm: 72, change_score: 4 });
  assert.equal(frame.features.mean_rssi, -47);
  assert.equal(frame.features.motion_band_power, 4);
  assert.equal(frame.classification.presence, null);
  assert.equal(frame.estimated_persons, null);
  assert.equal(frame.vital_signs, null);
  assert.deepEqual(frame.persons, []);
  assert.equal(frame.meta.synthetic, false);
});
test('offline and invalid values do not appear as current measurements', () => {
  const frame = normalizeFrame({ type: 'sensing_update', source: 'offline', features: { mean_rssi: -45, variance: 100 },
    classification: { presence: true }, vital_signs: { heart_rate_bpm: 72 }, estimated_persons: 2 });
  assert.equal(frame.meta.fresh, false);
  assert.equal(frame.features.variance, null);
  assert.equal(frame.estimated_persons, null);
  const invalid = normalizeFrame({ type: 'sensing_update', source: 'esp32', features: { mean_rssi: NaN }, vital_signs: { heart_rate_bpm: Infinity } });
  assert.equal(invalid.features.mean_rssi, null);
  assert.equal(invalid.vital_signs.heart_rate_bpm, null);
  assert.throws(() => normalizeFrame({ type: 'random' }));
});
test('CSI heuristic positions do not generate poses; named COCO joints are reordered and confidence checked', () => {
  const raw = { type: 'sensing_update', source: 'esp32', classification: { presence: true, confidence: .8 }, persons: [{ id: 1, position: [0, 0, 0] }], estimated_persons: 1 };
  assert.equal(normalizeFrame(raw).persons.length, 0);
  const keypoints = COCO_JOINTS.map((name, i) => ({ name, x: i / 20, y: 1, z: 0, confidence: .8 })).reverse();
  raw.persons[0].keypoints = keypoints;
  const frame = normalizeFrame(raw);
  assert.equal(frame.persons.length, 1);
  assert.equal(frame.persons[0].keypoints[0][0], 0);
  assert.equal(frame.persons[0].keypoints[16][0], .8);
  keypoints[0].confidence = 0;
  assert.equal(normalizeFrame(raw).persons.length, 0);
  assert.equal(poseKeypoints([null]), null);
});
test('unknown and RSSI-only upstream sources cannot enable advanced sensing', () => {
  for (const source of ['wifi', 'unknown']) {
    const frame = normalizeFrame({ type: 'sensing_update', source, classification: { presence: true }, estimated_persons: 3 });
    assert.equal(frame.estimated_persons, null);
    assert.equal(frame.classification.presence, null);
  }
  assert.equal(normalizeFrame({ type: 'sensing_update', source: 'simulated' }).meta.synthetic, true);
});
test('all twelve scenarios generate finite poses and transition back to an empty live view', () => {
  const generator = new DemoDataGenerator();
  const pool = new FigurePool(new THREE.Scene(), { ...DEFAULTS }, new PoseSystem());
  const scenarios = ['empty_room', 'single_breathing', 'two_walking', 'fall_event', 'sleep_monitoring', 'intrusion_detect',
    'gesture_control', 'crowd_occupancy', 'search_rescue', 'elderly_care', 'fitness_tracking', 'security_patrol'];
  for (const scenario of scenarios) {
    generator.setScenario(scenario);
    let frame;
    for (let i = 0; i < 100; i++) frame = generator.update(.1);
    frame.meta = { synthetic: true };
    assert.ok(Number.isFinite(frame.features.mean_rssi), scenario);
    pool.update(frame, 10);
    for (const figure of pool._figures.filter(f => f.visible)) {
      assert.ok(figure.joints.every(j => Number.isFinite(j.position.x) && Number.isFinite(j.position.y) && Number.isFinite(j.position.z)), scenario);
    }
    pool.update(emptyFrame('disconnected'), 11);
    assert.ok(pool._figures.every(f => !f.visible));
  }
});
test('websocket reconnects, rejects malformed payloads and expires repeated stale frames without demo fallback', t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: 10000 });
  const originalWindow = globalThis.window, originalSocket = globalThis.WebSocket;
  const sockets = [], frames = [], statuses = [];
  globalThis.window = { location: { href: 'http://localhost:8000' } };
  globalThis.WebSocket = class {
    constructor() { sockets.push(this); }
    close() { this.onclose?.(); }
    message(value) { this.onmessage?.({ data: JSON.stringify(value) }); }
  };
  const connection = new LiveConnection(f => frames.push(f), s => statuses.push(s));
  try {
    assert.throws(() => connection.connect('https://example.com'));
    connection.connect('ws://localhost:8000/ws/radar'); sockets[0].onopen();
    sockets[0].message({ type: 'bad' });
    assert.equal(statuses.at(-1), 'Unsupported frame type');
    const payload = { type: 'radar_update', sequence: 4, system_status: 'ok', source: 'native_rssi' };
    sockets[0].message(payload);
    for (let i = 0; i < 8; i++) { t.mock.timers.tick(500); sockets[0].message(payload); }
    assert.ok(statuses.includes('stale'));
    assert.ok(frames.some(frame => frame.meta.state === 'disconnected'));
    assert.equal(frames.at(-1).meta.fresh, false);
    assert.ok(frames.every(frame => frame.meta.synthetic === false));
    t.mock.timers.tick(2000);
    assert.ok(sockets.length >= 2);
    connection.close(); const count = sockets.length;
    t.mock.timers.tick(5000); assert.equal(sockets.length, count);
  } finally { connection.close(); globalThis.window = originalWindow; globalThis.WebSocket = originalSocket; }
});
