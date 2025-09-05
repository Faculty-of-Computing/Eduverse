import psycopg2
import psycopg2.extras
from flask import g

# ==============================
# Database Configuration
# ==============================
render_env = {
    "dbname": "eduverse_bl6a",
    "user": "eduverse_bl6a_user",
    "password": "fMGTDzHwIHMuPhKL3371tis8iEzi6XNj",
    "host": "dpg-d2ra9ngdl3ps73ctlue0-a.oregon-postgres.render.com",
    "port": 5432
}

local_env = {
    "dbname": "eduverse",
    "user": "postgres",
    "password": "kemfon",
    "host": "localhost",
    "port": 5432
}


def get_db_connection():
    """Try Render DB first, fallback to local."""
    try:
        return psycopg2.connect(**render_env)
    except Exception as e:
        print("⚠️ Render DB connection failed, using local DB:", e)
        return psycopg2.connect(**local_env)


def init_db():
    """Initialize all tables if they don't exist."""
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # Users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            firstname VARCHAR(100),
            lastname VARCHAR(100),
            email VARCHAR(255) UNIQUE,
            password TEXT,
            role VARCHAR(50)
        )
    """)

    # Courses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            video_url TEXT,
            video_path TEXT,
            instructor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            topics TEXT,
            image_path TEXT
        )
    """)

    # Enrollments
    cur.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
            milestones TEXT,
            PRIMARY KEY (user_id, course_id)
        )
    """)

    # Submissions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
            submission_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            feedback TEXT,
            graded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            grade INTEGER
        )
    """)

    # Topics
    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id SERIAL PRIMARY KEY,
            course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
            topic_index INTEGER,
            heading VARCHAR(255),
            content TEXT
        )
    """)

    # PDF Resources
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdf_resources (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_by INTEGER REFERENCES users(id) ON DELETE CASCADE,
            course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.close()
    conn.close()


def get_db():
    """Get DB connection for Flask request context."""
    if "db" not in g:
        try:
            g.db = psycopg2.connect(
                **render_env, cursor_factory=psycopg2.extras.DictCursor
            )
        except Exception as e:
            print("⚠️ Render DB unavailable, switching to local:", e)
            g.db = psycopg2.connect(
                **local_env, cursor_factory=psycopg2.extras.DictCursor
            )
    return g.db


def close_db(e=None):
    """Close DB after request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def execute_query(query, params=None, fetch=False):
    """Helper to run queries safely."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, params or [])
    result = cur.fetchall() if fetch else None
    conn.commit()
    cur.close()
    return result
