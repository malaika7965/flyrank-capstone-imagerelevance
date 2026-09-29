import sqlite3


def get_connection():
    conn = sqlite3.connect("capstone.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            subject TEXT,
            category TEXT,
            attributes TEXT,
            caption TEXT,
            confidence REAL,
            embedding TEXT,
            processed_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY,
            post_id INTEGER,
            image_id INTEGER,
            similarity_score REAL,
            subject_score REAL,
            matched BOOLEAN,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    # Migration: agar tumhara capstone.db pehle se bana hua hai (subject_score column ke bina),
    # to yeh usme add kar dega. Naye DB mein CREATE TABLE se hi ban jata hai, isliye error ignore karte hain.
    try:
        cursor.execute("ALTER TABLE suggestions ADD COLUMN subject_score REAL")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already hai

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_log (
            id INTEGER PRIMARY KEY,
            call_type TEXT,
            cost REAL,
            created_at TEXT
        )
    """)

    # Required indexes: suggestions ko post_id aur image_id se dhoondna
    # bohat common hoga (Review API mein), isliye index lagaya
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_post_id ON suggestions(post_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_image_id ON suggestions(image_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status)")

    conn.commit()
    conn.close()
    print("Database initialized: capstone.db")


if __name__ == "__main__":
    init_db()