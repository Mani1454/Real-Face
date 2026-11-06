# Deploy Speak with Sway on Render

The Python app uses a long-lived FastAPI WebSocket for microphone PCM, transcripts, and reply audio. [Render web services support inbound and outbound WebSockets](https://render.com/docs/websocket). The repository's `render.yaml` deploys the Docker app as a separate `speak-with-sway` service; it does not modify the original SwaySpeak service.

[Deploy this repository to Render](https://render.com/deploy?repo=https://github.com/Mani1454/speak-with-sway)

## Runtime configuration

Set these values as **server-side Render environment variables**, never as GitHub source:

| Variable | Required for | Value |
| --- | --- | --- |
| `DEEPGRAM_API_KEY` | Recognition and synthesized speech | Your Deepgram key |
| `GROQ_API_KEY` | Tutor replies | Your Groq key |
| `LLM_MODEL` | Tutor replies | Blueprint uses `qwen/qwen3.8-27b`; verified available to the supplied account |
| `OPENSPLINE_API_KEY` | Hosted live face with Cloud | Your OpenSpline Cloud key |
| `OPENSPLINE_URL` | Current Cloud endpoint with the pinned SDK | `https://app.openspline.dev/api` |
| `AVATAR_START_TIMEOUT` | Cloud initialization window | `180` seconds; browser uses this plus 15 seconds |
| `AVATAR_ID` | Optional saved Cloud avatar | Saved avatar ID; leave unset to use the included portrait |

For OpenSpline Cloud, use the explicit API address above: the pinned SDK's default dashboard address redirects. Alternatively, set `OPENSPLINE_URL` to your own GPU service's HTTPS URL and configure that service's browser-reachable public URL and WebRTC/TURN networking. A CPU Render web service cannot run the neural avatar model. The Groq and Deepgram keys do not authorize OpenSpline Cloud.

## Verify after deployment

1. Wait for Render's Docker build and `/healthz` health check to pass.
2. Open the actual service URL returned by Render. `/api/config` should report `voice_ready: true`.
3. Send a typed sentence and verify a reply plus audible speech.
4. Allow microphone access and test spoken input over `wss://…/ws`.
5. Connect the face once Cloud access or the GPU renderer is configured; verify actual facial animation and synchronized audio.

The service supports one active voice conversation per process. The browser receives no provider keys. Local `.env` files, virtual environments, GPU weights, and runtime data are excluded from both Git and the Docker build context. Hosting environment variables take precedence over local dotenv values.
