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

## Offline-status recovery fix

The local voice server was subsequently found listening on port 8000 while its HTTP health check timed out; the GPU service on port 7860 remained healthy. Code inspection identified synchronous speech-socket sends and transcription finalization in the asyncio event-loop path.

Audio sends and pipeline resets now run outside that event loop. Speech lifecycle locks no longer cover network sends or socket closure, and temporary connection failures retry rather than permanently shutting down recognition. Failed senders cannot close a newer replacement connection. Callback state resets no longer finalize the transcription socket after every tutor reply.

The browser checks server reachability at startup and every ten seconds. It shows `READY` before a session, `ONLINE` for an open conversation, and `OFFLINE` for an unreachable server. It also bounds connection attempts and recovers its status after the server returns without reserving a voice session merely to check availability.

Validation includes 16 backend tests (with blocked-send, close/reconnect, and health-responsiveness regressions), 5 browser tests, ten consecutive successful health checks during a real GPU face session, another successful real speech-input → Groq → Deepgram audio check, and a real 512×512 GPU avatar response with no browser errors.

## Audio/video stutter and interruption timing

The original uncompiled 512×512 path took approximately 1.7 seconds to produce a 0.96-second media block, causing gaps once queued media was exhausted. Compiling the same size reduced observed generation to approximately 1.28 seconds per block, still slower than playback.

The local renderer now uses a project-owned adapter around the pinned OpenSpline worker to select 384×384 spatial inference parameters, with PyTorch compilation enabled. Upstream installed source files are unchanged. The launcher warms one generated block before accepting sessions and keeps the compilation cache in `.avatar-runtime/torch-compile`.

An engine benchmark after first-use compilation measured:

- block duration: 0.96 seconds;
- steady median generation: 0.755 seconds;
- steady p95 generation: 0.764 seconds;
- generated throughput: 31.7 frames/second, above the 25 fps playback target;
- first-use compilation/inference: about 134 seconds, excluded from steady timing and performed before serving users.

The actual browser/provider path then produced 384×384 moving video with per-block inference times of 765, 727, and 719 ms. In that run, time from submitting text to the first speaking event was 5.803 seconds, including Groq, Deepgram, buffering, and rendering. Playback plus drain acknowledgement took 3.512 seconds for 2.880 seconds of generated speech. Cloud response time and transport are still material latency sources; engine throughput alone is not an end-to-end latency claim.

Interruption and turn completion were corrected independently of performance:

- the browser pauses/mutes immediately instead of waiting for the server;
- a single user stop no longer causes three renderer interruption round trips;
- stale speaking events stay muted after interruption until a new turn starts;
- the early player generation-end event no longer reopens input while audio is still buffered; the publisher's playback-drain acknowledgement completes the turn;
- repeated speaking events no longer send duplicate `tts_start` messages.

The live interruption check measured 0.2 ms to pause/mute and 23.2 ms to receive server-clear acknowledgement, with exactly one interruption request and zero duplicate avatar interruption requests. These are single local measurements, not a latency guarantee. The updated suite passed 17 backend tests and 7 Chrome browser tests.

## Page startup remaining busy

While investigating a page that remained loading, HTTP and normal browser `load` were fast, but waiting for `networkidle` timed out. Request tracing identified two startup worklet fetches whose response bodies were never consumed. Both remained pending after the page rendered. They were unnecessary: microphone recording already loads its processor with `audioWorklet.addModule`, and playback uses native Web Audio buffers.

Removed these preloads and added a browser regression that requires startup to reach network idle and a control to update the page. The running app then reached network idle in 571 ms with zero pending requests and no page errors. All 7 browser tests passed. A real provider/GPU conversation also passed with 384×384 changing video and a tutor reply; first speaking took 4.119 seconds in that run. A separate check using Chrome's synthetic microphone confirmed that Start conversation loads the microphone worklet on demand and changes to End conversation without page errors. Direct inspection of the user's existing in-app tab was unavailable because its browser automation service module was missing, so these observations were made in fresh Chrome sessions.

## Local quality and latency tuning

The user selected keeping the avatar renderer on the laptop. Added pinned SageAttention 1.0.6 through the renderer's existing integration and selected 448×448 output with 25 model frames (9 motion-context frames, 16 new frames). Each block now covers 0.64 seconds instead of 0.96 seconds. This increases output pixels by 36.1% and reduces the amount of audio needed before a block can be generated. The existing four denoising steps remain unchanged. Older environments without SageAttention keep the prior 384/33/SDPA profile; explicit environment overrides remain available.

The 120-block playback-paced benchmark reported 119 steady blocks, excluding startup: median 0.414 seconds, p95 0.458 seconds, maximum 0.493 seconds, all below the 0.64-second playback deadline. Generated throughput was 38.4 fps against 25 fps playback. Initial compilation took 162 seconds; a subsequent benchmark warmup took 46 seconds with caches. Startup warmup completes before the renderer becomes ready.

Thermal conditions materially affect comparisons. The laptop initially reported 89°C and software thermal throttling at low GPU clocks. A cooler rerun of the old 384 profile reached a 0.349-second median and about 68 generated fps. Consequently, the new profile is a resolution/initial-buffer tradeoff that retains realtime headroom, not proof that quantized attention makes every old workload faster. Cooling and other laptop workloads remain relevant.

WebRTC's initial video encoding target is now 1.5 Mbps instead of 500 kbps, with congestion feedback still able to reduce it. A 75-frame VP8 encode/decode comparison on a generated tutor recording measured additional-transcode PSNR of 38.65 vs 41.36 dB, with mean encoding times of 1.82 vs 2.11 ms/frame. The input recording was already compressed; this measures further codec distortion, not neural-avatar realism. `scripts/check_video_codec.py` repeats this comparison.

Groq Qwen3 requests now default to `reasoning_effort=none`, its documented instruct mode, while retaining validated tutor JSON and allowing configuration/call overrides. The parameter is not automatically sent to other model families. Three real instruct-mode requests returned valid conversational replies, correctly corrected “Yesterday I go to market and buy two apple.”, and left a grammatical sentence uncorrected. Warm direct requests measured 303–455 ms; a default-mode request measured 437 ms. One earlier full request waited about six seconds for LLM content, so provider/network variation also contributes to delays; that wait cannot be attributed solely to reasoning mode.

The full browser → staging voice app → real providers → local GPU → WebRTC check then produced 448×448 changing video at 25 fps, zero dropped frames, zero lost packets, an 8 ms mean video jitter-buffer delay, and no page errors. Time from submitting text to the first speaking event was 2.439 seconds in that run; this is not a latency guarantee or a measure from the user's last spoken syllable. A separate real interruption check paused/muted in 0.3 ms and received server-clear acknowledgement in 406 ms, with one interruption request and no duplicates. Live checks use a separate app on port 8002 so they do not reserve the user's port-8000 voice session.

Sources: [SageAttention installation and interfaces](https://github.com/thu-ml/SageAttention), [Groq Qwen 3.8 instruct/reasoning modes](https://console.groq.com/docs/model/qwen/qwen3.8-27b), and the pinned local OpenSpline/aiortc source. The GPU model remains the same Lite model; specific emotional-expression control and human-level realism were not added by these changes.

The final backend suite passed 21 tests, including model-specific request settings and override behavior; all 7 browser regressions passed. Python compilation, shell syntax, and diff whitespace checks also passed. The local voice app was restarted on port 8000 with the updated dialogue setting, and the warmed renderer remains on port 7860.
