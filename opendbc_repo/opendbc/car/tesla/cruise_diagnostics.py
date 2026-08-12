OPERATIONAL_CRUISE_STATES = frozenset(("ENABLED", "STANDSTILL", "OVERRIDE", "PRE_FAULT", "PRE_CANCEL"))
AVAILABLE_CRUISE_STATES = OPERATIONAL_CRUISE_STATES | {"STANDBY"}
FAILURE_CRUISE_STATES = frozenset(("UNAVAILABLE", "FAULT"))


def decode_das_control_payload(data: bytes) -> dict[str, bool | float | int | str]:
  """Decode the actual packed Tesla 0x2B9 payload used for fault evidence."""
  if len(data) != 8:
    raise ValueError(f"DAS_control payload must be 8 bytes, got {len(data)}")

  raw = int.from_bytes(data, "little")

  def field(start, size):
    return (raw >> start) & ((1 << size) - 1)

  checksum_expected = (0xB9 + 0x02 + sum(data[:7])) & 0xFF
  checksum = field(56, 8)
  return {
    "tx_raw": data.hex(),
    "tx_set_speed_kph": round(field(0, 12) * 0.1, 1),
    "tx_state": field(12, 4),
    "tx_aeb_event": field(16, 2),
    "tx_jerk_min": round(field(18, 9) * 0.018 - 9.1, 3),
    "tx_jerk_max": round(field(27, 8) * 0.034, 3),
    "tx_accel_min": round(field(35, 9) * 0.04 - 15, 2),
    "tx_accel_max": round(field(44, 9) * 0.04 - 15, 2),
    "tx_counter": field(53, 3),
    "tx_checksum": checksum,
    "tx_checksum_expected": checksum_expected,
    "tx_checksum_valid": checksum == checksum_expected,
  }


def is_cruise_failure_transition(previous: str | None, current: str | None) -> bool:
  """Return true only for a newly observed transition from usable cruise into a failure state."""
  return previous in AVAILABLE_CRUISE_STATES and current in FAILURE_CRUISE_STATES


def is_cruise_failure_after_recent_operation(history, current: str | None, now_nanos: int,
                                             max_age_nanos: int = 1_000_000_000) -> bool:
  """Catch Tesla's common ENABLED -> STANDBY -> UNAVAILABLE failure sequence."""
  if current not in FAILURE_CRUISE_STATES:
    return False
  return any(snapshot.get("cruise_state") in OPERATIONAL_CRUISE_STATES and
             0 <= now_nanos - int(snapshot.get("now_nanos", 0)) <= max_age_nanos
             for snapshot in history)


def classify_cruise_snapshot(snapshot: dict) -> dict[str, list[str]]:
  """Separate vehicle-reported fault fields from timing-correlated observations.

  Correlated observations are deliberately not called causes: proving causality
  requires the Tesla ECU's own diagnostic trouble codes or a controlled replay.
  """
  vehicle_reported = []
  for key in ("pmm_sys_fault", "pmm_camera_fault", "pmm_radar_fault", "pmm_ultrasonics_fault"):
    raw = int(snapshot.get(f"{key}_raw", 0) or 0)
    if raw:
      vehicle_reported.append(f"{key}:{snapshot.get(key, f'UNKNOWN_{raw}')}({raw})")

  correlated = []
  if snapshot.get("party_can_valid") is False or snapshot.get("ap_party_can_valid") is False:
    correlated.append("vehicle_can_invalid")
  if snapshot.get("brake_pressed"):
    correlated.append("brake_pressed")
  if snapshot.get("stock_aeb"):
    correlated.append("stock_aeb_active")
  oem_age_ms = snapshot.get("oem_2b9_age_ms")
  if isinstance(oem_age_ms, int | float) and oem_age_ms > 200.0:
    correlated.append("oem_2b9_stale")
  tx_age_ms = snapshot.get("tx_attempt_age_ms")
  recent_tx = tx_age_ms is None or (isinstance(tx_age_ms, int | float) and tx_age_ms <= 100.0)
  vehicle_tx = int(snapshot.get("tx_aeb_event", 0) or 0) == 0
  if recent_tx and vehicle_tx and snapshot.get("tx_state") == 4 and snapshot.get("cc_long_active") is False:
    correlated.append("cp_state4_while_long_inactive")
  if recent_tx and vehicle_tx and snapshot.get("tx_counter_gap"):
    correlated.append("cp_tx_counter_gap")

  if not vehicle_reported and not correlated:
    correlated.append("undetermined")
  return {"vehicle_reported": vehicle_reported, "correlated": correlated}
