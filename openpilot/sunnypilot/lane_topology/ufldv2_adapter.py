from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path

import numpy as np

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation
from openpilot.sunnypilot.lane_topology.ufldv2 import prepare_tusimple_rgb, row_outputs_to_observations
from openpilot.sunnypilot.lane_topology.yolop import HomographyProjector


EXPECTED_UFLDV2_TUSIMPLE_RES18_SHA256 = "ea26570cc22ded75364e6a151236b8a496e9f700775501b4ed0f10c2c3204dc0"


class UFLDv2OnnxLaneModel:
  """Lazy tinygrad runner that shares the caller's already-selected device."""

  OUTPUT_NAMES = ("loc_row", "loc_col", "exist_row", "exist_col")

  def __init__(self, model_path: str | Path):
    self.model_path = Path(model_path)
    if not self.model_path.is_file():
      raise FileNotFoundError(self.model_path)
    with self.model_path.open("rb") as model_file:
      self.model_sha256 = hashlib.file_digest(model_file, "sha256").hexdigest()
    if self.model_sha256 != EXPECTED_UFLDV2_TUSIMPLE_RES18_SHA256:
      raise RuntimeError(f"UFLDv2 TuSimple ResNet18 hash mismatch: {self.model_sha256}")

    # Delayed imports are intentional. Merely importing lane_topology must not
    # choose a tinygrad device or open the USBGPU endpoint.
    from tinygrad import TinyJit
    from tinygrad.nn.onnx import OnnxRunner

    self._runner = OnnxRunner(self.model_path)
    self._forward = TinyJit(lambda images: {
      name: output.contiguous() for name, output in self._runner({"images": images}).items() if name in self.OUTPUT_NAMES
    }, prune=True)

  def outputs(self, rgb: np.ndarray) -> dict[str, np.ndarray]:
    from tinygrad import Tensor

    result = self._forward(Tensor(prepare_tusimple_rgb(rgb)))
    return {name: result[name].numpy() for name in self.OUTPUT_NAMES}

  def close(self) -> None:
    pass


class UFLDv2LaneTopologyAdapter:
  def __init__(self, model: UFLDv2OnnxLaneModel,
               projector_factory: Callable[[object], Callable[[float, float], tuple[float, float] | None]] | None = None):
    self.model = model
    self.projector_factory = projector_factory or (lambda calibration: HomographyProjector(np.asarray(calibration)))

  def infer(self, frame: LaneTopologyFrame) -> tuple[LaneBoundaryObservation, ...]:
    if not isinstance(frame.payload, np.ndarray):
      raise TypeError("UFLDv2 candidate expects an RGB numpy frame; VisionBuf conversion is a later production seam")
    if frame.calibration is None:
      raise ValueError("UFLDv2 candidate requires an image-to-vehicle homography")
    outputs = self.model.outputs(frame.payload)
    return row_outputs_to_observations(outputs, frame.payload, self.projector_factory(frame.calibration))

  def close(self) -> None:
    self.model.close()
