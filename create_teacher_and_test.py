"""
Create teacher account "StanD" with password "081986" for Ecole Biblique
and ensure test student exists in EcoleUser
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.user import User
from app.models.user_gkach import UserGkach
from ecole_biblique.models import EcoleUser, Course

app = create_app()

with app.app_context():
    print("=" * 60)
    print("CREATING ACCOUNTS")
    print("=" * 60)

    # === 1. CREATE TEACHER StanD ===
    # Main app User
    teacher = User.query.filter_by(whatsapp='+509STAN').first()
    if not teacher:
        teacher = User(
            whatsapp='+509STAN',
            pseudo='StanD',
            name='StanD Teacher',
            auth_provider='whatsapp',
            is_active=True
        )
        db.session.add(teacher)
        print("[OK] Created main User: StanD")

    teacher.set_password('081986')
    teacher.is_active = True
    db.session.flush()
    print("[OK] Set password for StanD")

    # Gkach account
    gk = UserGkach.query.filter_by(user_whatsapp='+509STAN').first()
    if not gk:
        gk = UserGkach(user_id=teacher.id, user_whatsapp='+509STAN', gkach_balance=5000)
        db.session.add(gk)
        print("[OK] Created Gkach account for StanD")

    # EcoleUser as teacher
    ecole_teacher = EcoleUser.query.filter_by(whatsapp='+509STAN').first()
    if not ecole_teacher:
        ecole_teacher = EcoleUser(
            full_name='StanD Teacher',
            whatsapp='+509STAN',
            role='teacher'
        )
        ecole_teacher.set_password('081986')
        db.session.add(ecole_teacher)
        print("[OK] Created EcoleUser teacher: StanD Teacher")
    else:
        print("[INFO] EcoleUser teacher already exists")

    # Create a course
    courses = Course.query.filter_by(teacher_id=ecole_teacher.id).all()
    if not courses:
        course = Course(name='Theologie et Bible', teacher_id=ecole_teacher.id)
        db.session.add(course)
        print("[OK] Created course for teacher")
    else:
        print(f"[INFO] Teacher already has {len(courses)} course(s)")

    db.session.commit()

    # === 2. ENSURE TEST STUDENT EXISTS ===
    test_student = EcoleUser.query.filter_by(whatsapp='+50912345678').first()
    if not test_student:
        test_student = EcoleUser(
            full_name='Test User Student',
            whatsapp='+50912345678',
            role='student'
        )
        test_student.set_password('123456')
        db.session.add(test_student)
        db.session.commit()
        print("[OK] Created EcoleUser student: Test User Student")
    else:
        print(f"[INFO] Student exists: {test_student.full_name} role={test_student.role}")

    # === 3. VERIFICATION ===
    print()
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    print()
    print("--- Main App Users ---")
    for u in User.query.all():
        pw_test = '123456' if u.whatsapp == '+50912345678' else '081986'
        pw_ok = u.check_password(pw_test) if u.password_hash else False
        print(f"  {u.pseudo:15s} | {u.whatsapp:20s} | pw_ok={pw_ok} | admin={u.is_admin}")

    print()
    print("--- Ecole Biblique Users ---")
    for u in EcoleUser.query.all():
        print(f"  {u.full_name:25s} | {u.whatsapp:20s} | role={u.role}")
        if u.role == 'teacher':
            print(f"    Courses: {[c.name for c in u.courses]}")

    print()
    print("--- Login Credentials ---")
    print("  Teacher: pseudo='StanD' or whatsapp='+509STAN' password='081986'")
    print("  Student: pseudo='testuser' or whatsapp='+50912345678' password='123456'")
    print()
    print("DONE")