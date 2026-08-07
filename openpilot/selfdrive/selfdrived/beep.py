#!/usr/bin/env python3
import subprocess
import time
from opendbc.car.structs import car
import openpilot.cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper
import threading

AudibleAlert = car.CarControl.HUDControl.AudibleAlert
BEEP_PULSE_SECONDS = 0.001
BEEP_GAP_SECONDS = 0.02

class Beepd:
  def __init__(self):
    self.current_alert = AudibleAlert.none
    self.mads_enabled = None
    # timestamp until which promptRepeat should be suppressed
    self.prompt_suppress_until = 0
    self.enable_gpio()
    #self.startup_beep()

  def enable_gpio(self):
    # 尝试 export，忽略已 export 的错误
    try:
      subprocess.run("echo 42 | sudo tee /sys/class/gpio/export",
                     shell=True,
                     stderr=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     encoding='utf8')
    except Exception:
      pass
    subprocess.run("echo \"out\" | sudo tee /sys/class/gpio/gpio42/direction",
                   shell=True,
                   stderr=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,
                   encoding='utf8')

  def _beep(self, on):
    val = "1" if on else "0"
    subprocess.run(f"echo \"{val}\" | sudo tee /sys/class/gpio/gpio42/value",
                   shell=True,
                   stderr=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,
                   encoding='utf8')

  def engage(self):
    self._beep(True)
    time.sleep(BEEP_PULSE_SECONDS)
    self._beep(False)

  def disengage(self):
    for pulse in range(2):
      self._beep(True)
      time.sleep(BEEP_PULSE_SECONDS)
      self._beep(False)
      if pulse == 0:
        time.sleep(BEEP_GAP_SECONDS)

  def warning(self):
    for pulse in range(3):
      self._beep(True)
      time.sleep(BEEP_PULSE_SECONDS)
      self._beep(False)
      if pulse < 2:
        time.sleep(BEEP_GAP_SECONDS)

  #def startup_beep(self):
    #self._beep(True)
    #time.sleep(0.1)
    #self._beep(False)

  def dispatch_beep(self, func):
    threading.Thread(target=func, daemon=True).start()

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

  def update_mads(self, enabled):
    if self.mads_enabled is None:
      self.mads_enabled = enabled
      return

    if enabled != self.mads_enabled:
      self.mads_enabled = enabled
      self.dispatch_beep(self.engage if enabled else self.disengage)

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

    sm = messaging.SubMaster(['selfdriveState', 'selfdriveStateSP'])
    rk = Ratekeeper(20)

    while True:
      sm.update(0)
      self.get_audible_alert(sm)
      rk.keep_time()

def main():
  s = Beepd()
  s.beepd_thread(test=False)  # 改成 True 可启用模拟测试数据

if __name__ == "__main__":
  main()
