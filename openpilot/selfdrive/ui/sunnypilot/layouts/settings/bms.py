"""Read-only battery dashboard replacing Trips. No CAN publication or UDS requests."""
import time
import pyray as rl

from openpilot.cereal import messaging
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.sunnypilot.selfdrive.car.tesla.bms import BmsState
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.button import Button, ButtonStyle


class BmsLayout(Widget):
  def __init__(self):
    super().__init__()
    self.state = BmsState()
    self.sock = None
    self.supported = False
    self._visible = False
    self._car_fingerprint = None
    self.page = 0
    self._display = (float('-inf'), None, None)
    self.tabs = [Button(label, click_callback=lambda index=i: self._select_page(index), font_size=42)
                 for i, label in enumerate(('概览', '电芯', '诊断'))]
    for tab in self.tabs:
      self._child(tab)

  def show_event(self):
    super().show_event()
    self._visible = True
    self.state = BmsState()
    self._sync_subscription()

  def hide_event(self):
    self._visible = False
    self.sock = None
    self._car_fingerprint = None
    self.supported = False
    self.state = BmsState()
    super().hide_event()

  def _sync_subscription(self):
    cp = ui_state.CP
    fingerprint = cp.carFingerprint if cp is not None and cp.brand == 'tesla' and any(
      model in cp.carFingerprint for model in ('MODEL_3', 'MODEL_Y')) else None
    if fingerprint != self._car_fingerprint:
      self.state = BmsState()
      self.sock = None
      self._car_fingerprint = fingerprint
    self.supported = fingerprint is not None
    if self._visible and self.supported and self.sock is None:
      self.sock = messaging.sub_sock('can', timeout=0)

  def _update_state(self):
    super()._update_state()
    if self._visible:
      self._sync_subscription()
    if self.sock is None:
      return
    now = time.monotonic()
    for _ in range(200):  # bounded UI work; timestamp is the message's monotonic time
      msg = messaging.recv_one_or_none(self.sock)
      if msg is None:
        break
      timestamp = msg.logMonoTime * 1e-9
      if not msg.valid or not 0 <= now - timestamp <= 3:
        continue
      for frame in msg.can:
        self.state.update(frame.address, bytes(frame.dat), frame.src, timestamp)
    sm = ui_state.sm
    self.state.integrate(now, sm['carState'].vEgo if sm.alive['carState'] and sm.valid['carState'] else None)

  def _display_data(self, now):
    # 2 Hz text refresh; 100 Hz values redrawn every frame read as flicker.
    shown_at, state, data = self._display
    if state is not self.state or not 0 <= now - shown_at < .5:
      self._display = (now, self.state, self.state.snapshot(now))
    return self._display[2]

  def _select_page(self, index):
    self.page = index

  @staticmethod
  def _text(text, x, y, size, color, bold=False):
    font = gui_app.font(FontWeight.BOLD if bold else FontWeight.NORMAL)
    if text.isascii():
      # Keep large digits on the 200px Inter atlas instead of upscaling the 48px CJK fallback.
      rl._orig_draw_text_ex(font, text, rl.Vector2(x, y), size*FONT_SCALE, 0, color)
    else:
      rl.draw_text_ex(font, text, rl.Vector2(x, y), size, 0, color)

  def _card(self, rect, label, value, unit, precision=1, primary=False, note=None):
    scale = self.scale
    color = rl.Color(23, 47, 43, 255) if primary else rl.Color(28, 33, 42, 255)
    rl.draw_rectangle_rounded(rect, .08, 12, color)
    x, y = rect.x+28*scale, rect.y+22*scale
    self._text(label, x, y, 40*scale, self.muted)
    number = '—' if value is None else f'{value:.{precision}f}'
    size = (144 if primary else 88)*scale
    self._text(number, x, y+57*scale, size, self.white, True)
    # ASCII units use the Inter atlas in _text, not the language fallback.
    unit_width = rl.measure_text_ex(gui_app.font(), unit, 36*scale*FONT_SCALE, 0).x  # noqa: TID251
    self._text(unit, rect.x+rect.width-unit_width-28*scale, rect.y+rect.height-52*scale,
               36*scale, self.accent if primary else self.muted)
    if note:
      self._text(note, x, rect.y+rect.height-57*scale, 34*scale, self.muted)

  def _render(self, rect):
    now = time.monotonic()
    data = self._display_data(now)
    self.scale = min(1., rect.width/1560, rect.height/1030)
    s = self.scale
    self.white, self.muted = rl.Color(245, 247, 250, 255), rl.Color(176, 186, 201, 255)
    self.accent, amber = rl.Color(98, 229, 181, 255), rl.Color(255, 194, 94, 255)
    rl.draw_rectangle_rounded(rect, .025, 12, rl.Color(13, 16, 22, 255))
    x, y, w = rect.x+20*s, rect.y+16*s, rect.width-40*s
    self._text('电池与能耗', x, y, 56*s, self.white, True)
    fresh = any(v is not None for v in data.values())
    status = ('实时数据' if fresh else '等待车辆数据') if self.supported else '仅支持 Model 3 / Y'
    sw = measure_text_cached(gui_app.font(), status, 34*s).x
    self._text(status, x+w-sw, y+15*s, 34*s, self.accent if fresh else amber)
    gap = 20*s
    for i, tab in enumerate(self.tabs):
      tab.set_button_style(ButtonStyle.PRIMARY if i==self.page else ButtonStyle.NORMAL)
      tab.render(rl.Rectangle(x+i*(w+gap)/3, y+83*s, (w-2*gap)/3, 76*s))
    top = y+184*s
    half = (w-gap)/2
    cs_fresh = ui_state.sm.alive['carState'] and ui_state.sm.valid['carState']
    cs = ui_state.sm['carState']
    speed = cs.vEgo*3.6 if cs_fresh else None
    delta = None if data['cell_min'] is None or data['cell_max'] is None else (data['cell_max']-data['cell_min'])*1000
    if self.page == 0:
      if data['soc_display'] is not None:
        self._card(rl.Rectangle(x, top, half, 310*s), '剩余电量 · SOC', data['soc_display'], '%', 0, True,
                   f"BMS {data['soc']:.1f}%")
      else:
        self._card(rl.Rectangle(x, top, half, 310*s), '剩余电量 · SOC', data['soc'], '%', 1, True)
      self._card(rl.Rectangle(x+half+gap, top, half, 310*s), '平均能耗', data['consumption'], 'Wh/km', 0, True,
                 '近 2 km 滑动平均')
      third = (w-2*gap)/3
      for i, (label, key, unit, digits) in enumerate([('电池功率', 'power', 'kW', 1),
                                                     ('电池电压', 'voltage', 'V', 1), ('电池电流', 'current', 'A', 1)]):
        self._card(rl.Rectangle(x+i*(third+gap), top+330*s, third, 204*s), label, data[key], unit, digits)
      self._card(rl.Rectangle(x, top+554*s, half, 190*s), '剩余电量', data['remaining'], 'kWh')
      self._card(rl.Rectangle(x+half+gap, top+554*s, half, 190*s), 'BMS 估算满充容量', data['capacity'], 'kWh')
      self._text('正值为耗电，负值为能量回收。能耗为近 2 km 平均值。', x, top+775*s, 34*s, self.muted)
    elif self.page == 1:
      temp_delta = None if data['temp_min'] is None or data['temp_max'] is None else data['temp_max']-data['temp_min']
      cards = [('最低电芯温度', data['temp_min'], '°C', 1), ('最高电芯温度', data['temp_max'], '°C', 1),
               ('最低单体电压', data['cell_min'], 'V', 3), ('最高单体电压', data['cell_max'], 'V', 3),
               ('电芯温差', temp_delta, '°C', 1), ('单体电压差', delta, 'mV', 0)]
      for i, (label, value, unit, digits) in enumerate(cards):
        self._card(rl.Rectangle(x+(i%2)*(half+gap), top+(i//2)*250*s, half, 230*s), label, value, unit, digits)
      self._text('过期或不可信的数据不显示；数值不等同于电池健康结论。', x, top+770*s, 32*s, self.muted)
    else:
      cards = [('累计充入', data['charged'], 'kWh'), ('累计放出', data['discharged'], 'kWh'),
               ('实时车速', speed, 'km/h'), ('方向盘转角', cs.steeringAngleDeg if cs_fresh else None, '°')]
      for i, (label, value, unit) in enumerate(cards):
        self._card(rl.Rectangle(x+(i%2)*(half+gap), top+(i//2)*214*s, half, 194*s), label, value, unit)
      warnings = [label for key, label in [('drive_power_low', '驱动供电不足'), ('support_power_low', '辅助供电不足')] if data[key] == 1]
      status = ' / '.join(warnings) if warnings else ('供电告警位：未置位' if data['drive_power_low'] is not None else '供电状态：等待数据')
      self._text(status, x+10*s, top+451*s, 40*s, amber if warnings else self.white)
      brake = ('已踩下' if cs.brakePressed else '未踩下') if cs_fresh else '等待数据'
      self._text('制动踏板：'+brake, x+10*s, top+507*s, 36*s, self.muted)
      from openpilot.sunnypilot.selfdrive.car.tesla.bms import FRAME_LENGTHS
      for i, address in enumerate(FRAME_LENGTHS):
        item = self.state.frames.get(address)
        active = item is not None and 0<=now-item[1]<=3
        label = '在线' if active else ('已过期' if item else '未收到')
        bx, by = x+(i%4)*(w+gap)/4, top+579*s+(i//4)*82*s
        rw = (w-3*gap)/4
        rl.draw_rectangle_rounded(rl.Rectangle(bx, by, rw, 65*s), .15, 8, rl.Color(28,33,42,255))
        self._text(f'{address:03X}  ·  {label}', bx+20*s, by+12*s, 34*s, self.accent if active else self.muted)
      self._text('只读监测 · 不发送 CAN 指令，不执行故障码扫描。', x, top+777*s, 32*s, self.muted)
