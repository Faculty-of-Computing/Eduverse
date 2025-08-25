from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import init_db, get_db
from datetime import datetime
import sqlite3
import os
import secrets
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your-secret-key'

# Configure file upload settings
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Check if file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
init_db()

# Custom filter for formatting datetime
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    if value == 'now':
        return datetime.now().strftime(format)
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime(format) if value else ''
    except (ValueError, TypeError):
        return value

# Home page route
@app.route('/')
def index():
    return render_template('index.html')

# User profile page
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('index'))
    return render_template('profile.html', user=user)

# User registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        db = get_db()
        try:
            db.execute('INSERT INTO users (firstname, lastname, email, password, role) VALUES (?, ?, ?, ?, ?)',
                       (firstname, lastname, email, password, role))
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('User already exists.', 'error')
    return render_template('register.html')

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            if user['role'] == 'instructor':
                return redirect(url_for('instructor_dashboard'))
            return redirect(url_for('student_dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

# User logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Student dashboard
@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    enrolled_courses = db.execute('SELECT c.id, c.title, c.image_path, e.milestones FROM courses c '
                                  'INNER JOIN enrollments e ON c.id = e.course_id WHERE e.user_id = ?',
                                  (session['user_id'],)).fetchall()
    progress_data = {}
    for course in enrolled_courses:
        milestones = set(course['milestones'].split(',') if course['milestones'] else [])
        topics = db.execute('SELECT heading FROM topics WHERE course_id = ? ORDER BY topic_index', (course['id'],)).fetchall()
        total_milestones = 1 + len(topics)
        progress = (len(milestones) / total_milestones) * 100 if total_milestones > 0 else 0
        progress_data[course['id']] = {
            'title': course['title'],
            'progress': progress,
            'image_path': course['image_path']
        }
    return render_template('student_dashboard.html', user=user, progress_data=progress_data)

# View student submissions
@app.route('/submissions')
def submissions():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    submissions = db.execute('SELECT s.*, c.title AS course_title FROM submissions s '
                             'JOIN courses c ON s.course_id = c.id '
                             'WHERE s.user_id = ?', (session['user_id'],)).fetchall()
    return render_template('submissions.html', submissions=submissions)

# List available courses
@app.route('/courses')
def courses():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    courses = db.execute('SELECT * FROM courses').fetchall()
    enrolled_courses = db.execute('SELECT course_id, milestones FROM enrollments WHERE user_id = ?',
                                  (session['user_id'],)).fetchall()
    enrolled_milestones = {c['course_id']: c['milestones'].split(',') if c['milestones'] else [] for c in enrolled_courses}
    topics = {course['id']: [t['heading'] for t in db.execute('SELECT heading FROM topics WHERE course_id = ? ORDER BY topic_index', (course['id'],)).fetchall()] for course in courses}
    return render_template('courses.html', courses=courses, enrolled_milestones=enrolled_milestones, topics=topics)

# Course detail page
@app.route('/course/<int:course_id>')
def course_detail(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    enrollment = db.execute('SELECT milestones FROM enrollments WHERE user_id = ? AND course_id = ?',
                            (session['user_id'], course_id)).fetchone()
    milestones = enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else []
    topics = db.execute('SELECT heading FROM topics WHERE course_id = ? ORDER BY topic_index', (course_id,)).fetchall()
    topics = [t['heading'] for t in topics]
    total_milestones = 1 + len(topics)
    progress = (len(milestones) / total_milestones) * 100 if total_milestones > 0 else 0
    return render_template('course_detail.html', course=course, milestones=milestones, progress=progress, topics=topics)

# Topic page for a course
@app.route('/course/<int:course_id>/topic/<int:topic_index>')
def topic_page(course_id, topic_index):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    enrollment = db.execute('SELECT milestones FROM enrollments WHERE user_id = ? AND course_id = ?',
                            (session['user_id'], course_id)).fetchone()
    milestones = set(enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else [])
    topic = db.execute('SELECT heading, content FROM topics WHERE course_id = ? AND topic_index = ?',
                       (course_id, topic_index)).fetchone()
    if not course or not topic:
        flash('Invalid topic selection.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))
    current_topic = topic['heading']
    topic_content = topic['content'] or 'No content available for this topic.'
    topics = db.execute('SELECT heading FROM topics WHERE course_id = ? ORDER BY topic_index', (course_id,)).fetchall()
    topics = [t['heading'] for t in topics]
    next_index = topic_index + 1 if topic_index + 1 < len(topics) else None
    if current_topic not in milestones:
        milestones.add(current_topic)
        db.execute('UPDATE enrollments SET milestones = ? WHERE user_id = ? AND course_id = ?',
                   (','.join(milestones), session['user_id'], course_id))
        db.commit()
    return render_template('topic.html', course=course, topic=current_topic, topic_content=topic_content,
                           topic_index=topic_index, next_index=next_index, milestones=milestones, course_id=course_id)

# Enroll in a course
@app.route('/enroll/<int:course_id>')
def enroll(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    db.execute('INSERT OR IGNORE INTO enrollments (user_id, course_id, milestones) VALUES (?, ?, ?)',
               (session['user_id'], course_id, ''))
    db.commit()
    return redirect(url_for('topic_page', course_id=course_id, topic_index=0))

# Update course milestone
@app.route('/update_milestone/<int:course_id>/<string:milestone>', methods=['POST'])
def update_milestone(course_id, milestone):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    enrollment = db.execute('SELECT milestones FROM enrollments WHERE user_id = ? AND course_id = ?',
                            (session['user_id'], course_id)).fetchone()
    milestones = set(enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else [])
    if milestone not in milestones:
        milestones.add(milestone)
        db.execute('UPDATE enrollments SET milestones = ? WHERE user_id = ? AND course_id = ?',
                   (','.join(milestones), session['user_id'], course_id))
        db.commit()
    return redirect(url_for('course_detail', course_id=course_id))

# Submit course assignment
@app.route('/assignment/<int:course_id>', methods=['GET', 'POST'])
def assignment(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('student_dashboard'))
    if request.method == 'POST':
        submission = request.form['submission']
        try:
            db.execute('INSERT INTO submissions (user_id, course_id, submission_text) VALUES (?, ?, ?)',
                       (session['user_id'], course_id, submission))
            enrollment = db.execute('SELECT milestones FROM enrollments WHERE user_id = ? AND course_id = ?',
                                    (session['user_id'], course_id)).fetchone()
            milestones = set(enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else [])
            if 'Assignment Submitted' not in milestones:
                milestones.add('Assignment Submitted')
                db.execute('UPDATE enrollments SET milestones = ? WHERE user_id = ? AND course_id = ?',
                           (','.join(milestones), session['user_id'], course_id))
            db.commit()
            flash('Assignment submitted for review!', 'success')
            return redirect(url_for('course_detail', course_id=course_id))
        except sqlite3.Error:
            db.rollback()
            flash('Failed to submit assignment.', 'error')
    return render_template('assignment.html', course_id=course_id, course=course)

# Instructor dashboard
@app.route('/instructor_dashboard', methods=['GET', 'POST'])
def instructor_dashboard():
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    db = get_db()
    if request.method == 'POST':
        if 'submission_id' in request.form and 'feedback' in request.form and 'grade' in request.form:
            submission_id = request.form['submission_id']
            feedback = request.form['feedback']
            grade = request.form['grade']
            try:
                db.execute('UPDATE submissions SET feedback = ?, graded_by = ?, grade = ? WHERE id = ?',
                           (feedback, session['user_id'], grade, submission_id))
                db.commit()
                flash('Feedback and grade submitted!', 'success')
            except sqlite3.Error:
                db.rollback()
                flash('Failed to submit feedback.', 'error')
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    courses = db.execute('SELECT * FROM courses WHERE instructor_id = ?', (session['user_id'],)).fetchall()
    submissions = db.execute('''
        SELECT s.id, s.user_id, s.course_id, s.submission_text, s.submitted_at, s.feedback, s.grade,
        u.firstname || ' ' || u.lastname AS student_name, c.title AS course_title
        FROM submissions s
        JOIN users u ON s.user_id = u.id
        JOIN courses c ON s.course_id = c.id
        WHERE s.course_id IN (SELECT id FROM courses WHERE instructor_id = ?)
        AND s.feedback IS NULL
    ''', (session['user_id'],)).fetchall()
    return render_template('instructor_dashboard.html', user=user, courses=courses, submissions=submissions)

# Create a new course
@app.route('/create_course', methods=['GET', 'POST'])
def create_course():
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        topics = request.form['topics']
        instructor_id = session['user_id']
        topic_list = [t.strip() for t in topics.split(',') if t.strip()]
        image_path = None
        video_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{secrets.token_hex(8)}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_path = os.path.join('uploads', unique_filename).replace('\\', '/')
        if 'video' in request.files:
            file = request.files['video']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{secrets.token_hex(8)}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                video_path = os.path.join('uploads', unique_filename).replace('\\', '/')
        db = get_db()
        try:
            db.execute('INSERT INTO courses (title, description, video_url, video_path, instructor_id, topics, image_path) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (title, description, None, video_path, instructor_id, topics, image_path))
            course_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            for index, topic in enumerate(topic_list):
                db.execute('INSERT INTO topics (course_id, topic_index, heading, content) VALUES (?, ?, ?, ?)',
                           (course_id, index, topic, ''))
            db.commit()
            flash('Course created successfully!', 'success')
            return redirect(url_for('instructor_dashboard'))
        except sqlite3.Error:
            db.rollback()
            flash('Failed to create course.', 'error')
    return render_template('create_course.html')

# Manage courses
@app.route('/manage_courses', methods=['GET', 'POST'])
def manage_courses():
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    db = get_db()
    if request.method == 'POST':
        if 'delete_course' in request.form:
            course_id = request.form['delete_course']
            course = db.execute('SELECT image_path, video_path FROM courses WHERE id = ?', (course_id,)).fetchone()
            if course and course['image_path']:
                try:
                    os.remove(os.path.join('static', course['image_path']))
                except OSError:
                    pass
            if course and course['video_path']:
                try:
                    os.remove(os.path.join('static', course['video_path']))
                except OSError:
                    pass
            db.execute('DELETE FROM courses WHERE id = ? AND instructor_id = ?', (course_id, session['user_id']))
            db.execute('DELETE FROM topics WHERE course_id = ?', (course_id,))
            db.commit()
            flash('Course deleted!', 'success')
        elif 'title' in request.form:
            title = request.form['title']
            description = request.form['description']
            topics = request.form['topics']
            course_id = request.form.get('course_id')
            instructor_id = session['user_id']
            topic_list = [t.strip() for t in topics.split(',') if t.strip()]
            image_path = None
            video_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{secrets.token_hex(8)}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    image_path = os.path.join('uploads', unique_filename).replace('\\', '/')
                    old_course = db.execute('SELECT image_path FROM courses WHERE id = ?', (course_id,)).fetchone()
                    if old_course and old_course['image_path']:
                        try:
                            os.remove(os.path.join('static', old_course['image_path']))
                        except OSError:
                            pass
            if 'video' in request.files:
                file = request.files['video']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{secrets.token_hex(8)}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    video_path = os.path.join('uploads', unique_filename).replace('\\', '/')
                    old_course = db.execute('SELECT video_path FROM courses WHERE id = ?', (course_id,)).fetchone()
                    if old_course and old_course['video_path']:
                        try:
                            os.remove(os.path.join('static', old_course['video_path']))
                        except OSError:
                            pass
            try:
                update_query = 'UPDATE courses SET title = ?, description = ?, video_url = ?, instructor_id = ?, topics = ?'
                params = [title, description, None, instructor_id, topics]
                if image_path:
                    update_query += ', image_path = ?'
                    params.append(image_path)
                if video_path:
                    update_query += ', video_path = ?'
                    params.append(video_path)
                update_query += ' WHERE id = ?'
                params.append(course_id)
                db.execute(update_query, params)
                db.execute('DELETE FROM topics WHERE course_id = ?', (course_id,))
                for index, topic in enumerate(topic_list):
                    db.execute('INSERT INTO topics (course_id, topic_index, heading, content) VALUES (?, ?, ?, ?)',
                               (course_id, index, topic, ''))
                db.commit()
                flash('Course updated!', 'success')
            except sqlite3.Error:
                db.rollback()
                flash('Failed to update course.', 'error')
    courses = db.execute('SELECT * FROM courses WHERE instructor_id = ?', (session['user_id'],)).fetchall()
    return render_template('manage_courses.html', courses=courses)

# Manage course topics
@app.route('/manage_topics')
@app.route('/manage_topics/<int:course_id>')
def manage_topics(course_id=None):
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    db = get_db()
    if course_id is None:
        courses = db.execute('SELECT * FROM courses WHERE instructor_id = ?', (session['user_id'],)).fetchall()
        return render_template('select_course_for_topics.html', courses=courses)
    else:
        topics = db.execute('SELECT t.id, t.course_id, t.topic_index, t.heading, t.content, c.title AS course_title '
                            'FROM topics t JOIN courses c ON t.course_id = c.id WHERE t.course_id = ? AND c.instructor_id = ?',
                            (course_id, session['user_id'])).fetchall()
        if not topics:
            flash('Topic not found or you do not have permission.', 'error')
            return redirect(url_for('manage_topics'))
        return render_template('manage_topics.html', topics=topics)

# Edit a topic's content
@app.route('/edit_topic/<int:topic_id>', methods=['GET', 'POST'])
def edit_topic(topic_id):
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    db = get_db()
    topic = db.execute('SELECT t.*, c.title AS course_title FROM topics t JOIN courses c ON t.course_id = c.id WHERE t.id = ? AND c.instructor_id = ?',
                       (topic_id, session['user_id'])).fetchone()
    if not topic:
        flash('Topic not found or you do not have permission.', 'error')
        return redirect(url_for('manage_topics'))
    if request.method == 'POST':
        content = request.form['content']
        try:
            db.execute('UPDATE topics SET content = ? WHERE id = ?', (content, topic_id))
            db.commit()
            flash('Topic content updated!', 'success')
            return redirect(url_for('manage_topics', course_id=topic['course_id']))
        except sqlite3.Error:
            db.rollback()
            flash('Failed to update topic content.', 'error')
    return render_template('edit_topic.html', topic=topic)

# Run app
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)