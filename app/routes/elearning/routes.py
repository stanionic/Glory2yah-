"""
E-LEARNING (Konferans extension) blueprints.

PHASE 2 provides STUB routes only — structural scaffolding so
- the module boots
- `/e-learning/*` URLs exist (returning friendly "À venir" pages)
- templates can already link to dashboards without 404s.

All actual business logic (class CRUD, lesson launch flow, moderation,
assignment grading etc.) is deferred to PHASES 3/6/7 to keep PHASE 2
as non-breaking as possible.

Files modified by PHASE 2 (this module is ONLY NEW, no edits to others):
  * NEW app/routes/elearning.py
  * NEW templates/elearning/_base.html (extends base.html for consistency)
  * NEW templates/elearning/dashboard_teacher.html
  * NEW templates/elearning/dashboard_student.html
  * NEW templates/elearning/class_detail.html
  * NEW templates/elearning/course_detail.html
  * NEW templates/elearning/lesson_live.html   (empty iframe-placeholder /konferans/room)
  * NEW static/css/elearning.css               (isolated from konferans.css — §21)
"""
from __future__ import annotations

from functools import wraps
from typing import Dict, List

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, url_for, jsonify,
)
from flask_login import current_user, login_required

from app import db
from app.models import (
    ElAssignment, ElClass, ElClassCourse, ElClassMember, ElCourse,
    ElCourseMaterial, ElLesson, ElSubmission, User,
)


elearning_bp = Blueprint(
    'elearning', __name__,
    url_prefix='/e-learning',
    template_folder='templates',
    static_folder='static',
    static_url_path='/static/e-learning',
)


# ---------- tiny helpers ---------------------------------------------------------

def _teaching_classes_for(user_id: int) -> List[ElClass]:
    return (
        ElClass.active()
        .filter_by(teacher_user_id=user_id)
        .order_by(ElClass.created_at.desc())
        .all()
    )


def _student_classes_for(user_id: int) -> List[ElClass]:
    return (
        ElClass.active()
        .join(ElClassMember, ElClassMember.class_id == ElClass.id)
        .filter(
            ElClassMember.user_id == user_id,
            ElClassMember.removed_at.is_(None),
        )
        .order_by(ElClass.created_at.desc())
        .all()
    )


# ---------- entry points ---------------------------------------------------------

@elearning_bp.route('/')
@login_required
def home():
    """Redirect to teacher or student dashboard depending on role heuristic.

    Heuristic (PHASE 3 will add real user profile):
      * users.is_admin  OR  any ElClass.teacher_user_id == me  → TEACHER dashboard
      * else → STUDENT dashboard
    """
    is_teacher = bool(getattr(current_user, 'is_admin', False))
    if not is_teacher:
        is_teacher = ElClass.active().filter_by(teacher_user_id=current_user.id).first() is not None
    if is_teacher:
        return redirect(url_for('elearning.teacher_dashboard'))
    return redirect(url_for('elearning.student_dashboard'))


@elearning_bp.route('/teacher')
@login_required
def teacher_dashboard():
    classes = _teaching_classes_for(current_user.id)
    upcoming = (
        ElLesson.active()
        .filter_by(teacher_user_id=current_user.id)
        .filter(ElLesson.status.in_(['scheduled', 'live']))
        .order_by(ElLesson.scheduled_at.asc().nullslast())
        .limit(10)
        .all()
    )
    return render_template(
        'elearning/dashboard_teacher.html',
        classes=classes,
        upcoming_lessons=upcoming,
        ElLesson=ElLesson,
    )


@elearning_bp.route('/student')
@login_required
def student_dashboard():
    classes = _student_classes_for(current_user.id)
    enrolled_ids = [c.id for c in classes]
    upcoming: List[ElLesson] = []
    if enrolled_ids:
        upcoming = (
            ElLesson.active()
            .filter(ElLesson.class_id.in_(enrolled_ids))
            .filter(ElLesson.status.in_(['scheduled', 'live']))
            .order_by(ElLesson.scheduled_at.asc().nullslast())
            .limit(10)
            .all()
        )
    open_assignments = (
        ElAssignment.active()
        .filter(ElAssignment.class_id.in_(enrolled_ids or [-1]))
        .filter(ElAssignment.published.is_(True))
        .order_by(ElAssignment.due_date.asc().nullslast())
        .limit(10)
        .all()
    )
    return render_template(
        'elearning/dashboard_student.html',
        classes=classes,
        upcoming_lessons=upcoming,
        open_assignments=open_assignments,
        ElLesson=ElLesson,
    )


# ---------- Classes (skeleton) ---------------------------------------------------

@elearning_bp.route('/classes/new', methods=['GET', 'POST'])
@login_required
def class_create():
    """Stub — PHASE 6 will implement form + ElClass creation."""
    if request.method == 'POST':
        flash("Kreyasyon klas la ap vini nan PHASE 6 — mercí pou patjans.", "info")
        return redirect(url_for('elearning.teacher_dashboard'))
    return render_template('elearning/class_create.html')


@elearning_bp.route('/classes/join', methods=['POST'])
@login_required
def class_join_by_invite():
    """Stub — PHASE 6 will implement invite_code lookup + ElClassMember."""
    code = (request.form.get('invite_code') or '').strip().upper()
    if code:
        flash(f"Rejwèn klas pa kòd envitasyon ap vini nan PHASE 6 (kòd: {code}).", "info")
    return redirect(url_for('elearning.student_dashboard'))


