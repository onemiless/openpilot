from pathlib import Path

import pytest

from openpilot.sunnypilot.modeld_v2.egpu_loader import finish_model_loading, require_runtime_fallback


def test_successful_chestnut_survives_missing_small_fallback():
  big_model = object()

  def missing_small():
    raise RuntimeError("small bundle missing")

  model, small_model, error = finish_model_loading(big_model, True, missing_small)

  assert model is big_model
  assert small_model is None
  assert isinstance(error, RuntimeError)


def test_missing_big_still_requires_small_model():
  with pytest.raises(RuntimeError, match="small bundle missing"):
    finish_model_loading(None, True, lambda: (_ for _ in ()).throw(RuntimeError("small bundle missing")))


def test_small_model_is_preloaded_for_runtime_fallback():
  big_model = object()
  small_model = object()

  model, fallback, error = finish_model_loading(big_model, True, lambda: small_model)

  assert model is big_model
  assert fallback is small_model
  assert error is None
  assert require_runtime_fallback(fallback, RuntimeError("big failed")) is small_model


def test_runtime_failure_without_fallback_is_explicit():
  cause = RuntimeError("big failed")
  with pytest.raises(RuntimeError, match="small fallback unavailable") as exc:
    require_runtime_fallback(None, cause)
  assert exc.value.__cause__ is cause


def test_source_build_skips_absent_default_big_onnx():
  source = (Path(__file__).parents[4] / "openpilot/selfdrive/modeld/SConscript").read_text()
  assert "except FileNotFoundError:" in source
  assert "downloaded compiled bundles remain usable" in source
