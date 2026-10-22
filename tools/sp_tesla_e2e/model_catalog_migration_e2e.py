#!/usr/bin/env python3
"""Pinned catalogs -> real HTTP download -> Params activation without D0 writes."""
import argparse
import hashlib
import copy
import json
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as ns
from unittest.mock import patch

from openpilot.common.params import Params
from openpilot.sunnypilot.models import helpers
from openpilot.sunnypilot.models.fetcher import ModelParser
from openpilot.sunnypilot.models.manager import ModelManagerSP
from openpilot.sunnypilot.models import manager as manager_module
from openpilot.selfdrive.ui.sunnypilot import model_info as model_ui


def run(catalog_dir: Path, output: Path):
  records = []
  result = {'passed': False, 'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'scope': 'catalog, real HTTP transfer, real Params activation; no model inference', 'cases': records}
  try:
    assert helpers.REQUIRED_JSON_VERSION == 21
    for old_name, new_name in [('driving_models_v23.json', 'driving_models_v25.json'),
                               ('driving_models_chestnut_v27.json', 'driving_models_chestnut_v28.json')]:
      old = json.loads((catalog_dir / old_name).read_text())
      new = json.loads((catalog_dir / new_name).read_text())
      parsed = ModelParser.parse_models(new)
      refs = {bundle.ref for bundle in parsed}
      assert {bundle['ref'] for bundle in old['bundles']} <= refs
      for bundle in parsed:
        for model in bundle.models:
          artifact = model.artifact
          assert Path(artifact.fileName).parts[0] == artifact.downloadUri.sha256
          assert '..' not in Path(artifact.fileName).parts and not Path(artifact.fileName).is_absolute()
      records.append({'scenario': 'catalog_identity_' + new_name, 'old': len(old['bundles']), 'new': len(parsed),
                      'catalog_sha256': hashlib.sha256((catalog_dir / new_name).read_bytes()).hexdigest()})

    payload = b'SPTGPLN1' + b'migration HTTP fixture'
    digest = hashlib.sha256(payload).hexdigest()
    content = {'payload': payload}

    class Handler(BaseHTTPRequestHandler):
      def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', str(len(content['payload'])))
        self.end_headers()
        self.wfile.write(content['payload'])

      def log_message(self, *args):
        pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
      with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        model_root = root / 'models'
        model_root.mkdir()
        legacy = model_root / 'fixture.pkl'
        legacy.write_bytes(b'D0 old compiled payload')
        params = Params(str(root / 'params'))
        bundle = {'index': 0, 'short_name': 'fixture', 'display_name': 'fixture', 'ref': 'old-model-ref',
                  'generation': 12, 'minimum_selector_version': '21', 'runner': 'tinygrad',
                  'environment': 'development', 'is_20hz': True, 'overrides': {},
                  'models': [{'type': 'chunked', 'artifact': {'file_name': 'fixture.pkl',
                             'download_uri': {'url': f'http://127.0.0.1:{server.server_port}/fixture', 'sha256': digest}}}]}
        parsed = ModelParser._parse_bundle(bundle)
        old = parsed.to_dict()
        old['minimumSelectorVersion'] = 20
        old['models'][0]['artifact']['fileName'] = 'fixture.pkl'
        params.put('ModelManager_ActiveBundleChestnut', old, block=True)
        original = params.get('ModelManager_ActiveBundleChestnut')
        params.put('ModelManager_ActiveBundle', {'minimumSelectorVersion': 1}, block=True)
        qcom = params.get('ModelManager_ActiveBundle')
        manager = object.__new__(ModelManagerSP)
        manager.params, manager.selected_bundle, manager.active_bundle = params, None, None
        manager.chestnut_present, manager._block_size, manager._download_start_times = True, 128000, {}
        manager._download_ref, manager._report_status = 'old-model-ref', lambda: None
        params.put('ModelManager_DownloadRef', 'old-model-ref', block=True)
        destination = model_root / parsed.models[0].artifact.fileName
        with patch.object(helpers.Paths, 'model_root', return_value=str(model_root)), \
             patch.object(helpers, 'chestnut_present', return_value=True):
          helpers._LAST_VALIDATED_RAW.clear()
          helpers._validate_active_bundle(params, 'chestnut', [parsed])
          assert params.get('ModelManager_ActiveBundleChestnut') == original
          records.append({'scenario': 'pending_legacy_selection_preserved'})
          manager.download(parsed, str(model_root), 'chestnut')
          assert destination.read_bytes() == payload
          assert legacy.read_bytes() == b'D0 old compiled payload'
          assert helpers.get_selected_bundle(params, 'chestnut').ref == 'old-model-ref'
          assert params.get('ModelManager_ActiveBundle') == qcom
          records.append({'scenario': 'http_download_atomic_activation_and_slots', 'sha256': digest})
          destination.write_bytes(b'existing artifact must survive failed replacement')
          content['payload'] = b'corrupt response'
          try:
            manager.download(parsed, str(model_root), 'chestnut')
          except ValueError:
            pass
          else:
            raise AssertionError('corrupt response accepted')
          assert destination.read_bytes() == b'existing artifact must survive failed replacement'
          records.append({'scenario': 'corrupt_download_keeps_previous_file'})
          destination.write_bytes(payload)
          params.put('ModelManager_ActiveBundleChestnut', old, block=True)
          helpers._LAST_VALIDATED_RAW.clear()
          helpers._validate_active_bundle(params, 'chestnut', [parsed])
          assert helpers.get_selected_bundle(params, 'chestnut').ref == old['ref']
          assert params.get('ModelManager_ActiveBundleChestnut')['minimumSelectorVersion'] == 21
          records.append({'scenario': 'prepared_legacy_slot_migrates_same_ref'})
          manager.clear_model_cache()
          assert destination.read_bytes() == payload and legacy.read_bytes() == b'D0 old compiled payload'
          records.append({'scenario': 'cache_clear_preserves_active_hash_directory_and_D0'})

          pending = Params(str(root / 'pending-params'))
          old_qcom = copy.deepcopy(old)
          old_qcom.update(ref='retained-small-ref', internalName='KEEP', displayName='Retained small')
          pending.put('ModelManager_ActiveBundle', old_qcom, block=True)
          pending.put('ModelManager_ActiveBundleChestnut', parsed.to_dict(), block=True)
          manager.params = pending
          manager.sm = type('DeviceInputs', (dict,), {'update': lambda self, timeout: None})(
            deviceState=ns(chestnutPresent=True))
          manager.model_fetcher = ns(get_bundles_for_source=lambda source: [parsed] if source == 'chestnut' else [])
          queued = []
          manager._process_download_requests = lambda: queued.append(pending.get('ModelManager_DownloadRef'))

          class EndTick(BaseException):
            pass

          def end_tick():
            raise EndTick()

          with patch.object(manager_module, 'Ratekeeper', return_value=ns(keep_time=end_tick)), \
               patch.object(pending, 'put', wraps=pending.put) as writes:
            try:
              manager.main_thread()
            except EndTick:
              pass
          requested = [call.args[1] for call in writes.call_args_list if call.args[0] == 'ModelManager_DownloadRef']
          assert requested == [], f'legacy qcom selection replaced by automatic default request: {requested}'
          assert pending.get('ModelManager_ActiveBundle') == old_qcom
          records.append({'scenario': 'offline_qcom_catalog_keeps_pending_selection_without_default_request'})

          qcom_data = copy.deepcopy(bundle)
          qcom_data.update(ref='retained-small-ref', short_name='KEEP', display_name='Retained small')
          qcom_data['models'][0]['artifact']['file_name'] = 'retained_small.pkl'
          qcom = ModelParser._parse_bundle(qcom_data)
          helpers.validate_active_bundles(pending, {'qcom': [qcom], 'chestnut': [parsed]})
          deadline = time.monotonic() + 2.
          while pending.get('ModelManager_DownloadRef') != 'retained-small-ref' and time.monotonic() < deadline:
            time.sleep(0.01)
          assert pending.get('ModelManager_DownloadRef') == 'retained-small-ref'
          assert pending.get('ModelManager_ActiveBundle') == old_qcom
          assert helpers.get_selected_bundle(pending, 'qcom') is None
          assert helpers.get_active_bundle(pending, chestnut=False) is None
          with patch.object(helpers, 'chestnut_present', return_value=False):
            assert helpers.get_active_model_runner(pending, force_check=True) == helpers.custom.ModelManagerSP.Runner.stock
          saved = helpers.get_selected_bundle(pending, 'qcom', allow_legacy=True)
          assert saved.ref == old_qcom['ref'] and saved.minimumSelectorVersion == 20
          ui = ns(params=pending, chestnut_present=False, chestnut_active=False, chestnut_loading=False,
                  is_offroad=lambda: True)
          with patch.object(model_ui, 'ui_state', ui):
            assert model_ui.selected_model_name('qcom').startswith('Retained small (')
            assert model_ui.selected_model_name('qcom', short=True).startswith('KEEP (')
            assert model_ui.model_info()[1].startswith('Retained small (')
            assert model_ui.carrying_model()[2] == model_ui.default_model_name('qcom')
          records.append({'scenario': 'legacy_ui_name_is_pending_but_runtime_stays_stock_default'})

          manager._download_ref = qcom.ref
          content['payload'] = payload
          manager.download(qcom, str(model_root), 'qcom')
          ready = helpers.get_selected_bundle(pending, 'qcom')
          assert ready.ref == old_qcom['ref']
          assert ready.generation == old_qcom['generation'] and ready.is20hz == old_qcom['is20hz']
          assert ready.displayName == old_qcom['displayName']
          with patch.object(model_ui, 'ui_state', ui):
            assert model_ui.selected_model_name('qcom') == 'Retained small'
          records.append({'scenario': 'recovered_catalog_download_keeps_identity_generation_and_20hz'})

          expected_bytes = sum(file.stat().st_size for file in model_root.rglob('*') if file.is_file())
          assert model_ui.model_cache_size_mb() == expected_bytes / (1024 ** 2)
          records.append({'scenario': 'cache_size_includes_hash_directory_files', 'bytes': expected_bytes})
    finally:
      server.shutdown()
      server.server_close()
      worker.join()
    result['passed'] = True
  except Exception as error:
    result['error'] = f'{type(error).__name__}: {error}'
    raise
  finally:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--catalog-dir', type=Path, required=True)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  run(args.catalog_dir, args.output)
