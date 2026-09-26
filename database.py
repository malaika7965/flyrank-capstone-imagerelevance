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
            matched BOOLEAN,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_log (
            id INTEGER PRIMARY KEY,
            call_type TEXT,
            cost REAL,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized: capstone.db")


if __name__ == "__main__":
    init_db()
