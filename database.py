import psycopg2
import psycopg2.extras
from flask import g
import os

RENDER_DB = os.getenv("RENDER_DATABASE_URL")
LOCAL_DB = os.getenv("LOCAL_DATABASE_URL")


def get_db_connection():
    db_url = RENDER_DB or LOCAL_DB
    return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.DictCursor)


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
        g.db = get_db_connection()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
