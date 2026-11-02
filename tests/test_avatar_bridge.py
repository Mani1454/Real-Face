import asyncio
import base64
from unittest.mock import AsyncMock

import pytest

from avatar_bridge import AvatarBridge


class Session:
    def __init__(self):
        self.session = {"id": "view", "url": "http://localhost:7860", "token": "viewer-only"}
        self.publisher_token = "must-stay-on-server"
        self.close = AsyncMock()
        self.interrupt = AsyncMock()
        self.wait_for_viewer = AsyncMock()
        self.send_audio = AsyncMock()
        self.end_turn = AsyncMock()

    async def __aenter__(self):
        return self


async def ready_bridge():
    messages, session = asyncio.Queue(), Session()
    bridge = AvatarBridge(messages, factory=lambda: session)
    await bridge.start()
    bridge.activate()
    return bridge, session, messages


@pytest.mark.asyncio
async def test_pcm_goes_to_renderer_once_with_its_actual_sample_rate():
    bridge, session, messages = await ready_bridge()
    pcm = b'\x00\x01' * 64
    assert await bridge.route({"type": "tts_chunk", "content": base64.b64encode(pcm).decode(), "sample_rate": 48000})
    assert await bridge.route({"type": "tts_end"})
    await asyncio.wait_for(bridge.queue.join(), 1)
    session.send_audio.assert_awaited_once_with(pcm, sample_rate=48000)
    session.end_turn.assert_awaited_once()
    emitted = []
    while not messages.empty():
        emitted.append(messages.get_nowait())
    assert any(event["type"] == "avatar_turn_end" for event in emitted)
    descriptor = next(event["content"] for event in emitted if event["type"] == "avatar_session")
    assert "publisher_token" not in descriptor
    assert "must-stay-on-server" not in str(descriptor)
    await bridge.close()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_audio_remains_available_until_viewer_is_ready():
    messages, session = asyncio.Queue(), Session()
    bridge = AvatarBridge(messages, factory=lambda: session)
    await bridge.start()
    assert not await bridge.route({"type": "tts_chunk", "content": "AAAA"})
    session.send_audio.assert_not_awaited()
    await bridge.close()


@pytest.mark.asyncio
async def test_interrupt_cancels_blocked_drain_discards_old_audio_and_accepts_new_turn():
    bridge, session, _ = await ready_bridge()
    blocked = asyncio.Event()
    session.end_turn.side_effect = blocked.wait
    await bridge.route({"type": "tts_end"})
    await asyncio.sleep(0)
    await bridge.route({"type": "tts_chunk", "content": "AAAA"})
    await asyncio.wait_for(bridge.interrupt(), 1)
    assert bridge.queue.empty()
    session.interrupt.assert_awaited_once()
    session.send_audio.assert_not_awaited()
    session.end_turn.side_effect = None
    await bridge.route({"type": "tts_chunk", "content": "AAE="})
    await asyncio.wait_for(bridge.queue.join(), 1)
    session.send_audio.assert_awaited_once_with(b'\x00\x01', sample_rate=24000)
    await bridge.close()


@pytest.mark.asyncio
async def test_renderer_failure_falls_back_without_replaying_already_accepted_pcm():
    bridge, session, messages = await ready_bridge()
    session.send_audio.side_effect = RuntimeError("renderer down")
    await bridge.route({"type": "tts_chunk", "content": "AAAA"})
    await asyncio.wait_for(bridge.worker, 1)
    assert not bridge.active
    assert not await bridge.route({"type": "tts_chunk", "content": "AAAA"})
    assert any(messages.get_nowait()["type"] == "avatar_error" for _ in range(messages.qsize()))
    session.close.assert_awaited_once()
    await bridge.close()


@pytest.mark.asyncio
async def test_close_cancels_in_progress_gpu_initialization():
    session = Session()
    started, never = asyncio.Event(), asyncio.Event()

    class SlowSession(Session):
        async def __aenter__(self):
            started.set()
            await never.wait()

    session = SlowSession()
    bridge = AvatarBridge(asyncio.Queue(), factory=lambda: session)
    bridge.request_start()
    await started.wait()
    await asyncio.wait_for(bridge.close(), 1)
    assert bridge.start_task.done()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_backpressure_is_bounded_and_returns_chunk_to_voice_only_path():
    bridge, session, _ = await ready_bridge()
    assert not await bridge.route({"type": "tts_chunk", "content": "A" * 2_000_001})
    assert not bridge.active
    assert bridge.buffered_bytes == 0
    await bridge.close()
