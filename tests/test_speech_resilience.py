"""Slow speech-service I/O must not freeze the app or prevent reconnects."""
import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import numpy as np
import pytest

from audio_in import AudioInputProcessor
from transcribe import DeepgramTranscriptionProcessor
import server


def test_history_abort_clears_local_transcription_without_flushing_the_network():
    processor = DeepgramTranscriptionProcessor()
    finalize = Mock(side_effect=AssertionError('A reset must not touch the speech socket'))
    processor._socket = SimpleNamespace(send_finalize=finalize)
    processor._accumulated_parts = ['old speech']
    processor.realtime_text = processor.final_transcription = 'old speech'
    processor._last_final_time = 123
    processor.abort_generation()
    finalize.assert_not_called()
    assert processor._accumulated_parts == []
    assert processor.realtime_text is None
    assert processor.final_transcription is None
    assert processor._last_final_time == 0
    processor.perform_final()
    finalize.assert_called_once()


@pytest.mark.asyncio
async def test_health_remains_responsive_while_microphone_send_is_blocked():
    release = threading.Event()
    entered = threading.Event()

    def blocked_send(*args):
        entered.set()
        release.wait(timeout=1)

    processor = AudioInputProcessor.__new__(AudioInputProcessor)
    processor._transcription_failed = False
    processor.transcription_task = None
    processor.interrupted = False
    processor.process_audio_chunk = lambda pcm: np.zeros(16, dtype=np.int16)
    processor.transcriber = SimpleNamespace(feed_audio=blocked_send)
    queue = asyncio.Queue()
    queue.put_nowait({'pcm': b'\0' * 32})
    started = time.monotonic()
    consumer = asyncio.create_task(processor.process_chunk_queue(queue))
    try:
        await asyncio.sleep(0.02)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
            response = await client.get('/healthz')
        assert entered.is_set()
        assert response.status_code == 200
        assert time.monotonic() - started < 0.5
    finally:
        release.set()
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


def test_speech_socket_can_close_while_an_audio_send_is_stalled():
    entered, release = threading.Event(), threading.Event()
    processor = DeepgramTranscriptionProcessor()

    def send_media(chunk):
        entered.set()
        release.wait(timeout=2)

    processor._socket = SimpleNamespace(send_media=send_media, _websocket=SimpleNamespace(close=release.set))
    sender = threading.Thread(target=processor.feed_audio, args=(b'\0\0',), daemon=True)
    closer = threading.Thread(target=processor._close_socket, daemon=True)
    sender.start()
    assert entered.wait(timeout=1)
    try:
        closer.start()
        closer.join(timeout=0.3)
        assert not closer.is_alive(), 'Closing a failed connection must not wait behind its blocked send.'
        assert processor._socket is None
    finally:
        release.set()
        sender.join(timeout=1)
        closer.join(timeout=1)


def test_transient_connection_failure_retries_instead_of_permanently_disabling_speech():
    processor = DeepgramTranscriptionProcessor()
    attempts = []

    def connect():
        attempts.append(True)
        if len(attempts) == 1:
            raise ConnectionError('temporary outage')
        processor._socket = iter(())
        processor._stop_event.set()

    processor._ensure_connection = connect
    processor._close_socket = lambda: None
    processor._stop_event.wait = lambda timeout=None: processor._stop_event.is_set()
    processor.transcribe_loop()
    assert len(attempts) == 2
    assert not processor.shutdown_performed


def test_failed_old_sender_does_not_close_a_replacement_connection():
    processor = DeepgramTranscriptionProcessor()
    replacement_closed = threading.Event()
    replacement = SimpleNamespace(_websocket=SimpleNamespace(close=replacement_closed.set))

    def fail_old_send(chunk):
        processor._socket = replacement
        raise ConnectionError('old socket failed after reconnect')

    processor._socket = SimpleNamespace(send_media=fail_old_send)
    processor.feed_audio(b'\0\0')
    assert processor._socket is replacement
    assert not replacement_closed.is_set()
