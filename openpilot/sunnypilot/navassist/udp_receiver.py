from __future__ import annotations

import hashlib
import json
import socket
import threading

from openpilot.sunnypilot.navassist.protocol import NavAssistProtocolError, NavAssistStore
from openpilot.sunnypilot.navassist.server import ClientRateLimiter


UDP_SNAPSHOT_PORT = 4213
MAX_UDP_SNAPSHOT_BYTES = 8 * 1024
UDP_ACK_TYPE = "navassist_udp_ack"


def source_key_id(source_host: str) -> str:
  """Stable replay namespace for an unauthenticated UDP source address."""
  return hashlib.sha256(b"navassist-udp-v3\0" + source_host.encode("ascii")).hexdigest()[:32]


class NavAssistUDPServer:
  """Bounded, data-only UDP ingress for canonical NavAssist v3 snapshots.

  Authentication is deliberately absent for CP transport compatibility. The
  strict protocol parser, monotonic session/sequence checks, short TTL and rate
  limiter still apply. No command or generic request dispatch exists here.
  """

  def __init__(self, address: tuple[str, int], store: NavAssistStore, *,
               rate_limiter: ClientRateLimiter | None = None):
    self.store = store
    self.rate_limiter = rate_limiter or ClientRateLimiter()
    self._stopping = threading.Event()
    self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self._socket.bind(address)
    self._socket.settimeout(0.2)

  @property
  def server_address(self) -> tuple[str, int]:
    host, port = self._socket.getsockname()[:2]
    return str(host), int(port)

  def serve_forever(self) -> None:
    while not self._stopping.is_set():
      try:
        body, address = self._socket.recvfrom(MAX_UDP_SNAPSHOT_BYTES + 1)
      except TimeoutError:
        continue
      except OSError:
        if self._stopping.is_set():
          break
        raise
      source_host = str(address[0])
      if not body or len(body) > MAX_UDP_SNAPSHOT_BYTES or not self.rate_limiter.allow(source_host):
        continue
      try:
        accepted = self.store.accept(body, source_key_id(source_host))
      except NavAssistProtocolError:
        continue
      acknowledgement = json.dumps({
        "messageType": UDP_ACK_TYPE,
        "schemaVersion": 3,
        "sessionId": accepted.snapshot.session_id,
        "sequence": accepted.snapshot.sequence,
      }, separators=(",", ":")).encode()
      try:
        self._socket.sendto(acknowledgement, address)
      except OSError:
        if self._stopping.is_set():
          break

  def shutdown(self) -> None:
    self._stopping.set()

  def server_close(self) -> None:
    self._socket.close()
