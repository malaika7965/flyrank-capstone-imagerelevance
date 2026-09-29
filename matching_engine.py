import os
import json
import time
import numpy as np
from datetime import datetime, timezone
from google import genai
from dotenv import load_dotenv
from database import get_connection, init_db

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

EMBED_MODEL = "gemini-embedding-001"

# ---- Guard ke thresholds (eval data se tune honge) ----
SIMILARITY_THRESHOLD = 0.55   # post vs image caption: is se kam ho to reject
SUBJECT_THRESHOLD = 0.56      # post vs image ka subject label: is se kam ho to reject
                               # eval_threshold.py se tune kiya (8-case set, 88% precision — 1 known edge-case: bear/deer)
MIN_CONFIDENCE = 0.5          # vision model ka confidence: is se kam ho to reject

SAMPLE_POSTS = [
    {"id": 1, "title": "The Secret Life of Red Foxes", "content": "Red foxes are cunning, adaptable animals found across forests and cities alike. Their orange-red fur and bushy tail make them instantly recognizable."},
    {"id": 2, "title": "Wolves: The Pack Hunters", "content": "Gray wolves are apex predators that live and hunt in packs. Unlike solitary foxes, wolves rely on teamwork to take down large prey."},
    {"id": 3, "title": "Why Dogs Are Man's Best Friend", "content": "Dogs have been domesticated companions to humans for thousands of years, valued for their loyalty and trainability."},
    {"id": 4, "title": "Bears in the Wild", "content": "Bears are large, powerful mammals found in forests and mountains, known for their strength and hibernation habits."},
    {"id": 5, "title": "The Graceful Deer", "content": "Deer are gentle herbivores known for their speed and the antlers grown by males, often seen grazing in meadows at dawn."},
    {"id": 6, "title": "Corgi Puppies and Their Big Personalities", "content": "Corgis are small herding dogs with short legs and famously expressive faces. Despite their size, they were bred to herd cattle in Wales."},
    {"id": 7, "title": "The Black Pug's Charm", "content": "Pugs are small companion dogs known for their wrinkled faces, curled tails, and affectionate, comedic personalities."},
    {"id": 8, "title": "Two Dogs Playing in the Park", "content": "Dogs running together in an open park, chasing each other with pure joy — a familiar sight for any dog owner."},
    {"id": 9, "title": "The Red Deer Stag's Majestic Antlers", "content": "The red deer stag is known for its impressive branching antlers, shed and regrown every year, used in displays of dominance."},
    {"id": 10, "title": "More Adventures of the Red Fox", "content": "Foxes are solitary hunters, most active at dawn and dusk, using sharp hearing to locate small prey hidden beneath snow or grass."},
]

_subject_cache = {}


