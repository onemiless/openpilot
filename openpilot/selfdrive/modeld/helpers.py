import sys
import time
from pathlib import Path

from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
from openpilot.common.hardware import AGNOS
from openpilot.common.hardware.usb import USB_DEVICES_PATH, is_chestnut_runtime_device, read

MODELS_DIR = Path(__file__).resolve().parent / 'models'


def modeld_pkl_path(chestnut: bool):
  prefix = 'big_' if chestnut else ''
  return MODELS_DIR / f'{prefix}driving_tinygrad.pkl'

def load_oob(path, chestnut=False):
  from tinygrad import Context
  device = 'USB+AMD:LLVM' if chestnut else 'QCOM' if AGNOS else 'METAL' if sys.platform == 'darwin' else 'CPU:LLVM'
  with Context(DEV=device):
    from tinygrad_repo.examples.openpilot.helpers import load_pickle
    return load_pickle(path, out_of_band=True)

def chestnut_present() -> bool:
  for d in USB_DEVICES_PATH.glob("*"):
    try:
      device = {"vendorId": int((d / "idVendor").read_text(), 16), "productId": int((d / "idProduct").read_text(), 16),
                "product": read(d / "product") or "", "manufacturer": read(d / "manufacturer") or ""}
      if is_chestnut_runtime_device(device):
        return True
    except Exception:
      pass
  return False

def wait_for_chestnut(timeout: float = 10.) -> None:
  # the cable is detected before chestnut enumerates
  st = time.monotonic()
  while not chestnut_present():
    if time.monotonic() - st > timeout:
      raise TimeoutError("chestnut did not enumerate")
    time.sleep(0.1)


def _compiled_file(path: Path) -> bool:
  try:
    with path.open('rb') as f:
      header = f.read(64)
      return bool(header) and not header.startswith(b'version https://git-lfs.github.com/spec/v1')
  except OSError:
    return False


def compiled_model_file(path: Path, expected_chunks: int | None = None) -> bool:
  """Cheap loader-file completeness check; download/activation verifies hashes."""
  if path.is_file():
    return _compiled_file(path)
  try:
    count = int(Path(get_manifest_path(path)).read_text().strip())
    # ponytail: cap probes at 1024 chunks (~45 GiB); raise only for larger supported models.
    return 0 < count <= 1024 and (expected_chunks is None or count == expected_chunks) and all(
      _compiled_file(Path(get_chunk_name(path, i, count))) for i in range(count))
  except (OSError, ValueError):
    return False


def chestnut_warps_compiled() -> bool:
  return all(_compiled_file(MODELS_DIR / f'big_driving_warp_{size}_tinygrad.pkl') for size in ('1344x760', '1928x1208'))


def chestnut_compiled() -> bool:
  return compiled_model_file(modeld_pkl_path(chestnut=True)) and chestnut_warps_compiled()
