from openpilot.selfdrive.pandad import pandad


class FakePanda:
  def __init__(self):
    self.read_slots: list[int] = []

  def wake_journal_info(self, timeout=None):
    return {
      "magic": pandad.Panda.WAKE_JOURNAL_MAGIC,
      "version": pandad.Panda.WAKE_JOURNAL_VERSION,
      "record_size": pandad.Panda.WAKE_JOURNAL_RECORD_STRUCT.size,
      "capacity": 4096,
      "used_slots": 2,
      "valid_records": 2,
      "full": False,
      "foreign_data": False,
      "next_sequence": 2,
      "current_cycle": 0,
    }

  def wake_journal_record(self, slot: int, timeout=None):
    self.read_slots.append(slot)
    return {"valid": True, "sequence": slot, "type": "event" if slot == 0 else "result"}


def test_export_wake_journal_fsyncs_before_advancing_cursor(tmp_path, monkeypatch):
  cursor = tmp_path / "cursor"
  messages: list[str] = []
  monkeypatch.setattr(pandad, "PANDA_WAKE_JOURNAL_CURSOR", str(cursor))
  monkeypatch.setattr(pandad, "offline_wake_debug_log_lines",
                      lambda process, lines: messages.extend(lines) is None or True)
  panda = FakePanda()

  pandad.export_wake_journal(panda, "abc")

  assert panda.read_slots == [0, 1]
  assert cursor.read_text() == "abc 2\n"
  assert any("slot=0" in message for message in messages)
  assert any("slot=1" in message for message in messages)

  panda.read_slots.clear()
  pandad.export_wake_journal(panda, "abc")
  assert panda.read_slots == []


def test_export_failure_does_not_advance_cursor(tmp_path, monkeypatch):
  cursor = tmp_path / "cursor"
  fallback: list[str] = []
  monkeypatch.setattr(pandad, "PANDA_WAKE_JOURNAL_CURSOR", str(cursor))
  monkeypatch.setattr(pandad, "offline_wake_debug_log_lines", lambda process, lines: False)
  monkeypatch.setattr(pandad, "offline_wake_debug_log", fallback.append)

  pandad.export_wake_journal(FakePanda(), "abc")

  assert not cursor.exists()
  assert any("failed to fsync" in message for message in fallback)


def test_old_firmware_without_journal_does_not_block_startup(monkeypatch):
  fallback: list[str] = []
  monkeypatch.setattr(pandad, "offline_wake_debug_log", fallback.append)

  class OldPanda:
    def wake_journal_info(self, timeout=None):
      raise RuntimeError("unsupported control request")

  pandad.export_wake_journal(OldPanda(), "old")
  assert any("wake journal unavailable" in message for message in fallback)


def test_pre_heartbeat_export_is_bounded_to_recent_records(tmp_path, monkeypatch):
  cursor = tmp_path / "cursor"
  messages: list[str] = []
  monkeypatch.setattr(pandad, "PANDA_WAKE_JOURNAL_CURSOR", str(cursor))
  monkeypatch.setattr(pandad, "offline_wake_debug_log_lines",
                      lambda process, lines: messages.extend(lines) is None or True)
  panda = FakePanda()
  panda.wake_journal_info = lambda timeout=None: {
    **FakePanda().wake_journal_info(),
    "used_slots": 100,
    "valid_records": 100,
  }

  pandad.export_wake_journal(panda, "abc")

  assert panda.read_slots == list(range(92, 100))
  assert cursor.read_text() == "abc 100\n"
  assert any("skipped_slots=92" in message for message in messages)
