"""
Review API
==========
Brief ki requirement (Section 4 + 6): "A simple workflow to approve or reject
a suggested pairing and inspect why an image was selected or refused."

Chalane ka tareeqa:
    uvicorn api:app --reload
Phir browser mein: http://127.0.0.1:8000/docs (Swagger UI - test karne ke liye)
"""
import json
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from database import get_connection, init_db
from matching_engine import find_best_image_for_post, load_post, SAMPLE_POSTS

app = FastAPI(title="Image Matching Capstone - Review API")


# ---- Response/Request shapes (validation at the boundary) ----

class SuggestionOut(BaseModel):
    id: int
    post_id: int
    image_id: int | None
    similarity_score: float | None
    subject_score: float | None
    matched: bool
    reason: str
    status: str


class StatusUpdate(BaseModel):
    note: str | None = None


@app.on_event("startup")
def startup():
    init_db()


# ---- 1) Post ke liye suggestion generate + save karo ----

@app.get("/posts/{post_id}/images", response_model=SuggestionOut)
def get_suggestion_for_post(post_id: int):
    """Post ke liye best image suggest karta hai, DB mein save karta hai (status=pending),
    aur wapas deta hai. Agar pehle se ek pending/approved suggestion hai, wahi wapas milegi
    (dobara AI call nahi hoga)."""
    post = load_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    conn = get_connection()
    cursor = conn.cursor()

    # Agar already koi suggestion bani hui hai is post ke liye, wahi return karo
    existing = cursor.execute(
        "SELECT * FROM suggestions WHERE post_id = ? ORDER BY id DESC LIMIT 1", (post_id,)
    ).fetchone()
    if existing:
        conn.close()
        return _row_to_suggestion(existing)

    # Nahi to naya nikalo aur save karo
    result = find_best_image_for_post(post_id)
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO suggestions (post_id, image_id, similarity_score, subject_score, matched, reason, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (
        post_id,
        result.get("image_id"),
        result.get("similarity_score"),
        result.get("subject_score"),
        result.get("matched", False),
        result.get("reason", ""),
        now,
    ))
    conn.commit()
    new_id = cursor.lastrowid
    row = cursor.execute("SELECT * FROM suggestions WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return _row_to_suggestion(row)


# ---- 2) Ek suggestion inspect karo (kyun select/reject hua) ----

@app.get("/suggestions/{suggestion_id}", response_model=SuggestionOut)
def get_suggestion(suggestion_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")
    return _row_to_suggestion(row)


# ---- 3) Saari suggestions list karo (optionally status se filter) ----

@app.get("/suggestions", response_model=list[SuggestionOut])
def list_suggestions(status: str | None = None):
    conn = get_connection()
    if status:
        rows = conn.execute("SELECT * FROM suggestions WHERE status = ? ORDER BY id", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM suggestions ORDER BY id").fetchall()
    conn.close()
    return [_row_to_suggestion(r) for r in rows]


# ---- 4) Approve ----

@app.post("/suggestions/{suggestion_id}/approve", response_model=SuggestionOut)
def approve_suggestion(suggestion_id: int, body: StatusUpdate | None = None):
    return _update_status(suggestion_id, "approved")


# ---- 5) Reject ----

@app.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionOut)
def reject_suggestion(suggestion_id: int, body: StatusUpdate | None = None):
    return _update_status(suggestion_id, "rejected")


# ---- Helpers ----

def _update_status(suggestion_id, new_status):
    conn = get_connection()
    cursor = conn.cursor()
    existing = cursor.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")

    cursor.execute("UPDATE suggestions SET status = ? WHERE id = ?", (new_status, suggestion_id))
    conn.commit()
    row = cursor.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    conn.close()
    return _row_to_suggestion(row)


def _row_to_suggestion(row) -> SuggestionOut:
    return SuggestionOut(
        id=row["id"],
        post_id=row["post_id"],
        image_id=row["image_id"],
        similarity_score=row["similarity_score"],
        subject_score=row["subject_score"] if "subject_score" in row.keys() else None,
        matched=bool(row["matched"]),
        reason=row["reason"] or "",
        status=row["status"],
    )
