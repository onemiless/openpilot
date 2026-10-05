#!/usr/bin/env python3
"""Build the Chinese UI subset from a verified local source font."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--source', type=Path, required=True)
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--receipt', type=Path, required=True)
  args = parser.parse_args()
  from fontTools import __version__, subset
  from openpilot.system.ui.lib.font_characters import fallback_font_characters

  root = Path(__file__).resolve().parents[2]
  spec = json.loads((root/'docs/sp-tesla-migration/font-source.json').read_text())
  source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
  if source_hash != spec['source_sha256']:
    raise SystemExit('Source font SHA256 does not match font-source.json')
  if args.output.resolve() == args.source.resolve() or args.receipt.resolve() in (args.output.resolve(), args.source.resolve()):
    raise SystemExit('Source, output and receipt must be distinct files')
  chars = fallback_font_characters('zh-CHS')
  options = subset.Options()
  options.recalc_timestamp = False
  font = subset.load_font(str(args.source), options)
  subsetter = subset.Subsetter(options=options)
  subsetter.populate(text=''.join(sorted(chars)))
  subsetter.subset(font)
  required = {ord(c) for c in chars if 32 <= ord(c) < 127 or 0x3400 <= ord(c) <= 0x9FFF}
  missing = required - set(font.getBestCmap())
  if missing:
    raise SystemExit(f'Missing glyphs: {sorted(missing)}')
  args.output.parent.mkdir(parents=True, exist_ok=True)
  fd, temporary = tempfile.mkstemp(prefix=args.output.name+'.', dir=args.output.parent)
  os.close(fd)
  try:
    subset.save_font(font, temporary, options)
    os.chmod(temporary, 0o644)
    os.replace(temporary, args.output)
  finally:
    Path(temporary).unlink(missing_ok=True)
  result = {'source_sha256': source_hash, 'fonttools': __version__,
            'requested_codepoints': len(chars), 'verified_codepoints': len(required),
            'glyph_set_sha256': hashlib.sha256(''.join(sorted(chars)).encode()).hexdigest(),
            'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}
  args.receipt.parent.mkdir(parents=True, exist_ok=True)
  args.receipt.write_text(json.dumps(result, indent=2)+'\n')
  print(json.dumps(result))


if __name__ == '__main__':
  main()
