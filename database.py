import sqlite3

def init_db():
    conn = sqlite3.connect('database.db', timeout= 5)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
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
    conn.close()

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn