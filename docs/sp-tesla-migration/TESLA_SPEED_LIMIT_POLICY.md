# Tesla speed-limit policy extraction

Before edits, cover: mph/kmh threshold rounding, no-valid-limit fallback,
upper/lower saturation, other-brand fixed target behavior, compatibility imports,
and actual SpeedLimitAssist target assignment. This is not DynamicAutoStock ACC
ownership; no speed-offset semantics change is authorized here. Move the discrete
Tesla table and resolution into the Tesla domain, keep one small generic dispatch.
Capture the existing mapping before edits and compare after. No new unit tests.
