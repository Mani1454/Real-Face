"""Keep the low-latency setting within the models that support instruct mode."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from llm_module import LLM


@pytest.mark.parametrize('model,configured,explicit,expected', [
    ('qwen/qwen3.8-27b', None, None, 'none'),
    ('qwen/qwen3.8-27b', 'default', None, 'default'),
    ('qwen/qwen3.8-27b', 'none', 'high', 'high'),
    ('openai/gpt-oss-120b', 'none', None, None),
])
def test_groq_dialogue_mode_respects_model_support_and_overrides(monkeypatch, model, configured, explicit, expected):
    monkeypatch.delenv('GROQ_REASONING_EFFORT', raising=False)
    if configured is not None:
        monkeypatch.setenv('GROQ_REASONING_EFFORT', configured)
    reply = '{"conversational_reply":"Hello!"}'
    stream = Mock()
    stream.__iter__ = Mock(return_value=iter([
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=reply))]),
    ]))
    create = Mock(return_value=stream)
    llm = LLM(backend='groq', model=model, system_prompt='Return JSON.')
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, '_lazy_initialize_clients', lambda: True)
    kwargs = {'reasoning_effort': explicit} if explicit is not None else {}
    assert ''.join(llm.generate('Hello', **kwargs)) == reply
    sent = create.call_args.kwargs
    assert sent['model'] == model
    assert sent['response_format'] == {'type': 'json_object'}
    if expected is None:
        assert 'reasoning_effort' not in sent
    else:
        assert sent['reasoning_effort'] == expected
