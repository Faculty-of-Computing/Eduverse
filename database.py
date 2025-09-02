from dotenv import load_dotenv
load_dotenv()
import psycopg2
import psycopg2.extras
from flask import g
import os
import urllib.parse as urlparse


DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("RENDER_DATABASE_URL")

if DATABASE_URL:
    urlparse.uses_netloc.append("postgres")
    url = urlparse.urlparse(DATABASE_URL)
    env = {
        "dbname": url.path[1:],
        "user": url.username,
        "password": url.password,
        "host": url.hostname,
        "port": url.port or 5432,
    }
else:
    env = {
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", 5432),
    }


def get_db_connection():
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing PostgreSQL env variables: {missing}")
    return psycopg2.connect(**env)


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        firstname VARCHAR(100),
        lastname VARCHAR(100),
        email VARCHAR(255) UNIQUE,
        password TEXT,
        role VARCHAR(50)
    )''')

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

    cur.execute('''CREATE TABLE IF NOT EXISTS enrollments (
        user_id INTEGER REFERENCES users(id),
        course_id INTEGER REFERENCES courses(id),
        milestones TEXT,
        PRIMARY KEY (user_id, course_id)
    )''')

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
    if "db" not in g:
        g.db = psycopg2.connect(**env, cursor_factory=psycopg2.extras.DictCursor)
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
