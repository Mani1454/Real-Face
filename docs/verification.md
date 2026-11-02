# Verification record

Checked November 2, 2026, without live speech-provider or paid avatar credentials.

## Results

| Boundary | Result | Evidence |
| --- | --- | --- |
| App startup without secrets | Passed | FastAPI starts and `/api/config` reports `voice_ready: false` with the missing variable names |
| Server and avatar lifecycle tests | Passed | `12 passed` with pytest; covers real SwaySpeak workers behind fake provider calls, exact PCM routing/sample rate, grammar payloads, duplicate-audio suppression, cancellation, queue bounds, unavailable renderer, and second-session rejection |
| Browser interface/lifecycle | Passed | `3 passed` using installed Google Chrome; desktop/mobile layout, assets, no page errors, preview controls, failure/retry, readiness, interrupt, disconnect |
| Real OpenSpline SDK and browser transport | Passed with static test backend | Real service, real Python client, real vendored browser player, decoded `512 × 512` video, PCM drain and interruption; browser reported video `currentTime: 1.335407` |
| Dependency consistency | Checked with `pip check` | Main voice/client environment |
| Python/JavaScript/shell syntax | Passed | Python compileall, Node JavaScript syntax checks, bash syntax checks |
| Real Deepgram/Groq conversation | Passed in subsequent live check | See live provider check below; initial build was tested without credentials |
| Neural portrait inference with real tutor speech | Passed in subsequent local GPU check | Fully downloaded and checksummed model weights; actual `backend: gpu` service produced moving 512×512 video with a real tutor reply |

The browser tests replace the player module in lifecycle-specific cases. The separate transport check uses the actual player and actual SDK against OpenSpline's explicitly static test backend. Neither should be described as a photorealistic inference benchmark.

## Local environment

- NVIDIA GeForce RTX 4090 Laptop GPU, 16,376 MiB total VRAM.
- Python 3.12.3; CPU voice/client environment in `.venv`.
- Separate renderer environment in `.avatar-venv`; FFmpeg available.
- Reviewed renderer source `1e5f2b06e6c3dfc68e59ab9bfb3b30997d51caf9`.
- `openspline==0.1.2`, `openspline-server==0.1.2`, PyTorch `2.7.1+cu126` installed.
- No API keys, environments, runtime sessions, or model files are included in Git.

## Repeat automated checks

```bash
.venv/bin/python -m pytest -q
PLAYWRIGHT_CHANNEL=chrome npm run test:browser
```

Omit `PLAYWRIGHT_CHANNEL=chrome` after installing Playwright's Chromium with `npx playwright install chromium`. That browser download failed in this environment; the installed Chrome channel was used successfully instead.

## Repeat real transport check

Start the app on port 8000. In another terminal, start an explicit static test renderer:

```bash
OPENSPLINE_PUBLIC_URL=http://localhost:7861 \
OPENSPLINE_RUNTIME_DIR=.avatar-runtime/test \
.avatar-venv/bin/openspline serve --backend test --dev --host 127.0.0.1 --port 7861
```

Then:

```bash
PLAYWRIGHT_CHANNEL=chrome .venv/bin/python scripts/check_renderer_transport.py
```

This sends a short generated tone through the actual audio/video transport and closes its session. It does not call a speech service or evaluate lip-sync or emotional expression.

## Complete real model setup

```bash
.avatar-venv/bin/openspline models --directory models --quality low
bash scripts/start_avatar.sh
```

The selected Low portrait model files total about 7.25 GiB, plus the audio encoder and installed dependencies. The first command can resume the interrupted download. After it finishes, connect the face through the app and evaluate actual speech-driven motion. With Deepgram/Groq credentials configured, test microphone input, tutor replies, lip synchronization, interruption, and echo behavior together.

## Subsequent live provider check

On November 2, 2026, the supplied Groq and Deepgram credentials both returned HTTP 200 for their authentication checks. Values were stored only in the ignored local `.env` file with permission mode `0600`.

The old example Llama model was unavailable to this account. The live Groq model list confirmed `qwen/qwen3.8-27b`, which was selected for local configuration and the Render Blueprint.

- Text sent through the actual FastAPI `/ws` endpoint produced a real Groq reply and 180,480 bytes of Deepgram 24 kHz PCM audio.
- An offline-synthesized test utterance was streamed as 16 kHz PCM through the same microphone WebSocket protocol. Deepgram recognized `Hello. I went to the park today.`, Groq replied `Hi there! What did you do at the park?`, and Deepgram produced 168,960 bytes of 24 kHz reply audio.
- This exercises real STT → tutor generation → TTS and transport. It does not verify a person's microphone hardware, acoustic echo behavior, or neural face rendering.
- The 12 backend tests and 3 Chrome browser tests passed again with test environments isolated from live credentials.

Cloud deployment is prepared but not yet performed. Hosted photorealistic animation requires an OpenSpline Cloud key or a browser-reachable GPU renderer.

## Subsequent local GPU face check

The interrupted download was resumed using standard HTTP transfer with Xet disabled. All required weights finished downloading, with pinned revisions recorded in `models/manifest.json`. SHA-256 checks passed for the main portrait model, video decoder, and both downloaded audio encoder formats.

The renderer started on `http://localhost:7860` with `backend: gpu`, quality `low`, and one RTX 4090 Laptop GPU worker. It used approximately 7 GB VRAM after loading and about 8.8 GB during the observed session.

`node scripts/check_live_face.cjs` connected the actual app and actual GPU renderer in Chrome, sent a real tutor request through Groq and Deepgram, and observed:

- 512×512 decoded avatar video;
- 19 sampled frames during speaking;
- maximum mean RGB frame difference of `4.402587890625` on a 64×64 downsample, confirming that the output changed during speech;
- the tutor reply `Hi there! What did you do at the park?`;
- no browser page errors;
- clean session release after disconnect, leaving the GPU worker ready and unoccupied.

A WebM recording with the renderer's audio/video and screenshots were saved locally under `test-results/`. This confirms real neural animation and the integrated speech path; it is not a perceptual lip-sync benchmark or a guarantee of specific emotional expressions. Model weights and test media remain outside Git.

For subsequent local startup, use `bash scripts/start_local.sh`. No OpenSpline Cloud key is needed for this local GPU configuration.
