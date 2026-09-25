# WiWave: evidence, hardware, and implementation decisions

Research and local inspection: 25 September 2026.

## What the requested system needs to measure

The desired experience is an always-on Wi-Fi radar that detects people and other
objects. This contains several different tasks: detecting environmental changes,
detecting motion, establishing human presence, counting people, locating targets,
and identifying objects. Success at the first task does not establish the others.

RSSI is one signal-strength value for a wireless link. CSI describes the channel
across subcarriers with amplitude and phase. More independent measurements make
motion research possible, but neither representation by itself supplies a human
label. Espressif describes this distinction and provides CSI acquisition and
sensing components. [Espressif technical introduction](https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/solution-introduction/esp-csi/esp-csi-solution.html)

## Findings on this computer and the previous implementation

Local inspection found Windows, an Intel Dual Band Wireless-AC 8265, and an active
2.4 GHz Wi-Fi connection. A direct Native Wi-Fi read succeeded with an RSSI around
-38 dBm. That proves access to link telemetry, not CSI or human sensing.

The previous live loop launched netsh, ping, access-point scans, and ARP inspection
while processing asynchronous requests. It also reused old readings after failures,
automatically switched to synthetic measurements, and inferred human activity,
heartbeats, range, and multiple people from ordinary ping timing. The revised
server does not use that inference path. Those historical research modules remain
in the repository for reference.

Windows documents an RSSI query opcode. It also documents connection-quality
queries, which are useful for network telemetry. Polling a cached driver value
ten times a second does **not** mean the radio generated ten independent RF
measurements. WiWave therefore labels this quantity **read rate**. Windows may
require location permission for queries containing network identity.
[Native Wi-Fi query opcodes](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/ne-wlanapi-wlan_intf_opcode)

Normal ICMP latency includes processing, queuing, medium access, and transport
delays. It is not a measurement of the round trip from a transmitter to a person's
body. Consequently, this implementation does not convert ping milliseconds to
person distance or extract vital signs from ping spectra. This is an engineering
conclusion about the measurement model, not a performance claim about a classifier.

## Hardware paths

| Path | Available measurements | Practical use | Boundary |
| --- | --- | --- | --- |
| Current Windows laptop | Driver RSSI and connection metadata | Live link-change monitoring | Human presence, range, and count unavailable |
| ESP32-family CSI receiver + compatible router | Per-packet complex channel samples | Room-specific motion experiments | Requires firmware, calibration, placement, and validation |
| Two ESP32-family devices | A deliberately placed transmitter/receiver link | Better control over sensing geometry | Still not a general object scanner |
| Supported Linux NIC + CSI tools | Multi-subcarrier / multi-antenna channel captures | Advanced research and model training | Requires supported NIC, OS, drivers, and datasets |
| Dedicated RF imaging / radar system | Measurements designed for spatial inference | Position or pose research | Substantially different hardware and inference work |

Espressif documents a receiver-plus-router arrangement and a two-device
arrangement. The first depends on the existing router and its placement; the
second allows greater control of the link geometry. Its repository includes
acquisition examples and a sensing demo with on-site training. These make an
ESP32 CSI receiver a practical next experiment, rather than a promise of general
human recognition. [ESP-CSI project](https://github.com/espressif/esp-csi)

The Intel 5300 research tool explicitly says its firmware supports that card,
not arbitrary Intel adapters. It cannot simply be enabled on this machine's 8265.
[CSI Tool compatibility FAQ](https://dhalperi.github.io/linux-80211n-csitool/faq.html)

PicoScenes lists supported Intel AX200/AX210 families, QCA9300, IWL5300, and SDR
options, with corresponding installation requirements. Its documented hardware
list does not establish support for the installed 8265 under Windows. Buying a
random USB Wi-Fi adapter is therefore not a sufficient plan.
[PicoScenes installation requirements](https://github.com/wifisensing/PicoScenes-Manual/blob/master/source/installation.rst)

MIT's RF-Pose work demonstrates that detailed human pose inference from radio
measurements is possible with an engineered sensing and learning system. Its
method uses camera-derived supervision during training. It does not demonstrate
that netsh RSSI and ordinary internet ping alone can produce body positions.
[MIT RF-Pose project](https://rfvision.csail.mit.edu/)

IEEE 802.11bf addresses WLAN sensing measurements and associated protocol
mechanisms. A standard does not retrofit CSI access into an old driver or supply
a pretrained universal person/object classifier. That latter conclusion follows
from the distinction between collecting measurements and interpreting them.
[IEEE 802.11 timelines](https://www.ieee802.org/11/Reports/802.11_Timelines.htm),
[802.11bf research overview](https://ieeexplore.ieee.org/document/9941042/)

## What v5 implements

1. Direct Windows Native Wi-Fi queries in a worker thread, with reconnection
   attempts. No periodic broad network scans or internet pings are needed.
2. Twenty-second calibration using robust median / median absolute deviation.
   A two-second window and separate trigger/release thresholds suppress isolated
   spikes and rapid state switching. Sustained changes remain visible until the
   signal returns or the user deliberately recalibrates.
3. Baseline resets on a detected link change, channel change, frame-size change,
   or a measurement gap exceeding three seconds.
4. Optional ESP32 serial CSI parsing with firmware-provided CSV headers, signed
   byte validation, duplicate suppression, and invalid-first-word removal.
   Amplitudes are normalized per frame to reduce common receiver-gain effects.
   This also sacrifices sensitivity to purely common-mode changes; it is a
   tradeoff, not complete RF gain compensation.
5. Independent acquisition, publication, and recording tasks. WebSocket clients
   each have a one-message queue; slow clients cannot grow a backlog of old data.
6. Explicit source provenance and data age. A stale or failed source clears active
   detection. Polling and WebSocket responses share the same schema.
7. A responsive dashboard with live traces, calibration, state transitions,
   session recording, and CSV exports. The circular field is labelled as an
   illustration; it is not a position map.

The score is a scaled baseline-deviation statistic, **not** a probability of a
person being present. RSSI state `signal_change` means the link changed. CSI state
`motion_candidate` is an experimental movement indication. People, distance,
identity, classification, and vital-sign fields stay unavailable.

## Validation required before claiming human detection

First collect separately labelled sessions: empty quiet room, empty room with fan
or curtain movement, network traffic, one stationary person, one walking person,
multiple people, receiver movement, and link interruption. Record placement,
channel, firmware, and equipment with each session. Keep all radio hardware fixed
between calibration and trials.

Measure false alarms per empty-room hour, missed walking trials, event delay,
recovery after disconnection, and sampling irregularity. Repeat across rooms and
days. Do not randomly split adjacent frames between training and testing: use
held-out sessions, people, and rooms to assess generalization.

Only then consider a trained human-presence model and a capability flag that is
specific to its validated environment. Counting or localization requires a
separate model and suitable spatial measurements. No human-classification
accuracy or detection range has been established for this build.

## Validation boundaries for this delivery

Automated tests cover stable baselines, spikes, sustained changes, recovery,
calibration resets, malformed and duplicate CSI frames, slow sensor isolation,
HTTP/WebSocket payloads, recording, and export. A Native Wi-Fi query was verified
against the installed adapter. Synthetic tests verify software behavior; they do
not verify human-detection accuracy.

An ESP32 was not connected, so its firmware-to-dashboard path still needs a
physical receiver trial. Browser automation was unavailable in the session;
the production build and lint were checked, but visual browser QA was not run.

See [live setup and trial procedure](LIVE_SENSING_GUIDE.md) for the next steps.
