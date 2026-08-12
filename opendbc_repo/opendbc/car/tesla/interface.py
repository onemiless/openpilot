from opendbc.car import get_safety_config, structs
from opendbc.car.interfaces import CarInterfaceBase
from opendbc.car.tesla.carcontroller import CarController
from opendbc.car.tesla.carstate import CarState
from opendbc.car.tesla.radar_interface import RadarInterface
from opendbc.car.tesla.values import TeslaFlags, TeslaSafetyFlags
from openpilot.common.params import Params


class CarInterface(CarInterfaceBase):
  CarState = CarState
  CarController = CarController
  RadarInterface = RadarInterface

  @staticmethod
  def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw, alpha_long, is_release, docs) -> structs.CarParams:
    ret.brand = "tesla"

    ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.tesla)]

    ret.steerLimitTimer = 1.0
    ret.steerActuatorDelay = 0.1
    ret.steerAtStandstill = True

    ret.steerControlType = structs.CarParams.SteerControlType.angle
    # 0=OFF, 1=Monitor, 2=Fusion, 3=Debug. Unknown values fail safe to OFF.
    radar_mode = Params().get_int("TeslaRadarMode")
    ret.radarUnavailable = radar_mode not in (1, 2, 3)
    ret.radarTimeStep = 1.0 / 14.0

    ret.alphaLongitudinalAvailable = True
    if alpha_long:
      ret.openpilotLongitudinalControl = True
      ret.safetyConfigs[0].safetyParam |= TeslaSafetyFlags.LONG_CONTROL.value

      ret.vEgoStopping = 0.1
      ret.vEgoStarting = 0.1
      ret.stoppingDecelRate = 0.3

    params = Params()
    # Automatic lane changes use the same reviewed 0x3E9 safety path as the
    # web-only diagnostic, but do not depend on the diagnostic being enabled.
    ret.flags |= TeslaFlags.AUTO_TURN_SIGNAL.value
    ret.safetyConfigs[0].safetyParam |= TeslaSafetyFlags.TURN_SIGNAL_TEST.value
    if params.get_bool("EnableTeslaTools"):
      ret.flags |= TeslaFlags.TURN_SIGNAL_TEST.value

    # In CP-owned mode vCruise is the source and Tesla follows it through
    # synthetic right-wheel ticks. SpeedFromPCM=1 would feed each intermediate
    # Tesla value back into CP and collapse the target after the first tick.
    if (ret.openpilotLongitudinalControl and params.get_bool("TeslaSpeedSyncEnabled") and
        params.get_int("SpeedFromPCM") != 1):
      ret.flags |= TeslaFlags.SPEED_SYNC.value
      ret.safetyConfigs[0].safetyParam |= TeslaSafetyFlags.SPEED_SYNC.value

    return ret
