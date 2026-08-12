#pragma once

typedef enum __attribute__((packed)) {
  MADS_EDGE_NO_CHANGE = 0,
  MADS_EDGE_RISING = 1,
  MADS_EDGE_FALLING = 2,
} MadsEdgeTransition;

typedef enum __attribute__((packed)) {
  MADS_DISENGAGE_REASON_NONE = 0,
  MADS_DISENGAGE_REASON_BRAKE = 1,
  MADS_DISENGAGE_REASON_LAG = 2,
  MADS_DISENGAGE_REASON_RX_INVALID = 4,
  MADS_DISENGAGE_REASON_ACC_MAIN_OFF = 8,
  MADS_DISENGAGE_REASON_RELAY_MALFUNCTION = 16,
  MADS_DISENGAGE_REASON_HEARTBEAT_ENGAGED_MISMATCH = 32,
  MADS_DISENGAGE_REASON_STEERING_DISENGAGE = 64,
} MadsDisengageReason;

#define ALT_EXP_ENABLE_MADS 1024
#define ALT_EXP_MADS_DISENGAGE_LATERAL_ON_BRAKE 2048
#define ALT_EXP_MADS_PAUSE_LATERAL_ON_BRAKE 4096
#define ALT_EXP_MADS_COOPERATIVE_STEERING 8192

typedef struct {
  MadsEdgeTransition transition;
  bool current;
  bool previous;
} MadsBinaryState;

typedef struct {
  MadsBinaryState acc_main;
  MadsBinaryState op_controls_allowed;
  MadsBinaryState braking;
  MadsBinaryState steering_disengage;
  MadsDisengageReason disengage_reason;
  bool system_enabled;
  bool disengage_lateral_on_brake;
  bool pause_lateral_on_brake;
  bool cooperative_steering;
  bool controls_requested_lateral;
} MadsSafetyState;

extern MadsSafetyState mads_state;
extern bool controls_allowed_lateral;
extern bool heartbeat_engaged_mads;
extern uint32_t heartbeat_engaged_mads_mismatches;

void mads_set_alternative_experience(const int *mode);
void mads_state_update(bool op_acc_main, bool op_allowed, bool is_braking, bool steering_disengage_now);
void mads_exit_controls(MadsDisengageReason reason);
void mads_set_heartbeat_engaged(bool engaged);
void mads_heartbeat_engaged_check(void);
