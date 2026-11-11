
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path
import sys
import os
import uuid
from werkzeug.utils import secure_filename
from flask import send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import get_db_connection

app = Flask(__name__)
app.secret_key = "campushub-development-key"

# STUDY MATERIAL UPLOAD SETTINGS
app.config["UPLOAD_FOLDER"] = os.path.join(
    app.root_path, "uploads"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf"}


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ADMIN ACCESS PROTECTION
def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("login"))

        if session.get("user_role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))

        return function(*args, **kwargs)

    return wrapper


# HOME
@app.route("/")
def home():
    return render_template("index.html")


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not email or len(password) < 8:
            flash("Please enter valid details. Password needs 8 characters.", "error")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        db = None
        cursor = None

        try:
            db = get_db_connection()
            cursor = db.cursor()

            cursor.execute(
                """INSERT INTO users (full_name, email, password)
                   VALUES (%s, %s, %s)""",
                (full_name, email, hashed_password)
            )

            db.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            if db:
                db.rollback()

            print("Registration Error:", e)
            flash("Registration failed. Email may already exist.", "error")

        finally:
            if cursor:
                cursor.close()
            if db and db.is_connected():
                db.close()

    return render_template("register.html")



# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = None
        cursor = None

        try:
            db = get_db_connection()
            cursor = db.cursor(dictionary=True)

            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user = cursor.fetchone()

            if user and check_password_hash(user["password"], password):

                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["user_role"] = user["role"]

                # ROLE-BASED REDIRECTION
                if user["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))

                elif user["role"] == "teacher":
                    return redirect(url_for("teacher_dashboard"))

                else:
                    return redirect(url_for("dashboard"))

            flash("Invalid email or password.", "error")

        except Exception as e:
            print("Login Error:", e)
            flash("Something went wrong. Please try again.", "error")

        finally:
            if cursor:
                cursor.close()
            if db and db.is_connected():
                db.close()

    return render_template("login.html")


# STUDENT DASHBOARD
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") == "admin":
        return redirect(url_for("admin_dashboard"))

    if session.get("user_role") == "teacher":
        return redirect(url_for("teacher_dashboard"))

    db = None
    cursor = None

    notices = []
    materials = []
    attendance_summary = {
        "total": 0,
        "present": 0,
        "absent": 0,
        "late": 0,
        "percentage": 0
    }
    attendance_by_subject = []

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # FETCH COLLEGE NOTICES
        cursor.execute("""
            SELECT notices.*, users.full_name AS admin_name
            FROM notices
            JOIN users ON notices.created_by = users.id
            ORDER BY notices.created_at DESC
        """)
        notices = cursor.fetchall()

        # FETCH STUDY MATERIALS
        cursor.execute("""
            SELECT study_materials.*, users.full_name AS admin_name
            FROM study_materials
            JOIN users ON study_materials.uploaded_by = users.id
            ORDER BY study_materials.uploaded_at DESC
        """)
        materials = cursor.fetchall()

        # FETCH OVERALL ATTENDANCE
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(status = 'Present'), 0) AS present,
                COALESCE(SUM(status = 'Absent'), 0) AS absent,
                COALESCE(SUM(status = 'Late'), 0) AS late
            FROM attendance
            WHERE student_id = %s
        """, (session["user_id"],))

        attendance_summary = cursor.fetchone()

        total = attendance_summary["total"]
        present = attendance_summary["present"]

        attendance_summary["percentage"] = (
            round((present / total) * 100, 1) if total > 0 else 0
        )

        # FETCH SUBJECT-WISE ATTENDANCE
        cursor.execute("""
            SELECT
                subjects.subject_name,
                COUNT(attendance.id) AS total,
                COALESCE(SUM(attendance.status = 'Present'), 0) AS present,
                COALESCE(SUM(attendance.status = 'Absent'), 0) AS absent,
                COALESCE(SUM(attendance.status = 'Late'), 0) AS late
            FROM attendance
            JOIN subjects
                ON attendance.subject_id = subjects.id
            WHERE attendance.student_id = %s
            GROUP BY subjects.id, subjects.subject_name
            ORDER BY subjects.subject_name
        """, (session["user_id"],))

        attendance_by_subject = cursor.fetchall()

        for subject in attendance_by_subject:
            subject["percentage"] = (
                round(
                    (subject["present"] / subject["total"]) * 100, 1
                )
                if subject["total"] > 0 else 0
            )

    except Exception as e:
        print("Student Dashboard Error:", e)
        flash("Unable to load dashboard information.", "error")

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template(
        "dashboard.html",
        user_name=session["user_name"],
        notices=notices,
        materials=materials,
        attendance_summary=attendance_summary,
        attendance_by_subject=attendance_by_subject
    )

# ADMIN DASHBOARD
@app.route("/admin")
@admin_required
def admin_dashboard():

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT notices.*, users.full_name AS admin_name
            FROM notices
            JOIN users ON notices.created_by = users.id
            ORDER BY notices.created_at DESC
        """)

        notices = cursor.fetchall()

    except Exception as e:
        print("Admin Dashboard Error:", e)
        notices = []

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template(
        "admin_dashboard.html",
        admin_name=session["user_name"],
        notices=notices
    )


