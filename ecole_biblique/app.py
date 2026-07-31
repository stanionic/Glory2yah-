"""
Ecole Biblique - Bible School Management System v2.0
Blueprint for student/teacher/admin management with grades and rankings
Comprehensive system with modules, payments, and academic tracking
"""
import os
import random
import uuid
import json
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_required, current_user
from jinja2 import TemplateNotFound
from werkzeug.utils import secure_filename
from app import db
from ecole_biblique.models import (
    EcoleUser, Course, EcoleStudent, Grade, AdmissionTest, AdmissionAnswer,
    Module, StudentModule, Payment, TermsAcceptance, AuditLog
)
from ecole_biblique.admission_questions import ADMISSION_QUESTIONS

ecole_biblique_bp = Blueprint('ecole_biblique', __name__, template_folder='../ecole_biblique/templates', static_folder='static')

# Constants
TOTAL_MODULES = 20
PASSING_SCORE = 80
EXAM_WEIGHT = 0.7
ASSIGNMENTS_WEIGHT = 0.3
EXAM_DEADLINE = date(2026, 11, 30)
GRADUATION_DATE = date(2026, 12, 25)
TERMS_VERSION = '1.0'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
UPLOAD_FOLDER = 'static/uploads/ecole_payments'

# Fee structure
FREE_MODULES = 20  # All 20 modules free
FREE_STUDENT_FEE_PER_BLOCK = 0  # No fee per block for free students
FREE_STUDENT_GRADUATION_FEE = 100  # $100 graduation fee
PAID_STUDENT_FEE_PER_BLOCK = 0  # No fee per block for paid students
PAID_STUDENT_TOTAL = 600  # $600 total


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_ecole_user():
    """Get EcoleUser linked to the currently logged-in main app user"""
    if not current_user.is_authenticated:
        return None
    return EcoleUser.query.filter_by(whatsapp=current_user.whatsapp).first()


def log_audit(user_id, action, details=None):
    """Log an audit trail entry"""
    ip = request.remote_addr or '0.0.0.0'
    log = AuditLog(user_id=user_id, action=action, details=details, ip_address=ip)
    db.session.add(log)
    db.session.commit()


def init_modules():
    """Initialize all 20 modules from the COURS folder if they don't exist"""
    module_definitions = [
        (1, "Introduction à la Bible (Religion)", "Module 1: Introduction à la Bible (Religion)", "Module 1(RELIGION).pdf"),
        (2, "Le Premier Être", "Module 2: Le Premier Être", "Module 2 (Le Premier Etre.pdf"),
        (3, "Théologie", "Module 3: Théologie", "Module 3(Theologie).pdf"),
        (4, "Christologie", "Module 4: Christologie", "Module 4(CHRISTOLOGIE).pdf"),
        (5, "Angéologie", "Module 5: Angéologie", "ANGEOLOGIE.pdf"),
        (6, "Anthropologie Chrétienne", "Module 6: Anthropologie Chrétienne", "ANTROPOLOGIE CHRETIENNE.pdf"),
        (7, "Apologétique", "Module 7: Apologétique", "APOLOGETIQUE.pdf"),
        (8, "Démonologie", "Module 8: Démonologie", "DEMONOLOGIE.pdf"),
        (9, "Dogmatique", "Module 9: Dogmatique", "DOGMATIQUE.pdf"),
        (10, "Évangélisation", "Module 10: Évangélisation", "Evangélisation-1.pdf"),
        (11, "Exégèse", "Module 11: Exégèse", "EXEGESE.pdf"),
        (12, "Homilétique", "Module 12: Homilétique", "HOMILETIQUE.pdf"),
        (13, "La Houlette du Berger", "Module 13: La Houlette du Berger", "La houlette du berger.pdf"),
        (14, "Le Ministère Chrétien", "Module 14: Le Ministère Chrétien", "LE MINISTERE CHRETIEN.pdf"),
        (15, "Le Plus Grand Ennemis de l'Humanité", "Module 15: Le Plus Grand Ennemis de l'Humanité", "le-plus-grand-ennemis-de-l-humanite-16.pdf"),
        (16, "L'Église", "Module 16: L'Église", "LEglise-1.pdf"),
        (17, "Leurres de Satan", "Module 17: Leurres de Satan", "leurres-de-satan.pdf"),
        (18, "Louange et Adoration", "Module 18: Louange et Adoration", "Louange-et-Adoration.pdf"),
        (19, "Psaumes", "Module 19: Psaumes", "Psaumes.pdf"),
        (20, "Théologie", "Module 20: Théologie", "THEOLOGIE.pdf"),
    ]
    for number, name, description, course_file in module_definitions:
        module = Module.query.filter_by(number=number).first()
        if not module:
            module = Module(number=number, name=name, description=description, course_file=course_file)
            db.session.add(module)
        else:
            # Update course_file if not set
            if not module.course_file:
                module.course_file = course_file
    db.session.commit()


def init_student_modules(student_id):
    """Initialize module tracking for a new student"""
    modules = Module.query.order_by(Module.number).all()
    for i, module in enumerate(modules):
        sm = StudentModule.query.filter_by(student_id=student_id, module_id=module.id).first()
        if not sm:
            sm = StudentModule(
                student_id=student_id,
                module_id=module.id,
                locked=(i >= 3),  # First 3 modules unlocked, rest locked
                passed=False
            )
            db.session.add(sm)
    # Unlock modules 1, 2, 3 (first 3 modules free)
    unlocked_modules = StudentModule.query.filter_by(student_id=student_id).join(Module).order_by(Module.number).limit(3).all()
    for sm in unlocked_modules:
        sm.locked = False
    db.session.commit()


