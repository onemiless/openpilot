"""Tests for road-edge lane-change blocking."""

from types import SimpleNamespace

import pytest

from openpilot.cereal import custom, log
from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.selfdrive.controls.lib.relc import (
  EDGE_CLEAR_TIME,
  EDGE_REACTION_TIME,
  MIN_SPEED,
  RoadEdgeLaneChangeController,
)


class DummyParams:
  def __init__(self, enabled=True):
    self.enabled = enabled

  def get_bool(self, key):
    assert key == "RoadEdgeLaneChangeEnabled"
    return self.enabled


def road_edges(left_y=2.0, right_y=-2.0):
  return [SimpleNamespace(y=[left_y]), SimpleNamespace(y=[right_y])]


@pytest.fixture
def controller(monkeypatch):
  monkeypatch.setattr("openpilot.sunnypilot.selfdrive.controls.lib.relc.Params", lambda: DummyParams(True))
  return RoadEdgeLaneChangeController()


def run_for(controller, seconds, *, left=True, right=False, speed=MIN_SPEED + 1.0, edges=None):
  road_edge_stds = [0.5 if left else 1.0, 0.5 if right else 1.0]
  lane_line_probs = [0.0 if left else 0.8, 0.5, 0.5, 0.0 if right else 0.8]
  for _ in range(int(seconds / DT_MDL) + 1):
    controller.update(road_edge_stds, lane_line_probs, speed, edges or road_edges())


def test_enabled_by_preserved_fork_default(controller):
  assert controller.enabled


def test_below_minimum_speed_resets(controller):
  run_for(controller, EDGE_REACTION_TIME + DT_MDL)
  assert controller.left_edge_detected
  controller.update([0.5, 1.0], [0.0, 0.5, 0.5, 0.8], MIN_SPEED - 0.1, road_edges())
  assert not controller.edge_detected


def test_requires_reaction_time(controller):
  run_for(controller, EDGE_REACTION_TIME - 2 * DT_MDL)
  assert not controller.left_edge_detected
  run_for(controller, 2 * DT_MDL)
  assert controller.left_edge_detected


def test_clearance_prevents_false_block(controller):
  run_for(controller, EDGE_REACTION_TIME + DT_MDL, edges=road_edges(left_y=6.0))
  assert not controller.left_edge_detected


def test_clear_debounce(controller):
  run_for(controller, EDGE_REACTION_TIME + DT_MDL)
  assert controller.left_edge_detected
  run_for(controller, EDGE_CLEAR_TIME - 2 * DT_MDL, left=False)
  assert controller.left_edge_detected
  run_for(controller, 2 * DT_MDL, left=False)
  assert not controller.left_edge_detected


def test_disabled_controller_resets(monkeypatch):
  params = DummyParams(True)
  monkeypatch.setattr("openpilot.sunnypilot.selfdrive.controls.lib.relc.Params", lambda: params)
  controller = RoadEdgeLaneChangeController()
  run_for(controller, EDGE_REACTION_TIME + DT_MDL)
  assert controller.left_edge_detected
  params.enabled = False
  controller.param_read_counter = 0
  controller.update([0.5, 1.0], [0.0, 0.5, 0.5, 0.8], MIN_SPEED + 1.0, road_edges())
  assert not controller.edge_detected


def test_update_and_fill(controller):
  run_for(controller, EDGE_REACTION_TIME + DT_MDL)
  modelv2 = SimpleNamespace(
    roadEdgeStds=[0.5, 1.0], laneLineProbs=[0.0, 0.5, 0.5, 0.8], roadEdges=road_edges(),
  )
  mdv2sp = custom.ModelDataV2SP.new_message()
  left, right = controller.update_and_fill(modelv2, mdv2sp, MIN_SPEED + 1.0)
  assert left and not right
  assert mdv2sp.leftLaneChangeEdgeBlock and not mdv2sp.rightLaneChangeEdgeBlock


def test_legacy_query_helpers(controller):
  controller.left_edge_detected = True
  assert controller.is_lane_change_blocked(log.LaneChangeDirection.left)
  assert not controller.can_change_lane_left()
  assert controller.should_trigger_lane_change(None, True) == (False, log.LaneChangeDirection.none)