# PUBLISH NOTICE
@app.route("/admin/add-notice", methods=["POST"])
@admin_required
def add_notice():

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    if not title or not content:
        flash("Please enter both notice title and content.", "error")
        return redirect(url_for("admin_dashboard"))

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO notices (title, content, created_by)
            VALUES (%s, %s, %s)
        """, (title, content, session["user_id"]))

        db.commit()

        flash("Notice published successfully!", "success")

    except Exception as e:
        if db:
            db.rollback()

        print("Notice Publishing Error:", e)
        flash("Unable to publish notice.", "error")

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return redirect(url_for("admin_dashboard"))


# UPLOAD STUDY MATERIAL (ADMIN ONLY)
@app.route("/admin/upload-material", methods=["POST"])
@admin_required
def upload_material():

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("file")

    if not title or not file or file.filename == "":
        flash("Please enter a title and select a PDF file.", "error")
        return redirect(url_for("admin_dashboard"))

    if not allowed_file(file.filename):
        flash("Only PDF files are allowed.", "error")
        return redirect(url_for("admin_dashboard"))

    original_name = secure_filename(file.filename)

    if not original_name:
        flash("Invalid filename.", "error")
        return redirect(url_for("admin_dashboard"))

    # Check that the uploaded file is actually a PDF
    file_content = file.read()

    if not file_content.startswith(b"%PDF-"):
        flash("The selected file is not a valid PDF.", "error")
        return redirect(url_for("admin_dashboard"))

    file.seek(0)

    stored_filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        stored_filename
    )

    db = None
    cursor = None

    try:
        file.save(file_path)

        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO study_materials
            (title, description, filename, uploaded_by)
            VALUES (%s, %s, %s, %s)
        """, (
            title,
            description,
            stored_filename,
            session["user_id"]
        ))

        db.commit()

        flash("Study material uploaded successfully!", "success")

    except Exception as e:
        if db:
            db.rollback()

        if os.path.exists(file_path):
            os.remove(file_path)

        print("Material Upload Error:", e)
        flash("Unable to upload study material.", "error")

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return redirect(url_for("admin_dashboard"))