def get_module_fee(student_type, module_number):
    """Calculate fee for a given module based on student type"""
    # All 20 modules are free
    return 0


def get_graduation_fee(student_type):
    """Get graduation fee based on student type"""
    if student_type == 'gratuit':
        return FREE_STUDENT_GRADUATION_FEE
    return 0  # Included in total for paid students


def check_exam_deadline():
    """Check if exam deadline has passed"""
    today = date.today()
    return today > EXAM_DEADLINE


def get_passing_students():
    """Get students who passed all 20 modules"""
    students = EcoleUser.query.filter_by(role='student', registration_completed=True).all()
    passing = []
    for student in students:
        modules = StudentModule.query.filter_by(student_id=student.id).all()
        if len(modules) >= TOTAL_MODULES:
            passed_all = all(m.passed for m in modules)
            if passed_all:
                passing.append(student)
    return passing


@ecole_biblique_bp.context_processor
def inject_user():
    """Inject user data into all templates"""
    if 'user_id' in session and current_user.is_authenticated:
        session.pop('user_id', None)
    ecole_user = get_ecole_user()
    
    # Calculate deadlines for template injection
    deadline_passed = check_exam_deadline()
    days_until_deadline = (EXAM_DEADLINE - date.today()).days if not deadline_passed else 0
    
    return {
        'current_user': ecole_user or (current_user if current_user.is_authenticated else None),
        'is_logged_in': current_user.is_authenticated,
        'exam_deadline': EXAM_DEADLINE,
        'graduation_date': GRADUATION_DATE,
        'deadline_passed': deadline_passed,
        'days_until_deadline': days_until_deadline,
        'school_name': 'École Biblique MEGD-Haïti',
        'school_partner': 'GLOBAL CONNEXION NETWORK BIBLE SCHOOL – Alabama'
    }


# ===== MAIN ROUTES =====

@ecole_biblique_bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    ecole_user = get_ecole_user()
    if not ecole_user:
        flash('Vous n\'avez pas de compte à l\'École Biblique. Veuillez vous inscrire.', 'warning')
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
    try:
        if current_user.is_authenticated and get_ecole_user():
            return redirect(url_for('ecole_biblique.index'))
    except Exception as _e:
        current_app.logger.warning("register auth guard failed: %s", _e)

    if request.method == 'POST':
        try:
            from app.models.user import User

            if current_user.is_authenticated:
                full_name = request.form.get('full_name', '').strip() or \
                    (current_user.name or current_user.pseudo or '').strip()
                whatsapp = current_user.whatsapp
                role = 'student'
                password = None
            else:
                full_name = request.form.get('full_name', '').strip()
                whatsapp = request.form.get('whatsapp', '').strip()
                password = request.form.get('password', '').strip() or None
                # Security: client-side role select has Étudiant only; whitelist server-side
                client_role = (request.form.get('role', 'student') or 'student').lower()
                role = client_role if client_role in {'student'} else 'student'
                if not password or len(password) < 6:
                    flash('Le mot de passe doit contenir au moins 6 caractères.', 'error')
                    return _safe_register_render()

            if not full_name or not whatsapp:
                flash('Nom et numéro WhatsApp obligatoires.', 'error')
                return _safe_register_render()

            # Validation: whatsapp must look like a phone/token if user is NOT authenticated
            if not current_user.is_authenticated:
                import re as _re
                if not _re.match(r'^\+?[A-Za-z0-9\s\-]{6,25}$', whatsapp):
                    flash('Numéro WhatsApp invalide.', 'error')
                    return _safe_register_render()

            if EcoleUser.query.filter_by(whatsapp=whatsapp).first():
                flash('Ce numéro WhatsApp est déjà enregistré à l\'École Biblique.', 'error')
            else:
                try:
                    main_user = User.query.filter_by(whatsapp=whatsapp).first()
                    if not main_user and not current_user.is_authenticated:
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

                    ecole_user = EcoleUser(full_name=full_name, whatsapp=whatsapp, role=role)
                    # Authenticated users: derive ecole password from main app identity marker
                    pw_to_set = password if password else (
                        'ecole_authenticated_' + (whatsapp or 'user')[-6:]
                    )
                    ecole_user.set_password(pw_to_set)
                    db.session.add(ecole_user)
                    db.session.flush()

                    if role == 'student':
                        student = EcoleStudent.query.filter_by(whatsapp=whatsapp).first()
                        if not student:
                            student = EcoleStudent(full_name=full_name, whatsapp=whatsapp)
                            db.session.add(student)

                    db.session.commit()
                    log_audit(ecole_user.id, 'register', f'User registered as {role}')
                    flash('Inscription à l\'École Biblique réussie !', 'success')
                    return redirect(url_for('ecole_biblique.index'))
                except Exception as inner:
                    db.session.rollback()
                    current_app.logger.error("register POST commit failed: %s", inner, exc_info=True)
                    flash('Erreur lors de l\'inscription. Réessayez s\'il vous plaît.', 'error')
        except Exception as outer:
            db.session.rollback()
            current_app.logger.error("register POST handler failed: %s", outer, exc_info=True)
            flash('Une erreur est survenue pendant l\'inscription.', 'error')

    return _safe_register_render()


def _safe_register_render():
    """Render register.html with TemplateNotFound + generic exception fallback
    (avoids HTTP 500 on Render production when template or dependency missing)."""
    try:
        return render_template('register.html')
    except TemplateNotFound:
        current_app.logger.error(
            "ecole_biblique.register: template register.html missing on disk."
        )
        flash('Page inscription temporairement indisponible.', 'error')
        return redirect(url_for('main.index'))
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            "ecole_biblique.register render failed: %s", exc, exc_info=True
        )
        flash('Page inscription temporairement indisponible.', 'error')
        return redirect(url_for('main.index'))


