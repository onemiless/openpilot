from __future__ import annotations

from openpilot.sunnypilot.navassist.types import NavSource, ProtocolSnapshot


class StickySourceMux:
  """Prefer Carrot/NaviPilot without packet-by-packet source oscillation."""

  def __init__(self, preferred: NavSource = NavSource.CARROT_V2, recovery_s: float = 1.0) -> None:
    self.preferred = preferred
    self.recovery_ns = int(recovery_s * 1e9)
    self._selected = NavSource.NONE
    self._preferred_healthy_since_ns = 0

  @staticmethod
  def _healthy(snapshot: ProtocolSnapshot, now_ns: int, timeout_ns: int) -> bool:
    status = snapshot.record("navigation_status")
    age = now_ns - status.received_mono_ns
    return bool(snapshot.connected and not snapshot.protocol_error and not snapshot.sequence_error
                and status.present and status.received_mono_ns > 0 and 0 <= age <= timeout_ns)

  def select(self, snapshots: tuple[ProtocolSnapshot, ...], now_ns: int, timeout_s: float) -> ProtocolSnapshot:
    by_source = {snapshot.source: snapshot for snapshot in snapshots}
    timeout_ns = int(timeout_s * 1e9)
    preferred = by_source.get(self.preferred, ProtocolSnapshot())
    current = by_source.get(self._selected, ProtocolSnapshot())
    preferred_healthy = self._healthy(preferred, now_ns, timeout_ns)
    current_healthy = self._healthy(current, now_ns, timeout_ns)

    if self._selected == self.preferred and preferred_healthy:
      return preferred

    if preferred_healthy:
      if self._preferred_healthy_since_ns == 0:
        self._preferred_healthy_since_ns = now_ns
      if not current_healthy or now_ns - self._preferred_healthy_since_ns >= self.recovery_ns:
        self._selected = self.preferred
        return preferred
    else:
      self._preferred_healthy_since_ns = 0

    if current_healthy:
      return current

    for snapshot in snapshots:
      if self._healthy(snapshot, now_ns, timeout_ns):
        self._selected = snapshot.source
        return snapshot

    # Preserve connection diagnostics while every source is still syncing.
    connected = [snapshot for snapshot in snapshots if snapshot.connected]
    if connected:
      diagnostic = preferred if preferred.connected else connected[0]
      self._selected = diagnostic.source
      return diagnostic
    self._selected = NavSource.NONE
    return ProtocolSnapshot()
