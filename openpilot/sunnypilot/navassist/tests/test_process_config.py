import socket
from types import SimpleNamespace as ns

import pytest

from openpilot.sunnypilot.navassist.protocol.carrot_v2 import CarrotV2Receiver, CarrotV2Server
from openpilot.system.manager.process_config import navassist


class FakeParams:
  def __init__(self, enabled):
    self.enabled = enabled

  def get_bool(self, key):
    assert key == "NavAssistEnabled"
    return self.enabled


def test_disabled_process_is_inert():
  assert not navassist(True, FakeParams(False), ns())
  assert navassist(True, FakeParams(True), ns())
  assert not navassist(False, FakeParams(True), ns())


def test_server_bind_failure_is_synchronous():
  occupied = socket.socket()
  occupied.bind(("127.0.0.1", 0))
  occupied.listen()
  port = occupied.getsockname()[1]
  try:
    with pytest.raises(OSError):
      CarrotV2Server(CarrotV2Receiver(), port=port, bind_host="127.0.0.1", retry_count=0).start()
  finally:
    occupied.close()
