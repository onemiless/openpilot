from types import SimpleNamespace

import pytest

from openpilot.cereal import custom
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot.navassist.speed_controller import MIN_TARGET_SPEED_MPS, NavigationSpeedController


class FakeSM(dict):
  def __init__(self, nav, *, gas=False, brake=False, healthy=True, tesla_flags=0):
    super().__init__(
      navAssistStateSP=nav,
      carState=SimpleNamespace(gasPressed=gas, brakePressed=brake),
      carStateSP=SimpleNamespace(flags=tesla_flags),
    )
    self.seen = {"navAssistStateSP": healthy, "carStateSP": healthy}
    self.alive = {"navAssistStateSP": healthy, "carStateSP": healthy}
    self.valid = {"navAssistStateSP": healthy, "carStateSP": healthy}


def nav(*, distance=100.0, event_id=1, valid=True, stale=False, advisory=None,
        maneuver=custom.NavAssistStateSP.Maneuver.turnRight):
  return SimpleNamespace(
    valid=valid,
    stale=stale,
    maneuver=maneuver,
    maneuverDistanceM=distance,
    maneuverEventId=event_id,
    sessionId="session-a",
    routeRevision=1,
    advisorySpeedValid=advisory is not None,
    advisorySpeedMps=advisory or 0.0,
  )


def update(controller, sm, *, v_ego=10.0, v_cruise=20.0, override=False, long_enabled=True, planner_verified=True,
           vision_turn_active=False):
  controller.update(sm, long_enabled=long_enabled, long_override=override,
                    v_ego=v_ego, a_ego=0.0, v_cruise=v_cruise, planner_verified=planner_verified,
                    vision_turn_active=vision_turn_active)


def test_disabled_controller_is_exactly_transparent_without_nav_service_state():
  controller = NavigationSpeedController(enabled=False)
  sm = FakeSM(nav(), healthy=False)
  update(controller, sm)
  assert controller.output_v_target == V_CRUISE_UNSET
  assert controller.output_a_target == 0.0
  assert not controller.is_active


def test_controller_defaults_to_automatic_activation_when_navigation_is_valid():
  controller = NavigationSpeedController()
  update(controller, FakeSM(nav(distance=100.0)))
  assert controller.enabled
  assert controller.event_admitted


def test_early_event_is_admitted_then_activates_inside_comfort_window():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)))
  assert controller.event_admitted and not controller.is_active
  assert controller.output_v_target == V_CRUISE_UNSET

  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active
  assert controller.output_v_target == pytest.approx(5.0)
  assert controller.output_a_target == 0.0


def test_navigation_lane_change_without_a_turn_never_contributes_a_speed_ceiling():
  controller = NavigationSpeedController(enabled=True)
  sm = FakeSM(nav(distance=60.0, maneuver=custom.NavAssistStateSP.Maneuver.mergeRight))
  update(controller, sm)
  assert not controller.is_active
  assert controller.output_v_target == V_CRUISE_UNSET
  assert not controller.event_rejected


def test_imminent_turn_deceleration_is_independent_of_lane_alignment_state():
  controller = NavigationSpeedController(enabled=True)
  sm = FakeSM(nav(distance=100.0))
  update(controller, sm)
  assert controller.output_v_target == V_CRUISE_UNSET
  assert controller.event_admitted and not controller.is_active

  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active
  assert controller.output_v_target == pytest.approx(5.0)


def test_admitted_turn_holds_navigation_ceiling_at_zero_distance_until_handoff():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)))
  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active

  update(controller, FakeSM(nav(distance=0.0)))

  assert controller.is_active
  assert controller.output_v_target == pytest.approx(5.0)


def test_existing_sp_vision_turn_controller_takes_ownership_from_navigation_ceiling():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)))
  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active

  update(controller, FakeSM(nav(distance=40.0)), vision_turn_active=True)

  assert not controller.is_active
  assert controller.output_v_target == V_CRUISE_UNSET


def test_late_event_is_rejected_for_its_full_lifetime():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=40.0)))
  assert controller.event_rejected and not controller.is_active
  update(controller, FakeSM(nav(distance=20.0)))
  assert controller.event_rejected and controller.output_v_target == V_CRUISE_UNSET


def test_source_loss_or_driver_override_cancels_and_latches_event():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)))
  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active

  update(controller, FakeSM(nav(distance=55.0), healthy=False))
  assert not controller.is_active and controller.is_releasing and controller.event_rejected
  released_target = controller.output_v_target

  update(controller, FakeSM(nav(distance=50.0)))
  assert not controller.is_active
  assert controller.output_v_target > released_target

  next_event = FakeSM(nav(distance=100.0, event_id=2))
  update(controller, next_event, override=True)
  assert not controller.is_active


