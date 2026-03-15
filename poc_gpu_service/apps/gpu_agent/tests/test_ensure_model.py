from apps.gpu_agent.services.model_service import ensure_model


def test_ensure_model():
    result = ensure_model('llama3-8b-instruct')
    assert result['ok'] is True
