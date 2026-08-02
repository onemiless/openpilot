#!/usr/bin/env python3
import io
import sys
import math
import os
from pathlib import Path

CHUNK_SIZE = 45 * 1024 * 1024  # 45MB, under GitHub's 50MB limit

def get_chunk_name(name, idx, num_chunks):
  return f"{name}.chunk{idx+1:02d}of{num_chunks:02d}"

def get_manifest_path(name):
  return f"{name}.chunkmanifest"

def _chunk_paths(path, num_chunks):
  return [get_manifest_path(path)] + [get_chunk_name(path, i, num_chunks) for i in range(num_chunks)]

def get_chunk_targets(path, file_size):
  num_chunks = math.ceil(file_size / CHUNK_SIZE)
  return _chunk_paths(path, num_chunks)

def chunk_file(path, targets):
  manifest_path, *chunk_paths = targets
  file_size = os.path.getsize(path)
  actual_num_chunks = max(1, math.ceil(file_size / CHUNK_SIZE))
  assert len(chunk_paths) >= actual_num_chunks, f"Allowed {len(chunk_paths)} chunks but needs at least {actual_num_chunks}, for path {path}"
  with open(path, 'rb') as source:
    for i, chunk_path in enumerate(chunk_paths):
      with open(chunk_path, 'wb') as chunk:
        chunk.write(source.read(CHUNK_SIZE))
  Path(manifest_path).write_text(str(len(chunk_paths)))
  os.remove(path)

def get_existing_chunks(path):
  if os.path.isfile(path):
    return [path]
  if os.path.isfile(manifest := get_manifest_path(path)):
    num_chunks = int(Path(manifest).read_text().strip())
    return _chunk_paths(path, num_chunks)
  raise FileNotFoundError(path)

def read_file_chunked(path):
  manifest_path = get_manifest_path(path)
  if os.path.isfile(manifest_path):
    num_chunks = int(Path(manifest_path).read_text().strip())
    return b''.join(Path(get_chunk_name(path, i, num_chunks)).read_bytes() for i in range(num_chunks))
  if os.path.isfile(path):
    return Path(path).read_bytes()
  raise FileNotFoundError(path)


class ChunkStream(io.RawIOBase):
  """Read a chunked file without materializing the complete file in memory."""

  def __init__(self, paths):
    self.paths = paths
    self.path_idx = 0
    self.file = open(self.paths[0], 'rb')

  def readable(self):
    return True

  def readinto(self, buffer):
    pos = 0
    while pos < len(buffer):
      read = self.file.readinto(buffer[pos:])
      if read:
        pos += read
      elif self.path_idx + 1 < len(self.paths):
        self.file.close()
        self.path_idx += 1
        self.file = open(self.paths[self.path_idx], 'rb')
      else:
        break
    return pos

  def close(self):
    if not self.closed:
      self.file.close()
    super().close()


def open_file_chunked(path):
  manifest_path = get_manifest_path(path)
  if os.path.isfile(manifest_path):
    num_chunks = int(Path(manifest_path).read_text().strip())
    paths = [get_chunk_name(path, i, num_chunks) for i in range(num_chunks)]
  elif os.path.isfile(path):
    paths = [path]
  else:
    raise FileNotFoundError(path)
  return io.BufferedReader(ChunkStream(paths))


if __name__ == "__main__":
  path = sys.argv[1]
  chunk_paths = get_chunk_targets(path, os.path.getsize(path))
  chunk_file(path, chunk_paths)
