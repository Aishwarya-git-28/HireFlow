from types import SimpleNamespace

import config
from crew import pipelines
from models import SearchPlan


def _fake_world(monkeypatch, behaviour):
    """behaviour(model_spec, call_number) -> raises or returns; the fake Crew runs it."""
    pipelines._DEAD.clear()
    monkeypatch.setattr(config, "ROLE_MODELS", {"reason": "gemini:m1", "fallback": "gemini:m2"})
    monkeypatch.setattr(config, "role_available", lambda r: True)
    monkeypatch.setattr(config, "build_llm", lambda r: r)
    monkeypatch.setattr(pipelines, "build_agent", lambda key, llm, tools=None: llm)
    monkeypatch.setattr(pipelines, "build_task", lambda *a, **k: object())
    monkeypatch.setattr(pipelines.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class FakeCrew:
        def __init__(self, agents, **kw):
            self.role = agents[0]

        def kickoff(self, inputs):
            calls["n"] += 1
            return behaviour(config.ROLE_MODELS[self.role], calls["n"])

    monkeypatch.setattr(pipelines, "Crew", FakeCrew)


def test_retry_seconds_parses_provider_messages():
    assert pipelines._retry_seconds("Please try again in 7.66s.") == 7.66
    assert pipelines._retry_seconds("Please retry in 18.787508526s.") > 18
    assert pipelines._retry_seconds("try again in 1m3.5s") == 63.5
    assert pipelines._retry_seconds("no hint here") == 20.0


def test_daily_quota_retires_model_and_hops(monkeypatch):
    def behaviour(spec, n):
        if spec == "gemini:m1":
            raise RuntimeError("429 GenerateRequestsPerDayPerProjectPerModel-FreeTier limit: 20. retry in 18s")
        return SimpleNamespace(pydantic=SearchPlan(), raw="")

    _fake_world(monkeypatch, behaviour)
    out, model, err = pipelines.run_stage("x", "fact_auditor", SearchPlan, {}, llm_role="reason")
    assert out is not None and model == "gemini:m2" and err == ""
    assert "gemini:m1" in pipelines._DEAD


def test_per_minute_limit_waits_and_retries_same_model(monkeypatch):
    def behaviour(spec, n):
        if n == 1:
            raise RuntimeError("429 Rate limit reached on tokens per minute (TPM). Please try again in 2s.")
        return SimpleNamespace(pydantic=SearchPlan(), raw="")

    _fake_world(monkeypatch, behaviour)
    out, model, err = pipelines.run_stage("x", "fact_auditor", SearchPlan, {}, llm_role="reason")
    assert out is not None and model == "gemini:m1"
    assert not pipelines._DEAD