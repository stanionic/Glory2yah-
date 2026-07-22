"""
Ecole Biblique - Bible School Management System
Blueprint for student/teacher/admin management with grades and rankings
Uses main app Flask-Login for authentication
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import random
from datetime import datetime
from app import db
from ecole_biblique.models import EcoleUser, Course, EcoleStudent, Grade, AdmissionTest, AdmissionAnswer
from ecole_biblique.admission_questions import ADMISSION_QUESTIONS

ecole_biblique_bp = Blueprint('ecole_biblique', __name__, template_folder='../ecole_biblique/templates')


def get_ecole_user():
    """Get EcoleUser linked to the currently logged-in main app user"""
    if not current_user.is_authenticated:
        return None
    return EcoleUser.query.filter_by(whatsapp=current_user.whatsapp).first()


@ecole_biblique_bp.context_processor
def inject_user():
    # Clean up old ecole session key (migration from old auth)
    if 'user_id' in session and current_user.is_authenticated:
        session.pop('user_id', None)
    ecole_user = get_ecole_user()
    return {
        'current_user': ecole_user or (current_user if current_user.is_authenticated else None),
        'is_logged_in': current_user.is_authenticated
    }


# Routes
@ecole_biblique_bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    ecole_user = get_ecole_user()
    if not ecole_user:
        flash('Ou pa gen kont Lekòl Biblik. Tanpri anrejistre w.', 'warning')
        return redirect(url_for('ecole_biblique.register'))
    if ecole_user.role == 'admin':
        return redirect(url_for('ecole_biblique.admin_dashboard'))
    elif ecole_user.role == 'teacher':
        return redirect(url_for('ecole_biblique.teacher_dashboard'))
    elif ecole_user.role == 'student':
        return redirect(url_for('ecole_biblique.student_dashboard'))
    return redirect(url_for('ecole_biblique.ranking'))


@ecole_biblique_bp.route('/login')
def login():
    """Redirect to main app login"""
    return redirect(url_for('auth.login'))


@ecole_biblique_bp.route('/register', methods=['GET', 'POST'])
def register():
    # If already has EcoleUser, redirect to dashboard
    if current_user.is_authenticated and get_ecole_user():
        return redirect(url_for('ecole_biblique.index'))
    
    if request.method == 'POST':
        from app.models.user import User
        
        # Use current user info if logged in, otherwise use form data
        if current_user.is_authenticated:
            full_name = request.form.get('full_name', current_user.name or current_user.pseudo or '').strip()
            whatsapp = current_user.whatsapp
            role = request.form.get('role', 'student')
            # For logged-in users, use their existing password - just create EcoleUser
        else:
            full_name = request.form.get('full_name', '').strip()
            whatsapp = request.form.get('whatsapp', '').strip()
            password = request.form.get('password', '').strip()
            role = request.form.get('role', 'student')
        
        if not full_name or not whatsapp:
            flash('Non ak nimewo WhatsApp obligatwa.', 'error')
            return render_template('register.html')
        
        if EcoleUser.query.filter_by(whatsapp=whatsapp).first():
            flash('Nimewo WhatsApp sa a deja anrejistre nan Lekòl Biblik.', 'error')
        else:
            # Create or link to main app User
            main_user = User.query.filter_by(whatsapp=whatsapp).first()
            if not main_user and not current_user.is_authenticated:
                # Create main app user with same credentials
                main_user = User(
                    whatsapp=whatsapp,
                    pseudo=full_name,
                    name=full_name,
                    auth_provider='whatsapp',
                    is_active=True
                )
                main_user.set_password(password)
                db.session.add(main_user)
                db.session.flush()
            
            # Create EcoleUser linked to this whatsapp
            ecole_user = EcoleUser(full_name=full_name, whatsapp=whatsapp, role=role)
            ecole_user.set_password(password if not current_user.is_authenticated else 'ecole_only')
            db.session.add(ecole_user)
            db.session.flush()
            
            # Auto-create EcoleStudent record for student role
            if role == 'student':
                student = EcoleStudent.query.filter_by(whatsapp=whatsapp).first()
                if not student:
                    student = EcoleStudent(full_name=full_name, whatsapp=whatsapp)
                    db.session.add(student)
            
            db.session.commit()
            flash('Enskripsyon Lekòl Biblik reyisi!', 'success')
            return redirect(url_for('ecole_biblique.index'))
    return render_template('register.html')


@ecole_biblique_bp.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    session.clear()
    flash('Ou dekonekte avèk siksè.', 'info')
    return redirect(url_for('main.index'))


@ecole_biblique_bp.route('/ranking')
def ranking():
    courses = Course.query.all()
    overall_ranking = db.session.query(
        EcoleStudent,
        db.func.avg(Grade.average).label('overall_avg')
    ).join(Grade).group_by(EcoleStudent.id).order_by(db.desc('overall_avg')).all()
    return render_template('ranking.html', courses=courses, overall_ranking=overall_ranking)


@ecole_biblique_bp.route('/admin')
@login_required
def admin_dashboard():
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        flash('Ou pa gen aksè administrateur.', 'error')
        return redirect(url_for('ecole_biblique.index'))
    users = EcoleUser.query.all()
    courses = Course.query.all()
    students = EcoleStudent.query.all()
    return render_template('admin_dashboard.html', users=users, courses=courses, students=students)


@ecole_biblique_bp.route('/teacher')
@login_required
def teacher_dashboard():
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'teacher':
        flash('Ou pa gen aksè pwofesè.', 'error')
        return redirect(url_for('ecole_biblique.index'))
    courses = Course.query.filter_by(teacher_id=ecole_user.id).all()
    return render_template('teacher_dashboard.html', courses=courses)


@ecole_biblique_bp.route('/student')
@login_required
def student_dashboard():
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Ou pa gen aksè elèv.', 'error')
        return redirect(url_for('ecole_biblique.register'))
    student = EcoleStudent.query.filter_by(whatsapp=current_user.whatsapp).first()
    if not student:
        # Auto-create student record to prevent redirect loop
        student = EcoleStudent(full_name=ecole_user.full_name, whatsapp=current_user.whatsapp)
        db.session.add(student)
        db.session.commit()
    grades = Grade.query.filter_by(student_id=student.id).all()
    # Get the last admission test for this user
    last_test = AdmissionTest.query.filter_by(user_id=ecole_user.id).order_by(AdmissionTest.started_at.desc()).first()
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
@login_required
def admission_test():
    """Display admission test to logged-in student"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Se elèv sèlman ki ka pran tès admisyon.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    # Check if student already passed
    passed_test = AdmissionTest.query.filter_by(user_id=ecole_user.id, passed=True, completed=True).first()
    if passed_test:
        flash('Ou deja pase tès admisyon an!', 'success')
        return redirect(url_for('ecole_biblique.student_dashboard'))

    # Get or create a test attempt
    current_test = AdmissionTest.query.filter_by(user_id=ecole_user.id, completed=False).first()
    if not current_test:
        # Select 10 random questions from the bank
        selected_questions = random.sample(ADMISSION_QUESTIONS, min(10, len(ADMISSION_QUESTIONS)))
        current_test = AdmissionTest(
            user_id=ecole_user.id,
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
@login_required
def admission_test_submit():
    """Submit admission test answers"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Aksè pa otorize.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    current_test = AdmissionTest.query.filter_by(user_id=ecole_user.id, completed=False).first()
    if not current_test:
        flash('Pa gen tès aktif jwenn.', 'error')
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
@login_required
def admission_result(test_id):
    """Show admission test result"""
    ecole_user = get_ecole_user()
    if not ecole_user:
        return redirect(url_for('ecole_biblique.index'))

    test = AdmissionTest.query.get_or_404(test_id)
    if test.user_id != ecole_user.id and ecole_user.role != 'admin':
        flash('Aksè refize.', 'error')
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
@login_required
def admin_admission_results():
    """Admin view of all admission test results"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        return redirect(url_for('ecole_biblique.index'))

    tests = AdmissionTest.query.order_by(AdmissionTest.started_at.desc()).all()
    return render_template('admin_admission_results.html', tests=tests)