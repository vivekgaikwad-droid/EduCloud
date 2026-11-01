import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the .env file beside this app.py, even if Flask is started
# from a different working directory.
load_dotenv(Path(__file__).resolve().with_name('.env'), override=True)


import uuid
from datetime import datetime, timezone
from functools import wraps

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-deployment")
database_url = os.environ.get("DATABASE_URL", "sqlite:///educloud.db").strip()

# Normalize Supabase/PostgreSQL URLs for the installed psycopg v3 driver.
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
elif database_url.startswith("postgresql+psycopg:/") and not database_url.startswith("postgresql+psycopg://"):
    # Repair the common one-slash typo if it was copied into .env.
    database_url = database_url.replace("postgresql+psycopg:/", "postgresql+psycopg://", 1)

if not database_url:
    raise RuntimeError("DATABASE_URL is empty. Check the .env file beside app.py.")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "local_uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    teacher = db.relationship("User", backref="created_assignments")

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(30), default="Turned In")
    assignment = db.relationship("Assignment", backref="submissions")
    student = db.relationship("User", backref="submissions")
    __table_args__ = (db.UniqueConstraint("assignment_id", "student_id", name="one_submission_per_student_assignment"),)

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def role_required(role):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user().role != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def save_pdf(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Choose a PDF file first.")
    filename = secure_filename(file_storage.filename)
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are accepted.")
    if file_storage.mimetype not in ("application/pdf", "application/octet-stream"):
        raise ValueError("The uploaded file must be a PDF.")
    key = f"submissions/{uuid.uuid4().hex}_{filename}"
    bucket = os.environ.get("S3_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-southeast-2"))
        file_storage.stream.seek(0)
        s3.upload_fileobj(file_storage.stream, bucket, key, ExtraArgs={"ContentType": "application/pdf", "ServerSideEncryption": "AES256"})
        return key
    local_name = key.replace("/", "_")
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], local_name))
    return "local:" + local_name

def fetch_file(storage_key):
    if storage_key.startswith("local:"):
        return send_from_directory(app.config["UPLOAD_FOLDER"], storage_key[6:], as_attachment=True)
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        abort(404)
    try:
        obj = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")).get_object(Bucket=bucket, Key=storage_key)
        from flask import Response
        return Response(obj["Body"].read(), mimetype="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=assignment-submission.pdf"})
    except (BotoCoreError, ClientError):
        abort(404)

@app.context_processor
def inject_user():
    return {"logged_user": current_user()}

@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")
        invite = request.form.get("teacher_code", "").strip()
        expected_invite = os.environ.get("TEACHER_INVITE_CODE", "").strip()

        app.logger.warning(
    "TEACHER CHECK: role=%r field_present=%s expected_present=%s match=%s",
    role,
    bool(invite),
    bool(expected_invite),
    invite == expected_invite
)

        if not name or not email or len(password) < 8:
            flash("Enter your name and email, and use a password with at least 8 characters.", "error")

        elif role not in ("student", "teacher"):
            flash("Invalid account type.", "error")

        elif role == "teacher" and invite != expected_invite:
            flash("Teacher invitation code is incorrect.", "error")

        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")

        else:
            user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                role=role
            )

            try:
                db.session.add(user)
                db.session.commit()
            except Exception:
                db.session.rollback()
                app.logger.exception("Account registration failed while saving to the configured database.")
                flash("Could not create the account in the database. Check the server terminal for the error.", "error")
                return render_template("register.html")

            session["user_id"] = user.id
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear(); session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user.role == "teacher":
        assignments = Assignment.query.filter_by(teacher_id=user.id).order_by(Assignment.created_at.desc()).all()
        return render_template("teacher_dashboard.html", assignments=assignments)
    assignments = Assignment.query.order_by(Assignment.due_date.asc()).all()
    submitted = {s.assignment_id: s for s in Submission.query.filter_by(student_id=user.id).all()}
    return render_template("student_dashboard.html", assignments=assignments, submitted=submitted)

@app.route("/teacher/assignments/new", methods=["GET", "POST"])
@role_required("teacher")
def create_assignment():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        instructions = request.form.get("instructions", "").strip()
        due = request.form.get("due_date", "")
        try:
            from datetime import date
            due_date = date.fromisoformat(due)
            if not title or not subject or not instructions:
                raise ValueError()
            item = Assignment(title=title, subject=subject, instructions=instructions, due_date=due_date, teacher_id=current_user().id)
            db.session.add(item); db.session.commit()
            flash("Assignment published for students.", "success")
            return redirect(url_for("dashboard"))
        except ValueError:
            flash("Complete all fields and select a valid due date.", "error")
    return render_template("create_assignment.html")

@app.route("/assignments/<int:assignment_id>")
@login_required
def assignment_detail(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment: abort(404)
    submission = None
    if current_user().role == "student":
        submission = Submission.query.filter_by(assignment_id=assignment_id, student_id=current_user().id).first()
    elif assignment.teacher_id != current_user().id:
        abort(403)
    return render_template("assignment_detail.html", assignment=assignment, submission=submission)

@app.route("/assignments/<int:assignment_id>/turn-in", methods=["POST"])
@role_required("student")
def turn_in(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment: abort(404)
    upload = request.files.get("pdf_file")
    try:
        storage_key = save_pdf(upload)
        existing = Submission.query.filter_by(assignment_id=assignment_id, student_id=current_user().id).first()
        if existing:
            existing.storage_key = storage_key
            existing.original_filename = secure_filename(upload.filename)
            existing.submitted_at = datetime.utcnow()
            existing.status = "Turned In"
        else:
            db.session.add(Submission(assignment_id=assignment_id, student_id=current_user().id,
                                      original_filename=secure_filename(upload.filename),
                                      storage_key=storage_key, status="Turned In"))
        db.session.commit()
        flash("Your PDF has been uploaded and the assignment is marked Turned In.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except (BotoCoreError, ClientError):
        flash("S3 upload failed. Check the bucket, region and ECS task permissions.", "error")
    return redirect(url_for("assignment_detail", assignment_id=assignment_id))

@app.route("/teacher/assignments/<int:assignment_id>/submissions")
@role_required("teacher")
def view_submissions(assignment_id):
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment or assignment.teacher_id != current_user().id: abort(404)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).order_by(Submission.submitted_at.desc()).all()
    return render_template("submissions.html", assignment=assignment, submissions=submissions)

@app.route("/submission/<int:submission_id>/download")
@login_required
def download_submission(submission_id):
    submission = db.session.get(Submission, submission_id)
    if not submission: abort(404)
    user = current_user()
    if user.role == "student" and submission.student_id != user.id: abort(403)
    if user.role == "teacher" and submission.assignment.teacher_id != user.id: abort(403)
    return fetch_file(submission.storage_key)

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The page or resource could not be found."), 404

with app.app_context():
    db.create_all()
    # These diagnostics never print the database password.
    safe_url = db.engine.url
    app.logger.info("EduCloud database driver: %s", safe_url.drivername)
    app.logger.info("EduCloud database host: %s", safe_url.host or "local")
    app.logger.info("EduCloud database name: %s", safe_url.database)
    app.logger.info("EduCloud tables are ready.")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
