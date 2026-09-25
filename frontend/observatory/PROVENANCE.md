# Upstream source and license

Reference: https://github.com/ruvnet/RuView

Pinned revision: `dd02efe2fe129ae8068e9b805ea35aaa660e47dd`

License: MIT, copyright (c) 2024 rUv. The full notice is preserved in
`LICENSE.ruview` and distributed with the build at `/licenses/RuView.txt`.

Derived files: `frontend/index.html`, `css/observatory.css`, and these `js/` modules:
`main`, `hud-controller`, `figure-pool`, `pose-system`, `demo-data`,
`nebula-background`, `post-processing`, `scenario-props`.

WiWave changes: local Vite imports instead of CDN modules; WiWave identity and
preferences; explicit sensor/demo/external/replay modes; no automatic demo fallback;
unknown measurement states; generated skeletons restricted to synthetic frames;
source-reset cleanup; workspace controls, bounded replay and model-output validation.
`wiwave-data.js`, `wiwave-controls.js`, and `wiwave.css` implement the integration.

The adapted UI is not the entire RuView platform. Experimental visualizations,
training services, firmware and edge modules are not included. No affiliation or
endorsement by the upstream authors is implied.
