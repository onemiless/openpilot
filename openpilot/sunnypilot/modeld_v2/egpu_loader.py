from collections.abc import Callable
from typing import TypeVar


# Measured C3XL/UT3G model loads can exceed MR.ONE's original 60 second limit.
# Keep a bounded margin for cold starts and USB scheduling variance.
C3XL_MODEL_LOAD_TIMEOUT = 120

T = TypeVar("T")


def finish_model_loading(model: T | None, chestnut: bool, load_small: Callable[[], T]) -> tuple[T, T | None, Exception | None]:
  """Select the active model and preload a small fallback when available.

  A missing small fallback must not discard a successfully loaded Chestnut
  model. It remains fatal when no active model exists at all.
  """
  if model is None:
    small_model = load_small()
    return small_model, small_model, None

  if chestnut:
    try:
      return model, load_small(), None
    except Exception as error:
      return model, None, error

  return model, None, None


def require_runtime_fallback[T](small_model: T | None, error: Exception) -> T:
  if small_model is None:
    raise RuntimeError("chestnut failed and small fallback unavailable") from error
  return small_model