def log_cost(call_type, cost=0.0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO cost_log (call_type, cost, created_at) VALUES (?, ?, ?)",
        (call_type, cost, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def get_embedding(text):
    result = client.models.embed_content(model=EMBED_MODEL, contents=text)
    log_cost("embedding", 0.0)
    time.sleep(1)
    return result.embeddings[0].values


def get_embedding_with_retry(text, max_retries=3):
    """Retry wrapper: agar API call fail ho (network/rate-limit), 3 baar try karta hai
    beech mein exponential backoff (2s, 4s, 8s) ke saath, taake batch job crash na ho."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return get_embedding(text)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 2s, 4s, 8s
                print(f"    Attempt {attempt} failed ({e}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"    Attempt {attempt} failed ({e}), no more retries left.")
    raise last_error


def cosine_similarity(vec1, vec2):
    a, b = np.array(vec1), np.array(vec2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def get_subject_embedding(subject):
    if subject not in _subject_cache:
        _subject_cache[subject] = get_embedding(subject)
    return _subject_cache[subject]


def generate_image_embeddings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, caption FROM images WHERE embedding IS NULL")
    rows = cursor.fetchall()
    print(f"Generating embeddings for {len(rows)} images...")
    failed = []
    for row in rows:
        try:
            emb = get_embedding_with_retry(row["caption"])
            cursor.execute("UPDATE images SET embedding = ? WHERE id = ?", (json.dumps(emb), row["id"]))
            conn.commit()
            print(f"  Embedded image {row['id']}")
        except Exception as e:
            print(f"  Failed to embed image {row['id']} after retries: {e}")
            failed.append(row["id"])
    conn.close()
    if failed:
        print(f"  WARNING: {len(failed)} image(s) failed after all retries: {failed}")


def generate_post_embeddings():
    conn = get_connection()
    cursor = conn.cursor()
    for post in SAMPLE_POSTS:
        cursor.execute("SELECT id FROM posts WHERE id = ?", (post["id"],))
        if cursor.fetchone():
            continue
        try:
            emb = get_embedding_with_retry(post["title"] + ". " + post["content"])
            cursor.execute(
                "INSERT INTO posts (id, title, content, embedding) VALUES (?, ?, ?, ?)",
                (post["id"], post["title"], post["content"], json.dumps(emb))
            )
            conn.commit()
            print(f"  Embedded post: {post['title']}")
        except Exception as e:
            print(f"  Failed to embed post {post['id']} after retries: {e}")
    conn.close()


def load_post(post_id):
    conn = get_connection()
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return post


def rank_images_for_post(post_id, top_k=3):
    """Post ke liye images ko similarity ke hisab se rank karta hai"""
    post = load_post(post_id)
    if not post or not post["embedding"]:
        return []
    post_emb = json.loads(post["embedding"])

    conn = get_connection()
    images = conn.execute("SELECT * FROM images WHERE embedding IS NOT NULL").fetchall()
    conn.close()

    scored = [(cosine_similarity(post_emb, json.loads(img["embedding"])), img) for img in images]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def evaluate_pair(post, image, caption_score):
    """MISMATCH GUARD: ek (post, image) jodi ko check karta hai - accept ya reject + wajah"""
    if image["confidence"] is not None and image["confidence"] < MIN_CONFIDENCE:
        return {"matched": False, "reason": f"Low confidence classification ({image['confidence']:.2f} < {MIN_CONFIDENCE})"}

    if caption_score < SIMILARITY_THRESHOLD:
        return {"matched": False, "reason": f"Similarity below threshold ({caption_score:.2f} < {SIMILARITY_THRESHOLD})"}

    # Meaning-based subject check: image ka subject label post se semantically related hai?
    post_emb = json.loads(post["embedding"])
    subject_score = cosine_similarity(post_emb, get_subject_embedding(image["subject"]))
    if subject_score < SUBJECT_THRESHOLD:
        return {
            "matched": False,
            "reason": f"Subject mismatch: image shows '{image['subject']}' but post is about something else (subject similarity {subject_score:.2f} < {SUBJECT_THRESHOLD})"
        }

    return {
        "matched": True,
        "image_id": image["id"],
        "image_filename": image["filename"],
        "image_subject": image["subject"],
        "similarity_score": round(caption_score, 3),
        "subject_score": round(subject_score, 3),
        "reason": f"Matched '{image['subject']}' (caption similarity {caption_score:.2f}, subject similarity {subject_score:.2f})"
    }


def find_best_image_for_post(post_id):
    post = load_post(post_id)
    ranked = rank_images_for_post(post_id, top_k=1)
    if not ranked:
        return {"matched": False, "reason": "No embedded images/post available"}
    score, image = ranked[0]
    return evaluate_pair(post, image, score)


def force_candidate(post_id, subject_keyword):
    """Probe 3: kisi khaas subject wali image ko zabardasti candidate bana kar guard se guzaro"""
    post = load_post(post_id)
    conn = get_connection()
    image = conn.execute("SELECT * FROM images WHERE embedding IS NOT NULL AND LOWER(subject) LIKE ? LIMIT 1",
                         (f"%{subject_keyword.lower()}%",)).fetchone()
    conn.close()
    if not image:
        return {"matched": False, "reason": f"No image with subject '{subject_keyword}' found"}
    score = cosine_similarity(json.loads(post["embedding"]), json.loads(image["embedding"]))
    return evaluate_pair(post, image, score)


if __name__ == "__main__":
    init_db()
    print("=== Generating embeddings (jo pehle se hain wo skip hongi) ===")
    generate_image_embeddings()
    generate_post_embeddings()

    print("\n=== Top-3 ranking + guard decision for each post ===")
    for post in SAMPLE_POSTS:
        print(f"\nPost: {post['title']}")
        for rank, (score, img) in enumerate(rank_images_for_post(post["id"]), 1):
            print(f"  #{rank}: {img['subject']} (similarity {score:.3f})")
        print(f"  GUARD RESULT: {find_best_image_for_post(post['id'])}")

    print("\n=== Forced mismatch tests (guard ko wrong image do) ===")
    print("Fox post + wolf image:", force_candidate(1, "wolf"))
    print("Fox post + dog image:", force_candidate(1, "retriever"))
    print("Bear post + deer image:", force_candidate(4, "deer"))