@ecole_biblique_bp.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    # Preserve CSRF token to avoid issues on next login
    csrf_token = session.get('_csrf_token')
    session.clear()
    if csrf_token:
        session['_csrf_token'] = csrf_token
    flash('Vous êtes déconnecté avec succès.', 'info')
    return redirect(url_for('main.index'))


# ===== POST-ADMISSION REGISTRATION (Part 3, 4, 5) =====

@ecole_biblique_bp.route('/complete_registration', methods=['GET', 'POST'])
@login_required
def complete_registration():
    """Mandatory registration form after passing admission test"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    # Check if already completed
    if ecole_user.registration_completed:
        flash('Vous avez déjà complété votre inscription.', 'info')
        return redirect(url_for('ecole_biblique.student_dashboard'))

    # Check if passed admission test
    passed_test = AdmissionTest.query.filter_by(
        user_id=ecole_user.id, passed=True, completed=True
    ).first()
    if not passed_test:
        flash('Vous devez d\'abord réussir le test d\'admission.', 'warning')
        return redirect(url_for('ecole_biblique.admission_test'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        study_level = request.form.get('study_level', '').strip()
        theology_reason = request.form.get('theology_reason', '').strip()
        church_ministry = request.form.get('church_ministry', '').strip()
        whatsapp_number = request.form.get('whatsapp_number', '').strip()
        student_type = request.form.get('student_type', 'gratuit')
        accept_terms = request.form.get('accept_terms') == 'on'

        # Validation
        errors = []
        if not first_name: errors.append('Le prénom est obligatoire.')
        if not last_name: errors.append('Le nom est obligatoire.')
        if not study_level: errors.append('Le niveau d\'étude est obligatoire.')
        if not theology_reason: errors.append('La raison d\'étudier la théologie est obligatoire.')
        if not church_ministry: errors.append('Le ministère dans l\'église est obligatoire.')
        if not whatsapp_number: errors.append('Le numéro WhatsApp est obligatoire.')
        if student_type not in ['gratuit', 'payant']: errors.append('Type d\'étudiant invalide.')
        if not accept_terms: errors.append('Vous devez accepter les conditions de l\'école.')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            # Update user record
            ecole_user.first_name = first_name
            ecole_user.last_name = last_name
            ecole_user.study_level = study_level
            ecole_user.theology_reason = theology_reason
            ecole_user.church_ministry = church_ministry
            ecole_user.student_type = student_type
            ecole_user.registration_completed = True
            ecole_user.terms_accepted = True
            ecole_user.terms_accepted_at = datetime.utcnow()
            ecole_user.terms_accepted_ip = request.remote_addr
            ecole_user.terms_version = TERMS_VERSION
            ecole_user.full_name = f"{first_name} {last_name}"

            # Log terms acceptance
            terms = TermsAcceptance(
                user_id=ecole_user.id,
                terms_version=TERMS_VERSION,
                ip_address=request.remote_addr
            )
            db.session.add(terms)

            # Initialize modules for this student
            init_modules()
            init_student_modules(ecole_user.id)

            db.session.commit()
            log_audit(ecole_user.id, 'complete_registration',
                      f'Student {first_name} {last_name} completed registration as {student_type}')
            flash('Inscription complétée avec succès ! Bienvenue à l\'École Biblique.', 'success')
            return redirect(url_for('ecole_biblique.student_dashboard'))

    return render_template('complete_registration.html',
                         ecole_user=ecole_user,
                         terms_version=TERMS_VERSION)


# ===== ADMISSION TEST (Existing + Redirect to Registration) =====

@ecole_biblique_bp.route('/admission_test')
@login_required
def admission_test():
    """Display admission test to logged-in student"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Seuls les étudiants peuvent passer le test d\'admission.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    # Check if already completed registration
    if ecole_user.registration_completed:
        flash('Vous avez déjà complété votre inscription.', 'info')
        return redirect(url_for('ecole_biblique.student_dashboard'))

    # Check if student already passed
    passed_test = AdmissionTest.query.filter_by(user_id=ecole_user.id, passed=True, completed=True).first()
    if passed_test:
        # Redirect to registration form instead of dashboard
        flash('Félicitations ! Veuillez compléter votre inscription.', 'success')
        return redirect(url_for('ecole_biblique.complete_registration'))

    # Get or create a test attempt
    current_test = AdmissionTest.query.filter_by(user_id=ecole_user.id, completed=False).first()
    if not current_test:
        selected_questions = random.sample(ADMISSION_QUESTIONS, min(10, len(ADMISSION_QUESTIONS)))
        current_test = AdmissionTest(
            user_id=ecole_user.id,
            total_questions=len(selected_questions),
            completed=False
        )
        db.session.add(current_test)
        db.session.commit()
        session['admission_question_ids'] = [q['id'] for q in selected_questions]

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
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    current_test = AdmissionTest.query.filter_by(user_id=ecole_user.id, completed=False).first()
    if not current_test:
        flash('Aucun test actif trouvé.', 'error')
        return redirect(url_for('ecole_biblique.admission_test'))

    question_ids = session.get('admission_question_ids', [])
    correct_count = 0
    total = len(question_ids)

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

    score = (correct_count / total * 100) if total > 0 else 0
    passed = score >= 70

    current_test.score = score
    current_test.passed = passed
    current_test.completed = True
    current_test.completed_at = datetime.utcnow()
    db.session.commit()

    session.pop('admission_question_ids', None)
    log_audit(ecole_user.id, 'admission_test_completed', f'Score: {score}% - {"Passed" if passed else "Failed"}')

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
        flash('Accès refusé.', 'error')
        return redirect(url_for('ecole_biblique.index'))

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


