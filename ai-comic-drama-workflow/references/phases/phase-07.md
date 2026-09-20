# Phase 07 — Visual Assets

Require visual style and aspect ratio first. Define style, character, scene, and applicable prop
assets with stable IDs, versions, provenance, continuity constraints, and forbidden inheritance.
Prompt-ready does not mean an image was generated. End with explicit human approval or revision.

Use the supplied asset-plan Schema: assets[].asset_type must be style-reference, character-reference,
scene-reference, prop-reference, or other. Character assets identify entity_ids and wardrobe version.
Codex-native selection dispatches one media_job at a time. Read codex-imagegen.md only when dispatched.
Files are imported by Kernel; file checks and human visual approval remain separate.

For reference-guided asset revisions, assets[].reference_bindings uses the reference-binding Schema.
Bind the retained identity or prop files with their actual hashes; unapproved revision candidates use
approval_ref: null and remain subject to the asset review gate. The media job carries these bindings
to the host, and the result must report the same files actually passed to image generation.
