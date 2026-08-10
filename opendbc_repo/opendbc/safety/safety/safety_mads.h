#pragma once

#include "safety_mads_declarations.h"

MadsSafetyState mads_state;
bool controls_allowed_lateral = false;
bool heartbeat_engaged_mads = false;
uint32_t heartbeat_engaged_mads_mismatches = 0U;

static MadsEdgeTransition mads_edge_transition(const bool current, const bool previous) {
  MadsEdgeTransition transition = MADS_EDGE_NO_CHANGE;
  if (current && !previous) {
    transition = MADS_EDGE_RISING;
  } else if (!current && previous) {
    transition = MADS_EDGE_FALLING;
  }
  return transition;
}

static void mads_update_binary_state(MadsBinaryState *state) {
  state->transition = mads_edge_transition(state->current, state->previous);
  state->previous = state->current;
}

static void mads_state_init(void) {
  mads_state.acc_main = (MadsBinaryState){0};
  mads_state.op_controls_allowed = (MadsBinaryState){0};
  mads_state.braking = (MadsBinaryState){0};
  mads_state.steering_disengage = (MadsBinaryState){0};
  mads_state.disengage_reason = MADS_DISENGAGE_REASON_NONE;
  mads_state.controls_requested_lateral = false;
  controls_allowed_lateral = false;
  heartbeat_engaged_mads_mismatches = 0U;
}

void mads_exit_controls(const MadsDisengageReason reason) {
  mads_state.disengage_reason = reason;
  mads_state.controls_requested_lateral = false;
  controls_allowed_lateral = false;
}

void mads_set_alternative_experience(const int *mode) {
  mads_state_init();
  mads_state.system_enabled = (*mode & ALT_EXP_ENABLE_MADS) != 0;
  mads_state.disengage_lateral_on_brake = (*mode & ALT_EXP_MADS_DISENGAGE_LATERAL_ON_BRAKE) != 0;
  mads_state.pause_lateral_on_brake = (*mode & ALT_EXP_MADS_PAUSE_LATERAL_ON_BRAKE) != 0;
  mads_state.cooperative_steering = (*mode & ALT_EXP_MADS_COOPERATIVE_STEERING) != 0;
}

void mads_state_update(const bool op_acc_main, const bool op_allowed, const bool is_braking, const bool steering_disengage_now) {
  mads_state.acc_main.current = op_acc_main;
  mads_state.op_controls_allowed.current = op_allowed;
  mads_state.braking.current = is_braking;
  mads_state.steering_disengage.current = steering_disengage_now;

  mads_update_binary_state(&mads_state.acc_main);
  mads_update_binary_state(&mads_state.op_controls_allowed);
  mads_update_binary_state(&mads_state.braking);
  mads_update_binary_state(&mads_state.steering_disengage);

  bool allowed = true;
  if ((mads_state.acc_main.transition == MADS_EDGE_RISING) ||
      (mads_state.op_controls_allowed.transition == MADS_EDGE_RISING)) {
    mads_state.controls_requested_lateral = true;
  }

  if (mads_state.acc_main.transition == MADS_EDGE_FALLING) {
    mads_exit_controls(MADS_DISENGAGE_REASON_ACC_MAIN_OFF);
    allowed = false;
  }
  if (mads_state.steering_disengage.transition == MADS_EDGE_RISING) {
    mads_exit_controls(MADS_DISENGAGE_REASON_STEERING_DISENGAGE);
    allowed = false;
  }
  if (mads_state.disengage_lateral_on_brake && (mads_state.braking.transition == MADS_EDGE_RISING)) {
    mads_exit_controls(MADS_DISENGAGE_REASON_BRAKE);
    allowed = false;
  }

  if (allowed && mads_state.pause_lateral_on_brake) {
    if (mads_state.braking.transition == MADS_EDGE_RISING) {
      mads_exit_controls(MADS_DISENGAGE_REASON_BRAKE);
      allowed = false;
    } else if ((mads_state.braking.transition == MADS_EDGE_FALLING) &&
               (mads_state.disengage_reason == MADS_DISENGAGE_REASON_BRAKE)) {
      mads_state.controls_requested_lateral = true;
    } else if (mads_state.braking.current) {
      allowed = false;
    }
  }

  if (allowed && mads_state.system_enabled && mads_state.controls_requested_lateral && !controls_allowed_lateral) {
    mads_state.controls_requested_lateral = false;
    controls_allowed_lateral = true;
    mads_state.disengage_reason = MADS_DISENGAGE_REASON_NONE;
  }
}

void mads_heartbeat_engaged_check(void) {
  if (controls_allowed_lateral && !heartbeat_engaged_mads) {
    heartbeat_engaged_mads_mismatches += 1U;
    if (heartbeat_engaged_mads_mismatches >= 3U) {
      mads_exit_controls(MADS_DISENGAGE_REASON_HEARTBEAT_ENGAGED_MISMATCH);
    }
  } else {
    heartbeat_engaged_mads_mismatches = 0U;
  }
}
