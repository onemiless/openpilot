import json
import socket
import threading

import pytest

from openpilot.sunnypilot.navassist.discovery import (
  DISCOVERY_HTTP_PORT,
  DISCOVERY_MAX_DATAGRAM_BYTES,
  DISCOVERY_OFFER_TYPE,
  DISCOVERY_REQUEST_TYPE,
  DISCOVERY_SCHEMA_VERSION,
  DISCOVERY_SNAPSHOT_PATH,
  DiscoveryNonceCache,
  DiscoveryProtocolError,
  DiscoveryRateLimiter,
  NavAssistDiscoveryServer,
  build_discovery_offer,
  is_private_discovery_client,
  offer_proof,
  parse_discovery_request,
  request_proof,
)
from openpilot.sunnypilot.navassist.navassistd import LISTEN_PORT
from openpilot.sunnypilot.navassist.server import SNAPSHOT_PATH


TOKEN = b"0123456789abcdef0123456789abcdef"
NONCE = "00112233445566778899aabbccddeeff"
DUPLICATE_NONCE_DATAGRAM = (
  b'{"messageType":"navassist_discovery_request","schemaVersion":2,'
  + b'"nonce":"00112233445566778899aabbccddeeff","nonce":"00112233445566778899aabbccddeeff",'
  + b'"proof":"9d578b071534a597bb803bfe9372204164351983f241847dac1e5953d1255712"}'
)


def request_datagram(*, nonce: str = NONCE, proof: str | None = None, **updates) -> bytes:
  request = {
    "messageType": DISCOVERY_REQUEST_TYPE,
    "schemaVersion": DISCOVERY_SCHEMA_VERSION,
    "nonce": nonce,
    "proof": request_proof(TOKEN, nonce) if proof is None else proof,
  }
  request.update(updates)
  return json.dumps(request, separators=(",", ":")).encode()


def run_server(*, rate_limiter: DiscoveryRateLimiter | None = None):
  server = NavAssistDiscoveryServer(
    ("127.0.0.1", 0), TOKEN, rate_limiter=rate_limiter,
    client_allowed=lambda client: client == "127.0.0.1", socket_timeout_s=0.02,
  )
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  return server, thread


def stop_server(server: NavAssistDiscoveryServer, thread: threading.Thread) -> None:
  server.shutdown()
  thread.join(timeout=1)
  server.server_close()
  assert not thread.is_alive()


def test_discovery_proofs_have_cross_client_known_vectors():
  assert request_proof(TOKEN, NONCE) == "9d578b071534a597bb803bfe9372204164351983f241847dac1e5953d1255712"
  assert offer_proof(TOKEN, NONCE) == "d507c868871964322a3660c828cb6e55918525e7e21c1bbaa00d751bfbae2cf9"


def test_offer_endpoint_matches_the_http_receiver():
  assert DISCOVERY_HTTP_PORT == LISTEN_PORT
  assert DISCOVERY_SNAPSHOT_PATH == SNAPSHOT_PATH


def test_strict_request_parser_and_offer_contract():
  assert parse_discovery_request(request_datagram(), TOKEN) == NONCE
  offer_bytes = build_discovery_offer(NONCE, TOKEN)
  assert len(offer_bytes) <= DISCOVERY_MAX_DATAGRAM_BYTES
  assert json.loads(offer_bytes) == {
    "messageType": DISCOVERY_OFFER_TYPE,
    "schemaVersion": DISCOVERY_SCHEMA_VERSION,
    "nonce": NONCE,
    "port": DISCOVERY_HTTP_PORT,
    "path": DISCOVERY_SNAPSHOT_PATH,
    "proof": "d507c868871964322a3660c828cb6e55918525e7e21c1bbaa00d751bfbae2cf9",
  }


