import base64
import json

import pytest

from actsprite import config
from actsprite.meta_client import (
    BudgetExceeded,
    CostLog,
    MetaClient,
    MissingApiKey,
    data_url,
    estimate_sam_video_cost,
    parse_json_reply,
    request_key,
    response_images,
    response_text,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 10


def test_request_key_is_order_independent():
    assert request_key({"a": 1, "b": [1, 2]}) == request_key({"b": [1, 2], "a": 1})
    assert request_key({"a": 1}) != request_key({"a": 2})


def test_data_url_sniffs_png():
    assert data_url(PNG).startswith("data:image/png;base64,")
    with pytest.raises(ValueError):
        data_url(b"nope")


def test_cost_log_total(tmp_path):
    log = CostLog(tmp_path / "cost.csv")
    assert log.total() == 0.0
    log.append("m", "op", 1, 0.01, False, 1.0)
    log.append("m", "op", 1, 0.0, True, 0.0)
    log.append("m", "op", 1, 0.25, False, 1.0)
    assert log.total() == pytest.approx(0.26)


def test_cost_log_parallel_appends(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    log = CostLog(tmp_path / "cost.csv")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: log.append("m", "op", 1, 0.01, False, 1.0, f"call {i}"), range(200)))
    assert log.total() == pytest.approx(2.0)
    assert len((tmp_path / "cost.csv").read_text(encoding="utf-8").splitlines()) == 201  # header + 200 rows


def test_sam_video_minimum_billing():
    assert estimate_sam_video_cost(10) == pytest.approx(50 * config.PRICE_SAM_VIDEO_FRAME)
    assert estimate_sam_video_cost(120) == pytest.approx(120 * config.PRICE_SAM_VIDEO_FRAME)


def test_response_helpers():
    img = base64.b64encode(PNG).decode()
    data = {
        "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": "<0f>"}, {"type": "output_text", "text": "x"}]},
            {"type": "image_generation_call", "result": img},
        ]
    }
    assert response_text(data) == "<0f>x"
    assert response_images(data) == [PNG]


def test_parse_json_reply_handles_fences():
    assert parse_json_reply('```json\n{"identity_score": 8}\n```') == {"identity_score": 8}
    with pytest.raises(ValueError):
        parse_json_reply("no json here")


def test_missing_key_message(monkeypatch, tmp_path):
    monkeypatch.delenv(config.API_KEY_ENV, raising=False)
    monkeypatch.setattr(config, "ROOT", tmp_path)  # no .env there
    with pytest.raises(MissingApiKey, match=".env"):
        MetaClient()


def test_budget_guard_and_cache(tmp_path):
    log = CostLog(tmp_path / "cost.csv")
    log.append("m", "op", 1, 139.995, False, 1.0)
    client = MetaClient(api_key="test", cache_dir=tmp_path / "cache", cost_log=log)
    with pytest.raises(BudgetExceeded):
        client.check_budget(0.01)

    # A cached request is served without touching the network or the budget.
    payload = {"model": "m", "input": "hi"}
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / f"{request_key(payload)}.json").write_text(json.dumps({"output": []}))
    result = client._call(payload, operation="t", estimate_usd=1.0, units=1, cost_fn=lambda d: 1.0)
    assert result.cached and result.cost_usd == 0.0


def test_offline_mode_answers_from_cache_only(tmp_path, monkeypatch):
    from actsprite.meta_client import CacheMiss

    monkeypatch.delenv("META_API_KEY", raising=False)
    log = CostLog(tmp_path / "cost.csv")
    client = MetaClient(cache_dir=tmp_path / "cache", cost_log=log, offline=True)  # no key needed
    payload = {"model": "m", "input": "cached"}
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / f"{request_key(payload)}.json").write_text(json.dumps({"ok": 1}), encoding="utf-8")
    call = dict(operation="op", estimate_usd=1.0, units=1, cost_fn=lambda d: 1.0)
    assert client._call(payload, **call).data == {"ok": 1}
    with pytest.raises(CacheMiss):
        client._call({"model": "m", "input": "not cached"}, **call)  # never reaches the network
    assert not log.path.exists()  # offline runs log nothing
    assert client.calls == {"cached": 1, "new": 0}


def test_content_filter_refusal_is_its_own_error(tmp_path):
    from actsprite.meta_client import ContentRefused

    class Refused(Exception):
        status_code = 400

    class Responses:
        def create(self, **payload):
            raise Refused("Error code: 400 - The response was filtered due to the prompt triggering our "
                          "content management policy.")

    client = MetaClient(api_key="test", cache_dir=tmp_path / "cache", cost_log=CostLog(tmp_path / "cost.csv"))
    client._client = type("C", (), {"responses": Responses()})()
    with pytest.raises(ContentRefused):
        client._call({"model": "m", "input": "x"}, operation="t", estimate_usd=0.0, units=1, cost_fn=lambda d: 0.0)
    assert not (tmp_path / "cache").exists() or not any((tmp_path / "cache").iterdir())  # nothing cached
