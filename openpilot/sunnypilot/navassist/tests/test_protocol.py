import pytest

from openpilot.sunnypilot.navassist.protocol.carrot_v2 import CATALOG, CarrotV2Receiver


def requirements():
  return {
    "type": "requirements_query", "protocol_version": 2, "catalog_revision": 1,
    "streams": [{"kind": kind, "name": name, "schema_version": 1} for kind, name in CATALOG],
  }


def envelope(manifest, name, sequence, value):
  stream = next(s for s in manifest["streams"] if s["kind"] == "json" and s["name"] == name)
  return {
    "type": "item_update", "protocol_version": 2, "session_id": manifest["session_id"],
    "manifest_revision": 1, "schema_version": 1, "kind": "json", "name": name,
    "stream_handle": stream["stream_handle"], "sequence": sequence,
    "source_timestamp_ms": 1, "sent_at_ms": 2, "present": True, "value": value,
  }


def test_manifest_contains_all_catalog_items_but_only_control_json_enabled():
  receiver = CarrotV2Receiver()
  manifest = receiver.negotiate(requirements())
  assert len(manifest["streams"]) == 28
  assert all(not s["enabled"] for s in manifest["streams"] if s["kind"] != "json")


def test_duplicate_is_ignored_but_backward_sequence_fails_closed():
  receiver = CarrotV2Receiver()
  receiver.control_connected()
  manifest = receiver.negotiate(requirements())
  item = envelope(manifest, "vehicle", 2, {"lat": 1.0, "lon": 2.0})
  receiver.record_json(manifest["session_id"], "vehicle", item)
  receiver.record_json(manifest["session_id"], "vehicle", item)
  with pytest.raises(ValueError, match="backwards"):
    receiver.record_json(manifest["session_id"], "vehicle", envelope(manifest, "vehicle", 1, {}))
  assert receiver.snapshot().sequence_error


def test_disconnect_clears_records_and_control_validity():
  receiver = CarrotV2Receiver()
  receiver.control_connected()
  manifest = receiver.negotiate(requirements())
  receiver.record_json(manifest["session_id"], "vehicle", envelope(manifest, "vehicle", 1, {}))
  receiver.control_disconnected()
  assert not receiver.snapshot().connected
  assert not receiver.snapshot().record("vehicle").present


def test_protocol_error_remains_fail_closed_until_new_session():
  receiver = CarrotV2Receiver()
  receiver.control_connected()
  manifest = receiver.negotiate(requirements())
  receiver.fail("malformed stream")
  receiver.record_json(manifest["session_id"], "vehicle", envelope(manifest, "vehicle", 1, {}))
  assert receiver.snapshot().protocol_error == "malformed stream"
  receiver.negotiate(requirements())
  assert receiver.snapshot().protocol_error == ""


def test_duplicate_sequence_requires_identical_payload():
  receiver = CarrotV2Receiver()
  receiver.control_connected()
  manifest = receiver.negotiate(requirements())
  receiver.record_json(manifest["session_id"], "vehicle", envelope(manifest, "vehicle", 1, {"lat": 1.0, "lon": 2.0}))
  with pytest.raises(ValueError, match="duplicate"):
    receiver.record_json(manifest["session_id"], "vehicle", envelope(manifest, "vehicle", 1, {"lat": 3.0, "lon": 4.0}))


def test_rejects_invalid_coordinates_and_timestamps():
  receiver = CarrotV2Receiver()
  receiver.control_connected()
  manifest = receiver.negotiate(requirements())
  bad = envelope(manifest, "vehicle", 1, {"lat": 91.0, "lon": 2.0})
  with pytest.raises(ValueError, match="latitude"):
    receiver.record_json(manifest["session_id"], "vehicle", bad)
  bad = envelope(manifest, "vehicle", 2, {"lat": 1.0, "lon": 2.0})
  bad["source_timestamp_ms"] = -1
  with pytest.raises(ValueError, match="timestamp"):
    receiver.record_json(manifest["session_id"], "vehicle", bad)
