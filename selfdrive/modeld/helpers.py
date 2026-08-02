import json
import pickle
import shutil
import struct
import tempfile
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent / 'models'
TG_INPUT_DEVICES_PATH = MODELS_DIR / 'tg_input_devices.json'
USBGPU_VID = 0xADD1
USBGPU_PID = 0x0001


def get_tg_input_devices(process_name: str, usbgpu: bool):
  with open(TG_INPUT_DEVICES_PATH) as f:
    return json.load(f)[process_name]['default' if not usbgpu else 'usbgpu']

def modeld_pkl_path(usbgpu: bool):
  prefix = 'big_' if usbgpu else ''
  return MODELS_DIR / f'{prefix}driving_tinygrad.pkl'

def usbgpu_present() -> bool:
  for d in Path("/sys/bus/usb/devices").glob("*"):
    try:
      if int((d / "idVendor").read_text(), 16) == USBGPU_VID and \
          int((d / "idProduct").read_text(), 16) == USBGPU_PID:
        return True
    except Exception:
      pass
  return False


def dump_oob(obj, f):
  """Serialize a pickle protocol 5 object with buffers appended out-of-band."""
  with tempfile.TemporaryFile() as buffers_file:
    def buffer_callback(buffer):
      raw = buffer.raw()
      buffers_file.write(struct.pack('<Q', len(raw)))
      buffers_file.write(raw)
      buffer.release()

    opcodes = pickle.dumps(obj, protocol=5, buffer_callback=buffer_callback)
    buffers_file.seek(0)
    f.write(struct.pack('<Q', len(opcodes)))
    f.write(opcodes)
    shutil.copyfileobj(buffers_file, f)


def load_oob(f):
  opcodes_size = struct.unpack('<Q', f.read(8))[0]
  opcodes = f.read(opcodes_size)
  if len(opcodes) != opcodes_size:
    raise EOFError('truncated OOB pickle opcodes')

  def buffers():
    while True:
      size_data = f.read(8)
      if not size_data:
        return
      if len(size_data) != 8:
        raise EOFError('truncated OOB pickle buffer length')
      size = struct.unpack('<Q', size_data)[0]
      buffer = bytearray(size)
      view = memoryview(buffer)
      read = f.readinto(view)
      if read != size:
        raise EOFError('truncated OOB pickle buffer')
      yield pickle.PickleBuffer(view)

  return pickle.loads(opcodes, buffers=buffers())


def load_model_pickle(f):
  """Load either the legacy monolithic pickle or Sunnypilot's OOB format."""
  if hasattr(f, 'peek'):
    first = f.peek(1)[:1]
  else:
    pos = f.tell()
    first = f.read(1)
    f.seek(pos)
  return pickle.load(f) if first == b'\x80' else load_oob(f)
