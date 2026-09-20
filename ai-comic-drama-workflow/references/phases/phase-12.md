# Phase 12 — Voice, Subtitle, and Edit

Produce dialogue, voice, subtitle, SFX, music, and edit timing from approved shots. Generate or
render only with an authorized executable capability; otherwise deliver scripts and an edit package.

Use edit-plan.schema.json. dialogue_table entries require line_id, speaker_id, text, start_s and
explicit end_s or duration_s. Do not put lines only in a differently named dialogue array.
timeline order controls the edit; each item includes shot_id, in_s and duration_s. Supported
transition_in types are cut or dissolve with duration_s. Never silently substitute other transitions.
Local execution trims, assembles, mixes selected voices and muxes timed subtitles. Report scripts,
unmixed audio assets, mixed previews and final generated video as distinct states.
