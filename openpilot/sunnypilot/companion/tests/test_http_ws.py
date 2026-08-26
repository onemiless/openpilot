from openpilot.sunnypilot.companion.http_ws import trusted_local_address, websocket_frame


def masked_client_frame(opcode: int, payload: bytes, mask: bytes = b"abcd") -> bytes:
  length = len(payload)
  assert length < 126
  return bytes((0x80 | opcode, 0x80 | length)) + mask + bytes(
    value ^ mask[index % 4] for index, value in enumerate(payload)
  )


def test_server_frame_wire_lengths():
  assert websocket_frame(1, b"ok") == b"\x81\x02ok"
  assert websocket_frame(2, b"x" * 126)[:4] == b"\x82\x7e\x00\x7e"


def test_masked_client_fixture_is_deterministic():
  assert masked_client_frame(1, b"hello") == b"\x81\x85abcd\t\x07\x0f\x08\x0e"


def test_only_local_addresses_are_trusted():
  assert trusted_local_address("127.0.0.1")
  assert trusted_local_address("192.168.10.144")
  assert not trusted_local_address("8.8.8.8")
  assert not trusted_local_address("not-an-address")
