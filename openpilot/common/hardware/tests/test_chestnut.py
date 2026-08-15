from pathlib import Path

import pytest

from openpilot.common.hardware import usb
from openpilot.selfdrive.modeld import helpers
from openpilot.system.hardware.chestnut import flash


def write_usb_device(root: Path, name: str, usb_id: tuple[int, int], product: str) -> None:
  device = root / name
  device.mkdir()
  (device / "idVendor").write_text(f"{usb_id[0]:04x}\n")
  (device / "idProduct").write_text(f"{usb_id[1]:04x}\n")
  (device / "product").write_text(f"{product}\n")


@pytest.mark.parametrize("usb_id", usb.CHESTNUT_USB_IDS)
def test_usbgpu_present_requires_current_firmware(tmp_path, monkeypatch, usb_id):
  monkeypatch.setattr(helpers, "USB_DEVICES_PATH", tmp_path)
  write_usb_device(tmp_path, "1-1", usb_id, f"custom {usb.CHESTNUT_FW_VERSION}-CLEAN")
  assert helpers.usbgpu_present()


def test_usbgpu_present_rejects_old_firmware_and_rom(tmp_path, monkeypatch):
  monkeypatch.setattr(helpers, "USB_DEVICES_PATH", tmp_path)
  write_usb_device(tmp_path, "1-1", usb.CHESTNUT_USB_IDS[0], "custom deadbeef-CLEAN")
  write_usb_device(tmp_path, "1-2", usb.CHESTNUT_ROM_USB_IDS[0], flash.ROM_PRODUCT)
  assert not helpers.usbgpu_present()


def test_bundled_firmware_matches_declared_version():
  image = flash.FIRMWARE_PATH.read_bytes()
  flash.validate_image(image)
  assert flash.image_product(image) == f"custom {usb.CHESTNUT_FW_VERSION}-CLEAN"