# ===== GRADE CALCULATION ENGINE (Part 6) =====

@ecole_biblique_bp.route('/api/calculate_grade', methods=['POST'])
@login_required
def api_calculate_grade():
    """Calculate final grade using the formula: (Exam × 70%) + (Assignments × 30%)"""
    try:
        data = request.get_json()
        exam_score = float(data.get('exam_score', 0))
        assignments_score = float(data.get('assignments_score', 0))

        final_score = (exam_score * EXAM_WEIGHT) + (assignments_score * ASSIGNMENTS_WEIGHT)
        passed = final_score >= PASSING_SCORE

        # Determine mention
        if final_score >= 95:
            mention = 'Très Bien'
        elif final_score >= 90:
            mention = 'Bien'
        elif final_score >= 85:
            mention = 'Assez Bien'
        elif final_score >= 80:
            mention = 'Passable'
        else:
            mention = 'Échec'

        return jsonify({
            'success': True,
            'exam_score': round(exam_score, 2),
            'assignments_score': round(assignments_score, 2),
            'final_score': round(final_score, 2),
            'passed': passed,
            'mention': mention,
            'result': 'Réussi' if passed else 'Échec'
        })
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400


def calculate_student_module_grade(student_module):
    """Calculate and update a student's module grade"""
    if student_module.exam_score is not None and student_module.assignments_score is not None:
        student_module.final_score = (student_module.exam_score * EXAM_WEIGHT) + \
                                     (student_module.assignments_score * ASSIGNMENTS_WEIGHT)
        student_module.passed = student_module.final_score >= PASSING_SCORE
        return student_module.final_score
    return None


# ===== MODULE SYSTEM (Part 7) =====

@ecole_biblique_bp.route('/modules')
@login_required
def view_modules():
    """View all modules for the current student"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Accès réservé aux étudiants.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    if not ecole_user.registration_completed:
        flash('Veuillez d\'abord compléter votre inscription.', 'warning')
        return redirect(url_for('ecole_biblique.complete_registration'))

    init_modules()
    modules = Module.query.order_by(Module.number).all()
    student_modules = StudentModule.query.filter_by(student_id=ecole_user.id).all()
    student_module_map = {sm.module_id: sm for sm in student_modules}

    # Determine current module (first locked or incomplete one)
    current_module_num = None
    for m in modules:
        sm = student_module_map.get(m.id)
        if not sm or (sm.locked and not sm.passed):
            current_module_num = m.number
            break
        if sm and not sm.passed:
            current_module_num = m.number
            break

    module_data = []
    for m in modules:
        sm = student_module_map.get(m.id)
        if not sm:
            # Create missing student module record
            sm = StudentModule(student_id=ecole_user.id, module_id=m.id, locked=True)
            db.session.add(sm)
            db.session.commit()

        module_data.append({
            'module': m,
            'student_module': sm,
            'is_current': m.number == current_module_num,
            'fee': get_module_fee(ecole_user.student_type, m.number)
        })

    return render_template('modules.html',
                         modules=module_data,
                         total_modules=TOTAL_MODULES,
                         current_module_num=current_module_num)


@ecole_biblique_bp.route('/module/<int:module_id>', methods=['GET', 'POST'])
@login_required
def module_detail(module_id):
    """View and update a specific module"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role not in ['student', 'teacher', 'admin']:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    module = Module.query.get_or_404(module_id)
    sm = StudentModule.query.filter_by(student_id=ecole_user.id, module_id=module_id).first()

    if not sm:
        flash('Module non trouvé pour cet étudiant.', 'error')
        return redirect(url_for('ecole_biblique.view_modules'))

    # Check if deadline passed
    deadline_passed = check_exam_deadline()
    if deadline_passed and ecole_user.role == 'student':
        flash('La date limite des examens (30 Novembre 2026) est dépassée. Veuillez contacter l\'administration.', 'warning')

    # Check module lock
    if sm.locked and ecole_user.role == 'student':
        # Check if previous module was passed
        prev_module = Module.query.filter_by(number=module.number - 1).first()
        if prev_module:
            prev_sm = StudentModule.query.filter_by(student_id=ecole_user.id, module_id=prev_module.id).first()
            if prev_sm and not prev_sm.passed:
                flash('Vous devez réussir le module précédent avant de continuer.', 'warning')
                return redirect(url_for('ecole_biblique.view_modules'))

        # Check if fee is required
        fee = get_module_fee(ecole_user.student_type, module.number)
        if fee > 0:
            payment = Payment.query.filter_by(
                student_id=ecole_user.id,
                module_number=module.number,
                status='approved',
                payment_type='module_fee'
            ).first()
            if not payment:
                flash(f'Paiement requis pour accéder à ce module. Frais: ${fee} USD.', 'warning')
                return redirect(url_for('ecole_biblique.make_payment', module_number=module.number))

    if request.method == 'POST' and ecole_user.role in ['teacher', 'admin']:
        exam_score = request.form.get('exam_score')
        assignments_score = request.form.get('assignments_score')

        if exam_score is not None and assignments_score is not None:
            try:
                sm.exam_score = float(exam_score)
                sm.assignments_score = float(assignments_score)
                calculate_student_module_grade(sm)
                sm.completed_at = datetime.utcnow()
                db.session.commit()

                # Unlock next module if passed
                if sm.passed:
                    next_module = Module.query.filter_by(number=module.number + 1).first()
                    if next_module:
                        next_sm = StudentModule.query.filter_by(
                            student_id=ecole_user.id, module_id=next_module.id
                        ).first()
                        if next_sm:
                            next_sm.locked = False
                            db.session.commit()

                log_audit(ecole_user.id if ecole_user.role == 'teacher' else ecole_user.id,
                         'grade_updated', f'Module {module.number}: Exam={exam_score}, Assignments={assignments_score}')
                flash(f'Notes du module {module.number} mises à jour avec succès.', 'success')
            except (ValueError, TypeError):
                flash('Veuillez entrer des notes valides.', 'error')

    return render_template('module_detail.html',
                         module=module,
                         student_module=sm,
                         deadline_passed=deadline_passed,
                         exam_deadline=EXAM_DEADLINE,
                         passing_score=PASSING_SCORE,
                         total_modules=TOTAL_MODULES)


