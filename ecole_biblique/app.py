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

# Fee structure — Cycle 2026
FREE_MODULES = 3                       # Modules 1..3 = 100% gratuits pour TOUS, APRÈS acceptation CG
INITIAL_UNLOCKED_MODULES = 1           # MODULE #1 UNIQUEMENT initialement débloqué (immédiatement après acceptation CG)
FREE_STUDENT_FEE_PER_BLOCK = 30        # Étudiant gratuit : $30 USD par bloc TANDEM (2 modules) après #3
FREE_STUDENT_GRADUATION_FEE = 100      # Frais de graduation étudiant gratuit
PAID_STUDENT_FEE_PER_BLOCK = 0         # Étudiant payant : blocs TANDEM inclus (total $600)
PAID_STUDENT_TOTAL = 600               # Paiement unique étudiant payant (inclut blocs + graduation + Bachelor)
TANDEM_BLOCK_SIZE = 2                  # Modules 4+ se débloquent 2 par 2 en tandem


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
    """Initialize all 20 modules from the COURS folder if they don't exist.

    BUG FIX (Render Linux case-sensitive FS):
    Utilise le NOM RÉEL des fichiers PDF présents dans COURS/ (MODULE 1…, Module 2…)
    plutôt qu'un nom statique fictif qui peut ne pas exister (Module 1… vs MODULE 1…).
    """
    import os as _os
    import re as _re

    here = _os.path.dirname(_os.path.abspath(__file__))
    cours_dir = _os.path.join(here, 'COURS')
    real_pdfs = []
    try:
        real_pdfs = [f for f in _os.listdir(cours_dir) if f.lower().endswith('.pdf')]
    except OSError:
        real_pdfs = []

    def _find_pdf_for_module(n, fallback_guess):
        """Cherche un fichier PDF correspondant au module N.
        Priorité:
          1) filename == fallback_guess (exact match)
          2) normalized match: case+whitespace+accents folded vs fallback_guess
          3) starts with (MODULE|Module) N (e.g. MODULE 1… , Module 2 …)
          4) sinon fallback_guess original (même si pas présent = course_file cohérent avec get_course_url)
        """
        if fallback_guess and fallback_guess in real_pdfs:
            return fallback_guess
        def _fold(s):
            import unicodedata as _ud
            s = _ud.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
            return _re.sub(r'\s+', '', s).lower()
        if fallback_guess:
            fb_folded = _fold(fallback_guess)
            for f in real_pdfs:
                if _fold(f) == fb_folded:
                    return f
            fb_noext = _fold(fallback_guess[:-4]) if fallback_guess.endswith('.pdf') else fb_folded
            for f in real_pdfs:
                if _fold(f[:-4]) == fb_noext:
                    return f
        pat_start = _re.compile(r'^(?:MODULE|Module)\s*' + str(int(n)) + r'(?![0-9])', _re.IGNORECASE)
        for f in sorted(real_pdfs):
            if pat_start.match(f):
                return f
        return fallback_guess  # garde valeur de départ même si fichier absent

    module_definitions = [
        (1, "Introduction à la Bible (Religion)", "Module 1: Introduction à la Bible (Religion)", "MODULE 1(RELIGION).pdf"),
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
        resolved_course_file = _find_pdf_for_module(number, course_file)
        module = Module.query.filter_by(number=number).first()
        if not module:
            module = Module(number=number, name=name, description=description, course_file=resolved_course_file)
            db.session.add(module)
        else:
            if not module.course_file:
                module.course_file = resolved_course_file
            # Mise à jour vers nom réel si l'ancien ne correspond à AUCUN fichier (safe idempotent)
            else:
                old_exists = (module.course_file in real_pdfs) if real_pdfs else False
                if not old_exists and resolved_course_file and resolved_course_file in real_pdfs:
                    module.course_file = resolved_course_file
    db.session.commit()


def init_student_modules(student_id, unlock_count=None):
    """Initialize module tracking for a new student.

    - unlock_count: Nombre de modules à débloquer initialement. Default = INITIAL_UNLOCKED_MODULES (1).
      Avant Cycle 2026, c'était FREE_MODULES (3). Maintenant c'est MODULE #1 UNIQUEMENT (exigence:
      termes et conditions acceptés → accès MODULE #1 seulement; les modules 2+ doivent être
      débloqués explicitement après réussite de #1, ou via paiements blocs tandem).
    """
    if unlock_count is None:
        unlock_count = INITIAL_UNLOCKED_MODULES  # 1 (Module #1 seulement)
    modules = Module.query.order_by(Module.number).all()
    for i, module in enumerate(modules):
        sm = StudentModule.query.filter_by(student_id=student_id, module_id=module.id).first()
        if not sm:
            sm = StudentModule(
                student_id=student_id,
                module_id=module.id,
                locked=(i >= unlock_count),
                passed=False
            )
            db.session.add(sm)
        else:
            # Règle de migration: si la personne a déjà fait progresser son cursus (modules passés/
            # examens corrigés), on ne rétrograde pas. Sinon, applique nouveau verrou: #1 UNIQUEMENT.
            already_progressed = (sm.passed or sm.final_score is not None or sm.exam_score is not None
                                  or sm.assignments_score is not None or sm.completed_at is not None)
            if not already_progressed:
                sm.locked = (i >= unlock_count)
    db.session.commit()


def get_module_fee(student_type, module_number):
    """Calculate fee for a given module based on student type + tandem blocks.

    Business rules Cycle 2026 :
      - Modules 1..FREE_MODULES (1, 2, 3) : GRATUITS pour TOUS les étudiants.
      - Modules 4+ : par blocs de TANDEM_BLOCK_SIZE (2) appelés "blocs tandem".
        L'étudiant paie UNE SEULE FOIS le frais du bloc pour débloquer les
        2 modules qui le composent. Le frais est facturé sur le PREMIER module
        impair de chaque bloc (4, 6, 8, ..., 20). Le module pair qui suit
        (5, 7, 9, ..., 21) est alors gratuit car déjà couvert.
      - Student gratuit : FREE_STUDENT_FEE_PER_BLOCK ($30 USD) par bloc tandem.
      - Student payant  : blocs tandem inclus dans le $600 (frais = $0).
    """
    if not isinstance(module_number, int) or module_number <= FREE_MODULES:
        return 0

    if module_number > TOTAL_MODULES:
        return 0

    # Modules 4+ : chaque bloc est [pair_impair 4,5] [6,7] [8,9] ...
    # Premier module du bloc = module_number % TANDEM_BLOCK_SIZE == 0 when TANDEM_BLOCK_SIZE==2 and number>=4 even
    if TANDEM_BLOCK_SIZE == 2:
        is_first_of_block = (module_number % 2 == 0)  # 4,6,8...20
    else:
        offset = module_number - FREE_MODULES - 1
        is_first_of_block = (offset % TANDEM_BLOCK_SIZE == 0)

    if not is_first_of_block:
        # Deuxième module du bloc tandem : déjà payé via le premier module
        return 0

    if student_type == 'payant':
        return PAID_STUDENT_FEE_PER_BLOCK  # 0 (inclus)
    return FREE_STUDENT_FEE_PER_BLOCK  # 30 USD par bloc pour gratuit


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

                    # ===== SESSION FIX: auto-login main app user after ecole registration =====
                    # Bug: unauthenticated user creates ecole account → commit → redirect
                    # to /ecole_biblique/index → auth guard redirects to /auth/login again
                    # (feels like "session not kept / logged out"). Instead: log the user
                    # into the main app right now with remember=True + permanent=True so
                    # their session stays open until they explicitly log out.
                    from flask_login import login_user as _fl_login_user
                    from flask import session as _fl_sess
                    try:
                        _main_user = main_user or (
                            User.query.filter_by(whatsapp=whatsapp).first() if not current_user.is_authenticated else None
                        )
                        if _main_user and not current_user.is_authenticated:
                            _fl_login_user(_main_user, remember=True, force=True)
                            _fl_sess.permanent = True
                            _fl_sess['_remember_set'] = True
                    except Exception as _sess_err:
                        current_app.logger.warning(
                            'ecole_biblique.register: auto-login main user failed: %s',
                            _sess_err,
                        )

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

            # Auto-start Module #1 (set started_at immediately so timeline begins)
            mod1 = Module.query.filter_by(number=1).first()
            if mod1:
                sm1 = StudentModule.query.filter_by(student_id=ecole_user.id, module_id=mod1.id).first()
                if sm1 and not sm1.started_at:
                    sm1.started_at = datetime.utcnow()
                    db.session.commit()
                    log_audit(ecole_user.id, 'module_started',
                              f'Auto-start Module #1 immediately post-registration (route {student_type})')

            flash('Inscription complétée avec succès ! Bienvenue à l\'École Biblique. '
                  'Vous accédez dès maintenant au Module #1 (modules 2+ seront débloqués '
                  'successivement après chaque réussite).', 'success')
            if mod1:
                return redirect(url_for('ecole_biblique.module_detail', module_id=mod1.id))
            return redirect(url_for('ecole_biblique.student_dashboard'))

    return render_template('complete_registration.html',
                         ecole_user=ecole_user,
                         terms_version=TERMS_VERSION)


# ===== TERMES ET CONDITIONS — OBLIGATOIRES APRÈS TEST D'ADMISSION RÉUSSI =====

SCHOOL_TERMS_HTML_FR = """
<div class="terms-section">
  <h3>Article 1 — Présentation & Objectifs</h3>
  <p>L' <strong>École Biblique MEGD-Haïti</strong>, en partenariat officiel avec le <strong>GLOBAL CONNEXION NETWORK BIBLE SCHOOL (Alabama, États-Unis)</strong>, est un établissement d'enseignement supérieur théologique ouvert à tous les chrétiens engagés désireux de approfondir leur connaissance de la Parole de Dieu et de se préparer au service dans l'Église locale ou dans la mission.</p>
  <p>Le cycle complet est structuré en <strong>20 modules académiques progressifs</strong>, validés par des épreuves écrites (examens) et des devoirs d'application pratique, sous la supervision de professeurs qualifiés et agréés par la direction académique.</p>
</div>
<div class="terms-section">
  <h3>Article 2 — Parcours Pédagogique & Déblocage des Modules</h3>
  <ol>
    <li><strong>Étape 0 — Test d'admission :</strong> Tout postulant doit réussir un test d'admission interne (seuil minimum de <strong>70 %</strong> de bonnes réponses) avant de pouvoir accéder au reste du cursus.</li>
    <li><strong>Étape 1 — Signature électronique des présentes :</strong> Une fois le test d'admission réussi, le postulant doit lire et accepter explicitement ces <strong>Conditions Générales de l'École</strong> (présente page). Aucun module ne sera accessible tant que cette étape n'est pas validée.</li>
    <li><strong>Étape 2 — Module #1 UNIQUEMENT :</strong> Immédiatement après acceptation des conditions, l'étudiant accède au <strong>Module #1 seul</strong> : <em>Introduction à la Bible (Religion)</em>. Les modules #2 à #20 restent <strong>verrouillés</strong> tant que le module #1 n'est pas réussi.</li>
    <li><strong>Étape 3 — Progression séquentielle modules #2 et #3 gratuits :</strong>
      Chaque module #n (n ≥ 1) doit être réussi avant que le module #n+1 ne soit débloqué. Les modules #2 et #3 restent <strong>100 % gratuits</strong> pour tous les étudiants et sont débloqués un par un après chaque réussite.
    </li>
    <li><strong>Étape 4 — Blocs TANDEM payants à partir de #4 :</strong> Après le module #3, l'accès aux modules 4 → 20 se fait par <strong>blocs de 2 modules dits « blocs TANDEM »</strong> : #4 &amp; #5, #6 &amp; #7, ..., #20. L'étudiant paye UNE SEULE FOIS le frais du bloc pour débloquer les 2 modules. Les deux modules d'un bloc tandem se débloquent <em>simultanément</em> au paiement, et doivent ensuite être validés successivement (#4 → #5 → #6 → #7, etc.).</li>
  </ol>
</div>
<div class="terms-section">
  <h3>Article 3 — Évaluation, Moyenne & Reprises</h3>
  <ul>
    <li>Pour chaque module, la note finale est calculée selon la formule : <strong>Note Finale = (Examen × 70 %) + (Devoirs × 30 %)</strong>.</li>
    <li>Le <strong>seuil de réussite</strong> est fixé à <strong>80 / 100</strong>. Toute note finale inférieure à 80 est considérée comme un <em>échec</em>.</li>
    <li>En cas d'échec, l'étudiant doit s'acquitter de <strong>frais de reprise de $50 USD par module</strong> avant de pouvoir repasser les épreuves. Le module suivant reste impérativement <em>verrouillé</em> tant que le module courant n'est pas réussi.</li>
    <li>Toute fraude, tentative de triche, ou plagiat avéré lors d'un devoir ou d'un examen entraine <strong>l'exclusion immédiate et définitive</strong> de l'étudiant, sans aucun remboursement de frais déjà versés.</li>
  </ul>
</div>
<div class="terms-section">
  <h3>Article 4 — Frais &amp; Paiements (Cycle 2026)</h3>
  <h5>4.1 Plan « Étudiant GRATUIT »</h5>
  <ul>
    <li>Frais d'inscription initial : <strong>$0 USD</strong></li>
    <li>Modules #1, #2, #3 : <strong>100 % gratuits</strong> (débloqués un par un après chaque réussite)</li>
    <li>Chaque bloc TANDEM à partir de #4 : <strong>$30 USD / bloc de 2 modules</strong></li>
    <li>Frais de reprise en cas d'échec : <strong>$50 USD / module</strong></li>
    <li>Frais de graduation (cérémonie + certificat officiel) : <strong>$100 USD</strong> (en fin de cycle, modules 1→20 tous réussis)</li>
  </ul>
  <h5>4.2 Plan « Étudiant PAYANT » (RECOMMANDÉ)</h5>
  <ul>
    <li>Paiement unique d'engagement total : <strong>$600 USD</strong> (acquitté à l'inscription, ou en 1 seule transaction)</li>
    <li>Inclut : Modules #1→#20 (tous blocs TANDEM payés d'avance) + <strong>Bachelor Degree</strong> délivré par le partenaire américain GLOBAL CONNEXION NETWORK BIBLE SCHOOL + Frais de cérémonie de graduation INCLUS.</li>
    <li>Frais de reprise en cas d'échec : <strong>$50 USD / module</strong> (même règle que plan gratuit)</li>
  </ul>
  <h5>4.3 Moyens de paiement acceptés</h5>
  <p>Les paiements peuvent être effectués par :
    <strong>GKach</strong> (système interne de Glory2Yah, zéro frais, approbation instantanée),
    <strong>Wise</strong> (transfert international, approbation sous 24–48h sur présentation d'une preuve),
    ou <strong>paiement manuel</strong> (espèces, Mobile Money, chèque — approbation administrative après vérification).
    Les reçus de paiement sont conservés dans le tableau de bord étudiant et sont téléchargeables à tout moment.</p>
</div>
<div class="terms-section">
  <h3>Article 5 — Calendrier Officiel Cycle 2026</h3>
  <ol>
    <li>Date limite <strong>impérative et non prorogeable</strong> pour terminer <em>TOUS</em> les examens (modules 1→20) : <strong>30 Novembre 2026, 23h59, heure locale Port-au-Prince</strong>.</li>
    <li>Date limite <strong>impérative et non prorogeable</strong> pour solder <em>TOUS</em> les paiements en attente (blocs TANDEM, reprises, frais de graduation) : <strong>30 Novembre 2026</strong>.</li>
    <li>Au-delà du 30 Novembre 2026 : <em>accès aux examens fermé, scores gelés, aucun paiement ne sera plus accepté pour le cycle 2026</em>. Tout étudiant n'ayant pas terminé son cursus dans les délais devra se réinscrire au cycle suivant.</li>
    <li><strong>Cérémonie de GRADUATION 2026</strong> : <strong>25 Décembre 2026</strong>, Église MEGD. Seuls les étudiants admissibles (modules 1→20 réussis, soldes financiers à zéro) seront autorisés à monter sur scène et à recevoir leurs diplômes/certificats officiels.</li>
  </ol>
</div>
<div class="terms-section">
  <h3>Article 6 — Propriété Intellectuelle &amp; Confidentialité</h3>
  <p>Les supports de cours (PDF, vidéos, notes, questions d'examen, devoirs corrigés) sont la <strong>propriété exclusive</strong> de l'École Biblique MEGD-Haïti et de ses enseignants. Toute diffusion, revente, partage public, ou reproduction partielle ou totale, sans autorisation écrite préalable de la direction, est strictement interdite et pourra donner lieu à des poursuites disciplinaires ou judiciaires, ainsi qu'à l'exclusion immédiate sans remboursement.</p>
  <p>Les données personnelles des étudiants (nom, prénom, WhatsApp, notes, paiements) sont conservées dans le respect strict de la politique interne de confidentialité et ne sont jamais vendues ni partagées à des tiers commerciaux.</p>
</div>
<div class="terms-section">
  <h3>Article 7 — Engagement Personnel de l'Étudiant</h3>
  <p>En cochant la case ci-dessous, l'étudiant déclare explicitement :
    <br>1) Avoir lu <em>dans son intégralité</em> les 7 Articles des présentes Conditions Générales ;
    <br>2) Accepter sans réserve <em>toutes</em> les clauses académiques, financières et disciplinaires du cycle 2026 ;
    <br>3) S'engager personnellement à respecter les délais impératifs du 30 Novembre 2026 pour les examens et les paiements ;
    <br>4) S'engager à travailler sérieusement chaque module, sans fraude ni plagiat ;
    <br>5) Accepter le principe de déblocage séquentiel : <strong>Module #1 UNIQUEMENT après signature</strong>, puis #2 après réussite de #1, #3 après réussite de #2, puis blocs TANDEM payants 2 par 2 à partir de #4.
  </p>
  <p class="text-muted small"><em>Document Version : TERMS_VERSION_PLACEHOLDER — École Biblique MEGD-Haïti © 2026.</em></p>
</div>
""".replace('TERMS_VERSION_PLACEHOLDER', str(TERMS_VERSION))


@ecole_biblique_bp.route('/terms_conditions', methods=['GET', 'POST'])
@login_required
def terms_conditions():
    """Page officielle des Termes & Conditions.

    Accessible SEULEMENT si :
      - l'étudiant a RÉUSSI le test d'admission (seuil 70%, AdmissionTest.passed=True)
      - ET (pas encore accepté les CG) OU (consultation libre après acceptation)

    SUR POST (acceptation CG) :
      - enregistre TermsAcceptance + marque terms_accepted / terms_version / ip / date dans EcoleUser
      - (pas encore de registration_completed = True, car on a pas encore de first_name/last_name etc.,
         ça viendra sur /complete_registration ensuite, qui exige déjà la CG acceptée via son garde-fou)
      - SI l'étudiant a déjà COMPLÉTÉ l'inscription finale, on force aussi le déverrouillage MODULE #1 seulement
        (compatibilité anciens comptes)
      - Redirection : si inscription finalisée → Module #1 detail ; sinon → Complete Registration (formulaire identité)
    """
    ecole_user = get_ecole_user()
    if not ecole_user or ecole_user.role != 'student':
        flash('Accès réservé aux étudiants ayant un compte.', 'error')
        return redirect(url_for('ecole_biblique.index'))

    # Garde : doit avoir passé (admis) le test admission AVANT de lire/voir CG
    passed_test = AdmissionTest.query.filter_by(
        user_id=ecole_user.id, passed=True, completed=True
    ).first()
    if not passed_test:
        flash('Vous devez d\'abord réussir le test d\'admission (seuil 70%) avant de consulter '
              'les conditions de l\'École.', 'warning')
        return redirect(url_for('ecole_biblique.admission_test'))

    if request.method == 'POST':
        accept = request.form.get('accept_terms') == 'on'
        if not accept:
            flash('Vous devez cocher la case d\'acceptation pour continuer.', 'error')
            return redirect(url_for('ecole_biblique.terms_conditions'))

        # --- Enregistrement signature CG ---
        ecole_user.terms_accepted = True
        ecole_user.terms_accepted_at = datetime.utcnow()
        ecole_user.terms_accepted_ip = request.remote_addr
        ecole_user.terms_version = TERMS_VERSION

        # log du TermsAcceptance (audit légal)
        ta = TermsAcceptance.query.filter_by(user_id=ecole_user.id, terms_version=TERMS_VERSION).first()
        if not ta:
            ta = TermsAcceptance(user_id=ecole_user.id, terms_version=TERMS_VERSION,
                                 ip_address=request.remote_addr)
            db.session.add(ta)

        # --- SÉCURITÉ initiale MODULE #1 UNIQUEMENT ---
        init_modules()
        init_student_modules(ecole_user.id, unlock_count=INITIAL_UNLOCKED_MODULES)
        # Force déverrouillage #1 (garantie) + verrouillage #2..#20 (si pas encore commencé)
        all_sm = (StudentModule.query.filter_by(student_id=ecole_user.id)
                  .join(Module).order_by(Module.number).all())
        for sm in all_sm:
            already_progressed = (sm.passed or sm.final_score is not None or sm.exam_score is not None
                                  or sm.assignments_score is not None or sm.completed_at is not None)
            if sm.module and sm.module.number == 1:
                # Mod #1 toujours unlocked (même si ancien étudiant on préserve pas l'état si passé)
                if not already_progressed:
                    sm.locked = False
                if not sm.started_at:
                    sm.started_at = datetime.utcnow()
            elif sm.module and sm.module.number >= 2 and not already_progressed:
                # Verrouiller #2+ (on ne touche pas aux modules déjà travaillés par des anciens étudiants)
                sm.locked = True

        db.session.commit()
        log_audit(ecole_user.id, 'terms_accepted',
                  f'Acceptation CG v{TERMS_VERSION}. MODULE #1 UNIQUEMENT initialisé. '
                  f'registration_completed={ecole_user.registration_completed}')

        # -- Redirection post-acceptation CG --
        if ecole_user.registration_completed:
            # Ancien compte (ou déjà complété) → Module #1 directement
            flash('Termes et Conditions acceptés ! Bienvenue — vous accédez maintenant au Module #1.', 'success')
            mod1 = Module.query.filter_by(number=1).first()
            if mod1:
                return redirect(url_for('ecole_biblique.module_detail', module_id=mod1.id))
            return redirect(url_for('ecole_biblique.student_dashboard'))
        else:
            # Nouveau postulant → formulaire d'inscription identité (complete_registration)
            flash('Termes et Conditions acceptés ! Complétez maintenant votre identité (étape finale) '
                  'pour accéder au Module #1.', 'success')
            return redirect(url_for('ecole_biblique.complete_registration'))

    # GET : affiche CG
    already_signed = bool(ecole_user.terms_accepted and ecole_user.terms_version == TERMS_VERSION)

    return render_template(
        'terms_conditions.html',
        terms_html=SCHOOL_TERMS_HTML_FR,
        terms_version=TERMS_VERSION,
        already_signed=already_signed,
        school_name='École Biblique MEGD-Haïti',
        partner='GLOBAL CONNEXION NETWORK BIBLE SCHOOL – Alabama, USA',
        registration_completed=bool(ecole_user.registration_completed),
    )


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

    if passed and not ecole_user.registration_completed:
        flash('Bravo ! Vous avez réussi le test d\'admission. Consultez vos résultats '
              'puis acceptez les termes et conditions de l\'École Biblique avant d\'accéder '
              'au Module #1.', 'success')
        return redirect(url_for('ecole_biblique.admission_result', test_id=current_test.id))

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

    # Check if deadline passed — after 30 Novembre, exams are closed for students
    deadline_passed = check_exam_deadline()
    if deadline_passed and ecole_user.role == 'student':
        flash(f'La date limite des examens ({EXAM_DEADLINE.strftime("%d %B %Y")}) est dépassée. '
              f'Tous les examens et paiements devaient être soldés avant cette date. '
              f'Veuillez contacter l\'administration.', 'error')
        return redirect(url_for('ecole_biblique.student_dashboard'))

    # Check module lock
    if sm.locked and ecole_user.role == 'student':
        # Check if previous module was passed
        prev_module = Module.query.filter_by(number=module.number - 1).first()
        if prev_module:
            prev_sm = StudentModule.query.filter_by(student_id=ecole_user.id, module_id=prev_module.id).first()
            if prev_sm and not prev_sm.passed:
                flash('Vous devez réussir le module précédent avant de continuer.', 'warning')
                return redirect(url_for('ecole_biblique.view_modules'))

        # Check if fee is required for module (tandem block paid on FIRST-OF-BLOCK only — already computed by get_module_fee)
        fee = get_module_fee(ecole_user.student_type, module.number)
        if fee > 0:
            payment = Payment.query.filter_by(
                student_id=ecole_user.id,
                module_number=module.number,
                status='approved',
                payment_type='module_fee'
            ).first()
            if not payment:
                # Tandem block coverage check: if THIS module is the SECOND in the block (odd # >=5),
                # a payment on the first-of-block (module_number-1) ALSO counts as payment for both.
                if TANDEM_BLOCK_SIZE == 2 and module.number > FREE_MODULES and module.number % 2 == 1:
                    first_of_block = module.number - 1  # e.g. 5 -> 4
                    pair_payment = Payment.query.filter_by(
                        student_id=ecole_user.id,
                        module_number=first_of_block,
                        status='approved',
                        payment_type='module_fee'
                    ).first()
                    if not pair_payment:
                        # Redirect to pay for first-of-block (since it's cheaper & covers both)
                        flash(f'Paiement du bloc tandem requis pour débloquer Modules #{first_of_block} et #{module.number}. '
                              f'Frais bloc: ${get_module_fee(ecole_user.student_type, first_of_block)} USD.',
                              'warning')
                        return redirect(url_for('ecole_biblique.make_payment', module_number=first_of_block))
                else:
                    flash(f'Paiement requis pour accéder à ce module. Frais: ${fee} USD.', 'warning')
                    return redirect(url_for('ecole_biblique.make_payment', module_number=module.number))

    # Teacher/Admin grade update — also blocked AFTER 30 Novembre (scores frozen)
    if request.method == 'POST' and ecole_user.role in ['teacher', 'admin']:
        if check_exam_deadline():
            flash(f'Impossible de modifier les notes après le {EXAM_DEADLINE.strftime("%d %B %Y")}. '
                  f'Cycle 2026 est terminé.', 'error')
        else:
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

    # Auto-start: first time viewing module #1, mark started_at
    if module.number == 1 and not sm.started_at and ecole_user.role == 'student':
        sm.started_at = datetime.utcnow()
        try:
            db.session.commit()
            log_audit(ecole_user.id, 'module_started', 'Démarrage automatique du Module #1 après inscription complète')
        except Exception:
            db.session.rollback()

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
    """Serve PDF course files from the COURS directory.

    Robustesse anti-bug Render/Linux FS case-sensitive:
    - Les noms de fichiers COURS ont une casse mélangée (MODULE 1…, Module 2…, etc.)
      et les DB course_file utilisent parfois 'Module 1(RELIGION).pdf' alors que
      le fichier réel s'appelle 'MODULE 1(RELIGION).pdf' → 404 → Error.
    - Fallbacks:
        1) exact match (OS sensitive)
        2) case-insensitive + accents/whitespace folded match sur COURS/*
        3) par numéro de module: extrait N depuis "Module N(...)" ou "MODULE N(...)"
           → premier fichier PDF COURS dont nom match "^(MODULE|Module)\s*N"
    """
    import os
    import re
    import unicodedata
    from flask import send_from_directory, abort, current_app

    cours_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'COURS')
    if not os.path.isdir(cours_dir):
        current_app.logger.warning('COURS dir missing: %s', cours_dir)
        abort(404)

    # Only PDF allowed (404 silent otherwise — same as original behavior)
    if not filename.lower().endswith('.pdf'):
        abort(404)

    def _fold(s):
        s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
        s = re.sub(r'\s+', '', s).lower()
        return s

    # 1) exact match
    exact = os.path.join(cours_dir, filename)
    if os.path.isfile(exact):
        return send_from_directory(cours_dir, filename)

    # List available PDF files in COURS
    try:
        available = [f for f in os.listdir(cours_dir) if f.lower().endswith('.pdf')]
    except OSError:
        available = []

    req_folded = _fold(filename)

    # 2) exact-folded match
    for f in available:
        if _fold(f) == req_folded:
            return send_from_directory(cours_dir, f)

    # 3) prefix-folded match (sans extension .pdf)
    req_noext = _fold(filename[:-4])
    for f in available:
        if _fold(f[:-4]) == req_noext:
            return send_from_directory(cours_dir, f)

    # 4) module number fallback: extrait N depuis /Module N( | MODULE N(
    m = re.search(r'(?:MODULE|Module)\s*([0-9]{1,2})', filename, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        pattern = re.compile(r'^(?:MODULE|Module)\s*' + str(n) + r'(?![0-9])', re.IGNORECASE)
        for f in sorted(available):
            if pattern.match(f):
                return send_from_directory(cours_dir, f)

    current_app.logger.warning(
        'serve_course_file 404: requested=%s available=%s',
        filename, available,
    )

    # Fallback FINAL — au lieu d'une page "Error / Go Home" minimale,
    # on redirige l'utilisateur vers la liste des modules de l'école
    # avec un message explicatif (ou login page si non authentifié).
    from flask import url_for as _uf, redirect as _rd, flash as _fl
    from flask_login import current_user as _cu, login_required as _lr
    try:
        from unicodedata import normalize as _norm
        _msg = (
            "❌ Fichier du cours introuvable : \"" +
            _norm('NFKD', filename).encode('ascii','ignore').decode('ascii')[:60] +
            "\". Retournez à la liste des modules pour choisir un autre cours."
        )
    except Exception:
        _msg = ("❌ Fichye kou a pa jwenn. "
                "Retounen nan lis modil yo pou chwazi yon lòt kou.")
    try:
        _fl(_msg, 'error')
    except Exception:
        pass
    try:
        if _cu and _cu.is_authenticated:
            return _rd(_uf('ecole_biblique.student_dashboard'))
        return _rd(_uf('ecole_biblique.index'))
    except Exception:
        return _rd(_uf('main.index'))
