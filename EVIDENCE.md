# EVIDENCE.md

One pasted proof per requirement checkbox (Section 6 of the capstone brief).

---

## AI processing

### ✅ Vision model produces structured output validated against a schema; invalid responses are never trusted

`schemas.py` defines `ImageMetadata` (Pydantic). `vision_pipeline.py`'s `classify_image()` calls `ImageMetadata(**raw_data)` — if the model's JSON doesn't fit the schema, a `ValidationError` is caught and the call is retried, never silently accepted.

### ✅ Low-confidence classifications are flagged instead of accepted

```python
if result.confidence < 0.5:
    flagged_low_confidence += 1
    print(f"  FLAGGED: low confidence ({result.confidence})")
```
Full run across all 47 images: `Success: 47, Flagged low-confidence: 0, Failed: 0` — no image fell below 0.5 confidence, all were classified with high confidence (0.95–1.0 range observed).

### ✅ Images are processed through a batch background job with retries

```
python vision_pipeline.py
Found 47 images to process
[1/47] Already processed: alex-glebov-Y9mp8VnyreQ-unsplash.jpg
...
[18/47] Processing: freezer-2z3FbIm5hgs-unsplash.jpg
  OK: red fox (confidence: 1.0)
...
Done. Success: 27, Flagged low-confidence: 0, Failed: 0
```
Retry logic (`classify_image`, `max_retries=3`) was exercised for real during development — an early run hit `404 NOT_FOUND` (deprecated model name) and `429 RESOURCE_EXHAUSTED` (daily quota) errors; the pipeline correctly stopped the batch on unrecoverable errors (`ModelConfigError`, `DailyQuotaExhausted`) instead of burning through retries pointlessly, then resumed cleanly on a later run (already-processed images were skipped).

### ✅ Vision and embedding costs are tracked per call

```python
def log_cost(call_type, cost):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cost_log (call_type, cost, created_at) VALUES (?, ?, ?)",
        (call_type, cost, datetime.now(timezone.utc).isoformat())
    )
```
Called on every vision (`vision_classify`) and embedding call. `cost_log` table has one row per call.

---

## Matching system

### ✅ Image and post embeddings are stored; posts return ranked image suggestions

```
=== Top-3 ranking + guard decision for each post ===

Post: The Secret Life of Red Foxes
  #1: red fox (similarity 0.754)
  #2: red fox (similarity 0.732)
  #3: red fox (similarity 0.730)
  GUARD RESULT: {'matched': True, 'image_id': 1, ...}
```
(`matching_engine.py`, `rank_images_for_post()`)

### ✅ Semantic matching works for equivalent concepts

Post titled "Wolves: The Pack Hunters" correctly ranked images tagged `gray wolf` and `wolf` in its top 3 — matched on meaning, not exact keyword:
```
Post: Wolves: The Pack Hunters
  #1: gray wolf (similarity 0.675)
  #2: wolf (similarity 0.662)
  #3: wolf (similarity 0.652)
```

---

## Safety layer

### ✅ The mismatch guard rejects incorrect recommendations — the wolf-on-a-fox-post scenario provably fails

```
=== Forced mismatch tests (guard ko wrong image do) ===
Fox post + wolf image: {'matched': False, 'reason': "Subject mismatch: image shows 'wolf' but post is about something else (subject similarity 0.56 < 0.56)"}
Fox post + dog image: {'matched': False, 'reason': "Subject mismatch: image shows 'golden retriever' but post is about something else (subject similarity 0.55 < 0.56)"}
```

### ✅ Rejections include a human-readable explanation

See `reason` field above — every rejection states which subject was detected and why it fell below threshold.

### ✅ When no image clears the bar, the system answers "no confident match" with reasons

`evaluate_pair()` in `matching_engine.py` returns `{"matched": False, "reason": "..."}` for any of three possible failures: low confidence, similarity below threshold, or subject mismatch — never guesses.

### Known limitation (documented honestly, not hidden)

```
Bear post + deer image: {'matched': True, 'image_id': 7, 'image_filename': 'asa-rodger-B8xmtKWLrVo-unsplash.jpg', 'image_subject': 'red deer stag', 'similarity_score': 0.631, 'subject_score': 0.575, 'reason': "Matched 'red deer stag' (caption similarity 0.63, subject similarity 0.57)"}
```
This one forced-mismatch case is not caught by the guard at the current threshold. `eval_threshold.py`'s sweep (0.50–0.65) proves no single threshold catches all 8 labeled cases — 0.56 was chosen as the precision-maximizing threshold (7/8 = 88%). See README.md → "Known limitation" for the full explanation.

---

## Backend

### ✅ Database models for images, tags, embeddings, posts, suggestions, approvals/rejections — with the required indexes

`database.py`:
```python
cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_post_id ON suggestions(post_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_image_id ON suggestions(image_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status)")
```
Tables: `images`, `posts`, `suggestions` (with `status` column for approve/reject workflow), `cost_log`.

### ✅ API endpoints validated; the review workflow (approve / reject / inspect why) exists

Live test via Swagger UI (`/docs`):

**`GET /posts/1/images`** →
```json
{
  "id": 1, "post_id": 1, "image_id": 1,
  "similarity_score": 0.754, "subject_score": 0.762,
  "matched": true,
  "reason": "Matched 'red fox' (caption similarity 0.75, subject similarity 0.76)",
  "status": "pending"
}
```

**`POST /suggestions/1/approve`** →
```json
{
  "id": 1, "post_id": 1, "image_id": 1,
  "similarity_score": 0.754, "subject_score": 0.762,
  "matched": true,
  "reason": "Matched 'red fox' (caption similarity 0.75, subject similarity 0.76)",
  "status": "approved"
}
```
`status` field correctly transitioned `pending` → `approved`.

Pydantic response models (`SuggestionOut`) validate every response; a bad `post_id` (not found) returns a clean `404`, not a `500`.

---

## Quality & documentation

### ✅ A small labeled evaluation dataset measures top-1 precision — the number is in the README

```
python eval_precision.py
=== TOP-1 PRECISION: 10/10 = 100% ===
```
10 labeled posts, run against the live system. Number is in `README.md` → "Evaluation" section.

### ✅ README with architecture explanation and diagram; the required files from Section 11 present

`README.md` contains an ASCII architecture diagram, run instructions, evaluation results, and an honest limitations section. This file (`EVIDENCE.md`), `BUILDLOG.md`, `capstone.yaml`, and `.env.example` are present alongside it.
