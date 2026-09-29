"""
Top-1 Precision Eval Script
============================
Brief ki requirement (Section 7 + Probe 5): 10+ posts, har ek ka "sahi" image
labeled, aur top-1 precision measure karo.

Yahan "sahi" ka matlab hai: system ka #1 ranked image ka subject, expected
keyword se match karta hai (exact image id nahi, kyunke corpus mein kai
images same subject share karti hain — e.g. do fox images. Dono equally
"sahi" hain agar model fox post ko koi bhi fox image de).
"""
from matching_engine import rank_images_for_post, SAMPLE_POSTS

# Har post ke liye: expected subject keyword (top-1 image ke subject mein hona chahiye)
EXPECTED_SUBJECT_KEYWORD = {
    1: "fox",
    2: "wolf",
    3: "dog",        # generic "Why Dogs" post - koi bhi dog subject sahi hai
    4: "bear",
    5: "deer",        # generic "Graceful Deer" post - koi bhi deer subject sahi hai
    6: "corgi",
    7: "pug",
    8: "two dogs",
    9: "deer stag",
    10: "fox",
}


def main():
    print("=== Top-1 Precision Eval (10 posts) ===\n")
    correct = 0
    total = 0
    rows = []

    for post in SAMPLE_POSTS:
        post_id = post["id"]
        expected = EXPECTED_SUBJECT_KEYWORD.get(post_id)
        if expected is None:
            continue

        ranked = rank_images_for_post(post_id, top_k=1)
        if not ranked:
            print(f"  Post {post_id} ({post['title']}): NO EMBEDDING FOUND - skip")
            continue

        score, image = ranked[0]
        got_subject = image["subject"].lower()
        is_correct = expected.lower() in got_subject
        total += 1
        if is_correct:
            correct += 1

        status = "OK" if is_correct else "WRONG"
        print(f"  [{status}] Post {post_id} '{post['title'][:40]}' -> top-1='{image['subject']}' (expected contains '{expected}')")
        rows.append((post_id, is_correct))

    precision = correct / total * 100 if total else 0
    print(f"\n=== TOP-1 PRECISION: {correct}/{total} = {precision:.0f}% ===")
    print("(Yeh number README.md mein 'Evaluation' section mein likhna hai)")


if __name__ == "__main__":
    main()