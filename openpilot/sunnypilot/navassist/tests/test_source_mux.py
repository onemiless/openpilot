from openpilot.sunnypilot.navassist.protocol.source_mux import StickySourceMux
from openpilot.sunnypilot.navassist.types import NavSource, ProtocolSnapshot, StreamRecord


NOW = 10_000_000_000


def snapshot(source, received_ns, *, connected=True):
  return ProtocolSnapshot(
    connected=connected,
    session_id=source.name,
    source=source,
    records={"navigation_status": StreamRecord(True, 1, received_ns, {"guidance_active": True})},
  )


def test_preferred_navipilot_wins_even_when_amap_packet_is_newer():
  mux = StickySourceMux(recovery_s=0)
  carrot = snapshot(NavSource.CARROT_V2, NOW - 100_000_000)
  amap = snapshot(NavSource.AMAP_COMPANION_V1, NOW)
  assert mux.select((carrot, amap), NOW, 1.2).source == NavSource.CARROT_V2


def test_stale_preferred_falls_back_and_recovery_is_debounced():
  mux = StickySourceMux(recovery_s=1.0)
  carrot = snapshot(NavSource.CARROT_V2, NOW - 2_000_000_000)
  amap = snapshot(NavSource.AMAP_COMPANION_V1, NOW)
  assert mux.select((carrot, amap), NOW, 1.2).source == NavSource.AMAP_COMPANION_V1

  recovered = snapshot(NavSource.CARROT_V2, NOW + 100_000_000)
  assert mux.select((recovered, amap), NOW + 100_000_000, 1.2).source == NavSource.AMAP_COMPANION_V1
  assert mux.select((recovered, amap), NOW + 1_100_000_000, 1.2).source == NavSource.CARROT_V2


def test_connected_preferred_is_used_for_sync_diagnostics():
  mux = StickySourceMux()
  carrot = ProtocolSnapshot(connected=True, source=NavSource.CARROT_V2)
  amap = ProtocolSnapshot(connected=True, source=NavSource.AMAP_COMPANION_V1)
  assert mux.select((carrot, amap), NOW, 1.2).source == NavSource.CARROT_V2
