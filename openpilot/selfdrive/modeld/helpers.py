import io
import pickle
import struct
from pathlib import Path

from openpilot.common.file_chunker import get_manifest_path
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


def chestnut_compiled(selected_model: bool = False) -> bool:
  if selected_model:
    from openpilot.common.hardware.hw import Paths
    from openpilot.sunnypilot.models.helpers import get_selected_bundle, _bundle_artifacts
    bundle = get_selected_bundle(source='chestnut')
    if bundle is not None:
      artifacts = _bundle_artifacts(bundle)
      model_ready = bool(artifacts) and all(_compiled_file(Path(Paths.model_root()) / name) for name, _ in artifacts)
    else:
      model_ready = _compiled_file(modeld_pkl_path(chestnut=True)) or Path(get_manifest_path(modeld_pkl_path(chestnut=True))).is_file()
  else:
    path = modeld_pkl_path(chestnut=True)
    model_ready = _compiled_file(path) or Path(get_manifest_path(path)).is_file()
  return model_ready and all(
    _compiled_file(MODELS_DIR / f'big_driving_warp_{size}_tinygrad.pkl') for size in ('1344x760', '1928x1208'))
