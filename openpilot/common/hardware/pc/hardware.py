from openpilot.cereal import log
from openpilot.common.hardware.base import HardwareBase

NetworkType = log.DeviceState.NetworkType


class HardwarePc(HardwareBase):
  def get_device_type(self):
    return "pc"

  def get_network_type(self):
    return NetworkType.wifi


# Compatibility for local modules that still import the pre-migration name.
Pc = HardwarePc
