from opendbc.can import CANPacker


ARS408_BUS = 1
ARS408_SENSOR_ID = 0
ARS408_MAX_DISTANCE = 250
ARS408_MAX_OBJECTS = 32
ARS408_SEND_EXTENDED = True
ARS408_SPEED_ADDRESS = 0x300
ARS408_YAW_RATE_ADDRESS = 0x301
# The radar shares Tesla vehicle CAN. These IDs are intentionally blocked by
# Panda safety until an isolated bus or a vehicle capture proves no conflict.
ARS408_MOTION_INPUT_ENABLED = False

def should_configure_radar(_frame: int, reinitialize: bool = False) -> bool:
  # Radar configuration is persistent. Never transmit it automatically at
  # startup or after a transient CAN fault; only an explicit adjustment may
  # request one configuration write.
  return reinitialize


class ARS408CAN:
  """Creates the ARS408 configuration frames allowed on shared Tesla CAN."""

  def __init__(self):
    self.packer = CANPacker("ARS408")

  def create_radar_configuration(self):
    values = {
      "RadarCfg_RCS_Threshold_Valid": 1,
      "RadarCfg_RCS_Threshold": 0,       # standard sensitivity
      # Manual adjustments are rare and must survive vehicle/CP restarts.
      "RadarCfg_StoreInNVM_valid": 1,
      "RadarCfg_StoreInNVM": 1,
      "RadarCfg_SortIndex_valid": 1,
      "RadarCfg_SortIndex": 1,          # nearest objects first
      "RadarCfg_SendExtInfo_valid": 1,
      # General + Quality contain every field used for lead tracking. Turning
      # Extended off removes one frame per object from the shared Tesla bus.
      "RadarCfg_SendExtInfo": int(ARS408_SEND_EXTENDED),
      "RadarCfg_CtrlRelay_valid": 1,
      "RadarCfg_CtrlRelay": 0,
      "RadarCfg_SendQuality_valid": 1,
      "RadarCfg_SendQuality": 1,
      "RadarCfg_MaxDistance_valid": 1,
      "RadarCfg_MaxDistance": ARS408_MAX_DISTANCE,
      "RadarCfg_RadarPower_valid": 1,
      "RadarCfg_RadarPower": 0,          # standard Tx power
      "RadarCfg_OutputType_valid": 1,
      "RadarCfg_OutputType": 1,          # object list, never cluster list
      "RadarCfg_SensorID_valid": 1,
      "RadarCfg_SensorID": ARS408_SENSOR_ID,
    }
    return self.packer.make_can_msg("RadarConfiguration", ARS408_BUS, values)

  def create_object_count_filter(self):
    """Limit object-list traffic while retaining current and adjacent lanes."""
    values = {
      "FilterCfg_Type": 1,       # object filter
      "FilterCfg_Index": 0,      # number of objects
      "FilterCfg_Active": 1,
      "FilterCfg_Valid": 1,
      "FilterCfg_Min_NofObj": 0,
      "FilterCfg_Max_NofObj": ARS408_MAX_OBJECTS,
    }
    return self.packer.make_can_msg("FilterCfg", ARS408_BUS, values)

  def create_speed_information(self, speed_mps, direction):
    """Build an ARS408 ego-speed frame; Panda safety blocks transmission."""
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
