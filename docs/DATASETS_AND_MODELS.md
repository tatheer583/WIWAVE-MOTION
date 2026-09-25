# CSI research, datasets and model integration

Research reviewed on 2026-09-25. Primary sources are linked below. No paid data,
private recordings, large training archives or model weights were downloaded.

| Source | What it provides | Appropriate WiWave use |
| --- | --- | --- |
| [Espressif esp-csi](https://github.com/espressif/esp-csi) | Official CSI capture examples and sensing development tools | Capture raw I/Q CSI on compatible hardware; verify firmware CSV schema against the serial parser |
| [MM-Fi dataset and loader](https://github.com/ybhbingo/MMFi_dataset) | Synchronized multimodal sensing and annotated poses; official download links | Offline CSI-to-pose research; preserve the published subject/environment splits |
| [Tsinghua Widar 3.0](https://tns.thss.tsinghua.edu.cn/widar3.0/) | Gesture CSI data, Doppler representations and domain annotations | Gesture recognition experiments; it is not a general object-detection dataset |
| [SenseFi / WiFi-CSI-Sensing-Benchmark](https://github.com/xyanchen/WiFi-CSI-Sensing-Benchmark) | Dataset loaders and CSI sensing baselines including NTU-Fi | Reproducible activity baselines with the matching preprocessing and split |
| [RuView pretrained model card](https://huggingface.co/ruvnet/wifi-densepose-pretrained) | Published sensing embeddings and model documentation | Evaluate with the matching RuView runtime; verify artifacts, tensor formats and license before use |
| [RuView MM-Fi benchmark study](https://github.com/ruvnet/RuView/blob/main/docs/benchmarks/mmfi-wifi-sensing-study.md) | Upstream evaluation and transfer limitations | Compare held-out results; do not equate a benchmark with this room's accuracy |

## Findings that affect this implementation

Windows Native WLAN provides link RSSI, not the antenna/subcarrier CSI tensor
these models consume. Interpolating ten RSSI reads per second into an array does
not create CSI. Polling rate also does not establish the adapter's independent
measurement refresh rate.

MM-Fi combines multiple sensor modalities and pose labels. Its official loader
expects a specific dataset layout and configuration. A pose model trained on that
CSI representation cannot be attached to a single RSSI channel or ESP32 stream
without examining shapes, antenna layout, frequencies, units and temporal windows.

Widar and SenseFi support activity/gesture experiments. Those task labels do not
establish that a system identifies arbitrary people or objects, locates them in
meters, or works through this room's walls.

The RuView model card itself lists room dependence and weak camera-free pose
performance. Published embedding or benchmark scores are not proof of this
computer's human-detection accuracy. WiWave therefore exposes a compatible output
connection without claiming that a model is installed, trained or validated.

## Practical integration sequence

1. Capture CSI with known firmware, receiver identity, packet timestamps, channel,
   antenna/subcarrier ordering and packet sequence. Verify packet loss and sample
   rate on the hardware. The current serial source supports Espressif CSV; RuView
   firmware's binary UDP needs its matching upstream runtime or a new adapter.
2. Collect an empty-room baseline and labelled room trials: empty, one stationary
   person, walking, fan motion, door changes and ordinary network traffic. Record
   failures as well as successes, with consent from participants.
3. Choose one measurable task first, such as motion versus quiet. Split trials by
   recording session and room/day so adjacent frames do not leak into the test set.
4. Match preprocessing to the published model. Run a held-out baseline before
   fine-tuning. Report confusion matrices, missed detections, false alarms per hour,
   latency, packet loss and calibration drift, rather than a single training score.
5. For pose, use synchronized ground-truth joints, document coordinate transforms,
   and evaluate MPJPE/PCK on unseen subjects and rooms. Confidence-zero output is
   rejected by the Observatory adapter.
6. Connect validated output through `sensing_update`. Keep source provenance,
   model version and evaluation conditions alongside results. Separately validate
   any multi-person, vital-sign or fall claim before enabling operational use.

Data usage terms are dataset-specific; inspect each official download's terms.
Hardware tests and model training cannot be substituted by the included demos.
