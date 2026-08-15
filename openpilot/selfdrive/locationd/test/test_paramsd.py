import random
from types import SimpleNamespace
import numpy as np

from openpilot.cereal import messaging
from opendbc.car.structs import car
from openpilot.selfdrive.locationd.paramsd import retrieve_initial_vehicle_params, VehicleParamsLearner
from openpilot.selfdrive.locationd.models.car_kf import CarKalman
from openpilot.selfdrive.locationd.test.test_locationd_scenarios import TEST_ROUTE
from openpilot.selfdrive.test.process_replay.migration import migrate, migrate_carParams
from openpilot.common.params import Params
from openpilot.tools.lib.logreader import LogReader


def get_random_live_parameters(CP):
  msg = messaging.new_message("liveParameters")
  msg.liveParameters.steerRatio = (random.random() + 0.5) * CP.steerRatio
  msg.liveParameters.stiffnessFactor = random.random()
  msg.liveParameters.angleOffsetAverageDeg = random.random()
  msg.liveParameters.debugFilterState.std = [random.random() for _ in range(CarKalman.P_initial.shape[0])]
  return msg


class TestParamsd:
  def test_does_not_learn_in_reverse(self):
    class Filter:
      def set_filter_time(self, _):
        pass

      def reset_rewind(self):
        pass

    learner = VehicleParamsLearner.__new__(VehicleParamsLearner)
    learner.kf = SimpleNamespace(filter=Filter(), predict_and_observe=lambda *args: None)
    learner.active = True
    learner.observed_speed = 0.0

    msg = SimpleNamespace(steeringAngleDeg=0.0, vEgo=5.0, gearShifter=car.CarState.GearShifter.reverse)
    learner.handle_log(1.0, "carState", msg)

    assert not learner.active

  def test_read_saved_params(self):
    params = Params()

    lr = migrate(LogReader(TEST_ROUTE), [migrate_carParams])
    CP = next(m for m in lr if m.which() == "carParams").carParams

    msg = get_random_live_parameters(CP)
    params.put("LiveParametersV2", msg.to_bytes(), block=True)
    params.put("CarParamsPrevRoute", CP.as_builder().to_bytes(), block=True)

    sr, sf, offset, p_init = retrieve_initial_vehicle_params(params, CP, replay=True, debug=True)
    np.testing.assert_allclose(sr, msg.liveParameters.steerRatio)
    np.testing.assert_allclose(sf, msg.liveParameters.stiffnessFactor)
    np.testing.assert_allclose(offset, msg.liveParameters.angleOffsetAverageDeg)
    np.testing.assert_equal(p_init.shape, CarKalman.P_initial.shape)
    np.testing.assert_allclose(np.diagonal(p_init), msg.liveParameters.debugFilterState.std)
