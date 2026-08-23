from openpilot.sunnypilot.navassist.turn_mapper import TURN_TYPE_MAP, map_turn_type
from openpilot.sunnypilot.navassist.types import Maneuver


def test_turn_mapping_includes_gitcode_tollgate_values():
  assert map_turn_type(12) == Maneuver.TURN_LEFT
  assert map_turn_type(117) == Maneuver.FORK_RIGHT
  assert map_turn_type(154) == Maneuver.TOLLGATE
  assert map_turn_type(249) == Maneuver.TOLLGATE


def test_unknown_and_bool_fail_closed():
  assert map_turn_type(True) == Maneuver.NONE
  assert map_turn_type("12") == Maneuver.NONE
  assert map_turn_type(9999) == Maneuver.NONE


def test_every_audited_mapping_entry_round_trips():
  for raw, expected in TURN_TYPE_MAP.items():
    assert map_turn_type(raw) == expected