# DOWNLOAD STUDY MATERIAL (LOGGED-IN USERS)
@app.route("/materials/download/<int:material_id>")
def download_material(material_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT filename FROM study_materials WHERE id = %s",
            (material_id,)
        )

        material = cursor.fetchone()

        if not material:
            flash("Study material not found.", "error")
            return redirect(url_for("dashboard"))

        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            material["filename"],
            as_attachment=True
        )

    except Exception as e:
        print("Material Download Error:", e)
        flash("Unable to download study material.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()


# LOGOUT
@app.route("/logout")
def logout():

    session.clear()
    flash("You have logged out successfully.", "success")

    return redirect(url_for("login"))


# ADMIN: VIEW STUDENTS AND TEACHERS
@app.route("/admin/people")
@admin_required
def admin_people():
    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, full_name, email, created_at
            FROM users
            WHERE role = 'student'
            ORDER BY id DESC
        """)
        students = cursor.fetchall()

        cursor.execute("""
            SELECT users.id, users.full_name, users.email,
                   teacher_profiles.department,
                   teacher_profiles.qualification
            FROM users
            LEFT JOIN teacher_profiles
                ON users.id = teacher_profiles.user_id
            WHERE users.role = 'teacher'
            ORDER BY users.id DESC
        """)
        teachers = cursor.fetchall()

        return render_template(
            "admin_people.html",
            students=students,
            teachers=teachers
        )

    except Exception as e:
        print("Admin People Error:", e)
        flash("Unable to load user information.", "error")
        return redirect(url_for("admin_dashboard"))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()


# ADMIN: CREATE TEACHER ACCOUNT
@app.route("/admin/create-teacher", methods=["POST"])
@admin_required
def create_teacher():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    department = request.form.get("department", "").strip()
    qualification = request.form.get("qualification", "").strip()

    if not all([full_name, email, password]):
        flash("Please complete all required fields.", "error")
        return redirect(url_for("admin_people"))

    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "error")
        return redirect(url_for("admin_people"))

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email = %s",
            (email,)
        )

        if cursor.fetchone():
            flash("This email is already registered.", "error")
            return redirect(url_for("admin_people"))

        cursor.execute("""
            INSERT INTO users (full_name, email, password, role)
            VALUES (%s, %s, %s, 'teacher')
        """, (
            full_name,
            email,
            generate_password_hash(password)
        ))

        teacher_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO teacher_profiles
                (user_id, department, qualification)
            VALUES (%s, %s, %s)
        """, (teacher_id, department, qualification))

        db.commit()
        flash("Teacher account created successfully.", "success")

    except Exception as e:
        if db:
            db.rollback()
        print("Create Teacher Error:", e)
        flash("Unable to create teacher account.", "error")

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return redirect(url_for("admin_people"))