@elearning_bp.route('/classes/<int:class_id>')
@login_required
def class_detail(class_id: int):
    klass = ElClass.active().filter_by(id=class_id).first() or abort(404)
    is_teacher = klass.teacher_user_id == current_user.id or bool(getattr(current_user, 'is_admin', False))
    if not is_teacher:
        member = (
            ElClassMember.active()
            .filter_by(class_id=klass.id, user_id=current_user.id)
            .filter(ElClassMember.removed_at.is_(None))
            .first()
        )
        if member is None:
            abort(403)
    lessons = (
        ElLesson.active()
        .filter_by(class_id=klass.id)
        .order_by(ElLesson.scheduled_at.desc().nullslast())
        .limit(50)
        .all()
    )
    materials = (
        ElCourseMaterial.active()
        .filter_by(class_id=klass.id)
        .order_by(ElCourseMaterial.created_at.desc())
        .all()
    )
    assignments = (
        ElAssignment.active()
        .filter_by(class_id=klass.id)
        .order_by(ElAssignment.due_date.asc().nullslast())
        .all()
    )
    return render_template(
        'elearning/class_detail.html',
        klass=klass,
        is_teacher=is_teacher,
        lessons=lessons,
        materials=materials,
        assignments=assignments,
    )


# ---------- Courses (skeleton) ---------------------------------------------------

@elearning_bp.route('/courses/new', methods=['GET', 'POST'])
@login_required
def course_create():
    if request.method == 'POST':
        flash("Kreyon kou (sibjet) ap vini nan PHASE 6.", "info")
        return redirect(url_for('elearning.teacher_dashboard'))
    return render_template('elearning/course_create.html')


@elearning_bp.route('/courses/<int:course_id>')
@login_required
def course_detail(course_id: int):
    course = ElCourse.active().filter_by(id=course_id).first() or abort(404)
    is_teacher = course.teacher_user_id == current_user.id or bool(getattr(current_user, 'is_admin', False))
    materials = (
        ElCourseMaterial.active()
        .filter_by(course_id=course.id)
        .order_by(ElCourseMaterial.created_at.desc())
        .all()
    )
    return render_template(
        'elearning/course_detail.html',
        course=course,
        is_teacher=is_teacher,
        materials=materials,
    )


# ---------- Lessons / Live (skeleton) --------------------------------------------

@elearning_bp.route('/lessons/new', methods=['GET', 'POST'])
@login_required
def lesson_create():
    if request.method == 'POST':
        flash("Pwogramasyon sesyon (lesson) + lyezon ak Konferans room ap vini nan PHASE 6.", "info")
        return redirect(url_for('elearning.teacher_dashboard'))
    classes = _teaching_classes_for(current_user.id)
    return render_template('elearning/lesson_create.html', classes=classes)


@elearning_bp.route('/lessons/<int:lesson_id>')
@login_required
def lesson_live(lesson_id: int):
    """Live lesson view placeholder — PHASE 6 will:
       1. verify user is in the class (or teacher)
       2. ensure the linked KonferansRoom exists + permissions
       3. redirect / embed /konferans/room/<code>
    For PHASE 2 we just render an informative placeholder.
    """
    lesson = ElLesson.active().filter_by(id=lesson_id).first() or abort(404)
    is_teacher = lesson.teacher_user_id == current_user.id or bool(getattr(current_user, 'is_admin', False))
    if not is_teacher:
        member = (
            ElClassMember.active()
            .filter_by(class_id=lesson.class_id, user_id=current_user.id)
            .filter(ElClassMember.removed_at.is_(None))
            .first()
        )
        if member is None:
            abort(403)
    return render_template('elearning/lesson_live.html', lesson=lesson, is_teacher=is_teacher)


# ---------- Assignments (skeleton) ------------------------------------------------

@elearning_bp.route('/assignments/<int:assignment_id>')
@login_required
def assignment_detail(assignment_id: int):
    a = ElAssignment.active().filter_by(id=assignment_id).first() or abort(404)
    is_teacher = (
        a.teacher_user_id == current_user.id or bool(getattr(current_user, 'is_admin', False))
    )
    if not is_teacher:
        member = (
            ElClassMember.active()
            .filter_by(class_id=a.class_id, user_id=current_user.id)
            .filter(ElClassMember.removed_at.is_(None))
            .first()
        )
        if member is None:
            abort(403)
    my_submission = None
    if not is_teacher:
        my_submission = (
            ElSubmission.active()
            .filter_by(assignment_id=a.id, student_user_id=current_user.id)
            .first()
        )
    return render_template(
        'elearning/assignment_detail.html',
        assignment=a,
        is_teacher=is_teacher,
        my_submission=my_submission,
    )


# ---------- API stubs (return JSON for future SPA / JS integration) --------------

@elearning_bp.route('/api/me/classes', methods=['GET'])
@login_required
def api_my_classes():
    teacher = _teaching_classes_for(current_user.id)
    student = _student_classes_for(current_user.id)
    return jsonify({
        'ok': True,
        'teacher': [c.to_public_dict() for c in teacher],
        'student': [c.to_public_dict() for c in student],
    })
