"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import asyncio
import json
import os
from pathlib import Path
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.common.utils import atomic_write
from openpilot.common.hardware.hw import Paths

from openpilot.cereal import messaging, custom
from openpilot.sunnypilot.models.fetcher import ModelFetcher
from openpilot.sunnypilot.models.helpers import (ACTIVE_BUNDLE_KEYS, get_active_bundle, get_selected_bundle,
                                                  resolve_bundle_by_ref, validate_active_bundles, verify_file)

# (connect, read) seconds. read is per-request inactivity, not a total cap
DOWNLOAD_TIMEOUT = (30, 30)
# HuggingFace throttles each connection to ~1-2 MB/s but not the connection count; 12 saturates the device link
MAX_CONCURRENT_PIECES = 12
PIECE_SIZE = 8 * 1024 * 1024
PIECE_ATTEMPTS = 3
PIECE_BACKOFF = 1.0  # seconds, growing linearly: waits 1 s then 2 s between a piece's three attempts
DOWNLOAD_ATTEMPTS = 4
DOWNLOAD_BACKOFF = 2.0
TRANSIENT_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})
REPORT_INTERVAL = 0.5  # seconds between progress publications
# byte ranges count encoded bytes but iter_content yields decoded ones, so ask for an unencoded body
NO_COMPRESSION = {"Accept-Encoding": "identity"}
SPEED_SMOOTHING = 0.7  # weight of the previous speed sample in the published speed
SPEED_FLOOR = 0.05 * 1024 ** 2  # bytes/s; anything slower would only display as 0.0 MB/s, so it reads as no rate


class DownloadCancelled(Exception):
  pass


def _is_transient(e: BaseException) -> bool:
  if isinstance(e, requests.HTTPError):
    return e.response is not None and e.response.status_code in TRANSIENT_HTTP_STATUS
  return isinstance(e, (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError))


class _Progress:
  def __init__(self, path: str, layout: dict, done: set[int], done_bytes: int):
    self._path = path
    self._layout = layout
    self._done = done.copy()
    self._bytes = done_bytes
    self._lock = threading.Lock()

  def add_bytes(self, n: int) -> None:
    with self._lock:
      self._bytes += n

  def mark_done(self, index: int) -> None:
    with self._lock:
      self._done.add(index)
      with atomic_write(f"{self._path}.json", overwrite=True) as state:
        json.dump({**self._layout, "done": sorted(self._done)}, state)
        state.flush()
        os.fsync(state.fileno())
      fd = os.open(os.path.dirname(self._path) or ".", os.O_RDONLY)
      try:
        os.fsync(fd)
      finally:
        os.close(fd)

  def snapshot(self) -> int:
    with self._lock:
      return self._bytes


def _piece_ranges(total: int, piece_size: int) -> list[tuple[int, int]]:
  return [(start, min(start + piece_size, total)) for start in range(0, total, piece_size)]


def _prepare_target(path: str, layout: dict, piece_count: int) -> set[int]:
  total = layout["total"]
  state_path = Path(f"{path}.json")
  if layout["ranged"]:
    try:
      state = json.loads(state_path.read_text())
      if isinstance(state, dict) and all(state.get(key) == value for key, value in layout.items()) and os.path.getsize(path) == total:
        done = state.get("done")
        if isinstance(done, list) and all(type(index) is int and 0 <= index < piece_count for index in done):
          return set(done)
    except (OSError, ValueError):
      pass  # Missing or invalid resume data requires a fresh transfer.
  state_path.unlink(missing_ok=True)
  with open(path, "wb") as f:
    f.truncate(total)
  return set()


def _content_range_total(response: requests.Response) -> int | None:
  if response.status_code != 206:
    return None
  match = re.fullmatch(r"bytes \d+-\d+/(\d+)", response.headers.get("Content-Range", ""))
  return int(match.group(1)) if match else None


