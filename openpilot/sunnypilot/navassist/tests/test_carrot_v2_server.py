import json
import time

import websocket

from openpilot.sunnypilot.navassist.protocol.carrot_v2 import CATALOG, CarrotV2Receiver, CarrotV2Server


def requirements():
  return {
    "type": "requirements_query",
    "protocol_version": 2,
    "app_version": "device-integration-test",
    "catalog_revision": 1,
    "streams": [{"kind": kind, "name": name, "schema_version": 1} for kind, name in CATALOG],
  }


def test_standard_library_server_accepts_navipilot_control_and_stream():
  receiver = CarrotV2Receiver()
  server = CarrotV2Server(receiver, port=0, bind_host="127.0.0.1")
  server.start()
  control = websocket.create_connection(
    f"ws://127.0.0.1:{server.bound_port}/api/navi/ws/v2/control/2", timeout=2,
  )
  stream = None
  try:
    control.send(json.dumps(requirements()))
    manifest = json.loads(control.recv())
    session_id = manifest["session_id"]
    vehicle = next(item for item in manifest["streams"] if item["kind"] == "json" and item["name"] == "vehicle")
    stream = websocket.create_connection(
      f"ws://127.0.0.1:{server.bound_port}/api/navi/ws/v2/json/{session_id}/vehicle", timeout=2,
    )
    stream.send(json.dumps({
      "type": "item_update", "protocol_version": 2, "session_id": session_id,
      "kind": "json", "name": "vehicle", "manifest_revision": 1,
      "stream_handle": vehicle["stream_handle"], "schema_version": 1, "sequence": 1,
      "source_timestamp_ms": 1, "sent_at_ms": 2, "present": True,
      "value": {"lat": 31.2, "lon": 121.4, "heading_deg": 90.0, "speed_kph": 20.0},
    }))
    for _ in range(20):
      snapshot = receiver.snapshot()
      if snapshot.record("vehicle").present:
        break
      time.sleep(0.01)
    assert snapshot.connected
    assert snapshot.client_version == "device-integration-test"
    assert snapshot.record("vehicle").value["speed_kph"] == 20.0
  finally:
    if stream is not None:
      stream.close()
    control.close()
    server.close()
