import pytest

from openpilot.sunnypilot.navassist.geofence import TrackGeofence
from openpilot.sunnypilot.navassist.protocol import NavAssistProtocolError


def geofence():
  return TrackGeofence.parse({
    "coordinateSystem": "wgs84",
    "polygon": [[31.0, 121.0], [31.0, 121.01], [31.01, 121.01], [31.01, 121.0]],
  })


def test_wgs84_polygon_contains_only_track_interior():
  track = geofence()
  assert track.contains(31.005, 121.005)
  assert not track.contains(31.02, 121.005)
  assert not track.contains(float("nan"), 121.005)


def test_wgs84_polygon_requires_boundary_margin():
  track = geofence()
  assert track.contains_with_margin(31.005, 121.005, 100.0)
  assert not track.contains_with_margin(31.00005, 121.005, 20.0)
  assert track.boundary_distance_m(31.005, 121.005) > 400.0


@pytest.mark.parametrize("value", [
  None,
  {"coordinateSystem": "gcj02", "polygon": [[0, 0], [0, 1], [1, 1]]},
  {"coordinateSystem": "wgs84", "polygon": [[0, 0], [0, 1]]},
  {"coordinateSystem": "wgs84", "polygon": [[0, 0], [0, 1], [100, 1]]},
])
def test_invalid_geofence_is_rejected(value):
  with pytest.raises(NavAssistProtocolError):
    TrackGeofence.parse(value)
