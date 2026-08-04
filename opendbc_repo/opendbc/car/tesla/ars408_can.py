from opendbc.can import CANPacker


ARS408_BUS = 1
ARS408_SENSOR_ID = 5
ARS408_MAX_DISTANCE = 250


class ARS408CAN:
  """Creates the single safe, startup-only ARS408 configuration frame."""

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
      "RadarCfg_SendExtInfo": 1,
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
