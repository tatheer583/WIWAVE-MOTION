# RuView reference and WiWave feature status

Updated 2026-09-25. This is a feature comparison, not a claim of complete platform parity.

The reference is [RuView](https://github.com/ruvnet/RuView), pinned at
`dd02efe2fe129ae8068e9b805ea35aaa660e47dd`. WiWave adapts its MIT-licensed
`ui/observatory.html` and eight rendering modules. See
[the provenance record](../frontend/observatory/PROVENANCE.md).

| Reference feature | WiWave implementation | Evidence / dependency |
| --- | --- | --- |
| 3D Observatory room, grid, router, orbit camera | Included | Production build; scene helpers tested; visual browser QA pending |
| Wireframe skeletons, body segments, aura, scene props | Included for demo; model skeletons need valid keypoints | Procedural skeletons never created from live RSSI |
| Bloom, exposure, grain, chromatic effects, colors and sizing | Included from upstream | Settings bindings exercised in DOM tests; GPU rendering unverified |
| Six style presets, reset camera, settings export | Included | Preferences saved locally |
| Twelve scenarios with auto-cycle and keyboard controls | Included as synthetic demonstrations | Scenario/pose tests cover all twelve |
| Native Windows signal monitoring | Included | Native WLAN hardware stream verified on this computer |
| Calibration and signal-change detector | Included | Deterministic detector tests; movement accuracy needs room trials |
| Devices, source health and freshness | Included | Local adapter or upstream-reported nodes; no invented devices |
| Session recording and export | Included for local backend | HTTP / WebSocket / SQLite integration tests |
| Session replay, seek, pause, speed | Added | Preserves timestamps and source labels; first 10,000 snapshots; CSV exports full recording |
| ESP32 CSI serial capture | Implemented, hardware validation pending | Header-aware Espressif CSV parser; not RuView binary firmware UDP |
| RuView sensing-server connection | Included | Protocol adapter tested; an external compatible server is required |
| Human presence and count estimates | Can display upstream CSI output | No local human model; cannot certify upstream accuracy |
| 17-keypoint model poses | Can display upstream CSI output | COCO order; each joint confidence >= 0.25; placeholder/zero-confidence poses hidden |
| Heart rate, respiration and fall estimates | Can display upstream CSI output | Unvalidated estimates; not a medical or emergency system |
| Multi-node room mapping, measured range and object classification | Not implemented | Hardware geometry, synchronization, algorithms and validation required |
| Training, LoRA adaptation, model management UI | Not integrated | Research links and connection guidance provided |
| Firmware flashing, node provisioning and upstream edge/WASM modules | Not integrated | Use upstream tooling and compatible hardware |
| Full RuView control dashboard and other experimental visualizations | Not ported | This release adapts the Observatory, with a WiWave operations workspace |

## Sources and display rules

**Live sensor** connects to `/ws/radar` on WiWave. It displays real RSSI or the
configured serial CSI detector. Neither source currently has a validated human
classifier. Unsupported outputs remain unknown, including when the detector is quiet.

**Demo scenarios** runs the reference's generator locally. Labels identify every
scenario as synthetic. Selecting another mode clears its charts and generated bodies.

**Connect RuView** opens Settings → Data. Enter, for example,
`ws://127.0.0.1:3000/ws/sensing` for a separately running compatible sensing server.
No RuView server is installed or started by this repository. Its source field is
preserved: simulated upstream data is labelled simulated. A CSI source label is
provenance reported by that server, not independent hardware attestation.

Supported `sensing_update` fields include `nodes`, `features`, `classification`,
`estimated_persons`, `vital_signs`, and 17-joint `persons[].keypoints` or
`pose_keypoints`. Named joints are reordered to COCO order; array joints must be
`[x,y,z,confidence]`. Coordinates are displayed as supplied, without inferring
meters or room calibration. Low-confidence and position-only persons are not
converted into generated skeletons. Unknown sources cannot enable advanced outputs.

Connections retry after two seconds; three seconds without progressing frames
clears current measurements. Live connection loss never chooses demo mode.
HTTPS pages require a secure WebSocket endpoint. The backend defaults to loopback;
remote deployment needs authentication and transport configuration outside this release.

## Controls

- Drag to orbit; wheel to zoom. `A`: camera orbit, `F`: frame rate, `S`: settings.
- `D`: next demo scenario. `Space`: pause the displayed data. Acquisition continues.
- **Workspace → Operations**: calibrate, start or stop local recording.
- **Workspace → Recordings**: export CSV or replay a session.
- **Live Monitor**: detailed signal charts at `/monitor.html`, with polling fallback.

The room, waves and router model are decorative reference geometry. The application
does not scan physical room boundaries or locate ordinary objects.
