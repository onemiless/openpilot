import gc
import numpy as np
import pytest

from openpilot.sunnypilot.modeld_v2 import modeld as modeld_module
from openpilot.sunnypilot.models import manager as manager_module
from openpilot.sunnypilot.models.helpers import REQUIRED_JSON_VERSION


class FakeParams:
  def __init__(self):
    self.values = {}
    self.blocking_bool_writes = []

  def put_bool(self, key, value, block=False):
    self.values[key] = bool(value)
    if block:
      self.blocking_bool_writes.append((key, bool(value)))

  def put(self, key, value, block=False):
    self.values[key] = value

  def remove(self, key):
    self.values.pop(key, None)

  def get(self, key):
    return self.values.get(key)

  def get_bool(self, key):
    return bool(self.values.get(key, False))


def test_initial_big_model_failure_falls_back_to_small():
  params = FakeParams()
  small_model = object()

  def load_big():
    raise RuntimeError("USB AMD unavailable")

  model, fallback = modeld_module.load_models_with_fallback(
    chestnut=True,
    load_big=load_big,
    load_small=lambda: small_model,
    params=params,
    update_loading_progress=lambda _progress: None,
  )

  assert model is small_model
  assert fallback is small_model
  assert params.values["ChestnutActive"] is False
  assert params.values["ChestnutLoading"] is False


def test_successful_big_model_keeps_preloaded_small_for_runtime_fallback(monkeypatch):
  params = FakeParams()
  big_model = object()
  class SmallModel:
    def __init__(self):
      self.warmup_calls = 0

    def warmup(self):
      self.warmup_calls += 1

  small_model = SmallModel()
  calls = {"big": 0, "small": 0}
  monkeypatch.setattr(modeld_module, "load_with_timeout", lambda load, timeout: load())

  def load_big():
    calls["big"] += 1
    return big_model

  def load_small():
    calls["small"] += 1
    return small_model

  model, fallback = modeld_module.load_models_with_fallback(
    chestnut=True,
    load_big=load_big,
    load_small=load_small,
    params=params,
    update_loading_progress=lambda _progress: None,
  )

  assert model is big_model
  assert fallback is small_model
  assert calls == {"big": 1, "small": 1}
  assert small_model.warmup_calls == 1
  assert params.values["ChestnutActive"] is True
  assert params.values["ChestnutLoading"] is False


def test_small_fallback_warmup_clears_recurrent_state():
  state = modeld_module.ModelState.__new__(modeld_module.ModelState)
  state.is_run_model = False
  state.frame_buf_params = {"img": (1, 1, 1, 4), "big_img": (1, 1, 1, 4)}
  state._road_key = "img"
  state._wide_key = "big_img"
  state._vision_input_names = ["img", "big_img"]
  state.numpy_inputs = {
    "desire": np.ones(2, dtype=np.float32),
    "tfm": np.ones((3, 3), dtype=np.float32),
    "big_tfm": np.ones((3, 3), dtype=np.float32),
    "prev_feat": np.ones(2, dtype=np.float32),
  }
  state.full_frames = {"img": object()}
  state._blob_cache = {("img", 1): object()}
  state.prev_desire = np.ones(2, dtype=np.float32)

  def fake_run(_bufs, _transforms, _inputs):
    for value in state.numpy_inputs.values():
      value[:] = 7
    state.full_frames["big_img"] = object()
    state._blob_cache[("big_img", 2)] = object()

  state.run = fake_run
  state.warmup()

  assert all(not np.any(value) for value in state.numpy_inputs.values())
  assert not np.any(state.prev_desire)
  assert state.full_frames == {}
  assert state._blob_cache == {}


def test_successful_big_model_survives_missing_small_fallback(monkeypatch):
  params = FakeParams()
  big_model = object()
  monkeypatch.setattr(modeld_module, "load_with_timeout", lambda load, timeout: load())

  def load_small():
    raise AssertionError("No driving pkl found — qcom slot empty")

  model, fallback = modeld_module.load_models_with_fallback(
    chestnut=True,
    load_big=lambda: big_model,
    load_small=load_small,
    params=params,
    update_loading_progress=lambda _progress: None,
  )

  assert model is big_model
  assert fallback is None
  assert params.values["ChestnutActive"] is True
  assert params.values["ChestnutLoading"] is False


