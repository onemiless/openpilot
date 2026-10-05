# Reproducible Chinese UI font

Failure modes identified before implementation: unverified source font, missing new UI glyphs, host-specific input paths, output timestamps causing nondeterminism, silently changing the tool version, and incomplete writes. Font creation is a build step, not a live UI mutation.

Use `tools/sp_tesla_e2e/build_chinese_font.py` with a local full Noto Sans CJK SC font. Its SHA256 must match `font-source.json`. The source URL is provenance only; the command does not fetch mutable network content. FontTools is supplied by the development environment; its exact version is recorded in the output receipt. Rebuild with the same version when byte-for-byte identity is required.

The script reuses the UI's runtime glyph collector, keeps the source font timestamp, verifies CJK/ASCII coverage, writes atomically, and emits source/output hashes. Store the built font through Git LFS and publish its object before deploying a release. A clean checkout must retrieve the real font, not its LFS pointer.
