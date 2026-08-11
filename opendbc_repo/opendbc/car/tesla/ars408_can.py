from opendbc.can import CANPacker


# Panda bus 1 carries the directly connected ARS408 plus explicitly approved
# Tesla auxiliary frames through the vehicle safety gateway.
ARS408_BUS = 1
ARS408_SENSOR_ID = 0
ARS408_MAX_DISTANCE = 250
ARS408_SEND_EXTENDED = True
ARS408_SPEED_ADDRESS = 0x300
ARS408_YAW_RATE_ADDRESS = 0x301
# Vehicle motion input is allowed on the gateway-managed radar bus. A persistent user
# setting still provides a runtime rollback without changing Panda firmware.
ARS408_MOTION_INPUT_ENABLED = True

ARS408_FILTER_SIGNALS = {
  # DBC suffix, minimum, maximum, wire resolution
  0: ("NofObj", 0.0, 100.0, 1.0),
  1: ("Distance", 0.0, 409.5, 0.1),
  2: ("Azimuth", -50.0, 52.375, 0.025),
  3: ("VrelOncome", 0.0, 128.9925, 0.0315),
  4: ("VrelDepart", 0.0, 128.9925, 0.0315),
  5: ("RCS", -50.0, 52.375, 0.025),
  6: ("Lifetime", 0.0, 409.5, 0.1),
  7: ("Size", 0.0, 102.375, 0.025),
  8: ("ProbExists", 0.0, 7.0, 1.0),
  9: ("Y", -409.5, 409.5, 0.2),
  10: ("X", -500.0, 1138.2, 0.2),
  11: ("VYLeftRight", 0.0, 128.9925, 0.0315),
  12: ("VXOncome", 0.0, 128.9925, 0.0315),
  13: ("VYRightLeft", 0.0, 128.9925, 0.0315),
  14: ("VXDepart", 0.0, 128.9925, 0.0315),
}


class ARS408CAN:
  """Creates ARS408 configuration and ego-motion frames for its gateway-managed CAN."""

  def __init__(self):
    self.packer = CANPacker("ARS408")

  def create_radar_configuration(self, field=None, value=None):
    """Build one field-scoped RadarCfg write; unspecified fields stay invalid."""
    values = {}
    if field == "max_distance":
      max_distance = int(value)
      if max_distance < 200 or max_distance > 250 or max_distance % 2 != 0:
        raise ValueError("ARS408 maximum distance must be an even value from 200 to 250 m")
      values.update({"RadarCfg_MaxDistance_valid": 1, "RadarCfg_MaxDistance": max_distance})
    elif field == "send_extended":
      extended = int(value)
      if extended not in (0, 1):
        raise ValueError("ARS408 extended output must be disabled or enabled")
      values.update({"RadarCfg_SendExtInfo_valid": 1, "RadarCfg_SendExtInfo": extended})
    elif field == "output_type":
      output_type = int(value)
      if output_type not in (0, 1):
        raise ValueError("CP supports only disabled or Object ARS408 output")
      values.update({"RadarCfg_OutputType_valid": 1, "RadarCfg_OutputType": output_type})
    elif field == "store_nvm":
      values.update({"RadarCfg_StoreInNVM_valid": 1, "RadarCfg_StoreInNVM": 1})
    else:
      raise ValueError(f"unsupported ARS408 configuration field: {field}")
    return self.packer.make_can_msg("RadarConfiguration", ARS408_BUS, values)

  def create_filter_configuration(self, index, active, minimum, maximum):
    """Build one complete Object FilterCfg record; other indices are untouched."""
    index = int(index)
    if index not in ARS408_FILTER_SIGNALS:
      raise ValueError(f"unsupported ARS408 filter index: {index}")

    active = int(active)
    if active not in (0, 1):
      raise ValueError("ARS408 filter active state must be disabled or enabled")
    suffix, lower, upper, _resolution = ARS408_FILTER_SIGNALS[index]
    minimum, maximum = float(minimum), float(maximum)
    if index == 0:
      minimum = 0.0  # NofObj minimum is ignored by the protocol.
    if not (lower <= minimum <= upper and lower <= maximum <= upper and minimum <= maximum):
      raise ValueError(f"invalid ARS408 {suffix} filter range: {minimum}..{maximum}")

    values = {
      "FilterCfg_Type": 1,
      "FilterCfg_Index": index,
      "FilterCfg_Active": active,
      "FilterCfg_Valid": 1,
      f"FilterCfg_Min_{suffix}": minimum,
      f"FilterCfg_Max_{suffix}": maximum,
    }
    return self.packer.make_can_msg("FilterCfg", ARS408_BUS, values)

  def create_filter_query(self, index):
    """Read one Object FilterCfg record without modifying its NVM value."""
    index = int(index)
    if index not in ARS408_FILTER_SIGNALS:
      raise ValueError(f"unsupported ARS408 filter index: {index}")
    values = {
      "FilterCfg_Type": 1,
      "FilterCfg_Index": index,
      "FilterCfg_Active": 0,
      "FilterCfg_Valid": 0,
    }
    return self.packer.make_can_msg("FilterCfg", ARS408_BUS, values)

  def create_speed_information(self, speed_mps, direction):
    """Build an ARS408 ego-speed frame for the gateway-managed radar CAN."""
    values = {
      "RadarDevice_SpeedDirection": int(direction),
      "RadarDevice_Speed": min(max(abs(float(speed_mps)), 0.0), 163.8),
    }
    return self.packer.make_can_msg("SpeedInformation", ARS408_BUS, values)

  def create_yaw_rate_information(self, yaw_rate_deg_s):
    """Build an ARS408 yaw-rate frame; Panda safety blocks transmission."""
    values = {
      "RadarDevice_YawRate": min(max(float(yaw_rate_deg_s), -327.68), 327.67),
    }
    return self.packer.make_can_msg("YawRateInformation", ARS408_BUS, values)
