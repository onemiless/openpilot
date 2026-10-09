"""Exercise cancellation with ambiguous OEM frames; never publish CAN."""
import pytest

from openpilot.sunnypilot.selfdrive.car.tesla import validation_controller as v
from openpilot.sunnypilot.selfdrive.car.tests.test_turn_signal_recovery import cancelling, observe_off, template


def pending(direction):
  c = v.TeslaTurnSignalRealtimeController(True)
  t = 10_000_000_000
  assert c.submit_request('filter', direction, t, hold_until_cancel=True)
  # The observed ambiguous template must still support the existing action path.
  raw = bytes.fromhex('008c2220080010d2')
  c.observe_frame(t, 0x3E9, raw, 1)
  action = c.take_can_sends(t)[0]
  c.observe_frame(t + 1, 0x3E9, action.dat, 0x81)
  c.request_cancel(None, t + 2)
  c.observe_frame(t + 3, 0x3E9, raw, 1)
  return c, t


@pytest.mark.parametrize('direction', ['left', 'right'])
def test_skip_observed_ambiguous_frame_then_use_next_clean_template(direction):
  c, t = pending(direction)
  for delta in (4, 5, 100_000_000):
    assert c.take_can_sends(t + delta, cancel_only=True) == []
  assert c.status()['cancel_attempts'] == 0
  c.observe_frame(t + 483_000_000, 0x3E9, bytes.fromhex('00882220000030e6'), 1)
  cancel = c.take_can_sends(t + 483_000_000, cancel_only=True)[0]
  assert cancel.dat.hex() == '008b2820000040ff'
  assert c.status()['cancel_attempts'] == 1
  c.observe_frame(t + 483_000_001, 0x3E9, cancel.dat, 0x81)
  assert c.status() is not None
  observe_off(c, t + 483_000_002)
  result, records = c.drain_completed()[0]
  assert result['result'] == 'PASS'
  deferred = [r for r in records if r['event'] == 'cancel_template_deferred']
  assert len(deferred) == 1
  assert deferred[0]['data'] == '008c2220080010d2'


def test_persistent_ambiguous_templates_keep_original_send_timeout():
  c, t = pending('right')
  for delta in (4, 500_000_000, 1_000_000_000):
    c.observe_frame(t + delta, 0x3E9, bytes.fromhex('008c2220080010d2'), 1)
    assert c.take_can_sends(t + delta) == []
  c.advance_time(t + 2 + v.CANCEL_SEND_TIMEOUT_NS)
  assert c.status()['result'] == 'CANCEL_NOT_SENT'
  assert c.status()['cancel_attempts'] == 0


def test_rejected_cancel_skips_ambiguous_template_without_spending_retry():
  c, t, first = cancelling(ack=False)
  c.observe_frame(t + 7, 0x3E9, first.dat, 0xC1)
  c.observe_frame(t + 8, 0x3E9, bytes.fromhex('008c2220080010d2'), 1)
  assert c.take_can_sends(t + 8) == []
  assert c.status()['cancel_attempts'] == 1
  c.observe_frame(t + 9, 0x3E9, template(6), 1)
  retry = c.take_can_sends(t + 9)[0]
  assert retry.dat[1] & 7 == 3
  assert c.status()['cancel_attempts'] == 2
