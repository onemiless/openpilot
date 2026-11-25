#!/usr/bin/env python3
"""Fixed catalog refresh -> real local HTTP -> native Params cache and selected refs."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch

from openpilot.common.params import Params
from openpilot.sunnypilot.models.fetcher import ModelFetcher, ModelParser
from openpilot.sunnypilot.models.helpers import ACTIVE_BUNDLE_KEYS

CATALOG = "a89041fcbc13582893f81971214ff4120795b1d4"
TTM = "e46b35b0dcce35761ba28ada1a7df6ae36589c30"


def run(catalog_dir: Path, output: Path):
  assert ModelFetcher.CATALOG_REF == CATALOG
  files = {"qcom": "driving_models_v25.json", "chestnut": "driving_models_chestnut_v28.json"}
  old = {s: json.loads((catalog_dir / ("old-" + f)).read_text()) for s, f in files.items()}
  new = {s: json.loads((catalog_dir / ("new-" + f)).read_text()) for s, f in files.items()}
  cases = []
  for source in files:
    before = {b["ref"]: b for b in old[source]["bundles"]}
    after = {b["ref"]: b for b in new[source]["bundles"]}
    assert before.keys() <= after.keys()
    assert all(after[ref] == bundle for ref, bundle in before.items())
    assert after.keys() - before.keys() == ({TTM} if source == "chestnut" else set())
    assert old[source]["tinygrad_ref"] == new[source]["tinygrad_ref"]
  requests = []

  class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
      source = next(s for s, name in files.items() if self.path == "/" + CATALOG + "/" + name)
      data = json.dumps(new[source]).encode()
      requests.append(self.path)
      self.send_response(200)
      self.send_header("Content-Length", str(len(data)))
      self.end_headers()
      self.wfile.write(data)

    def log_message(self, *args):
      pass

  server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
  worker = threading.Thread(target=server.serve_forever, daemon=True)
  worker.start()
  try:
    sources = {s: (f"http://127.0.0.1:{server.server_port}/{CATALOG}/{name}", "" if s == "qcom" else "_Chestnut")
               for s, name in files.items()}
    with tempfile.TemporaryDirectory() as temp, patch.dict(ModelFetcher.MODEL_SOURCES, sources):
      for name in ["CTM", "BMV6"]:
        params = Params(str(Path(temp) / name))
        selected = next(b for b in ModelParser.parse_models(old["chestnut"]) if b.internalName == name)
        small = ModelParser.parse_models(old["qcom"])[0]
        params.put(ACTIVE_BUNDLE_KEYS["chestnut"], selected.to_dict(), block=True)
        params.put(ACTIVE_BUNDLE_KEYS["qcom"], small.to_dict(), block=True)
        saved = {key: params.get(key) for key in ACTIVE_BUNDLE_KEYS.values()}
        fetcher = ModelFetcher(params)
        for source, (_, suffix) in sources.items():
          params.put("ModelManager_ModelsCache" + suffix, old[source], block=True)
          params.put("ModelManager_LastSyncTime" + suffix, 0, block=True)
          parsed = fetcher.get_bundles_for_source(source)
          assert len(parsed) == (17 if source == "chestnut" else 77)
          assert all(Path(model.artifact.fileName).parts[0] == model.artifact.downloadUri.sha256
                     for bundle in parsed for model in bundle.models)
          assert fetcher.model_caches[source].get()[0] == new[source]
        assert all(params.get(key) == value for key, value in saved.items())
        assert params.get("ModelManager_DownloadRef") is None
        cases.append({"selected_big": name, "selected_ref": selected.ref, "selected_slots_unchanged": True,
                      "ttm_visible_without_auto_selection": True, "qcom_count": 77, "chestnut_count": 17})
  finally:
    server.shutdown()
    server.server_close()
    worker.join()
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({"passed": True, "catalog": CATALOG, "cases": cases, "http_requests": requests,
                               "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                               "scope": "real catalog HTTP/cache and saved refs; no model weights or inference"}, indent=2) + "\n")
  print(output)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--catalog-dir", type=Path, required=True)
  parser.add_argument("--output", type=Path, required=True)
  args = parser.parse_args()
  run(args.catalog_dir, args.output)
