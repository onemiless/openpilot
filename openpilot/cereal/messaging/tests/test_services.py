import subprocess
import tempfile

from openpilot.common.parameterized import parameterized

import openpilot.cereal.services as services
import openpilot.cereal.messaging as messaging
from openpilot.cereal.services import SERVICE_LIST


LEGACY_SERVICE_RENAMES = {
  "roadCameraState": "narrowRoadCameraState",
  "driverCameraState": "cabinCameraState",
  "roadEncodeIdx": "narrowRoadEncodeIdx",
  "driverEncodeIdx": "cabinEncodeIdx",
  "roadEncodeData": "narrowRoadEncodeData",
  "driverEncodeData": "cabinEncodeData",
  "qRoadEncodeIdx": "qNarrowRoadEncodeIdx",
  "qRoadEncodeData": "qNarrowRoadEncodeData",
  "livestreamRoadEncodeIdx": "livestreamNarrowRoadEncodeIdx",
  "livestreamDriverEncodeIdx": "livestreamCabinEncodeIdx",
  "livestreamRoadEncodeData": "livestreamNarrowRoadEncodeData",
  "livestreamDriverEncodeData": "livestreamCabinEncodeData",
  "liveCalibration": "extrinsicsCalibration",
  "livePose": "deviceMotion",
  "liveParameters": "vehicleParameters",
  "liveTorqueParameters": "lateralTorqueParameters",
  "liveDelay": "lateralDelay",
  "liveTracks": "radarTracks",
}


class TestServices:

  @parameterized.expand(SERVICE_LIST.keys())
  def test_services(self, s):
    service = SERVICE_LIST[s]
    assert service.frequency <= 104
    assert service.decimation != 0

  def test_generated_header(self):
    with tempfile.NamedTemporaryFile(suffix=".h") as f:
      ret = subprocess.run(f"python3 {services.__file__} > {f.name} && clang++ {f.name} -std=c++11", shell=True).returncode
      assert ret == 0, "generated services header is not valid C"

  def test_atomic_service_renames(self):
    for old_name, new_name in LEGACY_SERVICE_RENAMES.items():
      assert old_name not in SERVICE_LIST
      assert new_name in SERVICE_LIST
      assert messaging.new_message(new_name).which() == new_name
