#!/usr/bin/env python3
"""Headless renderer/Params E2E for Tesla display fixes; CAN stays in memory."""
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ['OPENPILOT_PREFIX'] = 'sp-tdisplay-' + uuid.uuid4().hex[:10]
os.environ.setdefault('BIG', '0')
os.environ.setdefault('SCALE', '1')
from openpilot.common.prefix import OpenpilotPrefix

prefix = OpenpilotPrefix(prefix=os.environ['OPENPILOT_PREFIX'])
prefix.__enter__()

from openpilot.cereal import messaging
from opendbc.car import structs
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.sunnypilot.layouts.settings import bms as bms_module
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.bms import BmsLayout
from openpilot.selfdrive.ui.sunnypilot.layouts.home import HomeLayoutSP
from openpilot.selfdrive.ui.layouts.home import HomeLayoutState
from openpilot.selfdrive.selfdrived.alertmanager import set_offroad_alert
from openpilot.selfdrive.ui.onroad.alert_renderer import AlertRenderer as C3AlertRenderer
from openpilot.selfdrive.ui.mici.onroad.alert_renderer import AlertRenderer as MiciAlertRenderer
from openpilot.system.ui.lib.multilang import multilang
from openpilot.system.ui.lib.application import gui_app

OUT = Path('artifacts/sp-tesla-migration/tesla-display-e2e.json')
OUT.parent.mkdir(parents=True, exist_ok=True)
failures = []
results = []


def check(name, condition, detail=''):
  results.append({'case': name, 'passed': bool(condition), 'detail': detail})
  if not condition:
    failures.append(name)


class FakeSubMaster:
  def __init__(self, state):
    self.state = state
    self.updated = {'selfdriveState': True}
    self.recv_frame = {'selfdriveState': 1}

  def __getitem__(self, key):
    return self.state


class FakeCanSocket:
  def __init__(self):
    self.queue = []
    self.closed = False

  def receive(self, non_blocking=False):
    return self.queue.pop(0) if self.queue else None


