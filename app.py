from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from database import init_db, get_db, close_db
from datetime import datetime
import psycopg2
import psycopg2.extras
import os
import secrets
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')

# Configure file upload settings (for images/videos in other routes)
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('cloud_name'),
    api_key=os.environ.get('api_key'),
    api_secret=os.environ.get('api_secret'),
    cloud_url=os.environ.get('cloud_url')
)

# Initialize DB connection before each request
@app.before_request
def before_request():
    init_db()

# Close DB connection after each request
@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Filter for formatting datetime
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    if value == 'now':
        return datetime.now().strftime(format)
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime(format) if value else ''
    except (ValueError, TypeError):
        return value


# PDF Management
@app.route('/pdfs')
def list_pdfs():
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT p.id, p.filename, p.file_path, p.uploaded_at,
               u.firstname || ' ' || u.lastname AS uploader,
               c.title AS course_title
        FROM pdf_resources p
        LEFT JOIN users u ON p.uploaded_by = u.id
        LEFT JOIN courses c ON p.course_id = c.id
        ORDER BY p.uploaded_at DESC
    """)
    pdfs = cur.fetchall()
    cur.close()
    return render_template("list_pdfs.html", pdfs=pdfs, role=session.get("role", "student"))

@app.route('/upload-pdf', methods=['GET', 'POST'])
def upload_pdf():
    if 'user_id' not in session or session['role'] != 'instructor':
        flash("Unauthorized", "danger")
        return redirect(url_for("list_pdfs"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, title FROM courses")
    courses = cur.fetchall()

    if request.method == 'POST':
        course_id = request.form.get("course_id")
        pdf_file = request.files.get("pdf_file")

        if not pdf_file or not course_id:
            flash("Course and PDF required", "danger")
            return redirect(url_for("upload_pdf"))

        filename = secure_filename(pdf_file.filename)
        unique_name = f"{secrets.token_hex(8)}_{filename}"
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        pdf_file.save(local_path)
        file_url = os.path.join('uploads', unique_name).replace('\\', '/')

        cur.execute("""
            INSERT INTO pdf_resources (filename, file_path, uploaded_by, uploaded_at, course_id)
            VALUES (%s, %s, %s, NOW(), %s)
        """, (filename, file_url, session['user_id'], course_id))
        db.commit()

        flash("PDF uploaded successfully!", "success")
        return redirect(url_for("list_pdfs"))

    cur.close()
    return render_template("upload_pdf.html", courses=courses)

@app.route('/view-pdf/<int:pdf_id>')
def view_pdf(pdf_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT file_path, filename FROM pdf_resources WHERE id = %s", (pdf_id,))
    pdf = cur.fetchone()
    cur.close()

    if not pdf or not pdf['file_path']:
        abort(404)

    # Redirect to Cloudinary URL
    return redirect(pdf['file_path'])

@app.route('/download-pdf/<int:pdf_id>')
def download_pdf(pdf_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT file_path, filename FROM pdf_resources WHERE id = %s", (pdf_id,))
    pdf = cur.fetchone()
    cur.close()

    if not pdf or not pdf['file_path']:
        abort(404)

    # Cloudinary handles downloads via the URL
    return redirect(pdf['file_path'])

@app.route('/delete-pdf/<int:pdf_id>', methods=['POST'])
def delete_pdf(pdf_id):
    if 'user_id' not in session or session['role'] != 'instructor':
        flash("Unauthorized", "danger")
        return redirect(url_for("list_pdfs"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT file_path FROM pdf_resources WHERE id = %s", (pdf_id,))
    pdf = cur.fetchone()

    if not pdf:
        flash("PDF not found", "danger")
        return redirect(url_for("list_pdfs"))

    # Delete from Cloudinary
    if pdf['file_path']:
        public_id = pdf['file_path'].split('/')[-1].split('.')[0]  # Extract public_id
        cloudinary.uploader.destroy(public_id, resource_type="raw")

    cur.execute("DELETE FROM pdf_resources WHERE id = %s", (pdf_id,))
    db.commit()
    cur.close()

    flash("PDF deleted successfully", "success")
    return redirect(url_for("list_pdfs"))

# home page
@app.route('/')
def index():
    return render_template('index.html')

# User profile page
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    cur.close()
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
        cur = db.cursor()
        try:
            cur.execute(
                'INSERT INTO users (firstname, lastname, email, password, role) VALUES (%s, %s, %s, %s, %s)',
                (firstname, lastname, email, password, role)
            )
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            db.rollback()
            flash('User already exists.', 'error')
        except psycopg2.Error as e:
            db.rollback()
            flash(f'Database error: {e}', 'error')
        finally:
            cur.close()

    return render_template('register.html')


# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        cur.close()
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
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    cur.execute('SELECT c.id, c.title, c.image_path, e.milestones FROM courses c INNER JOIN enrollments e ON c.id = e.course_id WHERE e.user_id = %s', (session['user_id'],))
    enrolled_courses = cur.fetchall()
    progress_data = {}
    for course in enrolled_courses:
        milestones = set(course['milestones'].split(',') if course['milestones'] else [])
        cur.execute('SELECT heading FROM topics WHERE course_id = %s ORDER BY topic_index', (course['id'],))
        topics = cur.fetchall()
        total_milestones = 1 + len(topics)
        progress = (len(milestones) / total_milestones) * 100 if total_milestones > 0 else 0
        progress_data[course['id']] = {
            'title': course['title'],
            'progress': progress,
            'image_path': course['image_path']
        }
    cur.close()
    return render_template('student_dashboard.html', user=user, progress_data=progress_data)

# View student submissions
@app.route('/submissions')
def submissions():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT s.*, c.title AS course_title FROM submissions s JOIN courses c ON s.course_id = c.id WHERE s.user_id = %s', (session['user_id'],))
    submissions = cur.fetchall()
    cur.close()
    return render_template('submissions.html', submissions=submissions)

# List available courses
@app.route('/courses')
def courses():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM courses')
    courses = cur.fetchall()
    cur.execute('SELECT course_id, milestones FROM enrollments WHERE user_id = %s', (session['user_id'],))
    enrolled_courses = cur.fetchall()
    enrolled_milestones = {c['course_id']: c['milestones'].split(',') if c['milestones'] else [] for c in enrolled_courses}
    topics = {}
    for course in courses:
        cur.execute('SELECT heading FROM topics WHERE course_id = %s ORDER BY topic_index', (course['id'],))
        topics[course['id']] = [t['heading'] for t in cur.fetchall()]
    cur.close()
    return render_template('courses.html', courses=courses, enrolled_milestones=enrolled_milestones, topics=topics)

# Course detail page
@app.route('/course/<int:course_id>')
def course_detail(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM courses WHERE id = %s', (course_id,))
    course = cur.fetchone()
    cur.execute('SELECT milestones FROM enrollments WHERE user_id = %s AND course_id = %s', (session['user_id'], course_id))
    enrollment = cur.fetchone()
    milestones = enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else []
    cur.execute('SELECT heading FROM topics WHERE course_id = %s ORDER BY topic_index', (course_id,))
    topics = [t['heading'] for t in cur.fetchall()]
    total_milestones = 1 + len(topics)
    progress = (len(milestones) / total_milestones) * 100 if total_milestones > 0 else 0
    cur.close()
    return render_template('course_detail.html', course=course, milestones=milestones, progress=progress, topics=topics)

# Topic page for a course
@app.route('/course/<int:course_id>/topic/<int:topic_index>')
def topic_page(course_id, topic_index):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM courses WHERE id = %s', (course_id,))
    course = cur.fetchone()
    cur.execute('SELECT milestones FROM enrollments WHERE user_id = %s AND course_id = %s', (session['user_id'], course_id))
    enrollment = cur.fetchone()
    milestones = set(enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else [])
    cur.execute('SELECT heading, content FROM topics WHERE course_id = %s AND topic_index = %s', (course_id, topic_index))
    topic = cur.fetchone()
    if not course or not topic:
        cur.close()
        flash('Invalid topic selection.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))
    current_topic = topic['heading']
    topic_content = topic['content'] or 'No content available for this topic.'
    cur.execute('SELECT heading FROM topics WHERE course_id = %s ORDER BY topic_index', (course_id,))
    topics = [t['heading'] for t in cur.fetchall()]
    next_index = topic_index + 1 if topic_index + 1 < len(topics) else None
    if current_topic not in milestones:
        milestones.add(current_topic)
        cur.execute('UPDATE enrollments SET milestones = %s WHERE user_id = %s AND course_id = %s',
                   (','.join(milestones), session['user_id'], course_id))
        db.commit()
    cur.close()
    return render_template('topic.html', course=course, topic=current_topic, topic_content=topic_content,
                           topic_index=topic_index, next_index=next_index, milestones=milestones, course_id=course_id)

# Enroll in a course
@app.route('/enroll/<int:course_id>')
def enroll(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('INSERT INTO enrollments (user_id, course_id, milestones) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING',
                   (session['user_id'], course_id, ''))
        db.commit()
    except psycopg2.Error:
        db.rollback()
    finally:
        cur.close()
    return redirect(url_for('topic_page', course_id=course_id, topic_index=0))

# Update course milestone
@app.route('/update_milestone/<int:course_id>/<string:milestone>', methods=['POST'])
def update_milestone(course_id, milestone):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT milestones FROM enrollments WHERE user_id = %s AND course_id = %s', (session['user_id'], course_id))
    enrollment = cur.fetchone()
    milestones = set(enrollment[0].split(',') if enrollment and enrollment[0] else [])
    if milestone not in milestones:
        milestones.add(milestone)
        cur.execute('UPDATE enrollments SET milestones = %s WHERE user_id = %s AND course_id = %s',
                   (','.join(milestones), session['user_id'], course_id))
        db.commit()
    cur.close()
    return redirect(url_for('course_detail', course_id=course_id))

# Submit course assignment
@app.route('/assignment/<int:course_id>', methods=['GET', 'POST'])
def assignment(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM courses WHERE id = %s', (course_id,))
    course = cur.fetchone()
    if not course:
        cur.close()
        flash('Course not found.', 'error')
        return redirect(url_for('student_dashboard'))
    if request.method == 'POST':
        submission = request.form['submission']
        try:
            cur.execute('INSERT INTO submissions (user_id, course_id, submission_text) VALUES (%s, %s, %s)',
                       (session['user_id'], course_id, submission))
            cur.execute('SELECT milestones FROM enrollments WHERE user_id = %s AND course_id = %s',
                                    (session['user_id'], course_id))
            enrollment = cur.fetchone()
            milestones = set(enrollment['milestones'].split(',') if enrollment and enrollment['milestones'] else [])
            if 'Assignment Submitted' not in milestones:
                milestones.add('Assignment Submitted')
                cur.execute('UPDATE enrollments SET milestones = %s WHERE user_id = %s AND course_id = %s',
                           (','.join(milestones), session['user_id'], course_id))
            db.commit()
            flash('Assignment submitted for review!', 'success')
            cur.close()
            return redirect(url_for('course_detail', course_id=course_id))
        except psycopg2.Error:
            db.rollback()
            flash('Failed to submit assignment.', 'error')
    cur.close()
    return render_template('assignment.html', course_id=course_id, course=course)

# Instructor dashboard
@app.route('/instructor_dashboard', methods=['GET', 'POST'])
def instructor_dashboard():
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        if 'submission_id' in request.form and 'feedback' in request.form and 'grade' in request.form:
            submission_id = request.form['submission_id']
            feedback = request.form['feedback']
            grade = request.form['grade']
            try:
                cur.execute('UPDATE submissions SET feedback = %s, graded_by = %s, grade = %s WHERE id = %s',
                           (feedback, session['user_id'], grade, submission_id))
                db.commit()
                flash('Feedback and grade submitted!', 'success')
            except psycopg2.Error:
                db.rollback()
                flash('Failed to submit feedback.', 'error')
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    cur.execute('SELECT * FROM courses WHERE instructor_id = %s', (session['user_id'],))
    courses = cur.fetchall()
    cur.execute('''
        SELECT s.id, s.user_id, s.course_id, s.submission_text, s.submitted_at, s.feedback, s.grade,
        u.firstname || ' ' || u.lastname AS student_name, c.title AS course_title
        FROM submissions s
        JOIN users u ON s.user_id = u.id
        JOIN courses c ON s.course_id = c.id
        WHERE s.course_id IN (SELECT id FROM courses WHERE instructor_id = %s)
        AND s.feedback IS NULL
    ''', (session['user_id'],))
    submissions = cur.fetchall()
    cur.close()
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
        cur = db.cursor()
        try:
            cur.execute('INSERT INTO courses (title, description, video_url, video_path, instructor_id, topics, image_path) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id',
                       (title, description, None, video_path, instructor_id, topics, image_path))
            course_id = cur.fetchone()[0]
            for index, topic in enumerate(topic_list):
                cur.execute('INSERT INTO topics (course_id, topic_index, heading, content) VALUES (%s, %s, %s, %s)',
                           (course_id, index, topic, ''))
            db.commit()
            flash('Course created successfully!', 'success')
            cur.close()
            return redirect(url_for('instructor_dashboard'))
        except psycopg2.Error:
            db.rollback()
            flash('Failed to create course.', 'error')
    return render_template('create_course.html')

# Manage courses
@app.route('/manage_courses', methods=['GET', 'POST'])
def manage_courses():
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        if 'delete_course' in request.form:
            course_id = request.form['delete_course']

            # Get image and video paths for cleanup
            cur.execute('SELECT image_path, video_path FROM courses WHERE id = %s', (course_id,))
            course = cur.fetchone()

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

            try:
                # ✅ Delete enrollments first (fix for foreign key violation)
                cur.execute('DELETE FROM enrollments WHERE course_id = %s', (course_id,))

                # Delete topics
                cur.execute('DELETE FROM topics WHERE course_id = %s', (course_id,))

                # Finally delete the course itself
                cur.execute(
                    'DELETE FROM courses WHERE id = %s AND instructor_id = %s',
                    (course_id, session['user_id'])
                )

                db.commit()
                flash('Course deleted!', 'success')
            except psycopg2.Error:
                db.rollback()
                flash('Failed to delete course.', 'error')

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

                    # Remove old image
                    cur.execute('SELECT image_path FROM courses WHERE id = %s', (course_id,))
                    old_course = cur.fetchone()
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

                    # Remove old video
                    cur.execute('SELECT video_path FROM courses WHERE id = %s', (course_id,))
                    old_course = cur.fetchone()
                    if old_course and old_course['video_path']:
                        try:
                            os.remove(os.path.join('static', old_course['video_path']))
                        except OSError:
                            pass

            try:
                update_query = '''
                    UPDATE courses 
                    SET title = %s, description = %s, video_url = %s, instructor_id = %s, topics = %s
                '''
                params = [title, description, None, instructor_id, topics]

                if image_path:
                    update_query += ', image_path = %s'
                    params.append(image_path)
                if video_path:
                    update_query += ', video_path = %s'
                    params.append(video_path)

                update_query += ' WHERE id = %s'
                params.append(course_id)

                cur.execute(update_query, params)

                # Reset topics
                cur.execute('DELETE FROM topics WHERE course_id = %s', (course_id,))
                for index, topic in enumerate(topic_list):
                    cur.execute(
                        'INSERT INTO topics (course_id, topic_index, heading, content) VALUES (%s, %s, %s, %s)',
                        (course_id, index, topic, '')
                    )

                db.commit()
                flash('Course updated!', 'success')
            except psycopg2.Error:
                db.rollback()
                flash('Failed to update course.', 'error')

    cur.execute('SELECT * FROM courses WHERE instructor_id = %s', (session['user_id'],))
    courses = cur.fetchall()
    cur.close()
    return render_template('manage_courses.html', courses=courses)

# Manage course topics
@app.route('/manage_topics')
@app.route('/manage_topics/<int:course_id>')
def manage_topics(course_id=None):
    if 'user_id' not in session or session['role'] != 'instructor':
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if course_id is None:
        cur.execute('SELECT * FROM courses WHERE instructor_id = %s', (session['user_id'],))
        courses = cur.fetchall()
        cur.close()
        return render_template('select_course_for_topics.html', courses=courses)
    else:
        cur.execute('SELECT t.id, t.course_id, t.topic_index, t.heading, t.content, c.title AS course_title FROM topics t JOIN courses c ON t.course_id = c.id WHERE t.course_id = %s AND c.instructor_id = %s', (course_id, session['user_id']))
        topics = cur.fetchall()
        cur.close()
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
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT t.*, c.title AS course_title FROM topics t JOIN courses c ON t.course_id = c.id WHERE t.id = %s AND c.instructor_id = %s',
                       (topic_id, session['user_id']))
    topic = cur.fetchone()
    if not topic:
        cur.close()
        flash('Topic not found or you do not have permission.', 'error')
        return redirect(url_for('manage_topics'))
    if request.method == 'POST':
        content = request.form['content']
        try:
            cur.execute('UPDATE topics SET content = %s WHERE id = %s', (content, topic_id))
            db.commit()
            flash('Topic content updated!', 'success')
            cur.close()
            return redirect(url_for('manage_topics', course_id=topic['course_id']))
        except psycopg2.Error:
            db.rollback()
            flash('Failed to update topic content.', 'error')
    cur.close()
    return render_template('edit_topic.html', topic=topic)


# Run app
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)