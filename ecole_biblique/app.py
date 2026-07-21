"""
Ecole Biblique - Bible School Management System
Blueprint for student/teacher/admin management with grades and rankings
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
import random
from datetime import datetime
from app import db
from ecole_biblique.models import EcoleUser, Course, EcoleStudent, Grade, AdmissionTest, AdmissionAnswer
from ecole_biblique.admission_questions import ADMISSION_QUESTIONS

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
    return render_template('login.html')


@ecole_biblique_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        role = request.form.get('role', 'student')
        if EcoleUser.query.filter_by(whatsapp=whatsapp).first():
            flash('WhatsApp number already registered', 'error')
        else:
            user = EcoleUser(full_name=full_name, whatsapp=whatsapp, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # Get user.id before commit
            
            # Auto-create EcoleStudent record for student role
            if role == 'student':
                student = EcoleStudent.query.filter_by(whatsapp=whatsapp).first()
                if not student:
                    student = EcoleStudent(full_name=full_name, whatsapp=whatsapp)
                    db.session.add(student)
            
            db.session.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('ecole_biblique.login'))
    return render_template('register.html')


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
    return render_template('ranking.html', courses=courses, overall_ranking=overall_ranking)


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
    return render_template('admin_dashboard.html', users=users, courses=courses, students=students)


@ecole_biblique_bp.route('/teacher')
def teacher_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'teacher':
        return redirect(url_for('ecole_biblique.login'))
    courses = Course.query.filter_by(teacher_id=user.id).all()
    return render_template('teacher_dashboard.html', courses=courses)


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
    # Get the last admission test for this user
    last_test = AdmissionTest.query.filter_by(user_id=user.id).order_by(AdmissionTest.started_at.desc()).first()
    return render_template('student_dashboard.html', grades=grades, last_test=last_test)


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


# Admission Test Routes
@ecole_biblique_bp.route('/admission_test')
def admission_test():
    """Display admission test to logged-in student"""
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'student':
        flash('Only students can take admission tests', 'error')
        return redirect(url_for('ecole_biblique.login'))

    # Check if student already passed
    passed_test = AdmissionTest.query.filter_by(user_id=user.id, passed=True, completed=True).first()
    if passed_test:
        flash('You have already passed the admission test!', 'success')
        return redirect(url_for('ecole_biblique.student_dashboard'))

    # Get or create a test attempt
    current_test = AdmissionTest.query.filter_by(user_id=user.id, completed=False).first()
    if not current_test:
        # Select 10 random questions from the bank
        selected_questions = random.sample(ADMISSION_QUESTIONS, min(10, len(ADMISSION_QUESTIONS)))
        current_test = AdmissionTest(
            user_id=user.id,
            total_questions=len(selected_questions),
            completed=False
        )
        db.session.add(current_test)
        db.session.commit()
        # Store selected question IDs in session
        session['admission_question_ids'] = [q['id'] for q in selected_questions]

    # Get the questions for this test
    question_ids = session.get('admission_question_ids', [])
    questions = []
    for qid in question_ids:
        q = next((q for q in ADMISSION_QUESTIONS if q['id'] == qid), None)
        if q:
            questions.append(q)

    return render_template('admission_test.html', 
                         test=current_test, 
                         questions=questions,
                         total=len(questions))


@ecole_biblique_bp.route('/admission_test/submit', methods=['POST'])
def admission_test_submit():
    """Submit admission test answers"""
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'student':
        flash('Unauthorized access', 'error')
        return redirect(url_for('ecole_biblique.login'))

    current_test = AdmissionTest.query.filter_by(user_id=user.id, completed=False).first()
    if not current_test:
        flash('No active test found', 'error')
        return redirect(url_for('ecole_biblique.admission_test'))

    question_ids = session.get('admission_question_ids', [])
    correct_count = 0
    total = len(question_ids)

    # Process each answer
    for qid in question_ids:
        selected = request.form.get(f'q_{qid}')
        if selected is not None:
            try:
                selected_option = int(selected)
                q = next((q for q in ADMISSION_QUESTIONS if q['id'] == qid), None)
                is_correct = q and q['correct'] == selected_option
                if is_correct:
                    correct_count += 1
                answer = AdmissionAnswer(
                    test_id=current_test.id,
                    question_id=qid,
                    selected_option=selected_option,
                    is_correct=is_correct
                )
                db.session.add(answer)
            except (ValueError, TypeError):
                pass

    # Calculate score
    score = (correct_count / total * 100) if total > 0 else 0
    passed = score >= 70  # Passing threshold

    # Update test record
    current_test.score = score
    current_test.passed = passed
    current_test.completed = True
    current_test.completed_at = datetime.utcnow()
    db.session.commit()

    # Clear session data
    session.pop('admission_question_ids', None)

    return redirect(url_for('ecole_biblique.admission_result', test_id=current_test.id))


@ecole_biblique_bp.route('/admission_result/<int:test_id>')
def admission_result(test_id):
    """Show admission test result"""
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user:
        return redirect(url_for('ecole_biblique.login'))

    test = AdmissionTest.query.get_or_404(test_id)
    if test.user_id != user.id and user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('ecole_biblique.index'))

    # Get answers with question details
    results = []
    for answer in test.answers:
        q = next((q for q in ADMISSION_QUESTIONS if q['id'] == answer.question_id), None)
        if q:
            results.append({
                'question': q['question_fr'],
                'options': q['options'],
                'selected': answer.selected_option,
                'correct': q['correct'],
                'is_correct': answer.is_correct
            })

    return render_template('admission_result.html',
                         test=test,
                         results=results)


@ecole_biblique_bp.route('/admin/admission_results')
def admin_admission_results():
    """Admin view of all admission test results"""
    if 'user_id' not in session:
        return redirect(url_for('ecole_biblique.login'))
    user = EcoleUser.query.get(session['user_id'])
    if not user or user.role != 'admin':
        return redirect(url_for('ecole_biblique.login'))

    tests = AdmissionTest.query.order_by(AdmissionTest.started_at.desc()).all()
    return render_template('admin_admission_results.html', tests=tests)