@pytest.mark.parametrize("datagram", [
  b"",
  b"not-json",
  b"{" + b" " * DISCOVERY_MAX_DATAGRAM_BYTES + b"}",
  request_datagram(proof="0" * 64),
  request_datagram(nonce=NONCE.upper(), proof="0" * 64),
  request_datagram(schemaVersion=True),
  request_datagram(extra="unexpected"),
  json.dumps({
    "messageType": DISCOVERY_REQUEST_TYPE,
    "schemaVersion": DISCOVERY_SCHEMA_VERSION,
    "nonce": NONCE,
  }, separators=(",", ":")).encode(),
  DUPLICATE_NONCE_DATAGRAM,
])
def test_request_parser_silently_rejectable_input(datagram: bytes):
  with pytest.raises(DiscoveryProtocolError):
    parse_discovery_request(datagram, TOKEN)


def test_udp_server_unicasts_authenticated_offer_from_discovery_port():
  server, thread = run_server()
  client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  client.settimeout(0.5)
  try:
    client.sendto(request_datagram(), ("127.0.0.1", server.server_port))
    offer_bytes, source = client.recvfrom(DISCOVERY_MAX_DATAGRAM_BYTES + 1)
    assert source == ("127.0.0.1", server.server_port)
    offer = json.loads(offer_bytes)
    assert offer["nonce"] == NONCE
    assert offer["port"] == DISCOVERY_HTTP_PORT
    assert offer["path"] == DISCOVERY_SNAPSHOT_PATH
    assert offer["proof"] == offer_proof(TOKEN, NONCE)
  finally:
    client.close()
    stop_server(server, thread)


def test_udp_server_does_not_answer_bad_auth_or_oversized_datagrams():
  server, thread = run_server()
  client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  client.settimeout(0.1)
  try:
    for datagram in (request_datagram(proof="0" * 64), b"x" * (DISCOVERY_MAX_DATAGRAM_BYTES + 1)):
      client.sendto(datagram, ("127.0.0.1", server.server_port))
      with pytest.raises(TimeoutError):
        client.recvfrom(DISCOVERY_MAX_DATAGRAM_BYTES + 1)
  finally:
    client.close()
    stop_server(server, thread)


def test_udp_server_can_rebind_immediately_after_clean_shutdown():
  server, thread = run_server()
  port = server.server_port
  stop_server(server, thread)

  replacement = NavAssistDiscoveryServer(
    ("127.0.0.1", port), TOKEN, client_allowed=lambda client: client == "127.0.0.1", socket_timeout_s=0.02,
  )
  replacement.server_close()


def test_discovery_rate_limiter_bounds_per_client_global_rate_and_client_memory():
  now = [1.0]
  limiter = DiscoveryRateLimiter(
    max_requests_per_client=1, max_requests_global=2, window_s=1.0, max_clients=1, clock=lambda: now[0],
  )
  assert limiter.allow("192.168.1.1")
  assert not limiter.allow("192.168.1.1")
  assert limiter.allow("192.168.1.2")
  assert not limiter.allow("192.168.1.3")
  assert len(limiter._client_events) <= 1
  now[0] += 1.0
  assert limiter.allow("192.168.1.3")


def test_discovery_accepts_only_rfc1918_sources():
  for address in ("10.1.2.3", "172.16.0.1", "172.31.255.254", "192.168.53.232"):
    assert is_private_discovery_client(address)
  for address in ("8.8.8.8", "172.32.0.1", "169.254.1.1", "0.0.0.0", "127.0.0.1", "::1", "not-an-address"):
    assert not is_private_discovery_client(address)


def test_nonce_cache_suppresses_short_replay_and_has_bounded_memory():
  now = [1.0]
  cache = DiscoveryNonceCache(ttl_s=2.0, max_entries=2, clock=lambda: now[0])
  assert cache.accept_once("192.168.1.1", "0" * 32)
  assert not cache.accept_once("192.168.1.1", "0" * 32)
  assert cache.accept_once("192.168.1.2", "0" * 32)
  assert cache.accept_once("192.168.1.3", "1" * 32)
  assert len(cache._entries) <= 2
  now[0] += 2.0
  assert cache.accept_once("192.168.1.1", "0" * 32)
