from io import StringIO

from openpilot.common.linux import LinuxSystemStats


def test_cpu_usage_percent(monkeypatch):
  samples = iter([
    "cpu0 10 0 10 80 0 0 0 0\ncpu1 20 0 10 70 0 0 0 0\n",
    "cpu0 20 0 20 160 0 0 0 0\ncpu1 30 0 20 150 0 0 0 0\n",
  ])
  monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: StringIO(next(samples)))

  stats = LinuxSystemStats()

  assert stats.cpu_usage_percent() == [20., 20.]


def test_memory_usage_percent(monkeypatch):
  meminfo = "MemTotal: 1000 kB\nMemAvailable: 250 kB\n"
  monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: StringIO(meminfo))

  assert LinuxSystemStats.memory_usage_percent() == 75.
