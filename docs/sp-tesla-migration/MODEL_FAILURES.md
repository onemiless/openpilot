# Model synchronization failure cases before implementation

Final user choice: official Chestnut, no old PCIe runner. CTV3M, original CTM,
BMV6, LM must be identified from a freshly hashed official manifest.

Failures: stale/recompiled24 manifest mistaken for recompiled40; CTM replaced by
CTMV2; matching name/ref mistaken for matching bytes; incomplete chunks activated;
corrupt local/remote chunk reused; Range response silently appends a full file;
partial retry loses completed content; bundle hash inconsistent with chunk hashes;
model/runtime tinygrad or warp ABI mismatch; absent Chestnut reported ready; menu
visibility or completed download reported as inference success; physical PCIe used
instead of requested Chestnut; fallback invalid after load failure.

Acceptance: record manifest bytes/hash, exact names/refs, every chunk and full SHA,
reuse/download/transferred bytes and count, atomic complete activation. Verify menu,
loader, warp, metadata, actual Chestnut USB enumeration and bounded inference on
C3. Missing physical Chestnut remains an explicit hardware dependency, while files,
configuration, small-model fallback and DM development proceed.
