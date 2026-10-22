#!/usr/bin/env python3
"""Temporary sysfs -> production detection/updater/monitoring; no USB writes."""
import argparse
import ctypes
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import usb1

import openpilot.cereal.messaging as messaging
from openpilot.common.hardware import usb
from openpilot.selfdrive.modeld import helpers
from openpilot.system.hardware import hardwared
from openpilot.system.hardware.chestnut import flash, monitoring, status
from tinygrad.runtime import ops_amd


class ReadOnlyHandle:
  def __init__(self, *, ltssm=0x78, supply=(12000, 1000, False), link_error=False, power_error=False):
    self.ltssm, self.supply = ltssm, supply
    self.link_error, self.power_error = link_error, power_error
    self.calls = []
    self.closed = False

  def controlRead(self, request_type, request, value, index, length, timeout):
    self.calls.append((request_type, request, value, index, length))
    assert request_type == 0xC0, 'monitoring must never issue a USB write'
    if (request, value, length) == (0xE4, 0xB450, 1):
      if self.link_error:
        raise usb1.USBErrorNoDevice()
      return bytes([self.ltssm])
    assert (request, value, length) == (0xC0, 0, 5)
    if self.power_error:
      raise usb1.USBErrorPipe()
    return struct.pack('<Hh?', *self.supply)

  def close(self):
    self.closed = True


