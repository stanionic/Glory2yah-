"""
Ecole Biblique Models
Separate models for the Bible School management system
"""
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class EcoleUser(db.Model):
    """User model for Ecole Biblique (separate from main app User)"""
    __tablename__ = 'ecole_users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')  # student, teacher, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    courses = db.relationship('Course', backref='teacher', lazy=True, foreign_keys='Course.teacher_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<EcoleUser {self.full_name}>'


class Course(db.Model):
    """Course model for Ecole Biblique"""
    __tablename__ = 'ecole_courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    grades = db.relationship('Grade', backref='course', lazy=True)

    def __repr__(self):
        return f'<Course {self.name}>'


class EcoleStudent(db.Model):
    """Student model for Ecole Biblique"""
    __tablename__ = 'ecole_students'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    grades = db.relationship('Grade', backref='student', lazy=True)

    def __repr__(self):
        return f'<EcoleStudent {self.full_name}>'


class Grade(db.Model):
    """Grade model for Ecole Biblique"""
    __tablename__ = 'ecole_grades'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('ecole_students.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('ecole_courses.id'), nullable=False)
    assignments = db.Column(db.Float, nullable=True)
    exam = db.Column(db.Float, nullable=True)
    average = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Grade {self.student.full_name} - {self.course.name}>'


class AdmissionTest(db.Model):
    """Admission test model for Ecole Biblique"""
    __tablename__ = 'ecole_admission_tests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=False)
    score = db.Column(db.Float, nullable=True)
    total_questions = db.Column(db.Integer, nullable=False, default=10)
    passed = db.Column(db.Boolean, default=False)
    completed = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship('EcoleUser', backref='admission_tests', lazy=True)
    answers = db.relationship('AdmissionAnswer', backref='test', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<AdmissionTest {self.user.full_name} - Score: {self.score}>'


class AdmissionAnswer(db.Model):
    """Individual answer for admission test"""
    __tablename__ = 'ecole_admission_answers'

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('ecole_admission_tests.id'), nullable=False)
    question_id = db.Column(db.Integer, nullable=False)
    selected_option = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<AdmissionAnswer Q:{self.question_id} - {"Correct" if self.is_correct else "Wrong"}>'
