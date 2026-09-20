# Recovery

Retry only the smallest evidenced layer. Record each failure signature and attempt. Attempts one
through three may retry when safe; the fourth identical failure becomes a blocking decision.

When an upstream artifact changes, invalidate only its downstream dependency closure and reject
approvals whose context fingerprint no longer matches. Preserve previous revisions in `.history/`.
Never use a platform workaround to alter Canonical facts or conceal unsupported capability.

For v1/v2, require an explicit migration choice. Non-destructive migration snapshots the old tree,
validates and carries eligible phase 1–6 artifacts, and invalidates phases 7–13. Read-only writes no
Schema 3.0 business artifact. Copy-new leaves the original project unchanged.

Use `revise` with one shot, scene or appearance asset scope when available. An unchanged image
can reuse a receipt after renewed approval; a requested creative image revision has its own token.
`export --draft` builds a detached inspection snapshot with a fresh draft report and hash index;
it does not advance the original project, approve stale files, or provide a resumable project copy.
