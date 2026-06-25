#!/usr/bin/env python3
import subprocess
import time
from cereal import car, messaging
from openpilot.common.realtime import Ratekeeper
import threading

AudibleAlert = car.CarControl.HUDControl.AudibleAlert

ALERTS_ALWAYS_PLAY = {
  AudibleAlert.engage,
  AudibleAlert.disengage,
  AudibleAlert.warningSoft,
  AudibleAlert.warningImmediate,
  AudibleAlert.promptDistracted,
  AudibleAlert.promptRepeat,
}

class Beepd:
  def __init__(self):
    self.current_alert = AudibleAlert.none
    self.beep_thread = None
    self.prompt_suppress_until = 0
    self.enable_gpio()
    #self.startup_beep()

  def _write_gpio(self, path, value, timeout=0.5):
    try:
      with open(path, "w") as f:
        f.write(value)
      return
    except Exception:
      pass

    subprocess.run(
      ["sudo", "sh", "-c", f"printf '%s' '{value}' > {path}"],
      stderr=subprocess.DEVNULL,
      stdout=subprocess.DEVNULL,
      timeout=timeout,
      check=False,
    )

  def enable_gpio(self):
    # 尝试 export，忽略已 export 的错误
    try:
      self._write_gpio("/sys/class/gpio/export", "42", timeout=1.0)
    except Exception:
      pass
    try:
      self._write_gpio("/sys/class/gpio/gpio42/direction", "out", timeout=1.0)
    except Exception:
      pass

  def _beep(self, on):
    val = "1" if on else "0"
    try:
      self._write_gpio("/sys/class/gpio/gpio42/value", val)
    except Exception:
      pass

  def engage(self):
    self._beep(True)
    time.sleep(0.05)
    self._beep(False)

  def disengage(self):
    for _ in range(2):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  def warning(self):
    for _ in range(3):
      self._beep(True)
      time.sleep(0.01)
      self._beep(False)
      time.sleep(0.01)

  #def startup_beep(self):
    #self._beep(True)
    #time.sleep(0.1)
    #self._beep(False)

  def dispatch_beep(self, func):
    if self.beep_thread is not None and self.beep_thread.is_alive():
      return
    self.beep_thread = threading.Thread(target=func, daemon=True)
    self.beep_thread.start()

  def update_alert(self, new_alert):
    now = time.time()
    if new_alert != self.current_alert:
      self.current_alert = new_alert
      print(f"[BEEP] New alert: {new_alert}")
      if new_alert in ALERTS_ALWAYS_PLAY:
        if new_alert == AudibleAlert.engage:
          self.dispatch_beep(self.engage)
        elif new_alert == AudibleAlert.disengage:
          self.dispatch_beep(self.disengage)
        elif new_alert == AudibleAlert.promptRepeat:
          if now >= self.prompt_suppress_until:
            self.prompt_suppress_until = now + 10
            self.dispatch_beep(self.engage)
          else:
            print(f"[BEEP] promptRepeat suppressed until {self.prompt_suppress_until}")
        elif new_alert in [AudibleAlert.warningSoft, AudibleAlert.warningImmediate, AudibleAlert.promptDistracted]:
          self.dispatch_beep(self.warning)

  def get_audible_alert(self, sm):
    if sm.updated['selfdriveState']:
      new_alert = sm['selfdriveState'].alertSound.raw
      self.update_alert(new_alert)

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

    sm = messaging.SubMaster(['selfdriveState'])
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
