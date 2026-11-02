# Real Face

An English conversation tutor with a photorealistic, audio-driven face. Built from [Mani1454/swayspeak](https://github.com/Mani1454/swayspeak) at `ff583e2`, with [OpenSpline](https://github.com/openspline/openspline) as the avatar renderer.

The tutor listens through your microphone, generates its reply, and streams the synthesized voice to the renderer. The avatar player delivers synchronized video and audio, while SwaySpeak keeps the transcript and grammar tips. Press **Your turn** to interrupt without clearing the conversation.

![Real Face tutor portrait](code/static/tutor-portrait.png)

The included portrait is an AI-generated fictional character. **The still portrait is a preview, not a running avatar.** Live face animation needs a configured OpenSpline GPU service or Cloud account. Natural lip, head, and facial motion are model-generated; specific emotional expressions are not independently controllable in this integration.

## Start the app

Requires Python 3.10–3.12. The voice app runs on CPU; the local renderer runs separately on an NVIDIA GPU.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn server:app --app-dir code --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://localhost:8000). Without voice credentials, the interface and avatar connection are available in **preview mode**, and conversation controls are disabled. No fake AI replies are generated.

For live conversation, set `DEEPGRAM_API_KEY` and `GROQ_API_KEY` in the local `.env` file, then restart the app. Keys stay on the server. A hosted face service may charge for usage; the app never creates an account or adds credits automatically.

## Enable the live face

### Local NVIDIA GPU

FFmpeg and an NVIDIA driver compatible with CUDA 12.6 are required. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. The setup creates an isolated environment and downloads model weights; allow several GB of disk space and time for first startup. This configuration selects the single-GPU Low model.

```bash
bash scripts/setup_avatar.sh
bash scripts/start_avatar.sh
```

Keep this service running in another terminal. The app defaults to `OPENSPLINE_URL=http://localhost:7860`. In the app, choose **Connect live face**, allow sound/video playback if prompted, then **Start conversation**.

### OpenSpline Cloud

Instead of a local service, set `OPENSPLINE_API_KEY` in `.env` and **remove `OPENSPLINE_URL`** so the SDK selects Cloud. Set `AVATAR_ID` for a saved Cloud avatar, or leave it unset to use the included portrait. Never put the Cloud key into browser JavaScript.

For remote deployments, configure the renderer's `public_url` to an address the browser can reach, use HTTPS, and configure WebRTC/TURN as needed. `localhost` refers to the viewer's own machine. A CPU Render container can host the voice app but cannot run the GPU model.

## Behavior

- **Connect live face** starts a per-browser renderer session; the face connection can be tested without speech-provider keys.
- When the face is connected, OpenSpline owns audio playback. Native PCM and browser speech synthesis are suppressed for that reply, preventing double speech.
- Audio uses its configured sample rate instead of assuming 24 kHz.
- **Your turn** stops queued avatar/native playback and cancels speech generation while retaining conversation history.
- **Clear conversation** resets history and stops playback.
- **End conversation** releases the microphone, browser socket, avatar stream, and renderer session.
- If the renderer fails or falls behind, the UI reports it and future audio chunks use voice-only playback. Part of an in-progress reply can be lost during a renderer failure; already-submitted audio is not replayed automatically.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
npm ci
npx playwright install chromium
npm run test:browser
```

Tests use fake provider/renderer boundaries; they do not consume paid API credits. Browser checks cover preview state, face-connection failure/retry, responsive layout, and the avatar playback lifecycle. GPU inference and conversational quality require a separate real-service check. See [verification](docs/verification.md) for this checkout's actual results.

## Research and provenance

See the [repository comparison and decision](docs/avatar-research.md), [third-party notices](THIRD_PARTY_NOTICES.md), and [original SwaySpeak README](docs/SWAYSpeak-UPSTREAM.md).

This retains SwaySpeak's original single-conversation voice architecture: its voice pipeline is shared inside one server process. Run one active voice conversation per instance until it is migrated to isolated session pipelines or LiveKit Agents. Avatar sessions themselves are isolated per browser connection.

If the Playwright browser download is unavailable but Google Chrome is installed, use `PLAYWRIGHT_CHANNEL=chrome npm run test:browser`. The optional real-service transport check is documented in [verification](docs/verification.md).
