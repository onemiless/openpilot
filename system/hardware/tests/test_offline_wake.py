from openpilot.system.hardware import offline_wake


def test_offline_wake_debug_log(tmp_path, monkeypatch):
  log_path = tmp_path / "offline_wake_debug.log"
  monkeypatch.setattr(offline_wake, "OFFLINE_WAKE_DEBUG_LOG", str(log_path))

  offline_wake.offline_wake_debug_log("test-process", "wake event")

  assert log_path.read_text().endswith(" test-process wake event\n")
