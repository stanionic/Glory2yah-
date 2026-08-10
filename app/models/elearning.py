"""
E-LEARNING (Konferans extension) data models.

Prefix rule: ALL new tables introduced by the E-Learning sub-platform use
the `el_*` name prefix so they are easily distinguishable from core app
tables and from the independent `ecole_*` tables of the Bible School module.

Soft delete + created_at / updated_at inherited from BaseModel.

This module is intentionally backwards compatible:
  * it does NOT modify KonferansRoom / KonferansRecording (those are
    extended at bootstrap time via idempotent ALTER TABLE in __init__.py)
  * it only adds NEW tables with ForeignKeys pointing at existing
    users.id / konferans_rooms.room_id / konferans_recordings.id.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app import db
from app.models.base import BaseModel


# ---------- Classes & membership -----------------------------------------------------

class ElClass(BaseModel):
    """A 'Classe' — group of students following a set of courses with one
    designated teacher-owner.  Archive linkable.
    """
    __tablename__ = 'el_classes'

    name = db.Column(db.String(180), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(64), nullable=True, index=True)
    level = db.Column(db.String(64), nullable=True, index=True)
    academic_year = db.Column(db.String(32), nullable=True, index=True)

    banner_image = db.Column(db.String(255), nullable=True)
    invite_code = db.Column(db.String(12), nullable=False, unique=True, index=True)

    teacher_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # ---- helpers ----------------------------------------------------------
    @classmethod
    def generate_invite_code(cls) -> str:
        while True:
            c = uuid.uuid4().hex[:8].upper()
            if not cls.active().filter_by(invite_code=c).first():
                return c

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'level': self.level,
            'academic_year': self.academic_year,
            'banner_image': self.banner_image,
            'invite_code': self.invite_code,
            'teacher_user_id': self.teacher_user_id,
            'is_archived': self.is_archived,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ElClassMember(BaseModel):
    """Membership of a single user inside a class.  Soft remove pattern:
    unique on (class_id, user_id) when removed_at IS NULL.
    """
    __tablename__ = 'el_class_members'

    class_id = db.Column(
        db.Integer, db.ForeignKey('el_classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    role = db.Column(
        db.Enum('teacher', 'assistant', 'student', name='el_member_role'),
        nullable=False, default='student', index=True,
    )
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    removed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        # ensure soft-deleted rows don't block re-enrolment uniqueness
        db.UniqueConstraint(
            'class_id', 'user_id', 'removed_at',
            name='uq_el_class_membership_active',
            sqlite_on_conflict='IGNORE',
        ),
        db.Index('ix_el_class_members_class_role', 'class_id', 'role'),
    )


# ---------- Courses (matières / programmes) ----------------------------------------

class ElCourse(BaseModel):
    """A 'Cours' — teachable subject / syllabus.  Can be assigned to many
    classes (many-to-many).  Owned by one teacher.
    """
    __tablename__ = 'el_courses'

    title = db.Column(db.String(220), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    subject = db.Column(db.String(80), nullable=True, index=True)
    category = db.Column(db.String(64), nullable=True, index=True)
    level = db.Column(db.String(64), nullable=True, index=True)

    teacher_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )
    default_duration_minutes = db.Column(db.Integer, nullable=True)
    syllabus = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True)


class ElClassCourse(BaseModel):
    """M2M table: a class follows several courses (subjects)."""
    __tablename__ = 'el_class_courses'

    class_id = db.Column(
        db.Integer, db.ForeignKey('el_classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey('el_courses.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    position = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint('class_id', 'course_id', name='uq_el_class_course_pair'),
    )


# ---------- Lessons (scheduled teaching sessions) -----------------------------------

class ElLesson(BaseModel):
    """One scheduled / live / ended teaching session.

    When the teacher clicks "Démarrer le cours en direct" we create a
    KonferansRoom of room_type='live_course' and link it back via
    konferans_room_id.  This lets us reuse ALL existing conferencing
    infrastructure (WebRTC, whiteboard sockets, recording upload, etc.)
    without rewriting it.
    """
    __tablename__ = 'el_lessons'

    class_id = db.Column(
        db.Integer, db.ForeignKey('el_classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey('el_courses.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    teacher_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )

    title = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True, index=True)
    duration_minutes = db.Column(db.Integer, nullable=True)

    status = db.Column(
        db.Enum('scheduled', 'live', 'ended', 'cancelled', name='el_lesson_status'),
        nullable=False, default='scheduled', index=True,
    )

    # nullable FK to konferans module (strings so the table can be created
    # before konferans_rooms on fresh SQLite dev boots without order issues)
    konferans_room_id = db.Column(
        db.String(128),
        db.ForeignKey('konferans_rooms.room_id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    recording_id = db.Column(
        db.Integer,
        db.ForeignKey('konferans_recordings.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )

    materials_count = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)


class ElLessonAttendance(BaseModel):
    __tablename__ = 'el_lesson_attendance'

    lesson_id = db.Column(
        db.Integer, db.ForeignKey('el_lessons.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    is_present = db.Column(db.Boolean, nullable=False, default=False, index=True)
    joined_at = db.Column(db.DateTime, nullable=True)
    left_at = db.Column(db.DateTime, nullable=True)

    connection_quality_avg = db.Column(
        db.Enum('low', 'medium', 'good', name='el_conn_quality'),
        nullable=True,
    )
    hand_raised_count = db.Column(db.Integer, nullable=False, default=0)
    spoke_duration_sec = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint('lesson_id', 'user_id', name='uq_el_attendance_lesson_user'),
    )


# ---------- Course materials (documents / PDFs / images) ----------------------------

class ElCourseMaterial(BaseModel):
    """Pedagogy resources: PDF, image, presentation, exercise sheets.

    Files are physically stored in the Render persistent disk under
    UPLOAD_FOLDER (or a dedicated SUBMISSION_DIR) — only metadata lives
    in Postgres.
    """
    __tablename__ = 'el_course_materials'

    owner_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )

    lesson_id = db.Column(
        db.Integer, db.ForeignKey('el_lessons.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    class_id = db.Column(
        db.Integer, db.ForeignKey('el_classes.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey('el_courses.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )

    title = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=True)
    mime_type = db.Column(db.String(128), nullable=True, index=True)
    pages_count = db.Column(db.Integer, nullable=True)

    is_public = db.Column(db.Boolean, nullable=False, default=False, index=True)
    allow_download = db.Column(db.Boolean, nullable=False, default=True)


# ---------- Assignments / student submissions ---------------------------------------

class ElAssignment(BaseModel):
    """Devoir / exercice to hand back."""
    __tablename__ = 'el_assignments'

    class_id = db.Column(
        db.Integer, db.ForeignKey('el_classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    lesson_id = db.Column(
        db.Integer, db.ForeignKey('el_lessons.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    teacher_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )

    title = db.Column(db.String(220), nullable=False)
    instructions = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True, index=True)
    max_score = db.Column(db.Integer, nullable=True)
    attachments_json = db.Column(db.Text, nullable=True)  # JSON-encoded list
    published = db.Column(db.Boolean, nullable=False, default=True, index=True)

    @property
    def attachments(self) -> List[Any]:
        if not self.attachments_json:
            return []
        try:
            return json.loads(self.attachments_json)
        except Exception:
            return []

    @attachments.setter
    def attachments(self, value: Any) -> None:
        self.attachments_json = json.dumps(value or [])


class ElSubmission(BaseModel):
    __tablename__ = 'el_submissions'

    assignment_id = db.Column(
        db.Integer, db.ForeignKey('el_assignments.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    student_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(512), nullable=True)

    score = db.Column(db.Integer, nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)
    feedback = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            'assignment_id', 'student_user_id',
            name='uq_el_submission_assignment_student',
        ),
    )


# ---------- Participant permission states (per live room) ---------------------------

class ElParticipantPermission(BaseModel):
    """Runtime permissions / moderation state for a participant in a
    live-course room.  Mirrors socket-side RAM state durably.
    """
    __tablename__ = 'el_participant_permissions'

    lesson_id = db.Column(
        db.Integer, db.ForeignKey('el_lessons.id', ondelete='CASCADE'),
        nullable=True, index=True,
    )
    konferans_room_id = db.Column(
        db.String(128),
        db.ForeignKey('konferans_rooms.room_id', ondelete='CASCADE'),
        nullable=True, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    guest_display_name = db.Column(db.String(120), nullable=True)

    can_speak = db.Column(db.Boolean, nullable=False, default=True)
    can_video = db.Column(db.Boolean, nullable=False, default=True)
    can_share_screen = db.Column(db.Boolean, nullable=False, default=False)
    can_draw = db.Column(db.Boolean, nullable=False, default=False)
    can_chat = db.Column(db.Boolean, nullable=False, default=True)

    muted = db.Column(db.Boolean, nullable=False, default=False)
    hand_raised = db.Column(db.Boolean, nullable=False, default=False)
    has_floor = db.Column(db.Boolean, nullable=False, default=False)

    role_label = db.Column(
        db.Enum('host', 'cohost', 'student', 'guest', name='el_role_label'),
        nullable=False, default='student', index=True,
    )


# ---------- Whiteboard persistent storage -------------------------------------------

class ElWhiteboard(BaseModel):
    """Meta-record for a persisted whiteboard attached to a lesson or a
    classic Konferans room."""
    __tablename__ = 'el_whiteboards'

    room_id = db.Column(
        db.String(128),
        db.ForeignKey('konferans_rooms.room_id', ondelete='CASCADE'),
        nullable=True, index=True,
    )
    lesson_id = db.Column(
        db.Integer, db.ForeignKey('el_lessons.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    title = db.Column(db.String(220), nullable=True)
    current_page = db.Column(db.Integer, nullable=False, default=1)

    # Periodic full snapshot for late-joiner re-sync (§6 sync complet)
    snapshot_json = db.Column(db.Text, nullable=True)


class ElWhiteboardPage(BaseModel):
    __tablename__ = 'el_whiteboard_pages'

    whiteboard_id = db.Column(
        db.Integer, db.ForeignKey('el_whiteboards.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    page_number = db.Column(db.Integer, nullable=False, index=True)
    background_image = db.Column(db.String(512), nullable=True)
    page_width = db.Column(db.Integer, nullable=False, default=1280)
    page_height = db.Column(db.Integer, nullable=False, default=720)

    __table_args__ = (
        db.UniqueConstraint(
            'whiteboard_id', 'page_number',
            name='uq_el_wb_page_wb_pagenum',
        ),
    )


class ElWhiteboardEvent(BaseModel):
    """Vector event log: strokes, shapes, text, annotations.

    Lightweight payloads (JSON) + timestamp allow us to rebuild any page
    deterministically for a late-joiner, and keep bandwidth usage very
    low on weak connections (§2 / §6).
    """
    __tablename__ = 'el_whiteboard_events'

    whiteboard_id = db.Column(
        db.Integer, db.ForeignKey('el_whiteboards.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    page_id = db.Column(
        db.Integer, db.ForeignKey('el_whiteboard_pages.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    session_uuid = db.Column(db.String(36), nullable=True)

    event_type = db.Column(db.String(32), nullable=False, index=True)
    # stroke_start / stroke_move / stroke_end / erase_region / text_add /
    # shape_add / image_add / pdf_annotate / clear / undo / redo / page_change
    payload_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, index=True,
    )

    __table_args__ = (
        db.Index(
            'ix_el_wb_events_resync',
            'whiteboard_id', 'page_id', 'created_at',
        ),
    )

    @property
    def payload(self) -> Dict[str, Any]:
        if not self.payload_json:
            return {}
        try:
            return json.loads(self.payload_json)
        except Exception:
            return {}

    @payload.setter
    def payload(self, value: Any) -> None:
        self.payload_json = json.dumps(value or {}, ensure_ascii=False, separators=(',', ':'))


# ---------- Convenience exports (alphabetical) --------------------------------------

__all__ = [
    'ElAssignment',
    'ElClass',
    'ElClassCourse',
    'ElClassMember',
    'ElCourse',
    'ElCourseMaterial',
    'ElLesson',
    'ElLessonAttendance',
    'ElParticipantPermission',
    'ElSubmission',
    'ElWhiteboard',
    'ElWhiteboardEvent',
    'ElWhiteboardPage',
]
