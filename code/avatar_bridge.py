"""Stream tutor PCM to OpenSpline; its player owns synchronized audio/video.

Each browser connection owns a bridge. The bounded worker keeps GPU/network
backpressure away from transcripts, microphone input, and interruption messages.
"""
import asyncio
import base64
import contextlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


class AvatarBridge:
    def __init__(self, messages, *, factory=None):
        self.messages = messages
        self.factory = factory
        self.session = None
        self.active = False
        self.start_task = None
        self.worker = None
        self.queue = asyncio.Queue(maxsize=128)
        self.buffered_bytes = 0
        self.closed = False
        self.turn_started = False

    def emit(self, kind, content=None):
        self.messages.put_nowait({"type": kind, "content": content})

    def request_start(self):
        if self.closed or self.session or (self.start_task and not self.start_task.done()):
            return
        self.start_task = asyncio.create_task(self.start())

    async def start(self):
        self.emit("avatar_status", "Preparing your tutor’s live face…")
        candidate = None
        try:
            if os.getenv("AVATAR_ENABLED", "true").lower() != "true":
                raise RuntimeError("Avatar rendering is disabled on this server.")
            if self.factory:
                candidate = self.factory()
            else:
                from openspline import Openspline

                client = Openspline(
                    quality=os.getenv("AVATAR_QUALITY", "low"),
                    timeout=float(os.getenv("AVATAR_TIMEOUT", "180")),
                    viewer_timeout=20,
                )
                avatar_id = os.getenv("AVATAR_ID")
                portrait = Path(os.getenv("AVATAR_PORTRAIT", "code/static/tutor-portrait.png"))
                if not portrait.is_absolute():
                    portrait = ROOT / portrait
                candidate = (client.avatar(avatar_id=avatar_id) if avatar_id
                             else client.avatar(str(portrait)))
            await candidate.__aenter__()
            self.session = candidate
            # Only the viewer descriptor is sent. Never expose publisher/API keys.
            self.emit("avatar_session", dict(candidate.session))
        except asyncio.CancelledError:
            if candidate:
                with contextlib.suppress(Exception):
                    await candidate.close()
            raise
        except Exception:
            logger.warning("Avatar renderer could not initialize", exc_info=True)
            if candidate:
                with contextlib.suppress(Exception):
                    await candidate.close()
            self.session = None
            self.emit("avatar_error", "Live face unavailable. Start the OpenSpline service or configure Cloud access. Voice-only conversation is still available when voice credentials are configured.")

    def activate(self):
        if self.session and not self.closed:
            self.active = True
            if not self.worker or self.worker.done():
                self.worker = asyncio.create_task(self._run())

    async def route(self, data):
        """Return True when avatar output replaces native browser PCM playback."""
        kind = data.get("type")
        if not self.active or kind not in {"tts_chunk", "tts_end"}:
            return False
        if kind == "tts_chunk" and not self.turn_started:
            self.turn_started = True
            self.emit("avatar_turn_start")
        size = len(data.get("content", "")) if kind == "tts_chunk" else 0
        if self.queue.full() or self.buffered_bytes + size > 2_000_000:
            await self.disable("The live face could not keep up. Continuing with voice only.")
            return False
        self.buffered_bytes += size
        self.queue.put_nowait((data, size))
        return True

    async def _run(self):
        try:
            while True:
                data, size = await self.queue.get()
                self.buffered_bytes -= size
                try:
                    if data["type"] == "tts_end":
                        # Drain completes after the viewer acknowledges playback.
                        await self.session.end_turn()
                        self.turn_started = False
                        self.emit("avatar_turn_end")
                    else:
                        await self.session.wait_for_viewer(timeout=20)
                        await self.session.send_audio(
                            base64.b64decode(data["content"], validate=True),
                            sample_rate=data.get("sample_rate", 24000),
                        )
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Avatar stream failed", exc_info=True)
            # Do not replay audio already accepted by the renderer. New chunks
            # resume native playback after the browser closes the video stream.
            await self.disable("Live face disconnected. Continuing with voice only.")

    def _clear_queue(self):
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        self.buffered_bytes = 0

    async def interrupt(self):
        self.turn_started = False
        if self.worker and self.worker is not asyncio.current_task():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        self.worker = None
        self._clear_queue()
        if self.session:
            try:
                await asyncio.wait_for(self.session.interrupt(), timeout=5)
                if self.active and not self.closed:
                    self.emit("avatar_interrupted")
            except Exception:
                self.active = False
                self.emit("avatar_error", "Live face disconnected. Reconnect it to continue with video.")
        if self.active and not self.closed:
            self.worker = asyncio.create_task(self._run())

    async def disable(self, reason=None):
        self.active = False
        if self.start_task and self.start_task is not asyncio.current_task():
            self.start_task.cancel()
            await asyncio.gather(self.start_task, return_exceptions=True)
        await self.interrupt()
        if self.session:
            with contextlib.suppress(Exception):
                await self.session.close()
            self.session = None
        if reason:
            self.emit("avatar_error", reason)

    async def close(self):
        self.closed = True
        await self.disable()
