from types import SimpleNamespace

from openpilot.sunnypilot.models.artifact_status import bundle_artifacts_ready


def _bmwv6_bundle():
  chunks = [SimpleNamespace(fileName=f"driving_bmrlnap_model_v6_september_01_2026_tinygrad.pkl.chunk{i:02d}of17")
            for i in range(1, 18)]
  artifact = SimpleNamespace(
    fileName="driving_bmrlnap_model_v6_september_01_2026_tinygrad.pkl",
    chunks=chunks,
  )
  return SimpleNamespace(models=[SimpleNamespace(artifact=artifact)])


def test_bmwv6_chunked_bundle_is_ready(tmp_path):
  bundle = _bmwv6_bundle()
  artifact = bundle.models[0].artifact
  (tmp_path / f"{artifact.fileName}.chunkmanifest").write_text("17")
  for chunk in artifact.chunks:
    (tmp_path / chunk.fileName).write_bytes(b"model")

  assert bundle_artifacts_ready(bundle, tmp_path)


def test_bmwv6_missing_chunk_is_not_ready(tmp_path):
  bundle = _bmwv6_bundle()
  artifact = bundle.models[0].artifact
  (tmp_path / f"{artifact.fileName}.chunkmanifest").write_text("17")
  for chunk in artifact.chunks[:-1]:
    (tmp_path / chunk.fileName).write_bytes(b"model")

  assert not bundle_artifacts_ready(bundle, tmp_path)


def test_bmwv6_wrong_manifest_count_is_not_ready(tmp_path):
  bundle = _bmwv6_bundle()
  artifact = bundle.models[0].artifact
  (tmp_path / f"{artifact.fileName}.chunkmanifest").write_text("16")
  for chunk in artifact.chunks:
    (tmp_path / chunk.fileName).write_bytes(b"model")

  assert not bundle_artifacts_ready(bundle, tmp_path)
