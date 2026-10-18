#!/usr/bin/env python3
"""Exercise the actual LANLink cache with isolated IPC and 100/20 Hz publishers."""
import argparse
import json
from pathlib import Path
import threading
import time

from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.system.lanlinkd.statusd import StatusCache


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  result = {'passed': False}
  with OpenpilotPrefix():
    params = Params()
    params.put_bool('BigmodelToggle', True, block=True)
    params.put('BigmodelLinkState', 'connected', block=True)
    snapshots = []

    class ObservedCache(StatusCache):
      def _capabilities_from_params(self):
        snapshots.append(time.monotonic())
        return super()._capabilities_from_params()

    cache = ObservedCache({}, 'tici', params=params)
    stop = threading.Event()
    worker = threading.Thread(target=cache.run, args=(stop,))
    pm = messaging.PubMaster(['deviceState', 'carState', 'modelV2', 'modelDataV2SP'])
    worker.start()
    try:
      time.sleep(.3)
      start = time.monotonic()
      for tick in range(300):
        for name in ('deviceState', 'carState'):
          msg = messaging.new_message(name, valid=True)
          if name == 'deviceState':
            msg.deviceState.deviceType = 'tici'
          pm.send(name, msg)
        if tick % 5 == 0:
          msg = messaging.new_message('modelV2', valid=True)
          msg.modelV2.big = True
          pm.send('modelV2', msg)
          msg = messaging.new_message('modelDataV2SP', valid=True)
          msg.modelDataV2SP.bigSource = 'big'
          msg.modelDataV2SP.bigDeadlineMs = 60.
          pm.send('modelDataV2SP', msg)
        time.sleep(max(0., start + (tick + 1) * .01 - time.monotonic()))
      time.sleep(1.2)
      result.update(snapshot_calls=len(snapshots), source_frames=len(cache._model_frames),
                    timing_frames=len(cache._timing_frames), snapshot=cache.snapshot(),
                    snapshot_gaps_s=[b-a for a, b in zip(snapshots, snapshots[1:])])
      result['passed'] = (len(snapshots) <= 6 and len(cache._model_frames) == 50 and
                          all(cache._model_frames) and len(cache._timing_frames) == 60 and
                          result['snapshot']['model']['timing']['window'] == 60 and
                          result['snapshot']['model']['timing']['sources']['big'] == 60 and
                          all(gap >= .95 for gap in result['snapshot_gaps_s']))
    finally:
      stop.set()
      worker.join(timeout=2)
      result['worker_stopped'] = not worker.is_alive()
      result['passed'] &= result['worker_stopped']
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(result, indent=2) + '\n')
  print(json.dumps(result))
  return 0 if result['passed'] else 1


if __name__ == '__main__':
  raise SystemExit(main())