def test_phone_advisory_is_bounded_and_never_requests_a_stop():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0, advisory=0.5)))
  update(controller, FakeSM(nav(distance=60.0, advisory=0.5)))
  assert controller.output_v_target >= MIN_TARGET_SPEED_MPS


def test_merge_signal_never_creates_a_navigation_speed_target():
  controller = NavigationSpeedController(enabled=True)
  merge = nav(distance=80.0, maneuver=custom.NavAssistStateSP.Maneuver.mergeRight)
  update(controller, FakeSM(merge))
  assert not controller.is_active
  assert controller.output_v_target == V_CRUISE_UNSET


def test_disengaging_rejects_the_current_event_until_a_new_event_arrives():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)))
  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active
  update(controller, FakeSM(nav(distance=55.0)), long_enabled=False)
  assert controller.event_rejected and not controller.is_active
  update(controller, FakeSM(nav(distance=50.0)))
  assert not controller.is_active


def test_speed_increase_that_makes_comfort_deceleration_late_rejects_event():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=120.0)), v_ego=10.0)
  assert controller.event_admitted
  update(controller, FakeSM(nav(distance=60.0)), v_ego=15.0)
  assert controller.event_rejected and not controller.is_active


def test_disappearing_maneuver_cannot_reactivate_same_event():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)))
  update(controller, FakeSM(nav(distance=60.0)))
  assert controller.is_active
  no_event = nav(distance=55.0, event_id=0)
  no_event.maneuver = custom.NavAssistStateSP.Maneuver.none
  update(controller, FakeSM(no_event))
  assert controller.event_rejected and not controller.is_active


def test_route_can_be_started_before_sp_takes_longitudinal_ownership():
  controller = NavigationSpeedController(enabled=True, require_sp_longitudinal_owner=True)
  stock = FakeSM(nav(distance=100.0), tesla_flags=int(TeslaFlagsSP.STOCK_LONGITUDINAL_ACTIVE))
  update(controller, stock)
  assert not controller.event_rejected and not controller.event_admitted and controller.output_v_target == V_CRUISE_UNSET

  # The same still-early event may be admitted after SP takes ownership.
  sp = FakeSM(nav(distance=100.0), tesla_flags=0)
  update(controller, sp)
  assert controller.event_admitted


@pytest.mark.parametrize("flags", [
  TeslaFlagsSP.DYNAMIC_STOCK_ACTIVE,
  TeslaFlagsSP.MANUAL_STOCK_ACTIVE,
  TeslaFlagsSP.AP_HYBRID_ACTIVE | TeslaFlagsSP.STOCK_LONGITUDINAL_ACTIVE,
])
def test_all_tesla_stock_ownership_modes_fail_closed(flags):
  controller = NavigationSpeedController(enabled=True, require_sp_longitudinal_owner=True)
  update(controller, FakeSM(nav(distance=100.0), tesla_flags=int(flags)))
  assert not controller.event_admitted and not controller.is_active
  assert controller.output_v_target == V_CRUISE_UNSET


def test_tesla_ap_hybrid_sp_owner_is_allowed():
  controller = NavigationSpeedController(enabled=True, require_sp_longitudinal_owner=True)
  flags = int(TeslaFlagsSP.AP_HYBRID_ACTIVE)
  update(controller, FakeSM(nav(distance=100.0), tesla_flags=flags))
  assert controller.event_admitted


def test_route_can_be_started_before_official_longitudinal_backend_is_selected():
  controller = NavigationSpeedController(enabled=True)
  update(controller, FakeSM(nav(distance=100.0)), planner_verified=False)
  assert not controller.event_rejected and controller.output_v_target == V_CRUISE_UNSET
  update(controller, FakeSM(nav(distance=90.0)), planner_verified=True)
  assert controller.event_admitted and not controller.event_rejected


def test_disengaging_after_event_admission_still_latches_that_event():
  controller = NavigationSpeedController(enabled=True)
  sm = FakeSM(nav(distance=100.0))
  update(controller, sm)
  assert controller.event_admitted
  update(controller, FakeSM(nav(distance=90.0)), long_enabled=False)
  assert controller.event_rejected
  update(controller, FakeSM(nav(distance=80.0)), long_enabled=True)
  assert not controller.is_active and controller.event_rejected