# ===== PAYMENT SYSTEM (Part 8 & 9) =====

@ecole_biblique_bp.route('/payments')
@login_required
def list_payments():
    """List all payments for the current student"""
    ecole_user = get_ecole_user()
    if not ecole_user:
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    if ecole_user.role == 'admin':
        payments = Payment.query.order_by(Payment.created_at.desc()).all()
    else:
        payments = Payment.query.filter_by(student_id=ecole_user.id).order_by(Payment.created_at.desc()).all()

    # Calculate fee summary
    total_paid = sum(p.amount for p in payments if p.status == 'approved')
    total_pending = sum(p.amount for p in payments if p.status == 'pending')

    return render_template('payments.html',
                         payments=payments,
                         total_paid=total_paid,
                         total_pending=total_pending)


@ecole_biblique_bp.route('/make_payment', methods=['GET', 'POST'])
@login_required
def make_payment():
    """Make a payment (GKach, Wise, or Manual)"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Accès non autorisé.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    module_number = request.args.get('module_number', type=int)

    if request.method == 'POST':
        payment_method = request.form.get('payment_method', 'gkach')
        amount = request.form.get('amount', type=float)
        currency = request.form.get('currency', 'USD')
        module_number = request.form.get('module_number', type=int)
        payment_type = request.form.get('payment_type', 'module_fee')
        reference = request.form.get('reference', '')
        description = request.form.get('description', '')

        if not amount or amount <= 0:
            flash('Montant invalide.', 'error')
            return render_template('make_payment.html', module_number=module_number,
                                 payment_method=payment_method)

        # Handle GKach payment
        if payment_method == 'gkach':
            from app.services.gkach_service import GkachService
            try:
                # Convert USD to GKach (assume 1 USD = 1 GKach for simplicity, or use rate)
                gkach_amount = int(amount)
                balance = GkachService.get_balance(current_user.whatsapp)

                if balance < gkach_amount:
                    flash(f'Solde GKach insuffisant. Vous avez {balance} GKach, besoin de {gkach_amount}.', 'error')
                    return render_template('make_payment.html', module_number=module_number)

                # Process payment
                GkachService.transfer(
                    from_whatsapp=current_user.whatsapp,
                    to_whatsapp='+50942882076',  # Admin account
                    amount=gkach_amount,
                    description=f'École Biblique - {payment_type} Module {module_number or "N/A"}'
                )

                payment = Payment(
                    student_id=ecole_user.id,
                    amount=amount,
                    currency='GKach',
                    payment_method='gkach',
                    payment_type=payment_type,
                    module_number=module_number,
                    description=description,
                    status='approved',  # Auto-approve GKach payments
                    reviewed_at=datetime.utcnow()
                )
                db.session.add(payment)
                db.session.commit()

                # Unlock module if fee payment
                if payment_type == 'module_fee' and module_number:
                    sm = StudentModule.query.filter_by(
                        student_id=ecole_user.id
                    ).join(Module).filter(Module.number == module_number).first()
                    if sm:
                        sm.locked = False
                        db.session.commit()

                log_audit(ecole_user.id, 'payment_gkach',
                         f'Payment of {amount} GKach for {payment_type} Module {module_number}')
                flash(f'Paiement de {amount} GKach effectué avec succès !', 'success')
                return redirect(url_for('ecole_biblique.list_payments'))

            except Exception as e:
                flash(f'Erreur de paiement GKach: {str(e)}', 'error')
                return render_template('make_payment.html', module_number=module_number)

        # Handle Wise payment
        elif payment_method == 'wise':
            proof_file = None
            if 'proof_file' in request.files:
                file = request.files['proof_file']
                if file and file.filename and allowed_file(file.filename):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    proof_file = f"payment_{uuid.uuid4().hex}.{ext}"
                    file.save(os.path.join(UPLOAD_FOLDER, proof_file))

            payment = Payment(
                student_id=ecole_user.id,
                amount=amount,
                currency='USD',
                payment_method='wise',
                payment_type=payment_type,
                module_number=module_number,
                reference=reference,
                description=description,
                proof_file=proof_file,
                status='pending'
            )
            db.session.add(payment)
            db.session.commit()
            log_audit(ecole_user.id, 'payment_wise_submitted',
                     f'Wise payment of ${amount} for {payment_type} Module {module_number}')
            flash('Paiement Wise soumis. Veuillez transférer le montant via Wise et attendez la validation.', 'success')
            return redirect(url_for('ecole_biblique.list_payments'))

        # Handle Manual payment
        elif payment_method == 'manual':
            proof_file = None
            if 'proof_file' in request.files:
                file = request.files['proof_file']
                if file and file.filename and allowed_file(file.filename):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    proof_file = f"payment_{uuid.uuid4().hex}.{ext}"
                    file.save(os.path.join(UPLOAD_FOLDER, proof_file))

            payment = Payment(
                student_id=ecole_user.id,
                amount=amount,
                currency='USD',
                payment_method='manual',
                payment_type=payment_type,
                module_number=module_number,
                reference=reference,
                description=description,
                proof_file=proof_file,
                status='pending'
            )
            db.session.add(payment)
            db.session.commit()
            log_audit(ecole_user.id, 'payment_manual_submitted',
                     f'Manual payment of ${amount} for {payment_type} Module {module_number}')
            flash('Paiement manuel soumis. En attente de validation.', 'success')
            return redirect(url_for('ecole_biblique.list_payments'))

        else:
            flash('Méthode de paiement invalide.', 'error')

    # Calculate suggested fee
    suggested_fee = 0
    if module_number:
        suggested_fee = get_module_fee(ecole_user.student_type, module_number)

    return render_template('make_payment.html',
                         module_number=module_number,
                         suggested_fee=suggested_fee,
                         wise_link='https://wise.com/pay/me/stanleyd256',
                         student_type=ecole_user.student_type)


# ===== STUDENT DASHBOARD (Part 10) =====

@ecole_biblique_bp.route('/student')
@login_required
def student_dashboard():
    """Enhanced student dashboard with full academic overview"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Accès réservé aux étudiants.', 'error')
        return redirect(url_for('ecole_biblique.register'))

    # Ensure student record exists
    student = EcoleStudent.query.filter_by(whatsapp=current_user.whatsapp).first()
    if not student:
        student = EcoleStudent(full_name=ecole_user.full_name, whatsapp=current_user.whatsapp)
        db.session.add(student)
        db.session.commit()

    # Get grades
    grades = Grade.query.filter_by(student_id=student.id).all()

    # Get admission test
    last_test = AdmissionTest.query.filter_by(user_id=ecole_user.id).order_by(AdmissionTest.started_at.desc()).first()

    # Module progress
    init_modules()
    student_modules = StudentModule.query.filter_by(student_id=ecole_user.id).all()
    total_modules = Module.query.count()
    passed_modules = sum(1 for sm in student_modules if sm.passed)
    failed_modules = sum(1 for sm in student_modules if sm.final_score is not None and not sm.passed)
    locked_modules = sum(1 for sm in student_modules if sm.locked and not sm.passed)

    # Calculate average grade
    graded_modules = [sm for sm in student_modules if sm.final_score is not None]
    overall_average = sum(sm.final_score for sm in graded_modules) / len(graded_modules) if graded_modules else 0

    # Progress percentage
    progress_pct = (passed_modules / TOTAL_MODULES * 100) if TOTAL_MODULES > 0 else 0

    # Payments
    payments = Payment.query.filter_by(student_id=ecole_user.id).order_by(Payment.created_at.desc()).all()
    total_paid = sum(p.amount for p in payments if p.status == 'approved')

    # Calculate remaining fees (all modules are free)
    remaining_fees = 0
    # Graduation fee only
    if ecole_user.student_type == 'gratuit' and passed_modules >= TOTAL_MODULES:
        remaining_fees += FREE_STUDENT_GRADUATION_FEE

    # Estimate graduation date
    estimated_graduation = GRADUATION_DATE

    # Current module
    current_module_number = None
    for sm in student_modules:
        m = Module.query.get(sm.module_id)
        if m and not sm.passed and not sm.locked:
            current_module_number = m.number
            break
    if not current_module_number:
        # Find first locked module
        for sm in student_modules:
            m = Module.query.get(sm.module_id)
            if m and sm.locked:
                current_module_number = m.number
                break

    return render_template('student_dashboard.html',
                         ecole_user=ecole_user,
                         grades=grades,
                         last_test=last_test,
                         student_modules=student_modules,
                         total_modules=TOTAL_MODULES,
                         passed_modules=passed_modules,
                         failed_modules=failed_modules,
                         locked_modules=locked_modules,
                         overall_average=round(overall_average, 1),
                         progress_pct=round(progress_pct, 1),
                         payments=payments,
                         total_paid=total_paid,
                         remaining_fees=remaining_fees,
                         estimated_graduation=estimated_graduation,
                         current_module_number=current_module_number,
                         deadline_passed=check_exam_deadline(),
                         days_until_deadline=(EXAM_DEADLINE - date.today()).days if not check_exam_deadline() else 0,
                         passing_score=PASSING_SCORE)


