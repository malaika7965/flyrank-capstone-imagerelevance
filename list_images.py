"""Sirf yeh dikhata hai DB mein kaunsi images hain, kis subject/category ke saath."""
from database import get_connection

conn = get_connection()
rows = conn.execute("SELECT id, filename, subject, category FROM images ORDER BY id").fetchall()
conn.close()

print(f"Total images: {len(rows)}\n")
for r in rows:
    print(f"  id={r['id']:<3} subject='{r['subject']}' category='{r['category']}' file={r['filename']}")
