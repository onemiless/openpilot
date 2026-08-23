import math

from openpilot.sunnypilot.navassist.route_speed import RouteSpeedPlanner, calculate_route_speed


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


def test_dateline_route_uses_short_longitude_delta():
  vehicle = (0.0, 179.9999)
  route = ((0.0, 179.9999), (0.0, -179.9999), (0.0, -179.9997))
  assert calculate_route_speed(vehicle, route).valid


def test_stable_route_index_has_bounded_rollback():
  origin = (37.0, 127.0)
  route = tuple(offset(*origin, east, 0) for east in range(0, 301, 5))
  planner = RouteSpeedPlanner()
  planner.calculate(offset(*origin, 150, 0), route)
  previous = planner.nearest_index
  planner.calculate(offset(*origin, 130, 0), route)
  assert planner.nearest_index >= previous - 3


def test_invalid_route_coordinate_fails_closed():
  result = calculate_route_speed((37.0, 127.0), ((37.0, 127.0), (91.0, 127.1), (37.2, 127.2)))
  assert not result.valid