try:
  gui_app.init_window('Tesla display E2E', fps=10)
  ui_state.params.remove('CarParamsPersistent')
  ui_state.CP = None
  ui_state.started_frame = 0
  ui_state.started_time = 0
  multilang.change_language('zh-CHS')

  alert_msg = messaging.new_message('selfdriveState').selfdriveState
  alert_msg.alertText1 = 'Camera Malfunction'
  alert_msg.alertText2 = 'Door Open'
  alert_msg.alertSize = 2
  alert_msg.alertStatus = 2
  alert_msg.alertType = 'cameraMalfunction/permanent'
  alert_msg.alertHudVisual = 0
  sm = FakeSubMaster(alert_msg)
  for name, renderer_type in (('c3-alert', C3AlertRenderer), ('mici-alert', MiciAlertRenderer)):
    alert = renderer_type.__new__(renderer_type).get_alert(sm)
    fields_ok = (alert.text1 == '相机故障' and alert.text2 == '车门未关好' and
                 alert.size == alert_msg.alertSize.raw and alert.status == alert_msg.alertStatus.raw)
    if name == 'mici-alert':
      fields_ok = fields_ok and alert.visual_alert == alert_msg.alertHudVisual and alert.alert_type == alert_msg.alertType
    check(name, fields_ok, f'text=({alert.text1!r}, {alert.text2!r}), size/status={alert.size}/{alert.status}')

  sockets = []

  def new_can_socket(service, **kwargs):
    assert service == 'can' and kwargs.get('timeout') == 0
    sock = FakeCanSocket()
    sockets.append(sock)
    return sock

  def write_car_params(fingerprint=None, brand='tesla'):
    if fingerprint is None:
      ui_state.params.remove('CarParamsPersistent')
      ui_state.CP = None
    else:
      cp = structs.CarParams.new_message()
      cp.brand = brand
      cp.carFingerprint = fingerprint
      ui_state.params.put('CarParamsPersistent', cp.to_bytes(), block=True)
      ui_state.update_params()

  with patch.object(messaging, 'sub_sock', side_effect=new_can_socket):
    layout = BmsLayout()
    write_car_params()
    layout.show_event()
    layout._update_state()
    check('missing-cp-does-not-subscribe', layout.sock is None and not sockets)

    write_car_params('TESLA_MODEL_3')
    layout._update_state()
    late_cp_ok = layout.sock is not None and len(sockets) == 1
    check('late-tesla-cp-subscribes-while-visible', late_cp_ok)

    can_msg = messaging.new_message('can', 1)
    can_msg.valid = True
    can_msg.logMonoTime = int(__import__('time').monotonic() * 1e9)
    frame = can_msg.can[0]
    frame.address = 0x292
    frame.src = 1
    frame.dat = (500 << 10).to_bytes(8, 'little')
    if layout.sock is None:
      sockets.append(FakeCanSocket())
      layout.sock = sockets[-1]  # Keep exercising the real parser after recording the expected baseline failure.
    layout.sock.queue.append(can_msg.to_bytes())
    layout._update_state()
    saw_soc = layout.state.snapshot(__import__('time').monotonic())['soc'] == 50.0
    check('can-message-reaches-bms-state', saw_soc, repr(layout.state.snapshot(__import__('time').monotonic())))

    # Display behavior on a fake clock local to the BMS module: 100 Hz 0x132 ripple, screen SOC, average consumption.
    clock = [1000.0]
    fake_time = SimpleNamespace(monotonic=lambda: clock[0])

    class CarStateSM:
      alive = valid = {'carState': True}

      def __getitem__(self, key):
        return SimpleNamespace(vEgo=20.0, steeringAngleDeg=0., brakePressed=False)

    def push(frames):
      msg = messaging.new_message('can', len(frames))
      msg.valid = True
      msg.logMonoTime = int(clock[0] * 1e9)
      for f, (address, dat) in zip(msg.can, frames, strict=True):
        f.address, f.src, f.dat = address, 1, dat
      layout.sock.queue.append(msg.to_bytes())

    def hv(volts, amps):  # 0x132 current is negative for discharge
      return round(volts * 100).to_bytes(2, 'little') + round(-amps * 10).to_bytes(2, 'little', signed=True)

    display = getattr(layout, '_display_data', lambda now: layout.state.snapshot(now))
    shown = []
    with patch.object(bms_module, 'time', fake_time), patch.object(ui_state, 'sm', CarStateSM()):
      for step in range(300):
        ripple = 1 if step % 2 else -1
        frames = [(0x132, hv(400 + 5 * ripple, 50 + 20 * ripple))]
        if step % 50 == 0:
          frames += [(0x292, (803 << 10).to_bytes(8, 'little')), (0x33A, (80 << 48).to_bytes(8, 'little'))]
        push(frames)
        layout._update_state()
        shown.append(display(clock[0]))
        clock[0] += .01
      last = shown[-1]
      volts = [d['voltage'] for d in shown[-100:]]
      check('bms-display-does-not-jitter', None not in volts and len({round(v, 1) for v in volts}) <= 3 and
            abs(last['voltage'] - 400) < 1 and abs(last['current'] - 50) < 2 and abs(last['power'] - 20) < 1,
            f'last-second voltages={sorted({round(v, 1) for v in volts if v is not None})}, last={last}')
      check('soc-matches-screen-ui-soc', last.get('soc_display') == 80 and abs(last['soc'] - 80.3) < .01, repr(last))
      consumption = last.get('consumption')
      check('average-consumption-shown', consumption is not None and 250 < consumption < 305, repr(consumption))

      push([(0x33A, (30 << 48).to_bytes(8, 'little'))])
      layout._update_state()
      clock[0] += .6
      check('implausible-ui-soc-rejected', display(clock[0]).get('soc_display') is None, repr(display(clock[0])))

      clock[0] += 4
      layout._update_state()
      check('stale-bms-values-clear', display(clock[0])['voltage'] is None, repr(display(clock[0])))
    layout.state = bms_module.BmsState()

    prior_sock = layout.sock
    write_car_params('TESLA_MODEL_Y')
    layout._update_state()
    switched_ok = layout.sock is not None and layout.sock is not prior_sock and len(sockets) == 2 and not layout.state.values
    check('supported-car-change-clears-old-readings', switched_ok)

    write_car_params('HONDA CIVIC', brand='honda')
    layout._update_state()
    unsupported_ok = layout.sock is None and not layout.state.values
    check('unsupported-car-releases-and-clears', unsupported_ok)

    layout.hide_event()
    write_car_params('TESLA_MODEL_3')
    layout._update_state()
    check('hidden-page-does-not-subscribe', layout.sock is None)

    layout.show_event()
    check('reopen-uses-latest-supported-car', layout.sock is not None and len(sockets) == 3)
    layout.hide_event()
    check('hide-releases-subscription', layout.sock is None)

  # Home page must not pop offroad alerts, except the excessive-actuation acknowledgement that gates engagement.
  set_offroad_alert('Offroad_TemperatureTooHigh', True, extra_text='99C')
  home = HomeLayoutSP()
  home._refresh()
  check('home-hides-offroad-alerts', home.current_state == HomeLayoutState.HOME and home.alert_count == 0,
        f'state={home.current_state}, count={home.alert_count}')
  set_offroad_alert('Offroad_ExcessiveActuation', True, extra_text='longitudinal')
  home._refresh()
  check('home-keeps-excessive-actuation-ack', home.current_state == HomeLayoutState.ALERTS,
        f'state={home.current_state}, count={home.alert_count}')

  OUT.write_text(json.dumps({
    'scope': 'actual UI renderers, BmsLayout, HomeLayoutSP and UIState Params integration; in-memory passive CAN only',
    'language': multilang.language,
    'cases': results,
    'failures': failures,
  }, indent=2, ensure_ascii=False) + '\n')
  print(OUT)
  print(json.dumps({'passed': len(results) - len(failures), 'total': len(results), 'failures': failures}))
  if failures:
    raise SystemExit(1)
finally:
  gui_app.close()
  prefix.__exit__(None, None, None)