# ===== ADMIN DASHBOARD (Part 11) =====

@ecole_biblique_bp.route('/admin')
@login_required
def admin_dashboard():
    """Enhanced admin dashboard with full management capabilities"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        flash('Accès administrateur requis.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    # Stats
    total_students = EcoleUser.query.filter_by(role='student').count()
    registered_students = EcoleUser.query.filter_by(role='student', registration_completed=True).count()
    gratuit_students = EcoleUser.query.filter_by(role='student', student_type='gratuit').count()
    payant_students = EcoleUser.query.filter_by(role='student', student_type='payant').count()

    # Pending payments
    pending_wise_payments = Payment.query.filter_by(payment_method='wise', status='pending').count()
    pending_manual_payments = Payment.query.filter_by(payment_method='manual', status='pending').count()

    # Retake students
    retake_students = StudentModule.query.filter(
        StudentModule.retake_count > 0,
        StudentModule.passed == False
    ).count()

    # Graduation eligible
    graduation_eligible = len(get_passing_students())

    # Recent payments
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(10).all()

    # All students with their info
    students = EcoleUser.query.filter_by(role='student').all()
    student_data = []
    for s in students:
        sm_count = StudentModule.query.filter_by(student_id=s.id).count()
        passed_count = StudentModule.query.filter_by(student_id=s.id, passed=True).count()
        total_paid = sum(p.amount for p in Payment.query.filter_by(student_id=s.id, status='approved').all())
        student_data.append({
            'user': s,
            'modules_completed': passed_count,
            'total_modules': max(sm_count, TOTAL_MODULES),
            'total_paid': total_paid
        })

    users = EcoleUser.query.all()
    courses = Course.query.all()

    return render_template('admin_dashboard.html',
                         users=users,
                         courses=courses,
                         total_students=total_students,
                         registered_students=registered_students,
                         gratuit_students=gratuit_students,
                         payant_students=payant_students,
                         pending_wise_payments=pending_wise_payments,
                         pending_manual_payments=pending_manual_payments,
                         retake_students=retake_students,
                         graduation_eligible=graduation_eligible,
                         recent_payments=recent_payments,
                         student_data=student_data)


@ecole_biblique_bp.route('/admin/payments')
@login_required
def admin_payments():
    """Admin view all payments"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        flash('Accès administrateur requis.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    payment_method = request.args.get('method', 'all')
    status_filter = request.args.get('status', 'all')

    query = Payment.query
    if payment_method != 'all':
        query = query.filter_by(payment_method=payment_method)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    payments = query.order_by(Payment.created_at.desc()).all()

    return render_template('admin_payments.html',
                         payments=payments,
                         payment_method=payment_method,
                         status_filter=status_filter)


