# BUILDLOG.md

Honest log of where AI (Claude) helped build this capstone, where it got things wrong, and what was changed as a result. Per the brief: "The AI wrote it" is not an answer — every decision below was reviewed and tested by running the actual code, not just accepted.

## What AI helped with

- Scaffolding `matching_engine.py`, `api.py`, and the guard logic (`evaluate_pair()`).
- Adding retry logic with exponential backoff to `matching_engine.py`'s embedding calls, and separately to `vision_pipeline.py`'s vision-classification calls.
- Adding database indexes (`post_id`, `image_id`, `status`) on the `suggestions` table.
- Writing the eval scripts (`eval_threshold.py`, `eval_precision.py`) to replace manual threshold-guessing with a data-driven sweep.
- Writing this documentation set (README, EVIDENCE, BUILDLOG, capstone.yaml, .env.example).

## Where AI was wrong, and what was changed

### 1. Guard threshold — started as a guess, fixed with data

The subject-similarity threshold started at `0.55`, was manually bumped to `0.60` after a false positive (bear post matched to a deer image), which then caused a false *negative* on a previously-correct match ("Why Dogs" → golden retriever). Manually guessing thresholds one at a time was unreliable and kept trading one error for another.

**Fix**: built `eval_threshold.py` to sweep every threshold from 0.50–0.65 against 8 labeled cases and report precision at each value. This found `0.56` as the best achievable threshold (7/8 = 88% precision), and also proved — with data, not a guess — that one edge case (bear post + red-deer-stag image) cannot be fixed by threshold alone, because its subject-similarity score (0.575) is actually higher than a legitimate match's score was at the time (0.572). This is documented as a known limitation in README.md rather than papered over.

### 2. Vision model name — hit a hard rate limit, then a deprecated model

The first `vision_pipeline.py` used a hardcoded model, `gemini-3.8-flash`, which turned out to have a **very restrictive 20-requests/day free-tier quota**. Worse, the original retry logic retried on *every* error type, including `429 RESOURCE_EXHAUSTED` daily-quota errors — meaning the retries themselves burned through the tiny remaining quota, causing 27 of 30 images to fail in one run even though only a handful of images actually needed processing that day.

**Fix**: added a `DailyQuotaExhausted` exception, detected specifically from the `"PerDay"` string in the API error, that aborts the whole batch immediately instead of retrying — so a quota hit costs one wasted attempt, not dozens.

Switched the model to `gemini-2.5-flash-lite`, expecting a more generous quota. This model then returned `404 NOT_FOUND — model no longer available to new users`. Google's own error message named the replacement: `gemini-3.5-flash-lite`. Switched again, and added a second exception type, `ModelConfigError`, so a permanent "model doesn't exist" error also aborts immediately instead of retrying 3 times per image for no reason.

**Lesson**: don't assume a model name or its quota — check for the actual error and let the code react to what the API says, not to an assumption baked in up front.

### 3. Eval labels were initially too narrow

When the corpus grew from 17 to 47 images, two of the 10 eval-set labels (`"retriever"` for the generic "Why Dogs" post, `"deer fawn"` for the generic "Graceful Deer" post) started failing — not because the guard got worse, but because a *different, equally-correct* image (a different dog, a different deer) now legitimately ranked #1. The original labels were too specific for posts that were written generically.

**Fix**: broadened the expected labels to `"dog"` and `"deer"` respectively, matching the actual generality of the post content. Precision returned to 10/10 = 100%.

## What was NOT blindly accepted

- Every retry-logic, threshold, and model change was verified by actually running the script and reading the real terminal output before moving on — not assumed to work from the code alone.
- The bear/deer guard limitation was investigated with data (`eval_threshold.py`'s sweep) rather than being threshold-tuned away or hidden; it's documented honestly in README.md instead.
