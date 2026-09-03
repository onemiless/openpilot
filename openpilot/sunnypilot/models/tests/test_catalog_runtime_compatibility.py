from pathlib import Path

from openpilot.sunnypilot.models.catalog_compat import (
  MODEL_URL, MODEL_URL_CHESTNUT, REQUIRED_JSON_VERSION, TINYGRAD_REF, catalog_matches_runtime,
)
from openpilot.sunnypilot.models.tinygrad_ref import get_tinygrad_ref


def test_vendored_tinygrad_ref_is_observable():
  marker = Path(__file__).parents[4] / "tinygrad_repo/TINYGRAD_REF"
  assert marker.read_text().strip() == TINYGRAD_REF
  assert get_tinygrad_ref() == TINYGRAD_REF


def test_catalogs_are_pinned_to_vendored_tinygrad_generation():
  assert REQUIRED_JSON_VERSION == 18
  assert MODEL_URL.endswith("driving_models_v21.json")
  assert MODEL_URL_CHESTNUT.endswith("driving_models_chestnut_v22.json")


def test_catalog_ref_must_match_runtime():
  assert catalog_matches_runtime({"tinygrad_ref": TINYGRAD_REF}, TINYGRAD_REF)
  assert not catalog_matches_runtime({"tinygrad_ref": "e837e367aac9e1a66e689f4f32ce20ca9367df13"}, TINYGRAD_REF)
  assert not catalog_matches_runtime({"tinygrad_ref": TINYGRAD_REF}, "e837e367aac9e1a66e689f4f32ce20ca9367df13")
  assert not catalog_matches_runtime({}, TINYGRAD_REF)
