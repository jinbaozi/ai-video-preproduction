# Phase 09 — Spatiotemporal Storyboard

After storyboard depth and derived views are selected, plan globally ordered shots and produce at
most five ShotTimelineSpecs per task. Every character, camera, director, spatial, fixed-scene, and
audio event needs an in-shot time range or `full_shot`. Preserve cross-shot state handoff. Reference
images use 1–3 deterministic key moments per shot and require explicit fallback when unavailable.

Camera tracks require numeric world position and target, projection, lens/sensor, and interpolation.
World character tracks continue offscreen. Supply rotations and explicit joint targets for important
gestures; default proxy bodies cannot establish anatomical/action quality. Record prop positions and
ownership through prop_tracks. Static prompts use a single evaluated instant, not the entire action.
Kernel normalizes supported second-based drafts into authoritative rational frame keys plus derived
seconds. Do not edit one representation without updating the other. Continuous shot handoffs require
continuity.transition.type=continuous; time_jump/scene_change require a reason and approval_ref.
For dual-reference delivery, actual Blender keyframes plus approved identity images enter native
image generation. Finished raster storyboards require human approval; a whitebox is not a substitute.
