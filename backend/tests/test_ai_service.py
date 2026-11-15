import pytest
import requests

from config import Config
from services.ai_service import AIService, AIServiceError


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def make(**env):
    return AIService(Config(env=env))


GOOD = {"AI_PROVIDER": "xai", "AI_MODEL": "some-model", "XAI_API_KEY": "secret-key"}


def ok_payload(text="hello"):
    return {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 5}}


def test_not_configured_reports_what_is_missing():
    svc = make()
    assert not svc.is_configured()
    with pytest.raises(AIServiceError) as exc:
        svc.complete([{"role": "user", "content": "x"}])
    assert exc.value.code == "ai_not_configured" and exc.value.http_status == 503
    assert "AI_PROVIDER" in exc.value.message
    assert make(AI_PROVIDER="openai", OPENAI_API_KEY="k").status()["missing"] == ["AI_MODEL"]


def test_success_and_request_shape(monkeypatch):
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return FakeResponse(200, ok_payload("answer"))

    monkeypatch.setattr("services.ai_service.requests.post", fake_post)
    res = make(**GOOD).generate("do task", "CTX", question="why?")
    assert res["text"] == "answer" and res["provider"] == "xai" and res["model"] == "some-model"
    assert seen["url"] == "https://api.x.ai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer secret-key"
    system, user = seen["json"]["messages"]
    assert "only facts you may use" in system["content"].lower()
    assert "CTX" in user["content"] and "why?" in user["content"]
    assert "temperature" not in seen["json"]  # not forced when unset


def test_provider_switch_uses_provider_settings(monkeypatch):
    urls = []
    monkeypatch.setattr("services.ai_service.requests.post",
                        lambda url, **kw: urls.append(url) or FakeResponse(200, ok_payload()))
    make(AI_PROVIDER="openai", AI_MODEL="m", OPENAI_API_KEY="k", AI_MAX_TOKENS="100").complete([])
    make(AI_PROVIDER="custom", AI_MODEL="m", AI_API_KEY="k", AI_BASE_URL="http://localhost:9999/v1/").complete([])
    assert urls == ["https://api.openai.com/v1/chat/completions", "http://localhost:9999/v1/chat/completions"]


@pytest.mark.parametrize("status,code,http", [(401, "ai_auth_failed", 502), (403, "ai_auth_failed", 502),
                                               (429, "ai_rate_limited", 429), (500, "ai_provider_error", 502),
                                               (400, "ai_bad_request", 502)])
def test_http_errors_are_mapped_and_do_not_leak_the_key(monkeypatch, status, code, http):
    monkeypatch.setattr("services.ai_service.requests.post",
                        lambda *a, **k: FakeResponse(status, {"error": {"message": "nope"}}))
    with pytest.raises(AIServiceError) as exc:
        make(**GOOD).complete([])
    assert exc.value.code == code and exc.value.http_status == http
    assert "secret-key" not in exc.value.message


@pytest.mark.parametrize("raised,code", [(requests.Timeout(), "ai_timeout"), (requests.ConnectionError(), "ai_unreachable")])
def test_network_errors(monkeypatch, raised, code):
    def boom(*a, **k):
        raise raised
    monkeypatch.setattr("services.ai_service.requests.post", boom)
    with pytest.raises(AIServiceError) as exc:
        make(**GOOD).complete([])
    assert exc.value.code == code


def test_malformed_and_empty_responses(monkeypatch):
    monkeypatch.setattr("services.ai_service.requests.post", lambda *a, **k: FakeResponse(200, {"unexpected": 1}))
    with pytest.raises(AIServiceError) as exc:
        make(**GOOD).complete([])
    assert exc.value.code == "ai_bad_response"
    monkeypatch.setattr("services.ai_service.requests.post", lambda *a, **k: FakeResponse(200, ok_payload("  ")))
    with pytest.raises(AIServiceError) as exc:
        make(**GOOD).complete([])
    assert exc.value.code == "ai_empty_response"
