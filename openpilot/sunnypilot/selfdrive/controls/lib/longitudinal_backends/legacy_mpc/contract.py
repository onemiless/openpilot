"""Pinned rs408 numerical/solver contract, independent of Official MPC updates."""
import numpy as np

from openpilot.cereal import log

ACADOS_SOLVER_TYPE = 'SQP_RTI'
N = 12
T_IDXS = np.array([10.0 * ((index / N) ** 2) for index in range(N + 1)])
T_DIFFS = np.diff(T_IDXS, prepend=[0.])
FCW_IDXS = T_IDXS < 5.0
COST_E_DIM = 5
COST_DIM = 6
X_EGO_COST = V_EGO_COST = A_EGO_COST = 0.
LIMIT_COST = 1e6
CRASH_DISTANCE = .25
ACCEL_MIN = -3.5
ACCEL_MAX = 2.0
COMFORT_BRAKE = 2.5
STOP_DISTANCE = 6.0
MIN_X_LEAD_FACTOR = 0.5
LEAD_ACCEL_TAU = 1.5
LongitudinalPlanSource = log.LongitudinalPlan.LongitudinalPlanSource


def get_jerk_factor(personality=log.LongitudinalPersonality.standard):
  if personality in (log.LongitudinalPersonality.relaxed, log.LongitudinalPersonality.standard):
    return 1.0
  elif personality == log.LongitudinalPersonality.aggressive:
    return 0.5
  raise NotImplementedError("Longitudinal personality not supported")


def get_T_FOLLOW(personality=log.LongitudinalPersonality.standard):
  if personality == log.LongitudinalPersonality.relaxed:
    return 1.75
  elif personality == log.LongitudinalPersonality.standard:
    return 1.45
  elif personality == log.LongitudinalPersonality.aggressive:
    return 1.25
  raise NotImplementedError("Longitudinal personality not supported")


def get_stopped_equivalence_factor(v_lead):
  return v_lead ** 2 / (2 * COMFORT_BRAKE)
