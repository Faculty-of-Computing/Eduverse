from dotenv import load_dotenv
load_dotenv()
import psycopg2
import psycopg2.extras
from flask import g
import os
import urllib.parse as urlparse


# Database configuration: use Render DATABASE_URL if available, else local settings
RENDER_DATABASE_URL = os.getenv("RENDER_DATABASE_URL")
if RENDER_DATABASE_URL:
    urlparse.uses_netloc.append("postgres")
    url = urlparse.urlparse(RENDER_DATABASE_URL)
    env = {
        "dbname": "eduverse_bl6a",
        "user": "eduverse_bl6a_user",
        "password": "fMGTDzHwIHMuPhKL3371tis8iEzi6XNj",
        "host": "dpg-d2ra9ngdl3ps73ctlue0-a.oregon-postgres.render.com",
        "port": 5432

    }
else:
    env = {
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST"),
        "port": os.getenv("POSTGRES_PORT", 5432)
    }


def get_db_connection():
    """Create a new PostgreSQL connection"""
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing PostgreSQL env variables: {missing}")
    return psycopg2.connect(**env)


def init_db():
    """Initialize the PostgreSQL database with required tables"""
    conn = get_db_connection()
    cur = conn.cursor()

    # Users table
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        firstname VARCHAR(100),
        lastname VARCHAR(100),
        email VARCHAR(255) UNIQUE,
        password TEXT,
        role VARCHAR(50)
    )''')

    # Courses table
    cur.execute('''CREATE TABLE IF NOT EXISTS courses (
        id SERIAL PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        video_url TEXT,
        video_path TEXT, 
        instructor_id INTEGER REFERENCES users(id),
        topics TEXT,
        image_path TEXT
    )''')

    # Enrollments table
    cur.execute('''CREATE TABLE IF NOT EXISTS enrollments (
        user_id INTEGER REFERENCES users(id),
        course_id INTEGER REFERENCES courses(id),
        milestones TEXT,
        PRIMARY KEY (user_id, course_id)
    )''')

    # Submissions table
    cur.execute('''CREATE TABLE IF NOT EXISTS submissions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        course_id INTEGER REFERENCES courses(id),
        submission_text TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        feedback TEXT,
        graded_by INTEGER REFERENCES users(id),
        grade INTEGER
    )''')

    # Topics table
    cur.execute('''CREATE TABLE IF NOT EXISTS topics (
        id SERIAL PRIMARY KEY,
        course_id INTEGER REFERENCES courses(id),
        topic_index INTEGER,
        heading VARCHAR(255),
        content TEXT
    )''')

    conn.commit()
    cur.close()
    conn.close()


def get_db():
    """Get a PostgreSQL connection for the current request"""
    if "db" not in g:
        g.db = psycopg2.connect(**env, cursor_factory=psycopg2.extras.DictCursor)
    return g.db


def close_db(e=None):
    """Close the database connection at the end of a request"""
    db = g.pop("db", None)
    if db is not None:
        db.close()
