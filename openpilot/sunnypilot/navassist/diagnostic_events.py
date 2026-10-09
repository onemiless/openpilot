"""Bounded scalar observations; no file, compression, model geometry or replay."""
from collections import deque
import math
import threading
import uuid


class DiagnosticEvents:
  def __init__(self, capacity=128):
    if not 1 <= capacity <= 128:
      raise ValueError('capacity must be in [1, 128]')
    self.epoch = uuid.uuid4().hex
    self._events = deque(maxlen=capacity)
    self._sequence = 0
    self._last_key = None
    self._last_ns = 0
    self._lock = threading.Lock()

  def observe(self, sm, now_ns, wall_ms):
    intent, model, topo, car = (sm[n] for n in ('navLaneIntentSP', 'modelV2', 'laneTopologyStateSP', 'carState'))
    key = (str(intent.sessionId), str(intent.reason), bool(intent.signalRequested), bool(intent.spLaneChangeReady),
           str(intent.direction), int(model.meta.laneChangeState.raw), int(model.meta.laneChangeDirection.raw),
           bool(topo.validForControl), bool(topo.stale), bool(car.brakePressed), bool(car.steeringPressed),
           bool(getattr(intent, 'valid', False)), int(getattr(intent, 'maneuverEventId', 0)),
           int(getattr(intent, 'requestId', 0)), int(getattr(intent, 'targetLaneIndex', -1)),
           bool(getattr(car, 'leftBlinker', False)), bool(getattr(car, 'rightBlinker', False)),
           bool(sm['carControl'].latActive),
           *(bool(sm.seen[n] and sm.alive[n] and sm.valid[n]) for n in
             ('navLaneIntentSP', 'modelV2', 'laneTopologyStateSP', 'carState', 'carControl', 'radarState')))
    if key == self._last_key and now_ns - self._last_ns < 1_000_000_000:
      return
    self._last_key, self._last_ns = key, now_ns
    ages = {n: round((now_ns - sm.logMonoTime[n]) / 1e6, 1) if sm.seen[n] else None
            for n in ('navLaneIntentSP', 'modelV2', 'laneTopologyStateSP', 'carState', 'carControl', 'radarState')}
    record = {'monoNs': now_ns, 'wallMs': wall_ms, 'sessionId': key[0], 'reason': key[1], 'signal': key[2],
              'ready': key[3], 'direction': key[4], 'laneState': key[5], 'laneDirection': key[6],
              'topologyValid': key[7], 'topologyStale': key[8], 'brake': key[9], 'steering': key[10],
              'topologyModelAgeMs': round((now_ns - topo.modelMonoTime) / 1e6, 1) if topo.modelMonoTime else None,
              'speedKph': round(float(car.vEgo) * 3.6, 1) if math.isfinite(float(car.vEgo)) else None,
              'lateralActive': bool(sm['carControl'].latActive),
              'inputHealthy': {n: bool(sm.seen[n] and sm.alive[n] and sm.valid[n]) for n in ages}, 'agesMs': ages}
    record.update(intentValid=bool(getattr(intent, 'valid', False)),
                  maneuverEventId=int(getattr(intent, 'maneuverEventId', 0)),
                  requestId=int(getattr(intent, 'requestId', 0)),
                  targetLaneIndex=int(getattr(intent, 'targetLaneIndex', -1)),
                  intentPublishMonoNs=int(getattr(intent, 'publishMonoTime', 0)),
                  leftBlinker=bool(getattr(car, 'leftBlinker', False)),
                  rightBlinker=bool(getattr(car, 'rightBlinker', False)),
                  leftNeighbor=bool(getattr(topo, 'leftNeighborExists', False)),
                  rightNeighbor=bool(getattr(topo, 'rightNeighborExists', False)))
    with self._lock:
      self._sequence += 1
      self._events.append({'sequence': self._sequence, **record})

  def snapshot(self, after=0):
    with self._lock:
      events = [e for e in self._events if e['sequence'] > after]
      return {'version': 1, 'epoch': self.epoch, 'latestSequence': self._sequence,
              'oldestSequence': self._events[0]['sequence'] if self._events else 0,
              'events': events, 'basis': 'receiverObservationNotSynchronousDecisionInputs'}
