"""Real FastAPI + SwaySpeak workers; only external provider calls are replaced."""
import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import server
import speech_pipeline_manager as pipeline
from avatar_bridge import AvatarBridge
from transcribe import DeepgramTranscriptionProcessor

PCM = b'\x00\x01' * 200
REPLY = 'What did you enjoy about your trip?'
COACH = {
    'correction_needed': True,
    'original_sentence': 'I goes there yesterday.',
    'corrected_sentence': 'I went there yesterday.',
    'explanation': 'Use went for the past tense.',
    'conversational_reply': REPLY,
}


@pytest.fixture
def voice_client(monkeypatch):
    spoken = []

    class Audio:
        tts_inference_time = 0
        on_first_audio_chunk_synthesize = None

        def __init__(self, **kwargs):
            pass

        def synthesize(self, text, audio_chunks, stop_event, **kwargs):
            spoken.append(text)
            self.on_first_audio_chunk_synthesize()
            audio_chunks.put_nowait(PCM)
            return True

        def stop_playback(self):
            pass

    class LLM:
        def __init__(self, **kwargs):
            pass

        def generate(self, *args, **kwargs):
            raw = json.dumps(COACH)
            yield raw[:40]
            yield raw[40:]

        def cancel_generation(self):
            pass

    class Input:
        def __init__(self, *args):
            self.transcriber = SimpleNamespace()
            self.interrupted = False

        def abort_generation(self):
            pass

        async def process_chunk_queue(self, chunks):
            await asyncio.Event().wait()

        def shutdown(self):
            pass

    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test-only-not-a-key')
    monkeypatch.setenv('GROQ_API_KEY', 'test-only-not-a-key')
    monkeypatch.setenv('DEEPGRAM_TTS_SAMPLE_RATE', '48000')
    monkeypatch.setattr(pipeline, 'AudioProcessor', Audio)
    monkeypatch.setattr(pipeline, 'LLM', LLM)
    monkeypatch.setattr(server, 'AudioInputProcessor', Input)
    with TestClient(server.app) as client:
        yield client, spoken


def test_real_coaching_pipeline_delivers_native_pcm_and_grammar_without_network(voice_client):
    client, spoken = voice_client
    with client.websocket_connect('/ws') as socket:
        socket.send_json({'type': 'user_text', 'text': COACH['original_sentence']})
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event['type'] == 'tts_end':
                break
        chunks = [event for event in events if event['type'] == 'tts_chunk']
        assert len(chunks) == 1
        assert base64.b64decode(chunks[0]['content']) == PCM
        assert chunks[0]['sample_rate'] == 48000
        assert next(event['content'] for event in events if event['type'] == 'final_assistant_answer') == COACH
        assert spoken == [REPLY]


def test_fresh_session_and_explicit_clear_allow_face_start_without_speech_finalize(voice_client, monkeypatch):
    client, _ = voice_client
    transcriber = DeepgramTranscriptionProcessor()
    finalize = Mock()
    transcriber._socket = SimpleNamespace(send_finalize=finalize)
    transcriber._accumulated_parts = ['previous session']
    monkeypatch.setattr(server.app.state.AudioInputProcessor, 'abort_generation', transcriber.abort_generation)

    class Session:
        session = {'id':'view', 'url':'http://localhost:7860', 'token':'viewer-only'}

        async def __aenter__(self):
            return self

        async def interrupt(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(server, 'AvatarBridge', lambda messages: AvatarBridge(messages, factory=Session))
    with client.websocket_connect('/ws') as socket:
        socket.send_json({'type':'avatar_start'})
        assert socket.receive_json()['type'] == 'avatar_status'
        assert socket.receive_json()['type'] == 'avatar_session'
        assert transcriber._accumulated_parts == []
        transcriber._accumulated_parts = ['discard this utterance']
        socket.send_json({'type':'clear_history'})
        socket.send_json({'type':'user_text','text':COACH['original_sentence']})
        while socket.receive_json()['type'] != 'tts_end':
            pass
        assert transcriber._accumulated_parts == []
        finalize.assert_not_called()


def test_same_coaching_audio_reaches_avatar_without_duplicate_native_audio(voice_client, monkeypatch):
    client, spoken = voice_client

    class Session:
        session = {'id': 'viewer', 'url': 'http://localhost:7860', 'token': 'view-only'}
        send_audio = AsyncMock()
        wait_for_viewer = AsyncMock()
        end_turn = AsyncMock()
        interrupt = AsyncMock()
        close = AsyncMock()

        async def __aenter__(self):
            return self

    session = Session()
    monkeypatch.setattr(server, 'AvatarBridge', lambda messages: AvatarBridge(messages, factory=lambda: session))
    with client.websocket_connect('/ws') as socket:
        socket.send_json({'type': 'avatar_start'})
        assert socket.receive_json()['type'] == 'avatar_status'
        assert socket.receive_json()['type'] == 'avatar_session'
        socket.send_json({'type': 'avatar_ready'})
        socket.send_json({'type': 'user_text', 'text': COACH['original_sentence']})
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event['type'] == 'avatar_turn_end':
                break
        assert not any(event['type'] == 'tts_chunk' for event in events)
        session.send_audio.assert_awaited_once_with(PCM, sample_rate=48000)
        session.end_turn.assert_awaited_once()
        assert spoken == [REPLY]
        assert any(event['type'] == 'final_assistant_answer' for event in events)
        # Explicit interruption must preserve the dialogue context.
        socket.send_json({'type': 'interrupt'})
        while socket.receive_json()['type'] != 'stop_tts':
            pass
        assert any(entry['role'] == 'assistant' for entry in server.app.state.SpeechPipelineManager.history)
    session.close.assert_awaited_once()


def test_second_voice_connection_is_rejected_without_resetting_first(voice_client):
    client, _ = voice_client
    with client.websocket_connect('/ws'):
        manager = server.app.state.SpeechPipelineManager
        manager.history.append({'role': 'user', 'content': 'preserve me'})
        with client.websocket_connect('/ws') as second:
            assert second.receive_json()['type'] == 'session_busy'
        assert manager.history == [{'role': 'user', 'content': 'preserve me'}]