def _probe_size(url: str) -> tuple[int, bool]:
  with requests.get(url, headers={**NO_COMPRESSION, "Range": "bytes=0-0"}, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
    response.raise_for_status()
    total = _content_range_total(response)
    if total is not None:
      return total, True
    return int(response.headers.get("Content-Length", 0)), False


def _fetch_piece(url: str, path: str, index: int, start: int, end: int | None, progress: _Progress,
                 cancel: threading.Event, block_size: int) -> None:
  headers = {**NO_COMPRESSION, "Range": f"bytes={start}-{end - 1}"} if end is not None else NO_COMPRESSION
  label = f"{os.path.basename(path)} piece {index}"
  for attempt in range(PIECE_ATTEMPTS):
    written = 0
    try:
      with requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        if end is not None and response.status_code != 206:
          raise ValueError(f"server ignored byte range for {label}")
        with open(path, "r+b") as f:
          f.seek(start)
          for block in response.iter_content(chunk_size=block_size):
            if cancel.is_set():
              raise DownloadCancelled("Download cancelled")
            f.write(block)
            written += len(block)
            progress.add_bytes(len(block))
          if end is None:
            f.truncate()  # unknown length: the body defines the file size
          else:
            if written != end - start:
              raise requests.exceptions.ConnectionError(f"short read: {written} of {end - start} bytes")
            # Persist the piece before the resume state can refer to it.
            f.flush()
            os.fsync(f.fileno())
            progress.mark_done(index)
      return
    except requests.RequestException as e:
      progress.add_bytes(-written)  # the piece restarts from scratch
      if not _is_transient(e) or attempt == PIECE_ATTEMPTS - 1:
        raise
      cloudlog.warning(f"retrying {label} after {type(e).__name__}: {e}")
      if cancel.wait(PIECE_BACKOFF * (1 + attempt)):
        raise DownloadCancelled("Download cancelled") from None


class ModelManagerSP:
  """Manages model downloads and status reporting"""

  def __init__(self):
    self.params = Params()
    self.model_fetcher = ModelFetcher(self.params)
    self.pm = messaging.PubMaster(["modelManagerSP"])
    self.sm = messaging.SubMaster(["deviceState"])
    self.chestnut_present = False
    self.available_models: list[custom.ModelManagerSP.ModelBundle] = []
    self.source_models: dict[str, list[custom.ModelManagerSP.ModelBundle]] = {}
    self.selected_bundle: custom.ModelManagerSP.ModelBundle = None
    self.active_bundle: custom.ModelManagerSP.ModelBundle = get_active_bundle(self.params, chestnut=self.chestnut_present)
    self._block_size = 128 * 1000  # 128 KB network read blocks
    self._download_start_times: dict[str, float] = {}  # Track start time per model
    self._download_ref: bytes | str | None = None

  def _download_interrupted(self) -> bool:
    # only removal cancels: a different ref is a queued selection that
    # _release_download_ref leaves in place for the next tick
    return self.params.get("ModelManager_DownloadRef") is None

  def _release_download_ref(self) -> None:
    if self.params.get("ModelManager_DownloadRef") == self._download_ref:
      self.params.remove("ModelManager_DownloadRef")
    self._download_ref = None

  def _sync_artifact_progress(self, source_artifact) -> None:
    if not self.selected_bundle:
      return
    for model in self.selected_bundle.models:
      artifact = model.artifact
      if artifact is not source_artifact and artifact.fileName == source_artifact.fileName:
        artifact.downloadProgress.status = source_artifact.downloadProgress.status
        artifact.downloadProgress.progress = source_artifact.downloadProgress.progress
        artifact.downloadProgress.eta = source_artifact.downloadProgress.eta
        artifact.downloadProgress.speed = source_artifact.downloadProgress.speed
        artifact.downloadProgress.resuming = source_artifact.downloadProgress.resuming
        artifact.downloadProgress.canceling = source_artifact.downloadProgress.canceling

  def _calculate_eta(self, filename: str, progress: float) -> int:
    if filename not in self._download_start_times or progress <= 0:
      return 60  # Default ETA for new downloads

    elapsed_time = time.monotonic() - self._download_start_times[filename]
    if elapsed_time <= 0:
      return 60

    total_estimated_time = (elapsed_time / progress) * 100
    eta = total_estimated_time - elapsed_time
    return max(1, int(eta))  # Return at least 1 second if download is ongoing

  def _set_progress(self, artifact, status, progress: float, eta: int = 0, speed: float = 0.0) -> None:
    artifact.downloadProgress.status = status
    artifact.downloadProgress.progress = progress
    artifact.downloadProgress.eta = eta
    artifact.downloadProgress.speed = speed
    self._sync_artifact_progress(artifact)
    self._report_status()

  def _publish_progress(self, artifact, done_bytes: int, total: int, speed: float) -> None:
    # held at 99 until the file passes its hash check
    progress = min(99.0, done_bytes / total * 100) if total > 0 else 0.0
    if speed > 0 and total > 0:
      eta = max(1, int((total - done_bytes) / speed))
    else:
      eta = self._calculate_eta(artifact.fileName, progress)
    self._set_progress(artifact, custom.ModelManagerSP.DownloadStatus.downloading, progress, eta, speed)

  async def _report_until_done(self, tasks: list[asyncio.Future], artifact, progress: _Progress, total: int,
                               started: tuple[int, float]) -> None:
    pending = set(tasks)
    last_bytes, last_time = started
    speed = 0.0
    while pending:
      done, pending = await asyncio.wait(pending, timeout=REPORT_INTERVAL)
      for task in done:
        task.result()  # re-raises a worker failure
      if self._download_interrupted():
        raise DownloadCancelled("Download cancelled")
      now = time.monotonic()
      done_bytes = progress.snapshot()
      if (dt := now - last_time) > 0:
        instant = max(0.0, (done_bytes - last_bytes) / dt)  # bytes/s this tick; clamped since retried pieces can lower the byte count
        speed = instant if speed == 0 else SPEED_SMOOTHING * speed + (1 - SPEED_SMOOTHING) * instant
        if speed < SPEED_FLOOR:  # a stall decays toward 0 without reaching it, and a near-0 speed overflows the eta
          speed = 0.0
      last_time, last_bytes = now, done_bytes
      self._publish_progress(artifact, done_bytes, total, speed)

  async def _download_file(self, url: str, path: str, artifact) -> None:
    self._download_start_times[artifact.fileName] = time.monotonic()
    loop = asyncio.get_running_loop()

    total, ranged = await loop.run_in_executor(None, _probe_size, url)
    pieces: list[tuple[int, int | None]] = list(_piece_ranges(total, PIECE_SIZE)) if ranged else [(0, None)]
    layout = {"total": total, "piece_size": PIECE_SIZE, "ranged": ranged, "sha256": artifact.downloadUri.sha256.lower()}
    done = await loop.run_in_executor(None, _prepare_target, path, layout, len(pieces))
    done_bytes = sum(end - start for i, (start, end) in enumerate(pieces) if i in done and end is not None)
    progress = _Progress(path, layout, done, done_bytes)
    if done:
      artifact.downloadProgress.resuming = True
      self._publish_progress(artifact, done_bytes, total, 0)
      artifact.downloadProgress.resuming = False
    cancel = threading.Event()
    started = progress.snapshot(), time.monotonic()  # before any worker can land bytes

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PIECES) as pool:
      tasks = [loop.run_in_executor(pool, _fetch_piece, url, path, i, start, end, progress, cancel, self._block_size)
               for i, (start, end) in enumerate(pieces) if i not in done]
      try:
        await self._report_until_done(tasks, artifact, progress, total, started)
      except BaseException as e:
        cancel.set()
        if isinstance(e, DownloadCancelled):
          artifact.downloadProgress.canceling = True
          self._set_progress(artifact, custom.ModelManagerSP.DownloadStatus.downloading, artifact.downloadProgress.progress)
        for task in tasks:
          task.cancel()  # drops queued pieces; running ones see the event at their next block
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    del self._download_start_times[artifact.fileName]

  async def _download_with_retries(self, url: str, path: str, artifact) -> None:
    for attempt in range(DOWNLOAD_ATTEMPTS):
      if self._download_interrupted():
        raise DownloadCancelled("Download cancelled")
      try:
        await self._download_file(url, path, artifact)
        return
      except requests.RequestException as e:
        if not _is_transient(e) or attempt == DOWNLOAD_ATTEMPTS - 1:
          raise
        progress = artifact.downloadProgress
        self._set_progress(artifact, progress.status, progress.progress, progress.eta, 0)
        deadline = time.monotonic() + DOWNLOAD_BACKOFF * 2 ** attempt
        while (remaining := deadline - time.monotonic()) > 0:
          if self._download_interrupted():
            raise DownloadCancelled("Download cancelled") from e
          await asyncio.sleep(min(remaining, 0.25))

  async def _process_artifact(self, artifact, destination_path: str) -> None:
    if not artifact.downloadUri.uri:
      return None
    if self._download_interrupted():
      raise DownloadCancelled("Download cancelled")

    url = artifact.downloadUri.uri
    expected_hash = artifact.downloadUri.sha256
    filename = artifact.fileName
    full_path = os.path.join(destination_path, filename)
    temporary = f"{full_path}.partial"
    resume_state = Path(f"{temporary}.json")
    destination = Path(destination_path).resolve()  # noqa: ASYNC240
    if any(not path.resolve().is_relative_to(destination) for path in (Path(full_path), Path(temporary), resume_state)):
      raise ValueError("Model artifact path escapes destination")
    Path(full_path).parent.mkdir(parents=True, exist_ok=True)
    status = custom.ModelManagerSP.DownloadStatus
    artifact.downloadProgress.canceling = False
    artifact.downloadProgress.resuming = False

    try:
      self._set_progress(artifact, status.verifying, 0)
      if await verify_file(full_path, expected_hash):
        self._set_progress(artifact, status.cached, 100)
        return

      self._set_progress(artifact, status.downloading, 0)
      await self._download_with_retries(url, temporary, artifact)
      self._set_progress(artifact, status.verifying, 99)
      valid = await verify_file(temporary, expected_hash)
      resume_state.unlink(missing_ok=True)  # noqa: ASYNC240
      if not valid:
        os.remove(temporary)
        raise ValueError(f"Hash validation failed for {filename}")
      os.replace(temporary, full_path)

      self._set_progress(artifact, status.downloaded, 100)

    except DownloadCancelled:
      self._set_progress(artifact, status.downloading, artifact.downloadProgress.progress)
      raise
    except Exception:
      if self.selected_bundle:
        self.selected_bundle.status = status.failed
      self._set_progress(artifact, status.failed, artifact.downloadProgress.progress)
      raise
    finally:
      self._download_start_times.pop(artifact.fileName, None)

  async def _process_model(self, model, destination_path: str) -> None:
    """Processes a single model download including verification"""
    await self._process_artifact(model.artifact, destination_path)

  def _report_status(self) -> None:
    """Reports current status through messaging system"""
    msg = messaging.new_message('modelManagerSP', valid=True)
    model_manager_state = msg.modelManagerSP
    if self.selected_bundle:
      model_manager_state.selectedBundle = self.selected_bundle

    if self.active_bundle:
      model_manager_state.activeBundle = self.active_bundle

    model_manager_state.availableBundles = self.available_models
    self.pm.send('modelManagerSP', msg)

  async def _download_bundle(self, model_bundle: custom.ModelManagerSP.ModelBundle, destination_path: str, source: str) -> None:
    self.selected_bundle = model_bundle
    self.selected_bundle.status = custom.ModelManagerSP.DownloadStatus.downloading
    for model in self.selected_bundle.models:
      model.artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.downloading
    self._report_status()
    os.makedirs(destination_path, exist_ok=True)

    try:
      seen_artifacts: set[str] = set()
      for model in self.selected_bundle.models:
        artifact = model.artifact
        if not artifact.fileName:
          continue
        if artifact.fileName in seen_artifacts:
          artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.cached
          artifact.downloadProgress.progress = 100
          artifact.downloadProgress.eta = 0
          artifact.downloadProgress.speed = 0
        else:
          seen_artifacts.add(artifact.fileName)
          await self._process_artifact(artifact, destination_path)

      if self._download_interrupted():
        raise DownloadCancelled("Download cancelled")
      self.selected_bundle.status = custom.ModelManagerSP.DownloadStatus.downloaded
      self.params.put(ACTIVE_BUNDLE_KEYS[source], model_bundle.to_dict(), block=True)
      self.active_bundle = get_active_bundle(self.params, chestnut=self.chestnut_present)

    except DownloadCancelled:
      raise
    except Exception:
      if self.selected_bundle is not None:
        self.selected_bundle.status = custom.ModelManagerSP.DownloadStatus.failed
      raise

    finally:
      self._report_status()

  def download(self, model_bundle: custom.ModelManagerSP.ModelBundle, destination_path: str, source: str) -> None:
    """Main entry point for downloading a model bundle"""
    asyncio.run(self._download_bundle(model_bundle, destination_path, source))

  def _process_download_requests(self) -> None:
    # loops so a ref queued during a download starts in the same tick, without
    # the bar dropping to idle for a tick between the two transfers
    last_ref = None
    while (ref_to_download := self.params.get("ModelManager_DownloadRef")) is not None:
      if ref_to_download == last_ref:  # a repeating ref falls back to the next tick instead of spinning
        return
      last_ref = ref_to_download
      resolved = resolve_bundle_by_ref(ref_to_download, self.source_models)
      if not resolved:
        return
      model_to_download, source = resolved
      self._download_ref = ref_to_download
      try:
        self.download(model_to_download, Paths.model_root(), source)
      except DownloadCancelled:
        self.selected_bundle = None
      except Exception as e:
        cloudlog.exception(e)
      else:
        self.selected_bundle = None
      finally:
        self._release_download_ref()

  def main_thread(self) -> None:
    """Main thread for model management"""
    rk = Ratekeeper(1, print_delay_threshold=None)

    while True:
      try:
        self.sm.update(0)
        self.chestnut_present = self.sm['deviceState'].chestnutPresent
        self.source_models = {source: self.model_fetcher.get_bundles_for_source(source) for source in ModelFetcher.MODEL_SOURCES}
        self.available_models = self.source_models[ModelFetcher.active_source(self.chestnut_present)]
        validate_active_bundles(self.params, self.source_models)
        self.active_bundle = get_active_bundle(self.params, chestnut=self.chestnut_present)

        if get_selected_bundle(self.params, "chestnut") is not None and get_selected_bundle(self.params, "qcom") is None:
          if self.params.get("ModelManager_DownloadRef") is None:
            from openpilot.sunnypilot.models.model_name import DEFAULT_MODEL_REF
            self.params.put("ModelManager_DownloadRef", DEFAULT_MODEL_REF)

        self._process_download_requests()

        if self.params.get("ModelManager_ClearCache"):
          self.clear_model_cache()
          self.params.remove("ModelManager_ClearCache")

        self._report_status()
        rk.keep_time()

      except Exception as e:
        cloudlog.exception(f"Error in main thread: {str(e)}")
        rk.keep_time()

  def clear_model_cache(self) -> None:
    """ Clears the model cache directory of all files except those in the active model bundle."""
    active_files = []
    for source in ACTIVE_BUNDLE_KEYS:
      if selected_bundle := get_selected_bundle(self.params, source):
        for model in selected_bundle.models:
          if model.artifact.fileName:
            active_files.append(model.artifact.fileName)

    model_dir = Paths.model_root()
    try:
      for filename in os.listdir(model_dir):
        if filename not in active_files:
          file_path = os.path.join(model_dir, filename)
          if os.path.isfile(file_path):
            os.remove(file_path)
      cloudlog.info("Model cache cleared, keeping active model files")
    except Exception as e:
      cloudlog.exception(f"Error clearing model cache: {str(e)}")

def main():
  ModelManagerSP().main_thread()


if __name__ == "__main__":
  main()
