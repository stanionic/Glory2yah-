from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
from models import db

ecole_biblique_bp = Blueprint('ecole_biblique', __name__)

# Import models will be done lazily to avoid circular imports

@ecole_biblique_bp.context_processor
def inject_user():
    from app import EcoleUser as User
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        return {'current_user': user}
    return {'current_user': None}

# Routes
@ecole_biblique_bp.route('/')
def index():
    from app import EcoleUser as User
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = User.query.get(session['user_id'])
    if user.role == 'admin':
        return redirect(url_for('ecole_biblique.admin_dashboard'))
    elif user.role == 'teacher':
        return redirect(url_for('ecole_biblique.teacher_dashboard'))
    elif user.role == 'student':
        return redirect(url_for('ecole_biblique.student_dashboard'))
    return redirect(url_for('ecole_biblique.ranking'))

@ecole_biblique_bp.route('/login', methods=['GET', 'POST'])
def login():
    from app import EcoleUser as User
    if request.method == 'POST':
        full_name = request.form['full_name']
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        user = User.query.filter_by(full_name=full_name, whatsapp=whatsapp).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            flash('Login successful!', 'success')
            return redirect(url_for('ecole_biblique.index'))
        flash('Invalid credentials', 'error')
    return render_template('ecole_biblique/login.html')

@ecole_biblique_bp.route('/register', methods=['GET', 'POST'])
def register():
    from app import EcoleUser as User
    if request.method == 'POST':
        full_name = request.form['full_name']
        whatsapp = request.form['whatsapp']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        if User.query.filter_by(whatsapp=whatsapp).first():
            flash('WhatsApp number already registered', 'error')
        else:
            user = User(full_name=full_name, whatsapp=whatsapp, password=password, role=role)
            db.session.add(user)
            db.session.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('ecole_biblique.login'))
    return render_template('ecole_biblique/register.html')

@ecole_biblique_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('ecole_biblique.login'))

@ecole_biblique_bp.route('/ranking')
def ranking():
    from app import Course, EcoleStudent as Student, Grade
    courses = Course.query.all()
    overall_ranking = db.session.query(Student, db.func.avg(Grade.average).label('overall_avg')).join(Grade).group_by(Student.id).order_by(db.desc('overall_avg')).all()
    return render_template('ecole_biblique/ranking.html', courses=courses, overall_ranking=overall_ranking)

@ecole_biblique_bp.route('/admin')
def admin_dashboard():
    from app import EcoleUser as User, Course, EcoleStudent as Student
    if 'user_id' not in session or User.query.get(session['user_id']).role != 'admin':
        return redirect(url_for('ecole_biblique.login'))
    users = User.query.all()
    courses = Course.query.all()
    students = Student.query.all()
    return render_template('ecole_biblique/admin_dashboard.html', users=users, courses=courses, students=students)

@ecole_biblique_bp.route('/teacher')
def teacher_dashboard():
    from app import EcoleUser as User, Course
    if 'user_id' not in session or User.query.get(session['user_id']).role != 'teacher':
        return redirect(url_for('ecole_biblique.login'))
    teacher = User.query.get(session['user_id'])
    courses = Course.query.filter_by(teacher_id=teacher.id).all()
    return render_template('ecole_biblique/teacher_dashboard.html', courses=courses)

@ecole_biblique_bp.route('/student')
def student_dashboard():
    from app import EcoleUser as User, EcoleStudent as Student, Grade
    if 'user_id' not in session or User.query.get(session['user_id']).role != 'student':
        return redirect(url_for('ecole_biblique.login'))
    student = Student.query.filter_by(whatsapp=User.query.get(session['user_id']).whatsapp).first()
    if not student:
        flash('Student profile not found', 'error')
        return redirect(url_for('ecole_biblique.login'))
    grades = Grade.query.filter_by(student_id=student.id).all()
    return render_template('ecole_biblique/student_dashboard.html', grades=grades)

# API for real-time updates
@ecole_biblique_bp.route('/api/grades/<int:course_id>')
def get_grades(course_id):
    from app import Grade
    grades = Grade.query.filter_by(course_id=course_id).all()
    data = [{'student': g.student.full_name, 'assignments': g.assignments, 'exam': g.exam, 'average': g.average} for g in grades]
    return jsonify(data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
