TINYGRAD_REF = "66ee3cfb4f3a3908a6a20ddfbec7774ba7c09b4e"
REQUIRED_JSON_VERSION = 18

MODEL_URL = "https://raw.githubusercontent.com/sunnypilot/sunnypilot-models/refs/heads/gh-pages/docs/driving_models_v21.json"
MODEL_URL_CHESTNUT = "https://raw.githubusercontent.com/sunnypilot/sunnypilot-models/refs/heads/gh-pages/docs/driving_models_chestnut_v22.json"


def catalog_matches_runtime(json_data: dict, runtime_ref: str | None) -> bool:
  catalog_ref = json_data.get("tinygrad_ref")
  return bool(catalog_ref and runtime_ref and catalog_ref == runtime_ref == TINYGRAD_REF)
