OPERATIONAL_CRUISE_STATES = frozenset(("ENABLED", "STANDSTILL", "OVERRIDE", "PRE_FAULT", "PRE_CANCEL"))
AVAILABLE_CRUISE_STATES = OPERATIONAL_CRUISE_STATES | {"STANDBY"}
FAILURE_CRUISE_STATES = frozenset(("UNAVAILABLE", "FAULT"))


def decode_das_control_payload(data: bytes) -> dict[str, bool | float | int | str]:
  """Decode the packed Model 3/Y 0x2B9 payload recorded at the TX boundary."""
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
  return previous in AVAILABLE_CRUISE_STATES and current in FAILURE_CRUISE_STATES


def classify_cruise_snapshot(snapshot: dict) -> dict[str, list[str]]:
  """Keep ECU-reported faults separate from timing correlations."""
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
  if snapshot.get("tx_counter_gap"):
    correlated.append("cp_tx_counter_gap")
  if snapshot.get("tx_interval_ms") is not None and snapshot["tx_interval_ms"] > 55.0:
    correlated.append("cp_tx_interval_long")
  physical_echo_recent = (snapshot.get("physical_echo_age_ms") is not None and
                          0 <= snapshot["physical_echo_age_ms"] <= 200.0)
  if physical_echo_recent and snapshot.get("physical_echo_kind") == "rejected":
    correlated.append("panda_tx_rejected")
  if physical_echo_recent and snapshot.get("physical_echo_interval_ms") is not None and snapshot["physical_echo_interval_ms"] > 55.0:
    correlated.append("physical_tx_interval_long")
  if physical_echo_recent and snapshot.get("physical_echo_matches_last_attempt") is False:
    correlated.append("tx_echo_payload_mismatch")
  if not vehicle_reported and not correlated:
    correlated.append("undetermined")
  return {"vehicle_reported": vehicle_reported, "correlated": correlated}
