"""
PHASE 2f - Validation script / integration rapide pour l'extension E-LEARNING (non-braking).

Objectif :
  A. py_compile sur modules critiques (elimine erreurs syntaxe des le premier run)
  B. create_app() boot OK en mode TEST (testing config SQLite :memory:)
  C. db.create_all() -> verifie 12 tables el_* existent + FK konferans <-> el_lesson ok
  D. Regression Konferans : (1) anon /konferans/create_room POST -> 401 JSON (bloque depuis fix security)
                           (2) /konferans/ anon -> contient bien CTA "Konekte pou Kreye Sal"
                           (3) /konferans/ logged -> input creator=readonly et prefilled
Tous tests : stdout assertions Python assert ; sys.exit(0) si PASS sinon 1.
"""
from __future__ import annotations

import os
import py_compile
import sys
import tempfile
from pathlib import Path

# Force UTF-8 stdout (fix cp1252 charmap under windows with non-ascii arrows)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
PY3_IO = sys.stdout

PROJECT_ROOT = Path(__file__).resolve().parent
assert (PROJECT_ROOT / 'app' / '__init__.py').is_file(), "Mauvais project root"


def banner(msg: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n{msg}\n{line}")


# --- [A] py_compile ------------------------------------------------------------
banner("[A] py_compile — modules E-LEARNING + conf core")
files_to_compile = [
    PROJECT_ROOT / 'app' / '__init__.py',
    PROJECT_ROOT / 'app' / 'models' / '__init__.py',
    PROJECT_ROOT / 'app' / 'models' / 'elearning.py',
    PROJECT_ROOT / 'app' / 'routes' / 'elearning' / '__init__.py',
    PROJECT_ROOT / 'app' / 'routes' / 'elearning' / 'routes.py',
]
for f in files_to_compile:
    assert f.is_file(), f"Fichier introuvable: {f}"
    py_compile.compile(str(f), doraise=True)
    print(f"  OK compile {f.relative_to(PROJECT_ROOT)}")
print("  [A] PASS")


# --- [B] create_app ---------------------------------------------------------
banner("[B] create_app() en mode testing (SQLite memory)")

# Configure TESTING env avant import; evite imports Flask session / filesystem.
tmpdir = tempfile.mkdtemp(prefix='g2y_phase2_test_')
os.environ['TESTING'] = 'True'
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-phase2-secret'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['WTF_CSRF_ENABLED'] = 'False'
os.environ['SESSION_FILE_DIR'] = tmpdir
os.environ['UPLOAD_FOLDER'] = tmpdir
os.environ['LOG_DIR'] = tmpdir

from app import create_app, db  # noqa: E402

app = create_app()
assert app is not None, "create_app a retourné None"
print(f"  create_app OK  (TESTING={app.config.get('TESTING')}, config DATABASE_URL={app.config.get('SQLALCHEMY_DATABASE_URI')[:30]}...)")

# Blueprint présent ?
bp_names = {bp.name for bp in app.iter_blueprints()}
assert 'elearning' in bp_names, f"elearning blueprint absent ; blueprints trouvés: {bp_names}"
print(f"  blueprint 'elearning' BIEN REGISTRÉ")
print("  [B] PASS")


# --- [C] Tables el_* + FK konferans ← ElLesson --------------------------------
banner("[C] db.create_all() — existence tables el_* + FK vers konferans_rooms")

with app.app_context():
    db.create_all()

    from sqlalchemy import inspect
    insp = inspect(db.engine)
    table_names = set(insp.get_table_names())
    print("  Tables créées commençant par el_:")
    el_tables = sorted(t for t in table_names if t.startswith('el_'))
    for t in el_tables:
        print(f"    - {t}")

    # 12 au moins (ElClass.. ElWhiteboardEvent)
    assert len(el_tables) >= 12, f"Expected >= 12 tables el_*, trouvé {len(el_tables)}: {el_tables}"
    required = {
        'el_classes', 'el_class_members', 'el_courses', 'el_class_courses',
        'el_lessons', 'el_lesson_attendance', 'el_course_materials',
        'el_assignments', 'el_submissions', 'el_participant_permissions',
        'el_whiteboards', 'el_whiteboard_pages', 'el_whiteboard_events',
    }
    missing = required - set(el_tables)
    assert not missing, f"Tables el_* requises manquantes: {missing}"

    # colonnes konferans_rooms étendues ? (12 cols + index)
    assert 'konferans_rooms' in table_names, "konferans_rooms absent — migration pas crée (problème modèles konferans)"
    kr_cols = {c['name'] for c in insp.get_columns('konferans_rooms')}
    el_kr_expected = {'room_type','class_id','lesson_id','scheduled_at','started_at','ended_at',
                      'max_participants','mic_locked','cam_locked','chat_locked','class_locked','whiteboard_id'}
    missing_col = el_kr_expected - kr_cols
    assert not missing_col, f"colonnes konferans_rooms E-Learning manquantes: {missing_col}"
    print(f"  konferans_rooms bien étendu (+{len(el_kr_expected)} cols E-Learning OK")

    # Vérif FK ElLesson.konferans_room_id vers konferans_rooms.room_id
    fks_insp = insp.get_foreign_keys('el_lessons')
    fk_targets = {
        fk['referred_table'] for fk in fks_insp
        if 'konferans_room_id' in fk.get('constrained_columns', [])
    }
    assert 'konferans_rooms' in fk_targets, f"FK el_lessons.konferans_room_id → konferans_rooms ABSENTE. FKs: {fks_insp}"
    print("  FK el_lessons.konferans_room_id → konferans_rooms.room_id OK")

    # Petit test insertion ElClass / ElLesson / FK valide
    from app.models import ElClass, ElLesson, User, ElClassMember
    # Insert minimal (pas de save → juste objet pour tester qu'on ne plante pas; et qu'on peut flush)
    try:
        from werkzeug.security import generate_password_hash
        u = User(name="Prof Test", email="prof.phase2@test.local",
                 pseudo="prof_phase2", whatsapp="+50900000000",
                 password_hash=generate_password_hash("toto1234"),
                 is_active=True, is_admin=True)
        db.session.add(u)
        db.session.flush()
        assert u.id is not None

        cls = ElClass(name="Klas Tès P2", level="Test", academic_year="2026-2027",
                      teacher_user_id=u.id,
                      invite_code=ElClass.generate_invite_code())
        db.session.add(cls)
        db.session.flush()
        assert cls.id is not None and cls.invite_code and len(cls.invite_code) == 8

        mem = ElClassMember(class_id=cls.id, user_id=u.id, role='teacher')
        db.session.add(mem); db.session.flush()

        lesson = ElLesson(class_id=cls.id, title="Sesyon Tès",
                           teacher_user_id=u.id, status='scheduled')
        db.session.add(lesson); db.session.flush()
        assert lesson.id is not None
        print(f"  INSERT TEST ElClass#{cls.id} invite={cls.invite_code} + ElLesson#{lesson.id} OK")

        # rollback explicite (on touche pas base test qui est :memory: — mais bon)
        db.session.rollback()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Échec insertion test ElClass/ElLesson: {exc!r}")

    print("  [C] PASS")


# --- [D] Régression Konferans ------------------------------------------------
banner("[D] Régression Konferans (fix sécurité create_room + CTA anonyme")

client = app.test_client()

# D1: POST JSON /konferans/create_room ANON -> 401 JSON, login_redirect
payload = {"room_name":"Sal Tès Anon","password":"","creator_name":"HAKER","creator_whatsapp":"+50911111111"}
r = client.post('/konferans/create_room', json=payload, headers={'Accept':'application/json'})
assert r.status_code == 401, f"Anon create_room attendu 401, got {r.status_code}: {r.data[:200]}"
import json
try:
    data = r.get_json() or json.loads(r.data.decode('utf-8'))
except Exception:
    data = None
assert isinstance(data, dict), f"Réponse 401 pas JSON: {r.data[:200]}"
assert data.get('login_redirect'), f"Champ login_redirect manquant dans 401 JSON: {data}"
print(f"  D1 PASS: anon POST create_room → {r.status_code}, login_redirect={data.get('login_redirect')}")

# D2: GET /konferans/ anonyme → contient "Konekte pou Kreye Sal" (CTA visible
r2 = client.get('/konferans/')
assert r2.status_code == 200, f"/konferans/ anon attendu 200, got {r2.status_code}"
html2 = r2.get_data(as_text=True)
assert 'Konekte pou Kreye Sal' in html2, f"CTA login anon absent de /konferans/"
print("  D2 PASS: page anon affiche CTA de connexion OK")

# D3: LOGIN + GET /konferans/ authenticated → input readonly creator
# On réutilise l'app context précédent; là on est hors appcontext, on refait.
with app.app_context():
    from werkzeug.security import generate_password_hash
    from app.models import User as U2
    u2 = U2(name="Elèv Konf Tès", email="konf_phase2@test.local",
            pseudo="konf_p2", whatsapp="+50922222222",
            password_hash=generate_password_hash("toto1234"), is_active=True)
    db.session.add(u2); db.session.commit()
    uid = u2.id
    pseudo = u2.pseudo

    with app.test_client() as cli:
        # /auth/login POST form (cherche champ via inspection :
        rl = cli.post('/auth/login', data={
            'identifier': pseudo,
            'password': 'toto1234',
        }, follow_redirects=False)
        # login retourne parfois autre endpoint, check 302 ou 200
        assert rl.status_code in (200, 302, 401), f"login weird status: {rl.status_code}"
        # Vérifier si loggé via /profile redirige? plus simple: vérifier la session via flask_login
        from flask_login import current_user
        with cli.session_transaction() as sess:
            # essayons de checker manuellement en passant par un endpoint protected
            pass
        r_me = cli.get('/auth/profile', follow_redirects=False)
        logged = (r_me.status_code in (200,)) and 'logout' in (r_me.get_data(as_text=True).lower() or '')
        if not logged:
            # Parfois identifier = email ; on reteste avec email
            rl2 = cli.post('/auth/login', data={'identifier':'konf_phase2@test.local','password':'toto1234'})
            r_me = cli.get('/auth/profile', follow_redirects=False)
            logged = (r_me.status_code == 200)
        assert logged, f"Login TEST a échoué (status profile {r_me.status_code}); route login statuses: {rl.status_code}"
        print("  D3 login OK")

        r3 = cli.get('/konferans/')
        assert r3.status_code == 200
        h3 = r3.get_data(as_text=True)
        # Attend input creator prérempli+readonly
        assert 'readonly' in h3.lower(), "Page /konferans/ connectée n'a pas inputs readonly (creator)"
        # attend nom/pseudo
        assert (u2.name or '')[:6] in h3 or (u2.pseudo or '') in h3, f"Nom/pseudo user pas pré-rempli: name={u2.name!r} pseudo={u2.pseudo!r}"
        print(f"  D3 PASS: /konferans/ logged → readonly + prérempli (pseudo={u2.pseudo})")

# D4: GET /e-learning/ redirect → 302 teacher ou student dashboard
r4 = client.get('/e-learning/', follow_redirects=False)
# Pas loggé → redirigé vers /auth/login (car @login_required sur index /e-learning/)
# Soit 302 vers login, soit 401 JSON. Dans notre cas, login_required redirect 302 car requête browser.
assert r4.status_code in (302, 401), f"/e-learning/ attendu redirect 302/401, got {r4.status_code}"
loc = r4.headers.get('Location','')
assert '/auth/login' in loc or 'login' in loc, f"Redirect pas login: {loc}"
print(f"  D4 PASS: /e-learning/ anon → 302 login (Location: {loc})")

print("\n" + "="*72)
print("PHASE 2f TESTS: 4 sections PASS")
print("="*72)
sys.exit(0)
