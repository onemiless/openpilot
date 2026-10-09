#!/usr/bin/env python3
import os
import queue
import subprocess
import threading
import time
from opendbc.car.structs import car
import openpilot.cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper
from openpilot.sunnypilot.hardware.profile import HardwareProfile, get_hardware_profile
from openpilot.sunnypilot.navassist.settings import SettingsCache

AudibleAlert = car.CarControl.HUDControl.AudibleAlert
BEEP_PULSE_SECONDS = 0.010
BEEP_GAP_SECONDS = 0.02
GPIO_PIN = 42
GPIO_VALUE_PATH = f"/sys/class/gpio/gpio{GPIO_PIN}/value"

class Beepd:
  def __init__(self):
    self.current_alert = AudibleAlert.none
    self.mads_enabled = None
    self.maneuver_initialized = False
    self.maneuver_action = None
    self.maneuver_pending_until = 0.0
    self.settings_cache = SettingsCache()
    # timestamp until which promptRepeat should be suppressed
    self.prompt_suppress_until = 0
    self.beep_lock = threading.Lock()
    self.gpio_fd = None
    self.beep_queue: queue.Queue = queue.Queue(maxsize=8)
    self.worker = threading.Thread(target=self._worker, daemon=True)
    self.worker.start()
    # Never probe an unknown device's GPIO. The manager parameter is only an
    # enable switch; the hardware profile is the compatibility authority.
    if get_hardware_profile() == HardwareProfile.C3XL:
      self.enable_gpio()

  def enable_gpio(self):
    # GPIO setup may require root, but pulse edges must not spawn processes:
    # their startup latency would dominate a sub-millisecond beep.
    try:
      subprocess.run(["sudo", "tee", "/sys/class/gpio/export"], input=str(GPIO_PIN),
                     stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, text=True, check=False)
      subprocess.run(["sudo", "tee", f"/sys/class/gpio/gpio{GPIO_PIN}/direction"], input="out",
                     stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, text=True, check=False)
      subprocess.run(["sudo", "chmod", "0666", GPIO_VALUE_PATH],
                     stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)
      self.gpio_fd = os.open(GPIO_VALUE_PATH, os.O_WRONLY | os.O_CLOEXEC)
      self._beep(False)
    except OSError as error:
      print(f"[BEEP] GPIO initialization failed: {error}", flush=True)
      if self.gpio_fd is not None:
        os.close(self.gpio_fd)
      self.gpio_fd = None

  def _beep(self, on):
    if self.gpio_fd is None:
      raise OSError("buzzer GPIO unavailable")
    os.lseek(self.gpio_fd, 0, os.SEEK_SET)
    if os.write(self.gpio_fd, b"1" if on else b"0") != 1:
      raise OSError("short buzzer GPIO write")

  def _worker(self):
    while True:
      func = self.beep_queue.get()
      try:
        func()
        print("[BEEP] output complete", flush=True)
      except Exception as error:
        # A failed edge must not kill all subsequent warnings. Do not replay a
        # partially emitted pulse; keep evidence for a parked hardware check.
        print(f"[BEEP] output failed: {type(error).__name__}: {error}", flush=True)
      finally:
        self.beep_queue.task_done()

  def _pulse_sequence(self, count):
    def run_sequence():
      for pulse in range(count):
        try:
          self._beep(True)
          time.sleep(BEEP_PULSE_SECONDS)
        finally:
          self._beep(False)
        if pulse < count - 1:
          time.sleep(BEEP_GAP_SECONDS)

    lock = getattr(self, "beep_lock", None)
    if lock is None:
      run_sequence()
    else:
      with lock:
        run_sequence()

  def engage(self):
    self._pulse_sequence(1)

  def disengage(self):
    self._pulse_sequence(2)

  def warning(self):
    self._pulse_sequence(3)

  #def startup_beep(self):
    #self._beep(True)
    #time.sleep(0.1)
    #self._beep(False)

  def dispatch_beep(self, func):
    try:
      self.beep_queue.put_nowait(func)
      print("[BEEP] queued", flush=True)
      return True
    except queue.Full:
      # Alerts are edge notifications. Do not build an unbounded delayed queue.
      print("[BEEP] queue full", flush=True)
      return False

  def close(self):
    if self.gpio_fd is not None:
      try:
        self._beep(False)
      finally:
        os.close(self.gpio_fd)
        self.gpio_fd = None

  def update_alert(self, new_alert):
    now = time.monotonic()
    if new_alert != self.current_alert:
      self.current_alert = new_alert
      print(f"[BEEP] New alert: {new_alert}")
      #if new_alert == AudibleAlert.engage:
        #self.dispatch_beep(self.engage)
      #elif new_alert == AudibleAlert.disengage:
        #self.dispatch_beep(self.disengage)
      if new_alert in [AudibleAlert.warningSoft, AudibleAlert.warningImmediate]:
        self.dispatch_beep(self.warning)
      elif new_alert == AudibleAlert.promptRepeat:
        # 如果在抑制期内则忽略后续的 promptRepeat
        if now >= getattr(self, 'prompt_suppress_until', 0):
          # 设置抑制期（秒），在这段时间内忽略重复的 promptRepeat
          self.prompt_suppress_until = now + 10
          self.dispatch_beep(self.engage)
        else:
          print(f"[BEEP] promptRepeat suppressed until {self.prompt_suppress_until}")

  def get_audible_alert(self, sm):
    if sm.updated['selfdriveState']:
      new_alert = sm['selfdriveState'].alertSound.raw
      self.update_alert(new_alert)

    if sm.updated['selfdriveStateSP']:
      self.update_mads(bool(sm['selfdriveStateSP'].mads.enabled))

    if sm.updated['modelV2'] or sm.updated['modelDataV2SP']:
      self.update_maneuver(
        sm['modelV2'].meta, sm['modelDataV2SP'],
        enabled=self.settings_cache.read().lane_change_buzzer_enabled,
        healthy=sm.all_checks(['modelV2', 'modelDataV2SP', 'carControl']) and bool(sm['carControl'].latActive),
      )

  def update_mads(self, enabled):
    if self.mads_enabled is None:
      self.mads_enabled = enabled
      return

    if enabled != self.mads_enabled:
      self.mads_enabled = enabled
      self.dispatch_beep(self.engage if enabled else self.disengage)

  def update_maneuver(self, meta, turn, *, enabled, healthy):
    if not healthy:
      self.maneuver_initialized = False
      self.maneuver_action = None
      self.maneuver_pending_until = 0.0
      return
    lane_state = int(meta.laneChangeState.raw)
    lane_direction = int(meta.laneChangeDirection.raw)
    turn_direction = int(turn.laneTurnDirection.raw)
    action = None
    # Starting=2, finishing=3. Keeping the action through finishing prevents
    # duplicate pulses. This also covers ordinary blinker-led lane changes.
    if lane_state in (2, 3) and lane_direction in (1, 2):
      action = ('lane', lane_direction)
    elif turn.turnDecisionReason == 'turnActive' and turn_direction in (1, 2):
      action = ('turn', turn_direction)
    if not self.maneuver_initialized:
      self.maneuver_initialized = True
      self.maneuver_action = action
      return  # Do not announce an action already active at process startup.
    now = time.monotonic()
    if action != self.maneuver_action:
      self.maneuver_action = action
      self.maneuver_pending_until = now + 0.5 if action is not None and enabled else 0.0
      if action is not None:
        print(f"[BEEP] maneuver start: {action}, enabled={enabled}", flush=True)
    if not enabled or action is None:
      self.maneuver_pending_until = 0.0
    elif now < self.maneuver_pending_until:
      if self.dispatch_beep(self.engage):
        self.maneuver_pending_until = 0.0

  def test_beepd_thread(self):
    frame = 0
    rk = Ratekeeper(20)
    pm = messaging.PubMaster(['selfdriveState'])
    while True:
      cs = messaging.new_message('selfdriveState')
      if frame == 20:
        cs.selfdriveState.alertSound = AudibleAlert.engage
      if frame == 40:
        cs.selfdriveState.alertSound = AudibleAlert.disengage
      if frame == 60:
        cs.selfdriveState.alertSound = AudibleAlert.prompt
      if frame == 80:
        cs.selfdriveState.alertSound = AudibleAlert.disengage
      if frame == 85:
        cs.selfdriveState.alertSound = AudibleAlert.prompt

      pm.send("selfdriveState", cs)
      frame += 1
      rk.keep_time()

  def beepd_thread(self, test=False):
    if test:
      threading.Thread(target=self.test_beepd_thread, daemon=True).start()

    sm = messaging.SubMaster(['selfdriveState', 'selfdriveStateSP', 'modelV2', 'modelDataV2SP', 'carControl'], frequency=20)
    rk = Ratekeeper(20)

    while True:
      sm.update(0)
      self.get_audible_alert(sm)
      rk.keep_time()

def main():
  s = Beepd()
  try:
    s.beepd_thread(test=False)
  finally:
    s.close()

if __name__ == "__main__":
  main()
