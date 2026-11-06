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
async def test_avatar_start_timeout_releases_candidate_and_allows_retry(monkeypatch):
    monkeypatch.setenv('AVATAR_START_TIMEOUT', '0.01')

    class SlowSession(Session):
        async def __aenter__(self):
            await asyncio.Event().wait()

    candidate = SlowSession()
    messages = asyncio.Queue()
    bridge = AvatarBridge(messages, factory=lambda: candidate)
    await asyncio.wait_for(bridge.start(), 1)
    assert bridge.session is None
    candidate.close.assert_awaited_once()
    emitted = [messages.get_nowait()['type'] for _ in range(messages.qsize())]
    assert 'avatar_error' in emitted
    assert 'avatar_session' not in emitted
    replacement = Session()
    bridge.factory = lambda: replacement
    await bridge.start()
    assert bridge.session is replacement
    await bridge.close()


@pytest.mark.asyncio
async def test_backpressure_is_bounded_and_returns_chunk_to_voice_only_path():
    bridge, session, _ = await ready_bridge()
    assert not await bridge.route({"type": "tts_chunk", "content": "A" * 2_000_001})
    assert not bridge.active
    assert bridge.buffered_bytes == 0
    await bridge.close()


@pytest.mark.asyncio
async def test_playback_end_waits_for_drain_and_stop_message_does_not_interrupt_twice():
    bridge, session, messages = await ready_bridge()
    drain = asyncio.Event()
    session.end_turn.side_effect = drain.wait
    await bridge.route({'type': 'tts_chunk', 'content': 'AAAA'})
    await bridge.route({'type': 'tts_chunk', 'content': 'AAAA'})
    await bridge.route({'type': 'tts_end'})
    await asyncio.sleep(0)
    before=[]
    while not messages.empty():
        before.append(messages.get_nowait()['type'])
    assert before.count('avatar_turn_start') == 1
    assert 'avatar_turn_end' not in before
    drain.set()
    await asyncio.wait_for(bridge.queue.join(), 1)
    assert messages.get_nowait()['type'] == 'avatar_turn_end'
    await bridge.interrupt()
    assert not await bridge.route({'type': 'stop_tts'})
    session.interrupt.assert_awaited_once()
    await bridge.close()

@pytest.mark.asyncio
async def test_cloud_audio_window_preserves_pcm_order_and_drains_after_all_acks():
    bridge, session, _ = await ready_bridge()
    bridge.audio_window = 8
    release, filled = asyncio.Event(), asyncio.Event()
    received = []
    active = 0
    peak = 0

    async def send(pcm, sample_rate):
        nonlocal active, peak
        assert sample_rate == 24000
        assert len(pcm) <= 4800
        received.append(pcm)
        active += 1
        peak = max(peak, active)
        if active == 8:
            filled.set()
        try:
            await release.wait()
        finally:
            active -= 1

    session.send_audio.side_effect = send
    pcm = b''.join(bytes([i]) * 4800 for i in range(18))
    await bridge.route({'type':'tts_chunk','content':base64.b64encode(pcm).decode()})
    await bridge.route({'type':'tts_end'})
    await asyncio.wait_for(filled.wait(), 1)
    assert len(received) == 8
    session.end_turn.assert_not_awaited()
    release.set()
    await asyncio.wait_for(bridge.queue.join(), 1)
    assert b''.join(received) == pcm
    assert peak == 8
    session.end_turn.assert_awaited_once()
    await bridge.close()


@pytest.mark.asyncio
async def test_cloud_interrupt_joins_pending_packets_before_accepting_next_turn():
    bridge, session, _ = await ready_bridge()
    bridge.audio_window = 8
    release, filled = asyncio.Event(), asyncio.Event()
    active = set()
    received = []

    async def send(pcm, sample_rate):
        task = asyncio.current_task()
        active.add(task)
        received.append(pcm)
        if len(active) == 8:
            filled.set()
        try:
            await release.wait()
        finally:
            active.remove(task)

    session.send_audio.side_effect = send
    await bridge.route({'type':'tts_chunk','content':base64.b64encode(b'\x01\x00' * 48000).decode()})
    await bridge.route({'type':'tts_end'})
    await asyncio.wait_for(filled.wait(), 1)
    await asyncio.wait_for(bridge.interrupt(), 1)
    assert not active
    assert len(received) == 8
    session.end_turn.assert_not_awaited()
    release.set()
    await bridge.route({'type':'tts_chunk','content':base64.b64encode(b'new!').decode()})
    await bridge.route({'type':'tts_end'})
    await asyncio.wait_for(bridge.queue.join(), 1)
    assert received[8:] == [b'new!']
    session.end_turn.assert_awaited_once()
    await bridge.close()


@pytest.mark.asyncio
async def test_cloud_packet_failure_cancels_other_sends_and_releases_session():
    bridge, session, messages = await ready_bridge()
    bridge.audio_window = 8
    active = set()

    async def send(pcm, sample_rate):
        task = asyncio.current_task()
        active.add(task)
        try:
            if pcm[0] == 2:
                raise RuntimeError('connection lost')
            await asyncio.Event().wait()
        finally:
            active.remove(task)

    session.send_audio.side_effect = send
    pcm = b''.join(bytes([i]) * 4800 for i in range(8))
    await bridge.route({'type':'tts_chunk','content':base64.b64encode(pcm).decode()})
    await asyncio.wait_for(bridge.worker, 1)
    assert not active
    assert not bridge.active
    session.close.assert_awaited_once()
    assert any(messages.get_nowait()['type'] == 'avatar_error' for _ in range(messages.qsize()))
    await bridge.close()
