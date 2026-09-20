# Runtime Usage

Use a Python 3.12+ project virtual environment with `jsonschema==4.26.0` installed. Document and
image inspection need the `documents` and `media` optional dependencies. From the package root use
`PYTHONPATH=src .venv/bin/python -m ai_comic_drama_workflow`, or install the package in that environment.
Do not automatically install Blender or silently substitute a paid API.

```text
ai-comic-drama init INPUT... --project PROJECT_DIR [--title TITLE]
ai-comic-drama run PROJECT_DIR
ai-comic-drama submit PROJECT_DIR --result agent-result.json
ai-comic-drama add PROJECT_DIR INPUT... [--input-type TYPE]
ai-comic-drama resume PROJECT_DIR --decision decision.json
ai-comic-drama revise PROJECT_DIR STAGE_ID [--shot-id ID | --scene-id ID | --asset-id ID]
ai-comic-drama import-video PROJECT_DIR --shot-id ID --file VIDEO
ai-comic-drama status PROJECT_DIR
ai-comic-drama validate PROJECT_DIR [--final]
ai-comic-drama export PROJECT_DIR [--draft]
ai-comic-drama doctor
```

The CLI is internal machinery. In normal use, Codex loops over `run`, reads the emitted request,
asks the user only when required, submits one result, and resumes.

`revise` keeps old revisions in `.history`, marks the selected stage and every dependent stage as
invalidated, removes affected approvals, and returns the first new decision or TaskEnvelope.
Use `add` when a scan is unreadable or the user supplies missing novel/script/storyboard text; it
registers the new hashes, invalidates dependent context, and reopens intake without deleting history.

`doctor` reports local parsing, OCR, image/video inspection, TTS, render, and provider status.
`available` is evidence for that named capability only; it is never evidence that a media task ran.

New projects place business artifacts directly under the 13 numbered folders in `stages/`.
`runtime/` contains envelopes, draft results, and failures; `.history/` contains prior revisions and
migration snapshots. When `run` detects v1/v2, `resume` accepts exactly one of non-destructive migrate,
read-only, or copy-new. Migration archives the original tree before writing Schema 3.0 artifacts and rejects
all old stage 7–13 approvals.

Shot scope targets shot_timeline_specs; scene scope targets spatial_blocking. Asset scope is limited
to character/style appearance in asset_plan or asset_generation_or_prompt; geometry needs spatial
revision. Unchanged image inputs can reuse imported candidates but never bypass renewed required review.
Native image tasks count against an explicit cumulative dispatch budget, including retries. Host
uncertain responses must request a decision, not silently retry. Draft export never completes a project.