def test_runtime_big_model_failure_switches_to_preloaded_small(monkeypatch):
  params = FakeParams()
  params.values["ChestnutActive"] = True
  small_model = object()
  chestnut_state = type("ChestnutState", (), {"big": True})()
  logs = []
  retained = []
  destroyed = []
  monkeypatch.setattr(modeld_module, "_failed_chestnut_models", retained)
  monkeypatch.setattr(modeld_module.cloudlog, "exception", lambda *args: logs.append(args))

  class FailingBigModel:
    def run(self, *_args, **_kwargs):
      raise RuntimeError("non-finite model output")

    def __del__(self):
      destroyed.append(True)

  active = FailingBigModel()
  active, output, fell_back = modeld_module.run_model_with_fallback(
    active, small_model, params, chestnut_state, (), {}, {},
  )

  assert active is small_model
  assert output is None
  assert fell_back
  assert params.values["ChestnutActive"] is False
  assert chestnut_state.big is False
  assert ("ChestnutActive", False) in params.blocking_bool_writes
  assert logs == [("chestnut failed, falling back to small",)]
  assert len(retained) == 1
  assert destroyed == []

  retained.clear()
  gc.collect()
  assert destroyed == [True]


def test_failed_small_warmup_does_not_leave_broken_runtime_fallback(monkeypatch):
  params = FakeParams()
  big_model = object()

  class SmallModel:
    def warmup(self):
      raise RuntimeError("QCOM warmup failed")

  monkeypatch.setattr(modeld_module, "load_with_timeout", lambda load, timeout: load())
  model, fallback = modeld_module.load_models_with_fallback(
    chestnut=True,
    load_big=lambda: big_model,
    load_small=SmallModel,
    params=params,
    update_loading_progress=lambda _progress: None,
  )

  assert model is big_model
  assert fallback is None


def test_runtime_big_model_failure_without_small_fallback_is_explicit():
  params = FakeParams()
  params.values["ChestnutActive"] = True

  class FailingBigModel:
    def run(self, *_args, **_kwargs):
      raise RuntimeError("USB stream stopped")

  with pytest.raises(RuntimeError, match="small fallback unavailable"):
    modeld_module.run_model_with_fallback(
      FailingBigModel(), None, params, None, (), {}, {},
    )

  assert params.values["ChestnutActive"] is False


def test_non_finite_big_model_plan_becomes_fallback_error():
  outputs = {"plan": np.array([np.nan])}

  with pytest.raises(RuntimeError, match="not finite"):
    modeld_module.validate_model_outputs(chestnut=True, outputs=outputs)


def test_runtime_forwards_enqueue_callback_without_losing_fallback():
  params = FakeParams()
  calls = []

  class Model:
    def run(self, *args, after_enqueue=None):
      after_enqueue()
      return {"plan": np.array([1.0])}

  model = Model()
  active, output, fell_back = modeld_module.run_model_with_fallback(
    model, None, params, None, (), {}, {}, after_enqueue=lambda: calls.append("telemetry"),
  )
  assert active is model
  assert not fell_back
  assert calls == ["telemetry"]
  assert output["plan"][0] == 1.0


def test_missing_qcom_selection_queues_exact_default_fallback_ref():
  params = FakeParams()
  params.values["ModelManager_ActiveBundleChestnut"] = {
    "internalName": "BMV4",
    "minimumSelectorVersion": REQUIRED_JSON_VERSION,
  }

  manager_module.ensure_default_qcom_fallback(params)

  assert params.values["ModelManager_DownloadRef"] == "5b6436a90cf6902b8aaa71c2b6f3d7164d8ae391"


@pytest.mark.parametrize("existing", (
  {"ModelManager_ActiveBundle": {"internalName": "USER", "minimumSelectorVersion": REQUIRED_JSON_VERSION}},
  {"ModelManager_DownloadRef": "user-request"},
))
def test_default_fallback_never_overwrites_user_model_or_download(existing):
  params = FakeParams()
  params.values.update(existing)
  params.values["ModelManager_ActiveBundleChestnut"] = {
    "internalName": "BMV4",
    "minimumSelectorVersion": REQUIRED_JSON_VERSION,
  }

  manager_module.ensure_default_qcom_fallback(params)

  if "ModelManager_DownloadRef" in existing:
    assert params.values["ModelManager_DownloadRef"] == "user-request"
  else:
    assert "ModelManager_DownloadRef" not in params.values
