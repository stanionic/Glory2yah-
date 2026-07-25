"""
Ecole Biblique Models
Separate models for the Bible School management system
"""
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date


class EcoleUser(db.Model):
    """User model for Ecole Biblique (separate from main app User)"""
    __tablename__ = 'ecole_users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')  # student, teacher, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # New fields for student registration
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    study_level = db.Column(db.String(200), nullable=True)
    theology_reason = db.Column(db.Text, nullable=True)
    church_ministry = db.Column(db.String(200), nullable=True)
    student_type = db.Column(db.String(20), default='gratuit')  # gratuit, payant
    registration_completed = db.Column(db.Boolean, default=False)
    terms_accepted = db.Column(db.Boolean, default=False)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    terms_accepted_ip = db.Column(db.String(45), nullable=True)
    terms_version = db.Column(db.String(20), default='1.0')

    # Relationships
    courses = db.relationship('Course', backref='teacher', lazy=True, foreign_keys='Course.teacher_id')
    modules = db.relationship('StudentModule', backref='student', lazy=True, foreign_keys='StudentModule.student_id')

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


# ===== NEW MODELS FOR THE ENHANCED SYSTEM =====

class Module(db.Model):
    """Module model - 3 modules for the Bible School"""
    __tablename__ = 'ecole_modules'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False, unique=True)  # 1-21
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    course_file = db.Column(db.String(255), nullable=True)  # PDF filename in COURS folder
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student_modules = db.relationship('StudentModule', lazy=True)

    def get_course_url(self):
        """Get the URL for the course file if available"""
        if self.course_file:
            return f'/ecole_biblique/cours/{self.course_file}'
        return None

    def __repr__(self):
        return f'<Module {self.number}: {self.name}>'


class StudentModule(db.Model):
    """Tracks student progress through modules"""
    __tablename__ = 'ecole_student_modules'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('ecole_modules.id'), nullable=False)
    exam_score = db.Column(db.Float, nullable=True)
    assignments_score = db.Column(db.Float, nullable=True)
    final_score = db.Column(db.Float, nullable=True)
    passed = db.Column(db.Boolean, default=False)
    locked = db.Column(db.Boolean, default=True)
    retake_count = db.Column(db.Integer, default=0)
    retake_fee_paid = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    module = db.relationship('Module', lazy=True, overlaps="student_modules")

    def calculate_final_score(self):
        """Calculate final score: 70% exam + 30% assignments"""
        if self.exam_score is not None and self.assignments_score is not None:
            self.final_score = (self.exam_score * 0.7) + (self.assignments_score * 0.3)
            self.passed = self.final_score >= 80
        return self.final_score

    def get_mention(self):
        """Get mention based on final score"""
        if self.final_score is None:
            return None
        if self.final_score >= 95:
            return 'Très Bien'
        elif self.final_score >= 90:
            return 'Bien'
        elif self.final_score >= 85:
            return 'Assez Bien'
        elif self.final_score >= 80:
            return 'Passable'
        else:
            return 'Échec'

    def __repr__(self):
        return f'<StudentModule Student:{self.student_id} Module:{self.module_id} Score:{self.final_score}>'


class Payment(db.Model):
    """Payment model for tracking all payments"""
    __tablename__ = 'ecole_payments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')  # GKach, USD
    payment_method = db.Column(db.String(50), nullable=False)  # gkach, wise, manual
    payment_type = db.Column(db.String(50), nullable=False)  # module_fee, retake_fee, graduation_fee
    reference = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    proof_file = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_comment = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    module_number = db.Column(db.Integer, nullable=True)  # Which module this payment is for
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship('EcoleUser', backref='payments', lazy=True, foreign_keys=[student_id])
    reviewer = db.relationship('EcoleUser', backref='reviewed_payments', lazy=True, foreign_keys=[reviewed_by])

    def __repr__(self):
        return f'<Payment {self.id} - {self.amount} {self.currency} - {self.status}>'


class TermsAcceptance(db.Model):
    """Log of terms acceptance"""
    __tablename__ = 'ecole_terms_acceptance'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=False)
    terms_version = db.Column(db.String(20), default='1.0')
    accepted_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)

    # Relationships
    user = db.relationship('EcoleUser', backref='terms_acceptances', lazy=True)

    def __repr__(self):
        return f'<TermsAcceptance User:{self.user_id} Version:{self.terms_version}>'


class AuditLog(db.Model):
    """Audit log for important operations"""
    __tablename__ = 'ecole_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('ecole_users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('EcoleUser', backref='audit_logs', lazy=True)

    def __repr__(self):
        return f'<AuditLog {self.action} at {self.created_at}>'