# TEACHER DASHBOARD
@app.route("/teacher")
def teacher_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "teacher":
        flash("Teacher access only.", "error")
        return redirect(url_for("dashboard"))

    db = None
    cursor = None
    subjects = []

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT subjects.id, subjects.subject_name,
                   subjects.subject_code, courses.course_name
            FROM subjects
            LEFT JOIN courses ON subjects.course_id = courses.id
            WHERE subjects.teacher_id = %s
            ORDER BY subjects.subject_name
        """, (session["user_id"],))

        subjects = cursor.fetchall()

    except Exception as e:
        print("Teacher Dashboard Error:", e)
        flash("Unable to load teacher information.", "error")

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template(
        "teacher_dashboard.html",
        user_name=session["user_name"],
        subjects=subjects
    )


# ADMIN: COURSE AND SUBJECT MANAGEMENT
@app.route("/admin/academics", methods=["GET", "POST"])
@admin_required
def admin_academics():

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        if request.method == "POST":
            action = request.form.get("action")

            if action == "course":
                name = request.form.get("course_name", "").strip()
                code = request.form.get("course_code", "").strip()

                if not name or not code:
                    flash("Enter course name and code.", "error")
                else:
                    cursor.execute(
                        "INSERT INTO courses (course_name, course_code) VALUES (%s, %s)",
                        (name, code)
                    )
                    db.commit()
                    flash("Course created successfully.", "success")

            elif action == "subject":
                name = request.form.get("subject_name", "").strip()
                code = request.form.get("subject_code", "").strip()
                course_id = request.form.get("course_id")
                teacher_id = request.form.get("teacher_id") or None

                if not name or not course_id:
                    flash("Enter subject name and select a course.", "error")
                else:
                    cursor.execute("""
                        INSERT INTO subjects
                            (course_id, teacher_id, subject_name, subject_code)
                        VALUES (%s, %s, %s, %s)
                    """, (course_id, teacher_id, name, code))
                    db.commit()
                    flash("Subject assigned successfully.", "success")

            return redirect(url_for("admin_academics"))

        cursor.execute("SELECT * FROM courses ORDER BY course_name")
        courses = cursor.fetchall()

        cursor.execute("""
            SELECT id, full_name FROM users
            WHERE role = 'teacher' ORDER BY full_name
        """)
        teachers = cursor.fetchall()

        cursor.execute("""
            SELECT subjects.*, courses.course_name, users.full_name AS teacher_name
            FROM subjects
            JOIN courses ON subjects.course_id = courses.id
            LEFT JOIN users ON subjects.teacher_id = users.id
            ORDER BY subjects.id DESC
        """)
        subjects = cursor.fetchall()

        return render_template(
            "admin_academics.html",
            courses=courses,
            teachers=teachers,
            subjects=subjects
        )

    except Exception as e:
        if db:
            db.rollback()
        print("Admin Academics Error:", e)
        flash("Unable to manage academic information.", "error")
        return redirect(url_for("admin_dashboard"))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

# TEACHER: MARK STUDENT ATTENDANCE
@app.route("/teacher/attendance", methods=["GET", "POST"])
def teacher_attendance():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "teacher":
        flash("Teacher access only.", "error")
        return redirect(url_for("login"))

    from datetime import date

    db = None
    cursor = None
    students = []
    subjects = []
    selected_subject = request.values.get("subject_id", "")
    attendance_date = request.values.get(
        "attendance_date", date.today().isoformat()
    )

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, subject_name
            FROM subjects
            WHERE teacher_id = %s
            ORDER BY subject_name
        """, (session["user_id"],))
        subjects = cursor.fetchall()

        if selected_subject:
            cursor.execute("""
                SELECT id
                FROM subjects
                WHERE id = %s AND teacher_id = %s
            """, (selected_subject, session["user_id"]))

            if not cursor.fetchone():
                flash("Invalid subject selection.", "error")
                return redirect(url_for("teacher_attendance"))

        if request.method == "POST" and selected_subject:

            cursor.execute("""
                SELECT id FROM users WHERE role = 'student'
            """)
            student_ids = cursor.fetchall()

            for student in student_ids:
                student_id = student["id"]
                status = request.form.get(f"status_{student_id}")

                if status not in ("Present", "Absent", "Late"):
                    continue

                cursor.execute("""
                    SELECT id FROM attendance
                    WHERE student_id = %s
                    AND subject_id = %s
                    AND attendance_date = %s
                """, (student_id, selected_subject, attendance_date))

                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE attendance
                        SET status = %s, marked_by = %s
                        WHERE id = %s
                    """, (status, session["user_id"], existing["id"]))
                else:
                    cursor.execute("""
                        INSERT INTO attendance
                        (student_id, subject_id, marked_by,
                         attendance_date, status)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        student_id, selected_subject,
                        session["user_id"], attendance_date, status
                    ))

            db.commit()
            flash("Attendance saved successfully.", "success")

        if selected_subject:
            cursor.execute("""
                SELECT users.id, users.full_name, users.email,
                       attendance.status
                FROM users
                LEFT JOIN attendance
                    ON attendance.student_id = users.id
                    AND attendance.subject_id = %s
                    AND attendance.attendance_date = %s
                WHERE users.role = 'student'
                ORDER BY users.full_name
            """, (selected_subject, attendance_date))
            students = cursor.fetchall()

        return render_template(
            "teacher_attendance.html",
            subjects=subjects,
            students=students,
            selected_subject=selected_subject,
            attendance_date=attendance_date
        )

    except Exception as e:
        if db:
            db.rollback()
        print("Attendance Error:", e)
        flash("Unable to process attendance.", "error")
        return redirect(url_for("teacher_dashboard"))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()


if __name__ == "__main__":
    app.run(debug=True)

