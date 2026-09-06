"""Exercise each real Planner Backend's public publish path without running MPC."""

from importlib import import_module
from types import SimpleNamespace as ns

import numpy as np
import pytest

from openpilot.cereal import log
from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController, ModeTransitionManager
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, ordered_backends
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP
from openpilot.sunnypilot.selfdrive.traffic_control.controller import TrafficControlPhase
from openpilot.sunnypilot.selfdrive.traffic_control.final_plan_arbitrator import FinalPlanArbitrator, TrafficPlanAction


NOW_NS = 1_000_000_000


class CapturingPubMaster:
  """Snapshot messages at the external transport boundary, in send order."""

  def __init__(self):
    self.sent = []

  def send(self, service, message):
    self.sent.append((service, message.to_dict()))


class PublishInputs:
  def __init__(self, *, mode=0, event_id=11, now_ns=NOW_NS):
    self.values = {
      "trafficRadarState": ns(
        mode=mode, phase=int(TrafficControlPhase.braking), lightState=1,
        targetPresent=True, controlAllowed=True, stopControlAllowed=True, stopSafetyAllowed=True,
        confidence=1.0, shouldStop=False, plannerStartRequested=False,
        eventId=event_id, stopSessionId=event_id, publishMonoTime=now_ns,
        distanceToStopPoint=30.0, canRemaining=30.0, rawDistance=35.0, oemTargetDistance=35.0,
        sourceBus=2, quality=2, stationInnovation=0.0,
        directionUnknown=False, stopDirectionUnknown=False, driverOverrideActive=False,
        rawObservationFresh=True, observationAgeMs=0.0,
      ),
      "radarState": ns(leadOne=ns(present=False, dRel=0.0), leadTwo=ns(present=False, dRel=0.0)),
      "carState": ns(vEgo=8.0, aEgo=0.0, gasPressed=False, brakePressed=False, vCruise=50.0),
      "carControl": ns(enabled=True, longActive=True),
      "controlsState": ns(),
      "modelV2": ns(action=ns(shouldStop=False)),
      "selfdriveState": ns(personality=log.LongitudinalPersonality.standard),
    }
    self.logMonoTime = dict.fromkeys(self.values, now_ns)
    self.seen = dict.fromkeys(self.values, True)
    self.alive = dict.fromkeys(self.values, True)
    self.valid = dict.fromkeys(self.values, True)

  def __getitem__(self, service):
    return self.values[service]

  def all_checks(self, service_list=None):
    return all(self.seen[s] and self.alive[s] and self.valid[s] for s in service_list or self.values)


@pytest.fixture(params=ordered_backends(), ids=lambda spec: spec.slug)
def planner(request):
  module_name, class_name = request.param.provider.split(":", 1)
  provider = getattr(import_module(module_name), class_name)
  # Seed already computed planner outputs. All publish methods, including the
  # backend-specific diagnostics and the common SP publisher, remain real.
  # Skipping __init__ avoids opening Params or constructing an acados solver.
  result = object.__new__(provider)
  result.CP = ns(longitudinalActuatorDelay=0.2)
  result.mpc = ns(solve_time=0.001, source=log.LongitudinalPlan.LongitudinalPlanSource.cruise)
  result.v_desired_trajectory = np.full(17, 8.0)
  result.a_desired_trajectory = np.full(17, 0.5)
  result.j_desired_trajectory = np.zeros(17)
  result.output_v_target = 8.0
  result.output_a_target = 0.5
  result.output_should_stop = False
  result.allow_throttle = True
  result.fcw = False
  result.source = "cruise"
  result.events_sp = EventsSP()
  result.scc = ns(
    vision=ns(state=0, output_v_target=8.0, output_a_target=0.5, current_lat_acc=0.0,
              max_pred_lat_acc=0.0, is_enabled=False, is_active=False),
    map=ns(state=0, output_v_target=8.0, output_a_target=0.5, is_enabled=False, is_active=False),
  )
  result.resolver = ns(
    speed_limit=0.0, speed_limit_last=0.0, speed_limit_final=0.0, speed_limit_final_last=0.0,
    speed_limit_valid=False, speed_limit_last_valid=False, speed_limit_offset=0.0, distance=0.0, source=0,
  )
  result.sla = ns(state=0, is_enabled=False, is_active=False, output_v_target=8.0, output_a_target=0.5)
  result.e2e_alerts_helper = ns(green_light_alert=False, lead_depart_alert=False)
  if request.param.id == BackendId.TN_NO_DEC:
    result.accel_controller = ns(is_enabled=True, is_active=False, profile=0, state=0)
  else:
    result.dec = object.__new__(DynamicExperimentalController)
    result.dec._enabled = True
    result.dec._active = False
    result.dec._mode_manager = ModeTransitionManager()
  return result


