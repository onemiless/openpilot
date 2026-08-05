from opendbc.can import CANPacker


ARS408_BUS = 1
ARS408_SENSOR_ID = 5
ARS408_MAX_DISTANCE = 300
ARS408_MAX_OBJECTS = 32
ARS408_SEND_EXTENDED = False

# Tesla shares this bus with the radar. Cover slow power-up during the first
# ten seconds, then refresh occasionally so a brownout/reset does not leave
# the radar at its default sensor ID until the next ignition cycle.
ARS408_STARTUP_CONFIG_FRAMES = (10, 50, 100, 200, 500, 1000)
ARS408_CONFIG_REFRESH_FRAMES = 3000


def should_configure_radar(frame: int) -> bool:
  return frame in ARS408_STARTUP_CONFIG_FRAMES or \
         (frame > ARS408_STARTUP_CONFIG_FRAMES[-1] and frame % ARS408_CONFIG_REFRESH_FRAMES == 0)


class ARS408CAN:
  """Creates the ARS408 configuration frames allowed on shared Tesla CAN."""

  def __init__(self):
    self.packer = CANPacker("ARS408")

  def create_radar_configuration(self):
    values = {
      "RadarCfg_RCS_Threshold_Valid": 1,
      "RadarCfg_RCS_Threshold": 0,       # standard sensitivity
      "RadarCfg_StoreInNVM_valid": 0,   # configure each boot; do not wear EEPROM
      "RadarCfg_StoreInNVM": 0,
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
