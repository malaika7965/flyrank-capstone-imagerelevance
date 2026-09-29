import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from pydantic import ValidationError

from schemas import ImageMetadata
from database import get_connection, init_db

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

IMAGES_DIR = "images"

PROMPT = """Look at this image and describe it as JSON with exactly these fields:
{
  "subject": "the main thing in the image, e.g. 'red fox'",
  "category": "broad category, e.g. 'animal'",
  "attributes": ["short descriptive words", "like these"],
  "caption": "one sentence describing the image",
  "confidence": 0.0 to 1.0, how sure you are about the subject identification
}
Return ONLY the JSON, no extra text, no markdown fences."""

VISION_MODEL = "gemini-3.5-flash-lite"  # gemini-2.5-flash-lite ab available nahi (Google ne khud yeh suggest kiya)


class DailyQuotaExhausted(Exception):
    """Jab poori din ki quota khatam ho jaye - retry karna fizool hai, poori batch job rok do."""
    pass


class ModelConfigError(Exception):
    """Model ka naam hi ghalat/unavailable hai - retry karne se kuch nahi badlega, turant ruk jao."""
    pass


def log_cost(call_type, cost):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cost_log (call_type, cost, created_at) VALUES (?, ?, ?)",
        (call_type, cost, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def classify_image(image_path, max_retries=3):
    """Ek image ko Gemini se bhejta hai, structured metadata wapas laata hai.
    Agar DAILY quota khatam ho (retry karne se fayda nahi, kal tak available nahi hogi),
    turant DailyQuotaExhausted raise karta hai - koi retry nahi, koi fizool request nahi."""
    for attempt in range(1, max_retries + 1):
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                    PROMPT
                ]
            )

            # Gemini free tier: cost track karte hain (0 hai free tier mein, but habit ke liye)
            log_cost("vision_classify", 0.0)

            text = response.text.strip()
            # Kabhi kabhi AI ```json ... ``` mein wrap kar deta hai, use hatate hain
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            raw_data = json.loads(text)
            validated = ImageMetadata(**raw_data)  # schema check
            return validated

        except Exception as e:
            error_str = str(e)
            # Daily quota khatam = retry se koi fayda nahi (yeh 24h baad hi reset hogi)
            if "RESOURCE_EXHAUSTED" in error_str and "PerDay" in error_str:
                raise DailyQuotaExhausted(error_str)
            # Model hi exist nahi karta / unavailable hai - retry karne se kuch nahi badlega
            if "404" in error_str and "NOT_FOUND" in error_str:
                raise ModelConfigError(error_str)

            print(f"  Attempt {attempt} failed for {image_path.name}: {e}")
            if attempt < max_retries:
                time.sleep(2)
            else:
                return None


def run_vision_pipeline():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    image_files = list(Path(IMAGES_DIR).glob("*.jpg")) + list(Path(IMAGES_DIR).glob("*.jpeg")) + list(Path(IMAGES_DIR).glob("*.png"))
    print(f"Found {len(image_files)} images to process\n")

    success = 0
    flagged_low_confidence = 0
    failed = 0

    for i, image_path in enumerate(image_files, 1):
        # Agar pehle se process ho chuki hai, skip karo
        cursor.execute("SELECT id FROM images WHERE filename = ?", (image_path.name,))
        if cursor.fetchone():
            print(f"[{i}/{len(image_files)}] Already processed: {image_path.name}")
            continue

        print(f"[{i}/{len(image_files)}] Processing: {image_path.name}")
        try:
            result = classify_image(image_path)
        except DailyQuotaExhausted:
            print("\n  !! DAILY QUOTA KHATAM HO GAYI !!")
            print("  Yeh model 24 ghante baad reset hogi (Pacific Time ke hisab se).")
            print("  Jitni images process ho chuki hain woh DB mein save hain - dobara chalane pe skip ho jayengi.")
            print("  Kal (ya jab quota reset ho) yeh command dobara chalao: python vision_pipeline.py")
            break
        except ModelConfigError as e:
            print(f"\n  !! MODEL KA NAAM GHALAT/UNAVAILABLE HAI: {VISION_MODEL} !!")
            print(f"  Error: {e}")
            print("  vision_pipeline.py mein VISION_MODEL variable ko sahi model name se update karo, phir dobara chalao.")
            break

        if result is None:
            failed += 1
            print(f"  FAILED after retries")
            continue

        if result.confidence < 0.5:
            flagged_low_confidence += 1
            print(f"  FLAGGED: low confidence ({result.confidence})")

        cursor.execute("""
            INSERT INTO images (filename, subject, category, attributes, caption, confidence, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            image_path.name,
            result.subject,
            result.category,
            json.dumps(result.attributes),
            result.caption,
            result.confidence,
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        success += 1
        print(f"  OK: {result.subject} (confidence: {result.confidence})")

        time.sleep(1)  # politeness / free-tier rate limit ke liye

    conn.close()
    print(f"\nDone. Success: {success}, Flagged low-confidence: {flagged_low_confidence}, Failed: {failed}")


if __name__ == "__main__":
    run_vision_pipeline()