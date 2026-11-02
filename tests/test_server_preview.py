from fastapi.testclient import TestClient
import server


def test_preview_loads_without_credentials_and_explains_unavailable_voice(monkeypatch):
    monkeypatch.delenv('DEEPGRAM_API_KEY', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with TestClient(server.app) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert 'avatarVideo' in response.text
        assert client.get('/static/tutor-portrait.png').status_code == 200
        assert client.get('/static/vendor/openspline/index.js').status_code == 200
        config = client.get('/api/config').json()
        assert config['voice_ready'] is False
        assert 'DEEPGRAM_API_KEY' in config['missing_credentials']
        with client.websocket_connect('/ws') as socket:
            socket.send_json({'type': 'user_text', 'text': 'hello'})
            assert socket.receive_json()['type'] == 'voice_unavailable'


def test_renderer_unavailable_reports_actionable_error_without_killing_websocket(monkeypatch):
    monkeypatch.delenv('DEEPGRAM_API_KEY', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.setenv('AVATAR_ENABLED', 'false')
    with TestClient(server.app) as client:
        with client.websocket_connect('/ws') as socket:
            socket.send_json({'type': 'avatar_start'})
            assert socket.receive_json()['type'] == 'avatar_status'
            assert socket.receive_json()['type'] == 'avatar_error'
            socket.send_json({'type': 'user_text', 'text': 'still connected'})
            assert socket.receive_json()['type'] == 'voice_unavailable'


def test_untrusted_json_types_are_ignored():
    for raw in ['[]', 'null', '"string"', '42', '{']:
        assert server.parse_json_message(raw) == {}
