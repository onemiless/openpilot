from types import SimpleNamespace as NS

from openpilot.sunnypilot.navassist.diagnostic_events import DiagnosticEvents


class State(dict):
  def __init__(self):
    super().__init__(navLaneIntentSP=NS(sessionId='s', reason='ready', signalRequested=False,
                    spLaneChangeReady=False, direction='left'),
                    modelV2=NS(meta=NS(laneChangeState=NS(raw=0), laneChangeDirection=NS(raw=0))),
                    laneTopologyStateSP=NS(validForControl=True, stale=False, modelMonoTime=1),
                    carState=NS(brakePressed=False, steeringPressed=False, vEgo=10), carControl=NS(latActive=True))
    names = (*self.keys(), 'radarState')
    self.seen = dict.fromkeys(names, True)
    self.valid = dict.fromkeys(names, True)
    self.alive = dict.fromkeys(names, True)
    self.logMonoTime = dict.fromkeys(names, 1)


def test_bounded_cursor_changes_and_periodic_observations():
  state = State()
  events = DiagnosticEvents(2)
  events.observe(state, 1, 1)
  events.observe(state, 500_000_000, 2)
  assert events.snapshot()['latestSequence'] == 1
  events.observe(state, 1_000_000_001, 3)
  state['navLaneIntentSP'].signalRequested = True
  events.observe(state, 1_000_000_002, 4)
  result = events.snapshot(2)
  assert result['oldestSequence'] == 2
  assert len(result['events']) == 1
  assert result['events'][0]['signal']
  assert result['basis'] == 'receiverObservationNotSynchronousDecisionInputs'
  assert events.snapshot(3)['events'] == []


def test_invalid_inputs_are_labelled_not_requalified():
  state = State()
  state.seen['modelV2'] = False
  state.valid['laneTopologyStateSP'] = False
  events = DiagnosticEvents()
  events.observe(state, 200_000_001, 1)
  record = events.snapshot()['events'][0]
  assert record['agesMs']['modelV2'] is None
  assert not record['inputHealthy']['modelV2']
  assert not record['inputHealthy']['laneTopologyStateSP']
  state.valid['laneTopologyStateSP'] = True
  state['carState'].leftBlinker = True
  state['carState'].vEgo = float('nan')
  events.observe(state, 200_000_002, 2)
  record = events.snapshot()['events'][-1]
  assert record['sequence'] == 2 and record['leftBlinker']
  assert record['speedKph'] is None


def test_diagnostics_http_requires_fresh_udp_session_owner(tmp_path):
  import http.client
  import json
  import threading
  import time
  from openpilot.sunnypilot.navassist.tests.test_server import identities, stop_server
  from openpilot.sunnypilot.navassist.tests.test_protocol import payload, encode, SOURCE_WALL_MS
  from openpilot.sunnypilot.navassist.protocol import NavAssistStore
  from openpilot.sunnypilot.navassist.server import NavAssistHTTPServer
  from openpilot.sunnypilot.navassist.udp_receiver import source_key_id

  device, _, pairing = identities(tmp_path)
  store = NavAssistStore(wall_clock_ms=lambda: SOURCE_WALL_MS)
  store.accept(encode(payload(valid_for_ms=500)), source_key_id('127.0.0.1'))
  events = DiagnosticEvents()
  events.observe(State(), time.monotonic_ns(), 1)
  server = NavAssistHTTPServer(('127.0.0.1', 0), store, device, pairing, diagnostics_provider=events.snapshot)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  def get(query):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
    connection.request('GET', '/v3/diagnostics?' + query)
    response = connection.getresponse()
    status, result = response.status, json.loads(response.read())
    connection.close()
    return status, result
  try:
    assert get('sessionId=wrong')[0] == 403
    assert get('sessionId=session-a&after=-1')[0] == 400
    status, result = get('sessionId=session-a&after=0')
    assert status == 200 and len(result['events']) == 1
    assert get('sessionId=session-a&after=1')[1]['events'] == []
    store.reset()
    assert get('sessionId=session-a')[0] == 403
    store.accept(encode(payload()), source_key_id('127.0.0.2'))
    assert get('sessionId=session-a')[0] == 403
    store.reset()
    stale_store = NavAssistStore(wall_clock_ms=lambda: SOURCE_WALL_MS, clock_ns=lambda: time.monotonic_ns() - 1_000_000_000)
    stale_store.accept(encode(payload()), source_key_id('127.0.0.1'))
    server.store = stale_store
    assert get('sessionId=session-a')[0] == 403
  finally:
    stop_server(server, thread)
