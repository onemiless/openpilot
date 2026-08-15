import numpy as np

from openpilot.selfdrive.modeld.modeld import model_output_is_valid


def test_usbgpu_rejects_non_finite_model_output():
  assert model_output_is_valid(np.array([1.0, 2.0], dtype=np.float32), usbgpu=True)
  assert not model_output_is_valid(np.array([1.0, np.nan], dtype=np.float32), usbgpu=True)
  assert not model_output_is_valid(np.array([1.0, np.inf], dtype=np.float32), usbgpu=True)


def test_cpu_path_retains_existing_behavior():
  assert model_output_is_valid(np.array([np.nan], dtype=np.float32), usbgpu=False)
