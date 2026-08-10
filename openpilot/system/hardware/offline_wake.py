import fcntl
import os
import secrets
import time
from collections.abc import Generator
from contextlib import contextmanager


OFFLINE_WAKE_DEBUG_LOG = "/data/offline_wake_debug.log"
PANDA_BOOTKICK_TEST_SENTINEL = "/data/panda_bootkick_test_pending"
PANDA_BOOTKICK_TEST_TTL = 10 * 60
OFFLINE_WAKE_CAN_BUSES = (0, 1, 2)
OFFLINE_SHUTDOWN_CAN_QUIET_S = 300.0
OFFLINE_SHUTDOWN_PANDA_MAX_SAMPLE_AGE_S = 2.0
PANDA_WAKE_DEBUG_MAGIC = 0x57414B48
PANDA_WAKE_MONITOR_ARMED_STAGE = 0x30
PANDA_WAKE_MONITOR_STATUS_MAGIC = 0x574D4F4E
PANDA_WAKE_MONITOR_PREPARED_STATE = 1
PANDA_WAKE_MONITOR_COMMITTED_STATE = 2
PANDA_WAKE_MONITOR_FAILED_STATE = 7
PANDA_WAKE_MONITOR_STATUS_FLAG_RX_ARMED = 1 << 0
PANDA_WAKE_MONITOR_STATUS_FLAG_PREPARE_DIRTY = 1 << 1
PANDA_WAKE_MONITOR_STATUS_FLAG_CAN_HEALTHY = 1 << 2


class CanActivityTracker:
  """Record Panda logical CAN sources for diagnostics without blocking shutdown."""
  def __init__(self, now: float | None = None) -> None:
    current_time = time.monotonic() if now is None else now
    self.frame_counts: dict[int, int] = dict.fromkeys(OFFLINE_WAKE_CAN_BUSES, 0)
    self.last_activity: dict[int, float] = dict.fromkeys(OFFLINE_WAKE_CAN_BUSES, current_time)

  def update(self, can_messages, now: float | None = None) -> None:
    current_time = time.monotonic() if now is None else now
    for message in can_messages:
      bus = int(message.src)
      if bus in self.frame_counts:
        self.frame_counts[bus] += 1
        self.last_activity[bus] = current_time

  def snapshot(self, now: float | None = None) -> dict[int, dict[str, float | int]]:
    current_time = time.monotonic() if now is None else now
    return {
      bus: {
        "frames": self.frame_counts[bus],
        "last_activity_s": max(0.0, current_time - self.last_activity[bus]),
      }
      for bus in OFFLINE_WAKE_CAN_BUSES
    }


class CanShutdownGate:
  """Require fresh, fault-free Panda counters to remain unchanged before shutdown."""
  def __init__(self, quiet_s: float = OFFLINE_SHUTDOWN_CAN_QUIET_S,
               max_sample_age_s: float = OFFLINE_SHUTDOWN_PANDA_MAX_SAMPLE_AGE_S) -> None:
    self.quiet_s = quiet_s
    self.max_sample_age_s = max_sample_age_s
    self.last_counts: tuple[int, int, int] | None = None
    self.last_lost_counts: tuple[int, int, int] | None = None
    self.last_uptime: int | None = None
    self.last_sample_time: float | None = None
    self.quiet_since: float | None = None
    self.healthy = False
    self.reason = "no_panda_state"

  def reset(self, reason: str = "reset") -> None:
    self.last_counts = None
    self.last_lost_counts = None
    self.last_uptime = None
    self.last_sample_time = None
    self.quiet_since = None
    self.healthy = False
    self.reason = reason

  @staticmethod
  def _can_states(panda_state):
    return (panda_state.canState0, panda_state.canState1, panda_state.canState2)

  def update(self, panda_states, now: float | None = None, valid: bool = True) -> None:
    current_time = time.monotonic() if now is None else now
    if not valid or len(panda_states) != 1:
      self.reset("panda_state_invalid")
      return

    panda_state = panda_states[0]
    can_states = self._can_states(panda_state)
    faults = tuple(panda_state.faults)
    unhealthy_bus = any(bool(can_state.busOff) or bool(can_state.errorPassive) for can_state in can_states)
    if bool(panda_state.powerSaveEnabled):
      self.reset("panda_rx_power_save")
      return
    if faults:
      self.reset("panda_fault:" + ",".join(str(fault) for fault in faults))
      return
    if unhealthy_bus:
      self.reset("can_controller_unhealthy")
      return

    uptime = int(panda_state.uptime)
    counts = tuple(int(can_state.totalRxCnt) for can_state in can_states)
    lost_counts = tuple(int(getattr(can_state, "totalRxLostCnt", 0)) for can_state in can_states)
    stale_gap = self.last_sample_time is not None and (current_time - self.last_sample_time) > self.max_sample_age_s
    panda_reset = self.last_uptime is not None and uptime < self.last_uptime
    counter_reset = self.last_counts is not None and any(current < previous for current, previous in zip(counts, self.last_counts, strict=True))
    rx_lost = self.last_lost_counts is not None and any(current > previous for current, previous in zip(lost_counts, self.last_lost_counts, strict=True))
    activity = self.last_counts is not None and counts != self.last_counts

    if self.last_counts is None or stale_gap or panda_reset or counter_reset or rx_lost or activity:
      self.quiet_since = current_time

    self.last_counts = counts
    self.last_lost_counts = lost_counts
    self.last_uptime = uptime
    self.last_sample_time = current_time
    self.healthy = True
    self.reason = "quiet" if not activity else "can_activity"

  def ready(self, now: float | None = None) -> bool:
    current_time = time.monotonic() if now is None else now
    fresh = self.last_sample_time is not None and (current_time - self.last_sample_time) <= self.max_sample_age_s
    return self.healthy and fresh and self.quiet_since is not None and (current_time - self.quiet_since) >= self.quiet_s

  def snapshot(self, now: float | None = None) -> dict[str, object]:
    current_time = time.monotonic() if now is None else now
    return {
      "ready": self.ready(current_time),
      "reason": self.reason,
      "quiet_s": 0.0 if self.quiet_since is None else max(0.0, current_time - self.quiet_since),
      "last_counts": self.last_counts,
      "last_sample_age_s": None if self.last_sample_time is None else max(0.0, current_time - self.last_sample_time),
    }


