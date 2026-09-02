import time

import pytest

from openpilot.sunnypilot.modeld_v2.egpu_loader import (
  C3XL_MODEL_LOAD_TIMEOUT,
  C3XL_TINYGRAD_CACHE_HOME,
  EgpuModelLoadError,
  configure_default_device,
  load_with_timeout,
  wait_for_link,
)


def test_c3xl_timeout_covers_measured_bmw_models():
  assert C3XL_MODEL_LOAD_TIMEOUT == 120
  assert C3XL_MODEL_LOAD_TIMEOUT >= 75.58 * 1.5


def test_configure_default_device_keeps_tinygrad_off_usb_scan():
  environment = {}
  configure_default_device(True, environment, c3xl=True)
  assert environment["DEV"] == "QCOM"
  assert environment["XDG_CACHE_HOME"] == C3XL_TINYGRAD_CACHE_HOME


def test_configure_default_device_preserves_explicit_choice():
  environment = {"DEV": "CPU", "XDG_CACHE_HOME": "/tmp/cache"}
  configure_default_device(True, environment, c3xl=True)
  assert environment["DEV"] == "CPU"
  assert environment["XDG_CACHE_HOME"] == "/tmp/cache"


def test_load_with_timeout_returns_result():
  assert load_with_timeout(lambda: "bmwv6", 1) == "bmwv6"


def test_load_with_timeout_propagates_loader_error():
  with pytest.raises(EgpuModelLoadError, match="boom"):
    load_with_timeout(lambda: (_ for _ in ()).throw(RuntimeError("boom")), 1)


def test_load_with_timeout_is_bounded():
  started = time.monotonic()
  with pytest.raises(TimeoutError):
    load_with_timeout(lambda: time.sleep(1), 0.01)
  assert time.monotonic() - started < 0.5


def test_wait_for_link_retries_until_ready():
  states = iter((False, False, True))
  delays = []
  assert wait_for_link(lambda: next(states), attempts=3, delay_fn=delays.append)
  assert delays == [1.0, 1.0]


def test_wait_for_link_rejects_invalid_attempt_count():
  with pytest.raises(ValueError, match="positive"):
    wait_for_link(lambda: True, attempts=0)
