import subprocess

from openpilot.system.hardware.tici import hardware as hardware_module
from openpilot.system.hardware.tici.hardware import Tici
from openpilot.system.hardware.tici.modem import Modem


def test_initialize_hardware_tolerates_missing_spi_process(monkeypatch):
  hardware = Tici()
  hardware.__dict__["amplifier"] = None
  monkeypatch.setattr(hardware_module.os, "system", lambda *_args: 0)
  monkeypatch.setattr(hardware_module, "gpio_init", lambda *_args: None)
  monkeypatch.setattr(hardware_module, "gpio_set", lambda *_args: None)
  monkeypatch.setattr(hardware_module, "sudo_write", lambda *_args: None)
  monkeypatch.setattr(hardware_module, "affine_irq", lambda *_args: None)

  def missing_process(*_args, **_kwargs):
    raise subprocess.CalledProcessError(1, "pgrep")

  monkeypatch.setattr(hardware_module.subprocess, "check_output", missing_process)

  hardware.initialize_hardware()


def test_cellular_dns_falls_back_when_modem_reports_none():
  modem = Modem.__new__(Modem)
  modem._atv = lambda *_args: '+CGCONTRDP: 1,5,"internet","10.0.0.2","10.0.0.1","",""'

  assert modem._read_cellular_dns() == ["8.8.8.8", "1.1.1.1"]