@ecole_biblique_bp.route('/admin/payment/<int:payment_id>/review', methods=['POST'])
@login_required
def admin_review_payment(payment_id):
    """Admin approve or reject a payment"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        flash('Accès administrateur requis.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    payment = Payment.query.get_or_404(payment_id)
    action = request.form.get('action', '')
    comment = request.form.get('comment', '')

    if action == 'approve':
        payment.status = 'approved'
        payment.admin_comment = comment
        payment.reviewed_by = ecole_user.id
        payment.reviewed_at = datetime.utcnow()

        # Unlock module if fee payment
        if payment.payment_type == 'module_fee' and payment.module_number:
            sm = StudentModule.query.filter_by(
                student_id=payment.student_id
            ).join(Module).filter(Module.number == payment.module_number).first()
            if sm:
                sm.locked = False

        log_audit(ecole_user.id, 'payment_approved',
                 f'Payment {payment.id} approved: ${payment.amount} {payment.currency}')
        flash(f'Paiement #{payment.id} approuvé.', 'success')

    elif action == 'reject':
        payment.status = 'rejected'
        payment.admin_comment = comment
        payment.reviewed_by = ecole_user.id
        payment.reviewed_at = datetime.utcnow()

        log_audit(ecole_user.id, 'payment_rejected',
                 f'Payment {payment.id} rejected: {comment}')
        flash(f'Paiement #{payment.id} rejeté.', 'warning')

    db.session.commit()
    return redirect(url_for('ecole_biblique.admin_payments'))


@ecole_biblique_bp.route('/admin/students')
@login_required
def admin_students():
    """Admin view all students with filters"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        flash('Accès administrateur requis.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    student_type = request.args.get('type', 'all')
    status_filter = request.args.get('status', 'all')

    query = EcoleUser.query.filter_by(role='student')
    if student_type != 'all':
        query = query.filter_by(student_type=student_type)
    if status_filter == 'registered':
        query = query.filter_by(registration_completed=True)
    elif status_filter == 'unregistered':
        query = query.filter_by(registration_completed=False)

    students = query.order_by(EcoleUser.created_at.desc()).all()
    student_data = []
    for s in students:
        sm_list = StudentModule.query.filter_by(student_id=s.id).all()
        passed_count = sum(1 for sm in sm_list if sm.passed)
        payments = Payment.query.filter_by(student_id=s.id).all()
        total_paid = sum(p.amount for p in payments if p.status == 'approved')
        student_data.append({
            'user': s,
            'modules_passed': passed_count,
            'total_paid': total_paid,
            'payment_count': len(payments)
        })

    return render_template('admin_students.html',
                         student_data=student_data,
                         student_type=student_type,
                         status_filter=status_filter,
                         total_modules=TOTAL_MODULES)


