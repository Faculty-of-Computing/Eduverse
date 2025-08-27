import sqlite3
from flask import g

DATABASE = "database.db"

def init_db():
    with sqlite3.connect(DATABASE, timeout=10, check_same_thread=False) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Enable WAL for concurrency
        c.execute("PRAGMA journal_mode=WAL;")

        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firstname TEXT,
            lastname TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            video_url TEXT,
            video_path TEXT, 
            instructor_id INTEGER,
            topics TEXT,
            image_path TEXT,
            FOREIGN KEY (instructor_id) REFERENCES users(id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS enrollments (
            user_id INTEGER,
            course_id INTEGER,
            milestones TEXT,
            PRIMARY KEY (user_id, course_id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            course_id INTEGER,
            submission_text TEXT,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            feedback TEXT,
            graded_by INTEGER,
            grade INTEGER
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            topic_index INTEGER,
            heading TEXT,
            content TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )''')

        conn.commit()


def get_db():
    """Get a database connection for the current request"""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """Close the database connection at the end of a request"""
    db = g.pop("db", None)

    if db is not None:
        db.close()
