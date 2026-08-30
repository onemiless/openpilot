from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from openpilot.sunnypilot.navassist.protocol import NavAssistProtocolError


@dataclass(frozen=True)
class TrackGeofence:
  polygon: tuple[tuple[float, float], ...]

  @classmethod
  def parse(cls, value: Any) -> TrackGeofence:
    if not isinstance(value, dict) or set(value) != {"coordinateSystem", "polygon"}:
      raise NavAssistProtocolError("malformed", "track geofence must contain coordinateSystem and polygon")
    if value["coordinateSystem"] != "wgs84":
      raise NavAssistProtocolError("malformed", "track geofence must use wgs84")
    raw_polygon = value["polygon"]
    if not isinstance(raw_polygon, list) or not 3 <= len(raw_polygon) <= 64:
      raise NavAssistProtocolError("malformed", "track geofence requires 3..64 points")
    polygon: list[tuple[float, float]] = []
    for raw_point in raw_polygon:
      if (not isinstance(raw_point, list) or len(raw_point) != 2
          or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in raw_point)):
        raise NavAssistProtocolError("malformed", "track geofence points must be [latitude, longitude]")
      latitude, longitude = map(float, raw_point)
      if not all(math.isfinite(item) for item in (latitude, longitude)) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise NavAssistProtocolError("malformed", "track geofence point is out of range")
      polygon.append((latitude, longitude))
    return cls(tuple(polygon))

  def contains(self, latitude: float, longitude: float) -> bool:
    if not math.isfinite(latitude) or not math.isfinite(longitude):
      return False
    inside = False
    previous_latitude, previous_longitude = self.polygon[-1]
    for current_latitude, current_longitude in self.polygon:
      crosses = ((current_latitude > latitude) != (previous_latitude > latitude))
      if crosses:
        boundary_longitude = ((previous_longitude - current_longitude) * (latitude - current_latitude)
                              / (previous_latitude - current_latitude) + current_longitude)
        if longitude < boundary_longitude:
          inside = not inside
      previous_latitude, previous_longitude = current_latitude, current_longitude
    return inside

  def boundary_distance_m(self, latitude: float, longitude: float) -> float:
    """Approximate shortest track-boundary distance in a local tangent plane."""
    if not math.isfinite(latitude) or not math.isfinite(longitude):
      return 0.0
    meters_per_degree_latitude = 111_320.0
    meters_per_degree_longitude = meters_per_degree_latitude * abs(math.cos(math.radians(latitude)))
    points = tuple(
      ((point_longitude - longitude) * meters_per_degree_longitude,
       (point_latitude - latitude) * meters_per_degree_latitude)
      for point_latitude, point_longitude in self.polygon
    )
    minimum_distance = math.inf
    previous_x, previous_y = points[-1]
    for current_x, current_y in points:
      segment_x, segment_y = current_x - previous_x, current_y - previous_y
      segment_length_sq = segment_x * segment_x + segment_y * segment_y
      if segment_length_sq == 0.0:
        distance = math.hypot(previous_x, previous_y)
      else:
        projection = max(0.0, min(1.0, -(previous_x * segment_x + previous_y * segment_y) / segment_length_sq))
        distance = math.hypot(previous_x + projection * segment_x, previous_y + projection * segment_y)
      minimum_distance = min(minimum_distance, distance)
      previous_x, previous_y = current_x, current_y
    return minimum_distance

  def contains_with_margin(self, latitude: float, longitude: float, margin_m: float) -> bool:
    if not math.isfinite(margin_m) or margin_m < 0.0:
      raise ValueError("geofence margin must be finite and non-negative")
    return self.contains(latitude, longitude) and self.boundary_distance_m(latitude, longitude) >= margin_m
