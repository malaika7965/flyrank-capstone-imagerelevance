"""
Eval script: har threshold (0.50 se 0.65) test karta hai 8 labeled cases par,
aur best threshold batata hai jo sabse zyada cases sahi classify kare.

Yeh naye vision/embedding calls nahi karta jahan tak ho sake -
post aur image embeddings already DB mein cached hain, sirf
subject-label embeddings generate hote hain (kam calls, sasta).
"""
import json
from matching_engine import (
    load_post,
    rank_images_for_post,
    get_subject_embedding,
    cosine_similarity,
    get_connection,
)

# ---- Labeled eval set: (post_id, forced_subject_keyword ya None, expected_matched) ----
# None matlab: top-1 ranked image use karo (yeh REAL case hai, jo sahi match hona chahiye)
# keyword diya matlab: forced mismatch test (yeh REJECT hona chahiye)
EVAL_CASES = [
    (1, None, True),            # Fox post -> apni fox image (sahi match)
    (2, None, True),            # Wolf post -> apni wolf image (sahi match)
    (3, None, True),            # Dog post -> golden retriever image (sahi match)
    (4, None, True),            # Bear post -> apni bear image (sahi match)
    (5, None, True),            # Deer post -> apni deer image (sahi match)
    (1, "wolf", False),         # Fox post + wolf image (galat, reject hona chahiye)
    (1, "retriever", False),    # Fox post + dog image (galat, reject hona chahiye)
    (4, "deer", False),         # Bear post + deer image (galat, reject hona chahiye)
]


def get_case_subject_score(post_id, forced_keyword):
    """Ek eval case ke liye subject_score nikalta hai."""
    post = load_post(post_id)
    post_emb = json.loads(post["embedding"])

    if forced_keyword is None:
        ranked = rank_images_for_post(post_id, top_k=1)
        if not ranked:
            return None
        _, image = ranked[0]
    else:
        conn = get_connection()
        image = conn.execute(
            "SELECT * FROM images WHERE embedding IS NOT NULL AND LOWER(subject) LIKE ? LIMIT 1",
            (f"%{forced_keyword.lower()}%",),
        ).fetchone()
        conn.close()
        if not image:
            return None

    return cosine_similarity(post_emb, get_subject_embedding(image["subject"])), image["subject"]


def main():
    print("=== Step 1: Har case ka subject_score nikal rahe hain ===\n")
    results = []
    for post_id, forced_keyword, expected in EVAL_CASES:
        score, subject = get_case_subject_score(post_id, forced_keyword)
        kind = f"FORCED (+ '{forced_keyword}')" if forced_keyword else "REAL top-1"
        print(f"  Post {post_id} [{kind}] -> image subject='{subject}' | score={score:.3f} | expected_matched={expected}")
        results.append((post_id, forced_keyword, score, expected))

    print("\n=== Step 2: Thresholds 0.50 se 0.65 tak test kar rahe hain ===\n")
    best_threshold = None
    best_correct = -1
    all_scores = []

    for t in range(50, 66):
        threshold = t / 100
        correct = 0
        wrong_cases = []
        for post_id, forced_keyword, score, expected in results:
            predicted = score >= threshold
            if predicted == expected:
                correct += 1
            else:
                label = f"Post {post_id}" + (f"+{forced_keyword}" if forced_keyword else "(real)")
                wrong_cases.append(label)

        precision = correct / len(results) * 100
        all_scores.append((threshold, correct, wrong_cases))
        marker = ""
        if correct > best_correct:
            best_correct = correct
            best_threshold = threshold
            marker = "  <== ab tak best"
        wrong_str = f" | galat: {', '.join(wrong_cases)}" if wrong_cases else " | sab sahi!"
        print(f"  threshold={threshold:.2f}: {correct}/{len(results)} sahi ({precision:.0f}%){wrong_str}{marker}")

    print(f"\n=== NATIJA: Best threshold = {best_threshold:.2f} ({best_correct}/{len(results)} = {best_correct/len(results)*100:.0f}% precision) ===")

    # Agar 100% possible nahi hai, yeh batayega
    if best_correct < len(results):
        print(f"\nNOTE: {len(results) - best_correct} case(s) kisi bhi single threshold se sahi classify nahi ho sakte -")
        print("iska matlab hai subject_score akela kaafi nahi hai in edge-cases ke liye.")
        print("Agla step: 'category' field ya keyword-overlap check add karna guard mein.")


if __name__ == "__main__":
    main()