def wake_can_activity(can_messages) -> bool:
  """Ignore Panda echo buses and track the three logical vehicle CAN sources."""
  return any(int(message.src) in OFFLINE_WAKE_CAN_BUSES for message in can_messages)


def new_wake_monitor_transaction() -> int:
  transaction = secrets.randbits(32)
  return transaction if transaction != 0 else 1


def wake_monitor_transaction_string(transaction: int) -> str:
  return f"{transaction & 0xFFFFFFFF:08x}"


def acknowledge_panda_wake_monitor(params, transaction: int) -> None:
  params.remove("PandaWakeMonitorRequest")
  params.put("PandaWakeMonitorAck", wake_monitor_transaction_string(transaction), block=True)


def panda_wake_monitor_acknowledged(params, transaction: int) -> bool:
  return params.get("PandaWakeMonitorAck") == wake_monitor_transaction_string(transaction)


def panda_wake_monitor_ready(wake_debug: dict | None) -> bool:
  return wake_debug is not None and wake_debug.get("magic") == PANDA_WAKE_DEBUG_MAGIC \
    and wake_debug.get("stage") == PANDA_WAKE_MONITOR_ARMED_STAGE


def panda_wake_monitor_status_ready(status: dict | None, transaction: int, state: int,
                                    required_flags: int = 0, forbidden_flags: int = 0) -> bool:
  flags = 0 if status is None else int(status.get("flags", status.get("reserved", 0)))
  return status is not None and status.get("magic") == PANDA_WAKE_MONITOR_STATUS_MAGIC \
    and status.get("transaction") == transaction and status.get("state") == state \
    and (flags & required_flags) == required_flags and (flags & forbidden_flags) == 0


def panda_wake_monitor_health_ready(health: dict | None, can_health: list[dict] | None = None) -> bool:
  if health is None or int(health.get("faults", 0)) != 0:
    return False
  if can_health is None or len(can_health) != len(OFFLINE_WAKE_CAN_BUSES):
    return False
  return all(not bool(state.get("bus_off", False)) and not bool(state.get("error_passive", False))
             for state in can_health)


@contextmanager
def _panda_bootkick_test_lock() -> Generator[None, None, None]:
  lock_path = f"{PANDA_BOOTKICK_TEST_SENTINEL}.lock"
  fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    yield
  finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def offline_wake_debug_log_lines(process: str, messages: list[str]) -> bool:
  try:
    with open(OFFLINE_WAKE_DEBUG_LOG, "a") as f:
      for message in messages:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {process} {message}\n")
      f.flush()
      os.fsync(f.fileno())
    # The log can be created immediately before vehicle power disappears.
    # Persist the directory entry before allowing the journal cursor to move.
    parent = os.path.dirname(OFFLINE_WAKE_DEBUG_LOG) or "."
    directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
      os.fsync(directory_fd)
    finally:
      os.close(directory_fd)
    return True
  except Exception:
    return False


def offline_wake_debug_log(process: str, message: str) -> None:
  offline_wake_debug_log_lines(process, [message])


def panda_bootkick_test_pending() -> bool:
  try:
    with _panda_bootkick_test_lock():
      try:
        mtime = os.path.getmtime(PANDA_BOOTKICK_TEST_SENTINEL)
        if (time.time_ns() / 1e9) - mtime <= PANDA_BOOTKICK_TEST_TTL:
          return True
        os.remove(PANDA_BOOTKICK_TEST_SENTINEL)
      except FileNotFoundError:
        pass
  except Exception:
    pass
  return False


def clear_panda_bootkick_test_sentinel() -> bool:
  try:
    with _panda_bootkick_test_lock():
      try:
        os.remove(PANDA_BOOTKICK_TEST_SENTINEL)
        return True
      except FileNotFoundError:
        pass
  except Exception:
    pass
  return False
