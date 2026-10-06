#!/usr/bin/env python3
"""Closed-loop replay: gas and over-speed only suppress Traffic control while active;
a yellowPass belongs to one control point.

Drives the real TeslaTrafficControlController at 20 Hz with ~2 Hz 0x25D frames
from a synthetic road, a kinematic car, and the FinalPlanArbitrator one-shot
stop-feasibility gate (re-implemented from its constants because the arbitrator
module needs capnp). Runs with plain python3: numpy/opendbc are stubbed only if
they are missing. Exit status is non-zero when any expectation fails.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _interp(x, xp, fp):
  if x <= xp[0]:
    return fp[0]
  for i in range(1, len(xp)):
    if x <= xp[i]:
      return fp[i - 1] + (fp[i] - fp[i - 1]) * (x - xp[i - 1]) / (xp[i] - xp[i - 1])
  return fp[-1]


try:
  import numpy  # noqa: F401
  STUBS = []
except ImportError:
  sys.modules["numpy"] = types.SimpleNamespace(interp=_interp, clip=lambda x, a, b: max(a, min(b, x)))
  STUBS = ["numpy"]
try:
  from opendbc.can import CANParser  # noqa: F401
except Exception:
  sys.modules.setdefault("opendbc", types.ModuleType("opendbc"))
  sys.modules["opendbc.can"] = types.SimpleNamespace(CANParser=object)
  STUBS.append("opendbc.can")

from openpilot.sunnypilot.selfdrive.traffic_control.controller import (  # noqa: E402
  TeslaTrafficControlController, TrafficControlConfig, TrafficControlMode, TrafficControlPhase as P,
)
from openpilot.sunnypilot.selfdrive.traffic_control.stop_profile import StopProfileGenerator  # noqa: E402
from openpilot.sunnypilot.selfdrive.traffic_control.tesla_observer import TeslaTrafficControlObservation  # noqa: E402

# final_plan_arbitrator.py constants (Standard personality, Tesla default delay).
MAX_TRAFFIC_STOP_BRAKE = 3.0
ACTUATOR_DELAY = 0.15
STOP_CONTROL_PHASES = (P.approachRed, P.braking, P.hold, P.flashingGreenStop, P.yellowStop)
DT = 0.05
RED, GREEN, YELLOW = 1, 2, 3


def jerk_scale(v):
  return _interp(v * 3.6, [0.0, 30.0, 60.0, 90.0], [0.70, 0.85, 1.10, 1.25])


def activation_distance(v, a):
  d = StopProfileGenerator.required_stop_distance(v_ego=v, a_ego=a, actuator_delay=ACTUATOR_DELAY + 0.2,
                                                  max_brake=2.5, jerk_limit=0.8 * jerk_scale(v))
  return max(20.0, min(200.0, d + 26.0))


def stop_feasible(v, a, remaining, phase):
  if phase in (P.yellowStop, P.flashingGreenStop):
    brake, jerk, margin = 2.5, 0.8 * jerk_scale(v), max(2.0, min(4.0, 1.0 + 0.15 * v))
  else:
    brake, jerk, margin = MAX_TRAFFIC_STOP_BRAKE, 1.1, 0.0
  need = StopProfileGenerator.required_stop_distance(v_ego=v, a_ego=a, actuator_delay=ACTUATOR_DELAY + 0.05,
                                                     max_brake=brake, jerk_limit=jerk)
  return remaining >= need + margin


def color_at(light, t):
  color = light["colors"][0][1]
  for start, c in light["colors"]:
    if t >= start:
      color = c
  return color


def run(sc, frame_offset):
  c = TeslaTrafficControlController(TrafficControlConfig(
    mode=TrafficControlMode.stopGo, max_control_speed=sc.get("max_speed", float("inf"))))
  lights = sc["lights"]
  t, ego, v, a = 0.0, 0.0, sc["v0"], 0.0
  frame_t, obs = -1.0, None
  armed = rejected = 0
  stats = [{"latched": False, "controlled": False, "controlled_after_latch": False, "max_required_decel": 0.0,
            "ran_red": False, "stopped_before_line": False} for _ in lights]
  stopped_for = 0.0
  while t < 90.0 and ego < lights[-1]["station"] + 30.0:
    t += DT
    ahead = [i for i, light in enumerate(lights) if light["station"] > ego]
    idx = ahead[0] if ahead else None
    if t >= frame_t + 0.5 - 1e-9:
      # 2 Hz 0x25D frame: distance and colour are sampled at frame time and held until the next one.
      frame_t = frame_offset + math.floor((t - frame_offset) / 0.5 + 1e-9) * 0.5
      dist = lights[idx]["station"] - ego if idx is not None else 255.0
      light_state, distance = (color_at(lights[idx], t), dist) if dist <= 200.0 else (0, 255.0)
      obs = TeslaTrafficControlObservation(
        available=True, valid_for_control=distance <= 200.0, source_bus=2, dlc=8, control_source=3,
        control_type=3, distance=round(distance, 1), light_state=light_state, frame_mono_time=int(t * 1e9), quality=2)
    gas = sc["gas"](t, ego)
    d = c.update(obs, int(t * 1e9), v_ego=v, a_ego=a, enabled=True, long_active=True, gas_pressed=gas,
                 brake_pressed=False, turn_signal_active=False)

    # FinalPlanArbitrator ownership: decide feasibility once per stop session.
    trackable = d.phase in STOP_CONTROL_PHASES and d.stop_session_id > 0
    sid = d.stop_session_id
    if trackable:
      armed = 0 if armed not in (0, sid) else armed
      rejected = 0 if rejected not in (0, sid) else rejected
      if sid not in (armed, rejected) and (d.phase == P.hold or d.remaining_distance <= activation_distance(v, a)):
        if not stop_feasible(v, a, d.remaining_distance, d.phase):
          rejected = sid
        elif d.stop_control_allowed:
          armed = sid
    elif sid != armed:
      armed = 0
    active = trackable and sid == armed and d.stop_control_allowed and not gas
    if idx is not None and d.phase in (P.bypass, P.yellowPass):
      stats[idx]["latched"] = True

    cruise = sc["cruise"](t)
    accel = max(-1.5, min(1.5, 0.8 * (cruise - v)))
    if gas:
      accel = max(accel, 0.0)
    if active and idx is not None:
      required = v * v / (2.0 * max(d.remaining_distance, 0.05))
      s = stats[idx]
      s["controlled"] = True
      s["controlled_after_latch"] |= s["latched"]
      s["max_required_decel"] = round(max(s["max_required_decel"], required), 3)
      accel = min(accel, -min(required, MAX_TRAFFIC_STOP_BRAKE))
    a = accel
    v_next = max(0.0, v + a * DT)
    ego_next = ego + 0.5 * (v + v_next) * DT
    if idx is not None and ego_next >= lights[idx]["station"] and color_at(lights[idx], t) == RED:
      stats[idx]["ran_red"] = True
    v, ego = v_next, ego_next
    stopped_for = stopped_for + DT if v < 0.05 else 0.0
    if stopped_for >= 3.0:
      if idx is not None:
        stats[idx]["stopped_before_line"] = lights[idx]["station"] - ego >= 0.0
      break
  return stats


def check(expect, s):
  if expect == "bypass":
    return s["latched"] and not s["controlled_after_latch"]
  if expect == "stop":
    return s["controlled"] and s["stopped_before_line"] and not s["ran_red"] \
      and s["max_required_decel"] <= MAX_TRAFFIC_STOP_BRAKE + 1e-6
  if expect == "no_hard_brake":
    return s["max_required_decel"] <= MAX_TRAFFIC_STOP_BRAKE + 1e-6
  raise ValueError(expect)


def red(station):
  return {"station": station, "colors": [(0.0, RED)]}


SCENARIOS = [
  {"name": "plain_red_stops", "v0": 10.0, "cruise": lambda t: 10.0, "gas": lambda t, x: False,
   "lights": [red(150.0)], "expect": ["stop"]},
  # Gas tapped with no light in range is a speed adjustment: the later red must stop.
  {"name": "gas_tap_before_red", "v0": 10.0, "cruise": lambda t: 10.0, "gas": lambda t, x: 3.0 <= t < 3.05,
   "lights": [red(280.0)], "expect": ["stop"]},
  # Gas is a temporary override: after release the same red is controlled again when a stop is feasible.
  {"name": "gas_tap_on_approach_resumes", "v0": 10.0, "cruise": lambda t: 10.0, "gas": lambda t, x: 1.0 <= t < 1.05,
   "lights": [red(100.0)], "expect": ["stop"]},
  # Tap close to the line: resumption comes too late for a comfortable stop, so the arbitrator gives up.
  {"name": "gas_tap_close_gives_up", "v0": 10.0, "cruise": lambda t: 10.0, "gas": lambda t, x: 1.0 <= t < 1.05,
   "lights": [red(60.0)], "expect": ["no_hard_brake"]},
  # Over-speed suppresses control only while above the limit; after slowing the same red stops.
  {"name": "overspeed_then_slow_resumes", "v0": 20.0, "max_speed": 60 / 3.6, "gas": lambda t, x: False,
   "cruise": lambda t: 20.0 if t < 2.0 else 8.0, "lights": [red(150.0)], "expect": ["stop"]},
  # Gas held through a red; next red appears 200 m ahead with no 255 frame in between.
  {"name": "gas_through_red_then_next", "v0": 10.0, "cruise": lambda t: 10.0, "gas": lambda t, x: x < 62.0,
   "lights": [red(60.0), red(260.0)], "expect": ["bypass", "stop"]},
  {"name": "gas_held_through_red", "v0": 10.0, "cruise": lambda t: 10.0, "gas": lambda t, x: True,
   "lights": [red(100.0)], "expect": ["bypass"]},
  # Yellow PASS is one-time for its light; the next red (no 255 gap) must stop.
  {"name": "yellow_pass_then_red", "v0": 15.0, "cruise": lambda t: 15.0, "gas": lambda t, x: False,
   "lights": [{"station": 120.0, "colors": [(0.0, GREEN), (6.5, YELLOW), (9.5, RED)]}, red(320.0)],
   "expect": ["bypass", "stop"]},
  # Release right before a too-close red must give up (feasibility), never brake above 3 m/s^2.
  {"name": "release_then_infeasible_red", "v0": 15.0, "cruise": lambda t: 15.0, "gas": lambda t, x: x < 62.0,
   "lights": [red(60.0), red(95.0)], "expect": ["bypass", "no_hard_brake"]},
  {"name": "release_near_red_no_hard_brake", "v0": 15.0, "cruise": lambda t: 15.0, "gas": lambda t, x: x < 50.0,
   "lights": [red(70.0)], "expect": ["no_hard_brake"]},
]


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--out", default="/tmp/sp_traffic_override_e2e.json")
  args = parser.parse_args()
  controller_path = ROOT / "openpilot/sunnypilot/selfdrive/traffic_control/controller.py"
  results, ok = [], True
  for sc in SCENARIOS:
    for offset in (0.0, 0.125, 0.25, 0.375):
      stats = run(sc, offset)
      passed = all(check(e, s) for e, s in zip(sc["expect"], stats, strict=True))
      ok &= passed
      results.append({"scenario": sc["name"], "frame_offset_s": offset, "expect": sc["expect"],
                      "pass": passed, "lights": stats})
      print(f"{'PASS' if passed else 'FAIL'} {sc['name']:32s} offset={offset:<5} "
            + " | ".join(f"{e}: latched={s['latched']} ctl={s['controlled']} ctl_after_latch={s['controlled_after_latch']} stop={s['stopped_before_line']} ran_red={s['ran_red']} "
                         f"maxdec={s['max_required_decel']}" for e, s in zip(sc["expect"], stats, strict=True)))
  head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
  dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", str(controller_path)],
                         capture_output=True, text=True).stdout.strip()
  artifact = {"pass": ok, "source_commit": head, "controller_dirty": bool(dirty),
              "controller_sha256": hashlib.sha256(controller_path.read_bytes()).hexdigest(),
              "stubbed_modules": STUBS, "results": results}
  Path(args.out).write_text(json.dumps(artifact, indent=2))
  print(f"{'PASS' if ok else 'FAIL'} {sum(r['pass'] for r in results)}/{len(results)} -> {args.out}")
  return 0 if ok else 1


if __name__ == "__main__":
  sys.exit(main())
