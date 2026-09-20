# Quality Gates

Story review checks source coverage, causal logic, character state, core relationship/motivation,
episode capacity, and hook continuity. Asset review checks style, identity, costume, locations,
props, reference provenance, and prompt/media status. Spatial lock checks coordinates, factions,
positions, paths, interaction distances, fixed elements, and axis. Storyboard review checks in-shot
times, parallel tracks, action phases, emotion curves, director intent, and cross-shot state handoff.
The asset, spatial, and storyboard gates always require explicit approve/revise decisions. Media
review distinguishes static prompt validity from actual file evidence.

Return `status: approved` only when no blocking finding remains. Use `needs_decision` for ending,
core result, identity, relationship, motivation, world-rule, rights, or material platform-impact
changes. Include changed and unaffected artifact IDs.

Final validation must fail closed on stale context, missing standalone prompts, broken hashes,
unsupported shot duration/reference counts, unrecorded degradation, or media claims without files.
Technical video checks cover stream/codec metadata, expected duration and aspect, full decode,
audio-track presence, black-frame detection, and freeze-frame findings. Dialogue sync, subtitle safe
area, performance, and story continuity remain explicit human-review fields.