def run(output):
  records = []

  def check(name, action):
    try:
      evidence = action()
      records.append({'scenario': name, 'passed': True, 'evidence': evidence})
    except (AssertionError, RuntimeError) as exc:
      records.append({'scenario': name, 'passed': False, 'error': repr(exc)})

  with tempfile.TemporaryDirectory() as temp:
    sysfs = Path(temp)
    path = sysfs / '4-1'
    path.mkdir()
    (sysfs / 'orientation').write_text('1')

    def fixture(vid, pid, product, manufacturer='tiny', speed=5000):
      values = {'idVendor': f'{vid:04x}', 'idProduct': f'{pid:04x}', 'product': product,
                'manufacturer': manufacturer, 'busnum': '4', 'devnum': '2', 'speed': str(speed)}
      for key, value in values.items():
        (path / key).write_text(value)
      return usb.get_usb_state()

    def updater(devices):
      firmware = hardwared.Chestnut()
      with patch.object(hardwared.threading.Thread, 'start') as start, \
           patch.object(hardwared.subprocess, 'run', side_effect=AssertionError('firmware subprocess forbidden')):
        firmware.update(True, devices)
        firmware.update(False, devices)
        assert firmware.attempts == 0 and not start.called, 'unowned board scheduled automatic firmware write'
      return {'attempts': firmware.attempts, 'scheduled': start.called}

    def identity(vid, pid, product, expected, manufacturer='tiny'):
      devices = fixture(vid, pid, product, manufacturer)
      state = messaging.new_message('deviceState')
      usb.set_usb_state(state.deviceState, devices)
      model_present = helpers.chestnut_present()
      assert state.deviceState.chestnutPresent == expected, state.deviceState.to_dict()
      assert model_present == expected, (product, model_present)
      observed = state.deviceState.usbState.devices[0]
      assert (observed.vendorId, observed.productId, observed.product) == (vid, pid, product)
      flash_state = updater(devices)
      if expected:
        alerts = {}
        current = status.ChestnutStatus()
        current.update(True, 'dev-sp', devices, False, False, None, None,
                       lambda key, value, *args: alerts.update({key: value}))
        current.update(False, 'dev-sp', devices, False, True, None, None,
                       lambda key, value, *args: alerts.update({key: value}))
        assert current.usb_seen and not current.usb_failed, 'status disagrees with modeld runtime identity'
        assert not any(alerts.values()), alerts
      return {'device_state_present': state.deviceState.chestnutPresent, 'modeld_present': model_present,
              'usb_state': observed.to_dict(), 'updater': flash_state}

    with patch.object(usb, 'USB_DEVICES_PATH', sysfs), patch.object(helpers, 'USB_DEVICES_PATH', sysfs), \
         patch.object(usb, 'TYPEC_CC_ORIENTATION_PATH', sysfs / 'orientation'), \
         patch.object(status, 'selected_chestnut_compiled', return_value=True), \
         patch.object(status, 'get_build_metadata', return_value=SimpleNamespace(channel='dev-sp')):
      cases = [
        ('jiayi_ed4', 0x3801, 1, 'custom ed4e39b7-CLEAN', True, 'tiny'),
        ('ut3g_shared_ed4', 0xADD1, 1, 'custom ed4e39b7-CLEAN', True, 'tiny'),
        ('current_official_shared', 0x3801, 1, f'custom {usb.CHESTNUT_FW_VERSION}-CLEAN', True, 'tiny'),
        ('new_8516_runtime', 0xADD1, 1, 'custom 8516b768-CLEAN', True, 'tiny'),
        ('ut3g_dual', 0xADD1, 2, 'custom d1377a01-UT3G-DUAL', True, 'tiny'),
        ('dual_wrong_manufacturer', 0xADD1, 2, 'custom d1377a01-UT3G-DUAL', False, 'unknown'),
        ('dual_dirty', 0xADD1, 2, 'custom d1377a01-UT3G-DUAL-DIRTY', False, 'tiny'),
        ('shared_dirty', 0x3801, 1, 'custom ed4e39b7-DIRTY', False, 'tiny'),
        ('shared_unknown', 0xADD1, 1, 'custom deadbeef-CLEAN', False, 'tiny'),
        ('factory_unknown', 0x2065, 0x0001, 'UT3G factory firmware', False, 'ASMedia'),
        ('rom_2464', 0x174C, 0x2464, 'USB 3.2 PCIe TinyEnclosure', False, 'ASMedia'),
        ('rom_2463', 0x174C, 0x2463, 'AS2462', False, 'ASMedia'),
      ]
      for name, vid, pid, product, expected, manufacturer in cases:
        check(name, lambda v=vid, p=pid, s=product, e=expected, m=manufacturer: identity(v, p, s, e, m))

      for name, vid, pid, product in (
        ('zero_flash_legacy_shared', 0x3801, 1, 'custom ed4e39b7-CLEAN'),
        ('zero_flash_unknown_shared', 0xADD1, 1, 'custom deadbeef-CLEAN'),
        ('zero_flash_dual', 0xADD1, 2, 'custom d1377a01-UT3G-DUAL'),
      ):
        check(name, lambda v=vid, p=pid, s=product: updater(fixture(v, p, s)))

      def health(name, handle, valid, pcie_fault, power_fault):
        msg = monitoring.read_chestnut_state(handle)
        assert msg.valid == valid, (name, msg.to_dict(), handle.calls)
        alerts = {}
        devices = fixture(0xADD1, 2, 'custom d1377a01-UT3G-DUAL')
        current = status.ChestnutStatus()
        for offroad, loading, active in ((False, True, None), (False, False, True), (False, False, True)):
          current.update(offroad, 'dev-sp', devices, False, loading, active,
                         msg.chestnutState if msg.valid else None,
                         lambda key, value, *args: alerts.update({key: value}))
        assert current.pcie_failed == pcie_fault, (name, alerts)
        assert current.power_lost == power_fault, (name, alerts)
        assert (0xC0, 0xE4, 0xB450, 0, 1) in handle.calls, 'B450 was hidden by optional power failure'
        return {'message': msg.to_dict(), 'reads': handle.calls, 'alerts': alerts}

      for name, handle, valid, pcie_fault, power_fault in (
        ('full_telemetry', ReadOnlyHandle(), True, False, False),
        ('no_optional_supply', ReadOnlyHandle(power_error=True), True, False, False),
        ('no_supply_real_link_down', ReadOnlyHandle(power_error=True, ltssm=0), True, True, False),
        ('supply_fault', ReadOnlyHandle(supply=(12000, 1000, True)), True, True, True),
        ('supply_low', ReadOnlyHandle(supply=(4000, 1000, False)), True, True, True),
        ('link_read_error', ReadOnlyHandle(link_error=True), False, False, False),
      ):
        check(name, lambda n=name, h=handle, v=valid, p=pcie_fault, s=power_fault: health(n, h, v, p, s))

      def monitor_discovery():
        fixture(0xADD1, 2, 'custom d1377a01-UT3G-DUAL')
        stop = SimpleNamespace(stopped=False)
        stop.is_set = lambda: stop.stopped
        stop.wait = lambda _: setattr(stop, 'stopped', True)
        handle = ReadOnlyHandle(power_error=True)
        published, opened = [], []
        context = SimpleNamespace(openByVendorIDAndProductID=lambda vid, pid, **_: opened.append((vid, pid)) or handle)
        class Context:
          def __enter__(self):
            return context

          def __exit__(self, *args):
            return False

        sm = SimpleNamespace(update=lambda _: None, alive={'chestnutGpuState': False},
                             valid={'chestnutGpuState': False}, seen={'chestnutGpuState': False})
        with patch.object(monitoring.usb1, 'USBContext', Context), \
             patch.object(monitoring.messaging, 'PubMaster', return_value=SimpleNamespace(send=lambda service, msg: published.append(msg))), \
             patch.object(monitoring.messaging, 'SubMaster', return_value=sm):
          monitoring.chestnut_state_thread(stop)
        assert opened == [(0xADD1, 2)], opened
        assert len(published) == 1 and published[0].valid and handle.closed
        return {'opened_vid_pid': opened, 'published_valid': published[0].valid, 'handle_closed': handle.closed}

      check('production_monitor_discovery_dual', monitor_discovery)

      def compile_link_probe(vid, pid, product, ready):
        fixture(vid, pid, product)
        requests = []

        def ioctl(fd, operation, control):
          assert fd == 123 and operation == flash.USBDEVFS_CONTROL
          requests.append((control.request_type, control.request, control.value, control.length))
          if control.request_type == 0xC0:
            assert (control.request, control.value, control.length) == (0xE4, 0xB450, 1)
            ctypes.cast(control.data, ctypes.POINTER(ctypes.c_ubyte))[0] = 0x78
          else:
            assert (control.request_type, control.request, control.value, control.length) == (0x40, 0xF3, 1, 0), 'only transient power is allowed'

        with patch.object(flash.glob, 'glob', return_value=[str(path)]), \
             patch.object(flash, 'open_device', return_value=123), patch.object(flash.os, 'close'), \
             patch.object(flash.fcntl, 'ioctl', side_effect=ioctl):
          manual_path, _, _ = flash.find_chestnut()
          if pid == 2:
            assert manual_path is None, 'runtime device leaked into persistent flasher discovery'
          assert flash.link_up() == ready, (vid, pid, product, requests)
        assert bool(requests) == ready, 'unsupported firmware reached the runtime power/link probe'
        return {'ready': ready, 'manual_flasher_path': manual_path, 'stubbed_usb_requests': requests}

      for name, vid, pid, product, ready in (
        ('compile_dual_runtime_only', 0xADD1, 2, 'custom d1377a01-UT3G-DUAL', True),
        ('compile_legacy_shared', 0x3801, 1, 'custom ed4e39b7-CLEAN', True),
        ('compile_unknown_rejected', 0x3801, 1, 'custom deadbeef-CLEAN', False),
        ('compile_dirty_dual_rejected', 0xADD1, 2, 'custom d1377a01-UT3G-DUAL-DIRTY', False),
      ):
        check(name, lambda v=vid, p=pid, s=product, r=ready: compile_link_probe(v, p, s, r))

  def runtime_enumeration():
    seen = []
    marker = object()

    def enumerate_usb(vid, pid):
      seen.append((vid, pid))
      return [(marker, 'usb:4-2')] if (vid, pid) == (0xADD1, 2) else []

    with patch.object(ops_amd.USB3, 'list_devices', side_effect=enumerate_usb), \
         patch.object(ops_amd, 'USBPCIDevice', return_value=marker) as opened, \
         patch.object(ops_amd, 'AMDev', return_value=marker), patch.object(ops_amd.USBIface, '_compute_props'):
      iface = ops_amd.USBIface(SimpleNamespace(device='AMD'), 0)
      assert iface.pci_dev is marker and iface.count == 1
      opened.assert_called_once_with('AM', marker, 'usb:4-2')
    assert (0xADD1, 2) in seen
    assert ('add1', '0002') not in flash.VID_PIDS, 'runtime PID leaked into explicit official flasher'
    return {'enumerated_vid_pids': seen, 'physical_device_open_stubbed': True, 'manual_flasher_excludes_dual': True}

  check('actual_tinygrad_usbi_constructor', runtime_enumeration)
  root = Path(__file__).resolve().parents[2]
  paths = [Path(module.__file__) for module in (usb, helpers, hardwared, monitoring, status, flash, ops_amd)]
  result = {'passed': all(case['passed'] for case in records),
            'scope': 'host production call chains with temporary sysfs, real Capnp, read-only USB boundary fixtures; no physical hardware',
            'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}, 'cases': records}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(result, indent=2) + '\n')
  print(json.dumps({'passed': result['passed'], 'cases': len(records), 'failed': [r['scenario'] for r in records if not r['passed']],
                    'output': str(output)}))
  return result['passed']


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', required=True, type=Path)
  raise SystemExit(not run(parser.parse_args().output))
