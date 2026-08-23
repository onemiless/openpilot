import math

from openpilot.sunnypilot.navassist.route_speed import calculate_route_speed


def offset(lat, lon, east_m, north_m):
  return (lat + math.degrees(north_m / 6_378_137.0),
          lon + math.degrees(east_m / (6_378_137.0 * math.cos(math.radians(lat)))))


def test_straight_route_is_valid_and_unconstrained():
  origin = (37.0, 127.0)
  route = tuple(offset(*origin, east, 0) for east in range(0, 201, 10))
  result = calculate_route_speed(origin, route)
  assert result.valid
  assert result.speed_mps == 0


def test_curve_produces_finite_speed_constraint():
  origin = (37.0, 127.0)
  radius = 40.0
  route = tuple(offset(*origin, radius * math.sin(t), radius * (1 - math.cos(t)))
                for t in [i * math.pi / 36 for i in range(19)])
  result = calculate_route_speed(origin, route)
  assert result.valid
  assert 3.0 <= result.speed_mps < 15.0


def test_far_route_fails_closed():
  origin = (37.0, 127.0)
  route = tuple(offset(*origin, east, 60) for east in range(0, 100, 10))
  result = calculate_route_speed(origin, route)
  assert not result.valid
  assert result.speed_mps == 0
