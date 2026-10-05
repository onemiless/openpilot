import io
import pickle
import struct
from pathlib import Path

from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
from openpilot.common.hardware.usb import CHESTNUT_USB_PRODUCT, USB_DEVICES_PATH, is_chestnut_usb_id

MODELS_DIR = Path(__file__).resolve().parent / 'models'


def modeld_pkl_path(chestnut: bool):
  prefix = 'big_' if chestnut else ''
  return MODELS_DIR / f'{prefix}driving_tinygrad.pkl'

def load_oob(f):
  opcodes = f.read(struct.unpack('<q', f.read(8))[0])
  def buffers():
    while (h := f.read(8)):
      pb = pickle.PickleBuffer(bytearray(struct.unpack('<q', h)[0]))
      if f.readinto(pb) != pb.raw().nbytes:
        raise EOFError("incomplete model buffer")
      yield pb
  return pickle.load(io.BytesIO(opcodes), buffers=buffers())

def chestnut_present() -> bool:
  for d in USB_DEVICES_PATH.glob("*"):
    try:
      usb_id = (int((d / "idVendor").read_text(), 16), int((d / "idProduct").read_text(), 16))
      product = (d / "product").read_text().strip()
      if is_chestnut_usb_id(*usb_id) and product == CHESTNUT_USB_PRODUCT:
        return True
    except Exception:
      pass
  return False

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
