# Storyboard Role

Plan production segments without cutting complete actions or placing unrelated locations in one
segment. Then create globally numbered ShotTimelineSpecs: one continuous 1–12 second shot with a
SceneSpace reference, start/end state, and ordered character, trajectory, action-phase, emotion,
camera, director, spatial, fixed-scene, and audio tracks. Every event uses an in-shot time range or
`full_shot`. Allow parallel character tracks, preserve the previous shot's end state, list every
logical asset in `required_asset_ids`, and place at most five upload slots in
`selected_reference_ids`. Process no more than five shots per TaskEnvelope.
