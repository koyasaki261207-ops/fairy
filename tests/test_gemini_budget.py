"""
Kiểm thử ngắt mạch hạn ngạch & ngân sách Gemini bằng client giả (không gọi API thật).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stubs  # noqa: E402

_stubs.install()
pytest.importorskip("google.genai")

from config import config  # noqa: E402
from core import brain as brain_mod  # noqa: E402
from core.brain import GeminiBrain, quota_info  # noqa: E402

PER_MIN = ("429 RESOURCE_EXHAUSTED. {'error': {'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
           "'violations': [{'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}]}, "
           "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '7s'}]}}")
PER_DAY = ("429 RESOURCE_EXHAUSTED. {'error': {'details': [{'violations': [{'quotaId': "
           "'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}, {'retryDelay': '20s'}]}}")


class QuotaErr(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        self.code = 429


class FakeModels:
    def __init__(self, script):
        self.script = list(script)   # mỗi phần tử: Exception để ném, hoặc đối tượng phản hồi
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        item = self.script.pop(0) if self.script else "ok"
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


def make(script, keys=("k1",)):
    b = GeminiBrain(log_callback=lambda *a: None)
    config.gemini_api_keys = list(keys)
    b.client = FakeClient(script)
    b._client_key = keys[0]
    return b


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(brain_mod, "_sleep_interruptible", lambda s: slept.append(s) or True)
    monkeypatch.setattr(config, "gemini_model_fallback", True)
    return slept


def test_quota_info_parses_retry_and_daily():
    assert quota_info(PER_MIN) == (False, 7.0)
    assert quota_info(PER_DAY)[0] is True


def test_per_minute_429_waits_and_retries_same_model(_no_sleep):
    b = make([QuotaErr(PER_MIN), "resp"])
    model, resp, err = b._generate([], None, ["m1", "m2"])
    assert (model, resp) == ("m1", "resp")
    assert b.client.models.calls == ["m1", "m1"] and _no_sleep == [7.5]
    assert b.calls_used == 2   # mọi lần gửi request (kể cả thử lại) đều tính vào ngân sách


def test_daily_429_marks_model_exhausted_and_skips_it_later():
    b = make([QuotaErr(PER_DAY), "resp", "resp2"])
    model, resp, _ = b._generate([], None, ["m1", "m2"])
    assert model == "m2"
    b.client.models.calls.clear()
    model, _, _ = b._generate([], None, ["m1", "m2"])   # bước/nhiệm vụ con sau: không gõ lại m1
    assert model == "m2" and b.client.models.calls == ["m2"]


def test_no_fallback_stops_instead_of_draining_other_models(monkeypatch):
    monkeypatch.setattr(config, "gemini_model_fallback", False)
    b = make([QuotaErr(PER_DAY)])
    model, resp, err = b._generate([], None, ["m1", "m2", "m3"])
    assert resp is None and b.client.models.calls == ["m1"]


def test_bad_request_does_not_sweep_all_models():
    b = make([ValueError("400 INVALID_ARGUMENT: bad function response")])
    model, resp, err = b._generate([], None, ["m1", "m2", "m3"])
    assert resp is None and b.client.models.calls == ["m1"]


def test_shared_call_budget_stops_the_loop(monkeypatch):
    monkeypatch.setattr(config, "gemini_max_calls", 3)
    b = make([])
    b.calls_used = 3
    monkeypatch.setattr(b, "_init_client", lambda: "k1")
    monkeypatch.setattr(b, "_system_info", lambda: "")
    res = b.run_subtask("làm gì đó", max_steps=10)
    assert res["api_error"] and "GEMINI_MAX_CALLS" in res["error"]
    assert b.client.models.calls == []


def test_output_cap_is_sent_to_gemini():
    b = make([])
    assert b._build_config([]).max_output_tokens == config.gemini_max_output_tokens


def test_persistent_minute_limit_is_not_cached_as_daily():
    b = make([QuotaErr(PER_MIN)] * 3 + ["resp"])
    model, resp, _ = b._generate([], None, ["m1", "m2"])
    assert model == "m2" and not b._is_exhausted("m1")


def test_fallback_disabled_never_touches_other_models(monkeypatch):
    monkeypatch.setattr(config, "gemini_model_fallback", False)
    b = make([QuotaErr(PER_DAY), "resp"])
    b._generate([], None, ["m1", "m2"])
    _, resp, _ = b._generate([], None, ["m1", "m2"])   # nhiệm vụ sau: m1 đã cạn -> dừng, KHÔNG dùng m2
    assert resp is None and "m2" not in b.client.models.calls


def test_budget_counts_retries_and_rotations(monkeypatch):
    monkeypatch.setattr(config, "gemini_max_calls", 2)
    b = make([QuotaErr(PER_DAY)] * 5, keys=("k1", "k2", "k3"))
    monkeypatch.setattr(b, "rotate_key", lambda: True)
    _, resp, err = b._generate([], None, ["m1", "m2"])
    assert resp is None and len(b.client.models.calls) == 2 and "GEMINI_MAX_CALLS" in err
