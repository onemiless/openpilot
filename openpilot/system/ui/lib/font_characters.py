from importlib.resources import files
import ast
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def runtime_ui_characters() -> set[str]:
  characters: set[str] = set()
  for source in Path(str(files("openpilot.selfdrive.ui"))).rglob("*.py"):
    if "tests" in source.parts:
      continue
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
      if isinstance(node, ast.Constant) and isinstance(node.value, str):
        characters.update(c for c in node.value if ord(c) > 127)
  return characters


def fallback_font_characters(language: str, extra_characters: str = "") -> set[str]:
  """Collect every glyph requested when loading a language fallback font."""
  translations_dir = files("openpilot.selfdrive.ui").joinpath("translations")
  characters = set(map(chr, range(32, 127))) | set(extra_characters)
  characters.update(translations_dir.joinpath(f"app_{language}.po").read_text(encoding="utf-8"))

  # Onroad alerts originate in selfdrived, outside of the normal UI PO extraction.
  from openpilot.selfdrive.ui.onroad.alert_localizer import localized_alert_characters
  characters.update(localized_alert_characters(language))
  if language in ("zh-CHS", "zh-CHT"):
    characters.update(runtime_ui_characters())
  characters.difference_update({"\n", "\r", "\t"})
  return characters
