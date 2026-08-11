import pytest

from openpilot.selfdrive.car.card import Car, TESLA_TOOL_REQUEST_TTL_MS


def test_tesla_tool_request_requires_json_object():
  assert Car._decode_tool_request('{"id":"abc"}') == {"id": "abc"}
  with pytest.raises(ValueError):
    Car._decode_tool_request('["abc"]')


def test_tesla_tool_request_ttl_rejects_future_and_expired(monkeypatch):
  now_ms = 10_000
  monkeypatch.setattr("openpilot.selfdrive.car.card.time.time", lambda: now_ms / 1000)
  assert Car._request_is_fresh({"created_ms": now_ms})
  assert Car._request_is_fresh({"created_ms": now_ms - TESLA_TOOL_REQUEST_TTL_MS})
  assert not Car._request_is_fresh({"created_ms": now_ms - TESLA_TOOL_REQUEST_TTL_MS - 1})
  assert not Car._request_is_fresh({"created_ms": now_ms + 1})
