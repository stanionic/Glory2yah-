"""
Ecole Biblique - Bible School Management System
Blueprint for student/teacher/admin management with grades and rankings
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
from app import db
from ecole_biblique.models import EcoleUser, Course, EcoleStudent, Grade

ecole_biblique_bp = Blueprint('ecole_biblique', __name__, template_folder='../ecole_biblique/templates')


@ecole_biblique_bp.context_processor
def inject_user():
    if 'user_id' in session:
        user = EcoleUser.query.get(session['user_id'])
        return {'current_user': user}
    return {'current_user': None}


# Routes
@ecole_biblique_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if user.role == 'admin':
        return redirect(url_for('ecole_biblique.admin_dashboard'))
    elif user.role == 'teacher':
        return redirect(url_for('ecole_biblique.teacher_dashboard'))
    elif user.role == 'student':
        return redirect(url_for('ecole_biblique.student_dashboard'))
    return redirect(url_for('ecole_biblique.ranking'))


@ecole_biblique_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        full_name = request.form['full_name']
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        user = EcoleUser.query.filter_by(full_name=full_name, whatsapp=whatsapp).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Login successful!', 'success')
            return redirect(url_for('ecole_biblique.index'))
        flash('Invalid credentials', 'error')
    return render_template('ecole_biblique/login.html')


@ecole_biblique_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        role = request.form['role']
        if EcoleUser.query.filter_by(whatsapp=whatsapp).first():
            flash('WhatsApp number already registered', 'error')
        else:
            user = EcoleUser(full_name=full_name, whatsapp=whatsapp, role=role)
            user.set_password(password)
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
    courses = Course.query.all()
    overall_ranking = db.session.query(
        EcoleStudent,
        db.func.avg(Grade.average).label('overall_avg')
    ).join(Grade).group_by(EcoleStudent.id).order_by(db.desc('overall_avg')).all()
    return render_template('ecole_biblique/ranking.html', courses=courses, overall_ranking=overall_ranking)


@ecole_biblique_bp.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'admin':
        return redirect(url_for('ecole_biblique.login'))
    users = EcoleUser.query.all()
    courses = Course.query.all()
    students = EcoleStudent.query.all()
    return render_template('ecole_biblique/admin_dashboard.html', users=users, courses=courses, students=students)


@ecole_biblique_bp.route('/teacher')
def teacher_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'teacher':
        return redirect(url_for('ecole_biblique.login'))
    courses = Course.query.filter_by(teacher_id=user.id).all()
    return render_template('ecole_biblique/teacher_dashboard.html', courses=courses)


@ecole_biblique_bp.route('/student')
def student_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'student':
        return redirect(url_for('ecole_biblique.login'))
    student = EcoleStudent.query.filter_by(whatsapp=user.whatsapp).first()
    if not student:
        flash('Student profile not found', 'error')
        return redirect(url_for('ecole_biblique.login'))
    grades = Grade.query.filter_by(student_id=student.id).all()
    return render_template('ecole_biblique/student_dashboard.html', grades=grades)


# API for real-time updates
@ecole_biblique_bp.route('/api/grades/<int:course_id>')
def get_grades(course_id):
    grades = Grade.query.filter_by(course_id=course_id).all()
    data = [{
        'student': g.student.full_name,
        'assignments': g.assignments,
        'exam': g.exam,
        'average': g.average
    } for g in grades]
    return jsonify(data)