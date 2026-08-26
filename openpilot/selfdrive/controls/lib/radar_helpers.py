from __future__ import annotations


def is_radar_velocity_sane(v_ego: float, v_rel: float, vision_lead_speed: float,
                           ars408_stationary_conflict_guard: bool = False) -> bool:
  radar_lead_speed = v_ego + v_rel
  velocity_consistent = abs(radar_lead_speed - vision_lead_speed) < 10.0 or radar_lead_speed > 3.0
  stationary_conflict = (
    ars408_stationary_conflict_guard
    and radar_lead_speed < 3.0
    and vision_lead_speed - radar_lead_speed >= 5.0
  )
  return velocity_consistent and not stationary_conflict