@ecole_biblique_bp.route('/admin/graduation')
@login_required
def admin_graduation():
    """Admin view graduation-eligible students"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        flash('Accès administrateur requis.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    passing_students = get_passing_students()
    return render_template('admin_graduation.html',
                         students=passing_students,
                         graduation_date=GRADUATION_DATE)


# ===== RANKING =====

@ecole_biblique_bp.route('/ranking')
def ranking():
    courses = Course.query.all()
    overall_ranking = db.session.query(
        EcoleStudent,
        db.func.avg(Grade.average).label('overall_avg')
    ).join(Grade).group_by(EcoleStudent.id).order_by(db.desc('overall_avg')).all()

    # Also get module-based ranking
    students = EcoleUser.query.filter_by(role='student').all()
    module_ranking = []
    for s in students:
        sm_list = StudentModule.query.filter_by(student_id=s.id).all()
        if sm_list:
            avg = sum(sm.final_score for sm in sm_list if sm.final_score is not None)
            count = sum(1 for sm in sm_list if sm.final_score is not None)
            if count > 0:
                module_ranking.append((s, avg / count, count))

    module_ranking.sort(key=lambda x: x[1], reverse=True)

    return render_template('ranking.html',
                         courses=courses,
                         overall_ranking=overall_ranking,
                         module_ranking=module_ranking[:20])


# ===== TEACHER DASHBOARD =====

@ecole_biblique_bp.route('/teacher')
@login_required
def teacher_dashboard():
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'teacher':
        flash('Accès réservé aux enseignants.', 'error')
        return redirect(url_for('ecole_biblique.index'))
    courses = Course.query.filter_by(teacher_id=ecole_user.id).all()
    modules = Module.query.order_by(Module.number).all()
    
    # Get active conference rooms created by this teacher
    from app.models.konferans import KonferansRoom
    active_rooms = KonferansRoom.query.filter_by(
        creator_name=ecole_user.full_name,
        is_active=True
    ).all()
    
    return render_template('teacher_dashboard.html', 
                         courses=courses, 
                         modules=modules,
                         active_rooms=active_rooms)


# ===== KONFERANS INTEGRATION (LIVE CLASSES) =====

@ecole_biblique_bp.route('/teacher/start_live', methods=['GET', 'POST'])
@login_required
def teacher_start_live():
    """Teacher starts a live conference for a module"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'teacher':
        flash('Accès réservé aux enseignants.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    if request.method == 'POST':
        module_id = request.form.get('module_id', type=int)
        room_name = request.form.get('room_name', '').strip()
        password = request.form.get('password', '').strip()
        
        module = Module.query.get(module_id) if module_id else None
        
        if not room_name:
            room_name = f"Cours {module.name}" if module else "Klass An Live"
        
        # Call the konferans create_room logic
        import requests
        import json
        
        # Get the base URL
        from flask import url_for
        with current_app.test_request_context():
            create_url = url_for('konferans.create_room', _external=True)
        
        # Prepare request data
        data = {
            'room_name': room_name,
            'creator_name': ecole_user.full_name,
            'password': password
        }
        
        # Make internal request
        try:
            from konferans.routes import konferans_bp
            with current_app.test_request_context():
                resp = current_app.test_client().post('/konferans/create_room', 
                    data=json.dumps(data),
                    content_type='application/json')
                result = resp.get_json()
            
            if result and result.get('success'):
                flash(f'Live class started! Code: {result["room_code"]}', 'success')
                return redirect(result['redirect'])
            else:
                error_msg = result.get('message', 'Erè nan kreyasyon sal la.')
                flash(error_msg, 'error')
        except Exception as e:
            flash(f'Erè: {str(e)}', 'error')
        
        return redirect(url_for('ecole_biblique.teacher_dashboard'))
    
    modules = Module.query.order_by(Module.number).all()
    return render_template('teacher_start_live.html', modules=modules)


@ecole_biblique_bp.route('/live_classes')
def live_classes():
    """List all active live classes / conference rooms"""
    from app.models.konferans import KonferansRoom
    
    # Get all active rooms
    rooms = KonferansRoom.query.filter_by(is_active=True).order_by(KonferansRoom.created_at.desc()).all()
    
    # Get teachers list for filtering
    teachers = EcoleUser.query.filter_by(role='teacher').all()
    teacher_names = [t.full_name for t in teachers]
    
    return render_template('live_classes.html', rooms=rooms, teacher_names=teacher_names)


# ===== API ROUTES =====

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


@ecole_biblique_bp.route('/api/student_progress')
@login_required
def api_student_progress():
    """API endpoint for student progress data"""
    ecole_user = get_ecole_user()
    if not ecole_user:
        return jsonify({'error': 'Not authorized'}), 403

    student_modules = StudentModule.query.filter_by(student_id=ecole_user.id).all()
    data = []
    for sm in student_modules:
        m = Module.query.get(sm.module_id)
        if m:
            data.append({
                'module_number': m.number,
                'module_name': m.name,
                'exam_score': sm.exam_score,
                'assignments_score': sm.assignments_score,
                'final_score': sm.final_score,
                'passed': sm.passed,
                'locked': sm.locked,
                'mention': sm.get_mention()
            })

    return jsonify({
        'student_name': ecole_user.full_name,
        'student_type': ecole_user.student_type,
        'modules': data,
        'overall_average': round(
            sum(sm.final_score for sm in student_modules if sm.final_score is not None) /
            max(sum(1 for sm in student_modules if sm.final_score is not None), 1), 1
        )
    })


@ecole_biblique_bp.route('/api/export/students')
@login_required
def api_export_students():
    """Export students data as JSON"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        return jsonify({'error': 'Not authorized'}), 403

    fmt = request.args.get('format', 'json')
    students = EcoleUser.query.filter_by(role='student').all()

    data = []
    for s in students:
        sm_list = StudentModule.query.filter_by(student_id=s.id).all()
        passed_count = sum(1 for sm in sm_list if sm.passed)
        total_paid = sum(p.amount for p in Payment.query.filter_by(student_id=s.id, status='approved').all())
        data.append({
            'full_name': s.full_name,
            'first_name': s.first_name,
            'last_name': s.last_name,
            'whatsapp': s.whatsapp,
            'type': s.student_type,
            'study_level': s.study_level,
            'church_ministry': s.church_ministry,
            'modules_passed': passed_count,
            'total_paid': total_paid,
            'registered': s.registration_completed,
            'created_at': s.created_at.isoformat() if s.created_at else None
        })

    return jsonify(data)


@ecole_biblique_bp.route('/admin/admission_results')
@login_required
def admin_admission_results():
    """Admin view of all admission test results"""
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'admin':
        return redirect(url_for('ecole_biblique.index'))

    tests = AdmissionTest.query.order_by(AdmissionTest.started_at.desc()).all()
    return render_template('admin_admission_results.html', tests=tests)


# ===== COURSE FILES (PDF from COURS folder) =====

@ecole_biblique_bp.route('/cours/<path:filename>')
def serve_course_file(filename):
    """Serve PDF course files from the COURS directory"""
    import os
    from flask import send_from_directory, abort
    
    # Get the COURS directory path (relative to this blueprint)
    cours_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'COURS')
    
    # Security: ensure the file exists and is a PDF
    if not filename.lower().endswith('.pdf'):
        abort(404)
    
    # Check if file exists
    filepath = os.path.join(cours_dir, filename)
    if not os.path.exists(filepath):
        abort(404)
    
    return send_from_directory(cours_dir, filename)
