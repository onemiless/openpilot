from cereal import messaging
from openpilot.system.hardware import usb


def write(path, value):
  path.write_text(str(value))


def test_get_and_set_usb_state(tmp_path, monkeypatch):
  controller = tmp_path / "11200000.ssusb"
  device = controller / "usb1" / "1-1"
  device.mkdir(parents=True)
  write(device / "idVendor", "add1")
  write(device / "idProduct", "0001")
  write(device / "busnum", 1)
  write(device / "devnum", 2)
  write(device / "speed", 480)
  write(device / "manufacturer", "comma")
  write(device / "product", "panda")
  write(controller / "portli", 0x10003)
  monkeypatch.setattr(usb, "USB_DEVICES_PATH", controller / "usb1")

  devices = usb.get_usb_state()

  assert devices == [{
    "busnum": 1,
    "devnum": 2,
    "vendorId": usb.CHESTNUT_VENDOR_ID,
    "productId": usb.CHESTNUT_PRODUCT_ID,
    "speedMbps": 480,
    "manufacturer": "comma",
    "product": "panda",
    "linkErrorCount": 3,
  }]

  msg = messaging.new_message("deviceState")
  usb.set_usb_state(msg.deviceState, devices)
  assert msg.deviceState.chestnutPresent
  assert msg.deviceState.usbState.devices[0].linkErrorCount == 3


def test_get_usb_state_handles_missing_sysfs(tmp_path, monkeypatch):
  monkeypatch.setattr(usb, "USB_DEVICES_PATH", tmp_path / "missing")

  assert usb.get_usb_state() == []
