from types import SimpleNamespace as ns

from openpilot.sunnypilot.companion.telemetry import legacy_snapshot, multiplex_frame


def test_multiplex_frame_matches_android_wire_format():
  assert multiplex_frame("carState", b"capnp") == b"\x08carStatecapnp"


def test_legacy_snapshot_exposes_safe_vehicle_subset():
  messages = {
    "carState": ns(vEgo=12.5, vEgoCluster=13.0, steeringAngleDeg=-2.0,
                   leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=True,
                   gasPressed=False, brakePressed=True, cruiseState=ns(enabled=True, speed=20.0)),
    "controlsState": ns(enabled=True, active=True, vCruise=80.0),
    "selfdriveState": ns(enabled=True, active=True, engageable=True),
    "gpsLocationExternal": ns(latitude=31.2, longitude=121.4, speed=12.0, bearingDeg=90.0, accuracy=1.5),
  }
  alive = dict.fromkeys(messages, True)
  data = legacy_snapshot(messages, alive)
  assert data["carState"]["vEgo"] == 12.5
  assert data["carState"]["rightBlindspot"]
  assert data["systemState"] == {"enabled": True, "active": True, "engageAllowed": True, "vCruise": 80.0}
  assert data["gpsLocationExternal"]["longitude"] == 121.4


def test_legacy_snapshot_does_not_publish_stale_car_state():
  data = legacy_snapshot({"carState": ns(vEgo=30.0)}, {"carState": False})
  assert "carState" not in data
