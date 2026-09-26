# V6 evidence-control hardening review

Baseline: `37818613a4b7c2a49c0b497e9812d28a940b2ca1`

This change set is a targeted hardening pass over the existing Protocol 6.0 runtime. It does not introduce a parallel IR, does not reinterpret static reference media as execution proof, and does not claim real video or real Codex-agent validation.

## First-principles invariants

1. Frozen source bytes, versions and hashes remain authoritative.
2. A request or dispatch receipt is not proof that an external action completed.
3. UNKNOWN is not terminal and must keep its concurrency slot until reconciliation.
4. A downstream state transition must not proceed after an upstream dependency becomes stale.
5. Failed recovery must retain the evidence required for the next recovery attempt.
6. Static keyframes may validate a planned focus state, but temporal rack focus and color/emotion execution require real-media observation.
7. Material color, lighting and post-grade remain separate responsibilities.

## Changes

- Harden transaction journals against cleanup-path spoofing, cross-transaction backup reuse, partial rollback and swallowed journal failures.
- fsync parent directories for atomic replacement/unlink durability on the POSIX transaction store.
- Treat nested restore failure as transaction poisoning and prevent later writes from committing.
- Count V6 UNKNOWN agent work as active until reconciliation.
- Recheck dependencies at READY, DISPATCHING, RESULT_SUBMITTED, VALIDATING, REVIEW_REQUIRED and ACCEPTED gates.
- Reject empty acceptance plans, empty shot scopes and empty/malformed sequence decisions.
- Add focus-track start/end boundaries to keyframe sampling.
- Derive source-bound keyframe review obligations for rack focus, lighting/color intent, material palette, grading plan and existing performance context.
- Preserve `POST_PRODUCTION_NOT_MODEL_PARAMETER` for post-grade requirements.
- Keep the video-prompt-compiler control source and image-prompt-optimizer mirror byte-identical.

## Adversarial tests

The checked-in focused tests cover:

- rollback I/O failure and later recovery;
- spoofed journal cleanup path;
- transaction/backup identity mismatch;
- full write-set validation before restore;
- nested savepoint recovery ordering;
- swallowed child rollback failure;
- swallowed journal-write failure;
- process-death recovery;
- concurrent thread/process writers;
- UNKNOWN specialist/reviewer concurrency accounting;
- forward dependency TOCTOU guards;
- empty acceptance-set fail-closed behavior;
- rack-focus source binding;
- cross-shot focus leakage;
- color/emotion review without identity or drama rewriting;
- post-grade remaining a post-production obligation.

The focused suite was previously executed against the reviewed source candidate with 77/77 passing. That result is not a substitute for this repository's complete native test suite.

## Remaining release gates

Before merge/release, run:

```bash
python audit/v6-hardening/run_tests.py
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python ai-comic-drama-workflow/scripts/run_tests.py
python ai-comic-drama-workflow/scripts/package_suite.py --workspace . --out dists
```

Then validate real host dispatch/reconciliation, actual image/video outputs, selected takes, assembly and final video acceptance.

Open risk: CANCEL_REQUESTED still does not itself prove that an external agent or generation task terminated. A cancel-request -> reconciliation -> confirmed-terminal host protocol should be implemented before treating cancellation as proof of released external capacity.
