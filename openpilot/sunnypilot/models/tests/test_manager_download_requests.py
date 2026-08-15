import asyncio
import http.server
import os
from unittest import mock

import requests

from openpilot.cereal import custom
from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
from openpilot.selfdrive.test.helpers import http_server_context
from openpilot.sunnypilot.models import manager as manager_module
from openpilot.sunnypilot.models.manager import ModelManagerSP


CHUNKS = [b"A" * 3000, b"B" * 2000]
WHOLE = b"model" * 1000


class DownloadHandler(http.server.BaseHTTPRequestHandler):
  responses: dict[str, bytes] = {}

  def log_message(self, format, *args):  # noqa: A002
    pass

  def do_GET(self):
    body = self.responses.get(self.path)
    if body is None:
      self.send_response(404)
      self.end_headers()
      return

    self.send_response(200)
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)


def make_manager(cancelled=False):
  manager = ModelManagerSP.__new__(ModelManagerSP)
  manager.params = mock.MagicMock()
  manager.params.get.return_value = None if cancelled else b"0"
  manager.pm = mock.MagicMock()
  manager.selected_bundle = None
  manager.active_bundle = None
  manager.available_models = []
  manager._chunk_size = 512
  manager._download_start_times = {}
  manager._report_status = lambda: None
  return manager


def make_artifact(filename, base_url, chunked):
  bundle = custom.ModelManagerSP.ModelBundle.new_message()
  bundle.init("models", 1)
  artifact = bundle.models[0].artifact
  artifact.fileName = filename
  artifact.downloadUri.uri = f"{base_url}/{filename}"
  if chunked:
    artifact.init("chunks", len(CHUNKS))
  return bundle, artifact


def test_download_file_uses_requests_and_writes_exact_bytes(tmp_path):
  DownloadHandler.responses = {"/model.bin": WHOLE}
  with http_server_context(handler=DownloadHandler) as (host, port):
    base_url = f"http://{host}:{port}"
    _, artifact = make_artifact("model.bin", base_url, chunked=False)
    path = os.path.join(tmp_path, artifact.fileName)
    manager = make_manager()
    asyncio.run(manager._download_file(artifact.downloadUri.uri, path, artifact))

  with open(path, "rb") as f:
    assert f.read() == WHOLE
  assert manager._download_start_times == {}


def test_chunked_download_writes_chunks_and_manifest(tmp_path):
  with http_server_context(handler=DownloadHandler) as (host, port):
    base_url = f"http://{host}:{port}"
    _, artifact = make_artifact("model.pkl", base_url, chunked=True)
    DownloadHandler.responses = {
      "/" + os.path.basename(get_chunk_name(artifact.downloadUri.uri, i, len(CHUNKS))): body
      for i, body in enumerate(CHUNKS)
    }
    base_path = os.path.join(tmp_path, artifact.fileName)
    manager = make_manager()
    asyncio.run(manager._download_chunked(artifact.downloadUri.uri, base_path, artifact))

  for i, expected in enumerate(CHUNKS):
    with open(get_chunk_name(base_path, i, len(CHUNKS)), "rb") as f:
      assert f.read() == expected
  with open(get_manifest_path(base_path)) as f:
    assert f.read() == str(len(CHUNKS))
  assert manager._download_start_times == {}


def test_chunked_download_honors_cancellation(tmp_path):
  with http_server_context(handler=DownloadHandler) as (host, port):
    base_url = f"http://{host}:{port}"
    _, artifact = make_artifact("cancel.pkl", base_url, chunked=True)
    DownloadHandler.responses = {
      "/" + os.path.basename(get_chunk_name(artifact.downloadUri.uri, i, len(CHUNKS))): body
      for i, body in enumerate(CHUNKS)
    }
    base_path = os.path.join(tmp_path, artifact.fileName)

    try:
      asyncio.run(make_manager(cancelled=True)._download_chunked(artifact.downloadUri.uri, base_path, artifact))
    except Exception as exc:
      assert "cancelled" in str(exc).lower()
    else:
      raise AssertionError("cancelled download completed")

  assert not os.path.exists(get_manifest_path(base_path))


def test_requests_dependency_and_timeout_are_explicit():
  assert requests is not None
  assert "aiohttp" not in manager_module.__dict__
  connect_timeout, read_timeout = manager_module.DOWNLOAD_TIMEOUT
  assert connect_timeout > 0
  assert read_timeout > 0