def published_cycle(planner, inputs, arbitrator=None, *, now_ns=NOW_NS):
  pm = CapturingPubMaster()
  sink = pm if arbitrator is None else arbitrator.publisher(pm, inputs, now_ns)
  planner.publish(inputs, sink)
  assert [service for service, _ in pm.sent] == ["longitudinalPlan", "longitudinalPlanSP"]
  assert all(message["valid"] for _, message in pm.sent)
  return pm.sent[0][1]["longitudinalPlan"], pm.sent[1][1]["longitudinalPlanSP"]


def without_processing_delay(plan):
  # Message creation timestamps naturally differ between the two publications.
  return {key: value for key, value in plan.items() if key != "processingDelay"}


def assert_current_diagnostics(plan, plan_sp, inputs, *, base_a_target):
  traffic = plan_sp["teslaTrafficControl"]
  assert plan_sp["aTarget"] == plan["aTarget"]
  assert traffic["finalATarget"] == plan["aTarget"]
  assert traffic["baseATarget"] == base_a_target
  assert traffic["shouldStop"] == plan["shouldStop"]
  assert traffic["eventId"] == inputs["trafficRadarState"].eventId
  assert traffic["stopSessionId"] == inputs["trafficRadarState"].stopSessionId
  return traffic


def test_traffic_off_preserves_the_complete_backend_plan(planner):
  inputs = PublishInputs(mode=0)
  baseline, baseline_sp = published_cycle(planner, inputs)
  arbitrator = FinalPlanArbitrator(planner.CP)

  plan, plan_sp = published_cycle(planner, inputs, arbitrator)

  assert without_processing_delay(plan) == without_processing_delay(baseline)
  assert {key: value for key, value in plan_sp.items() if key != "teslaTrafficControl"} == baseline_sp
  traffic = assert_current_diagnostics(plan, plan_sp, inputs, base_a_target=baseline["aTarget"])
  assert traffic["mode"] == 0
  assert traffic["action"] == int(TrafficPlanAction.none)
  assert not traffic["active"]
  assert not traffic["applied"]


def test_stop_publishes_the_applied_constraint_and_matching_diagnostics(planner):
  inputs = PublishInputs(mode=4)
  baseline, _ = published_cycle(planner, inputs)
  arbitrator = FinalPlanArbitrator(planner.CP)

  plan, plan_sp = published_cycle(planner, inputs, arbitrator)

  assert plan["aTarget"] < baseline["aTarget"] - 1e-3
  assert plan["speeds"] != baseline["speeds"]
  assert plan["accels"] != baseline["accels"]
  traffic = assert_current_diagnostics(plan, plan_sp, inputs, base_a_target=baseline["aTarget"])
  assert traffic["mode"] == 4
  assert traffic["action"] == int(TrafficPlanAction.stop)
  assert traffic["active"]
  assert traffic["applied"]
  assert traffic["constraintAccel"] == pytest.approx(plan["aTarget"])
  # Traffic publishes a final constraint; it does not alter backend recursion.
  assert planner.output_a_target == baseline["aTarget"]


def test_next_cycle_off_replaces_stop_diagnostics_and_restores_the_current_base_plan(planner):
  arbitrator = FinalPlanArbitrator(planner.CP)
  stopping_inputs = PublishInputs(mode=4, event_id=21)
  stopped_plan, stopped_sp = published_cycle(planner, stopping_inputs, arbitrator)
  stopped = assert_current_diagnostics(stopped_plan, stopped_sp, stopping_inputs, base_a_target=0.5)
  assert stopped["applied"]
  assert stopped["action"] == int(TrafficPlanAction.stop)

  next_ns = NOW_NS + 50_000_000
  off_inputs = PublishInputs(mode=0, event_id=22, now_ns=next_ns)
  # A new base solution makes a one-cycle-old aTarget or shouldStop observable.
  planner.output_a_target = -0.75
  planner.output_should_stop = True
  planner.output_v_target = 7.5
  planner.v_desired_trajectory = np.full(17, 7.5)
  planner.a_desired_trajectory = np.full(17, -0.75)
  baseline, _ = published_cycle(planner, off_inputs)

  plan, plan_sp = published_cycle(planner, off_inputs, arbitrator, now_ns=next_ns)

  assert without_processing_delay(plan) == without_processing_delay(baseline)
  assert plan["modelMonoTime"] == next_ns
  assert plan["aTarget"] != stopped_plan["aTarget"]
  assert plan["shouldStop"] != stopped_plan["shouldStop"]
  traffic = assert_current_diagnostics(plan, plan_sp, off_inputs, base_a_target=-0.75)
  assert traffic["mode"] == 0
  assert traffic["action"] == int(TrafficPlanAction.none)
  assert not traffic["active"]
  assert not traffic["applied"]
