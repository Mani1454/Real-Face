# Third-party provenance

## SwaySpeak

The application and Git history were copied at the owner's request from [Mani1454/swayspeak](https://github.com/Mani1454/swayspeak), commit `ff583e2`. Original author: Manish Kumar. The upstream checkout did not contain a root license file; this project does not invent a license for that source. Its original README is retained under `docs/SWAYSpeak-UPSTREAM.md`.

## OpenSpline browser player

`code/static/vendor/openspline/index.js`, `socket.js`, and `playout.js` are copied without source changes from the compiled server browser assets in [openspline/openspline](https://github.com/openspline/openspline), commit `1e5f2b06e6c3dfc68e59ab9bfb3b30997d51caf9`. The MIT license is preserved beside those files as `LICENSE`. The Python client is installed as a dependency rather than copied.

The GPU service's vendored inference code retains its own Apache-2.0 license and third-party notices. Model weights have separate terms; review those when downloading or deploying the model. This repository does not redistribute model weights.

## SageAttention

The GPU setup installs [SageAttention](https://github.com/thu-ml/SageAttention), version 1.0.6, under its BSD-3-Clause license. It is a dependency rather than copied source. The local launcher uses the renderer's existing SageAttention integration; older environments without it retain the previous SDPA profile.

## Tutor portrait

`code/static/tutor-portrait.png` was generated for this project using the imagegen skill. It represents a fictional person and is not sourced from a real person's photo. The image is the reference input for live animation and the disconnected-state preview.
