"""
EVENTS module — SQLAlchemy models for the Glory2YahPub (SEVIS) app.

This is the Flask/SQLAlchemy port of the framework-agnostic events module
shipped in `events/backend/migrations/001_create_events_schema.sql`
(module ÉVÉNEMENTS / SOS ALO LEGLIZ).

Design notes
------------
* Portable across SQLite (dev/test) and PostgreSQL (prod): primary keys and
  foreign keys use ``String(36)`` UUIDs (same pattern as ``app.models.party``)
  instead of Postgres ``gen_random_uuid()`` / ``UUID`` columns.
* Each event is an independent entity identified by a unique ``slug``; adding a
  new event requires no code changes (insert one ``Event`` row + related rows).
* ``seed_events()`` is idempotent and is called at application bootstrap after
  ``db.create_all()`` so the SOS ALO LEGLIZ event exists out of the box.
"""
import uuid
from datetime import datetime

from app import db


def _uuid():
    """Portable UUID string primary key default."""
    return str(uuid.uuid4())


class Event(db.Model):
    """An event. `status`: draft | published | archived."""

    __tablename__ = 'events'
    __table_args__ = (
        db.CheckConstraint("status IN ('draft','published','archived')", name='ck_events_status'),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    subtitle = db.Column(db.String(255), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    hero_image_url = db.Column(db.Text, nullable=True)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    timezone = db.Column(db.String(64), nullable=False, default='America/Port-au-Prince')
    location_label = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='draft')
    registration_enabled = db.Column(db.Boolean, nullable=False, default=True)
    livestream_enabled = db.Column(db.Boolean, nullable=False, default=False)
    livestream_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    leaders = db.relationship(
        'EventLeader', backref='event', lazy='select',
        cascade='all, delete-orphan', order_by='EventLeader.display_order')
    program = db.relationship(
        'EventProgramItem', backref='event', lazy='select',
        cascade='all, delete-orphan', order_by='EventProgramItem.display_order')
    faq = db.relationship(
        'EventFaq', backref='event', lazy='select',
        cascade='all, delete-orphan', order_by='EventFaq.display_order')
    media = db.relationship(
        'EventMedia', backref='event', lazy='select',
        cascade='all, delete-orphan', order_by='EventMedia.display_order')
    news = db.relationship(
        'EventNews', backref='event', lazy='select',
        cascade='all, delete-orphan', order_by='desc(EventNews.published_at)')
    regions = db.relationship(
        'EventRegion', backref='event', lazy='select',
        cascade='all, delete-orphan')
    coordinators = db.relationship(
        'EventCoordinator', backref='event', lazy='select',
        cascade='all, delete-orphan')
    participants = db.relationship(
        'EventParticipant', backref='event', lazy='dynamic',
        cascade='all, delete-orphan')
    organizations = db.relationship(
        'EventOrganization', backref='event', lazy='dynamic',
        cascade='all, delete-orphan')

    # ---- Serialization helpers (API contract) ----
    def to_dict(self, include_children=True):
        data = {
            'id': self.id,
            'slug': self.slug,
            'title': self.title,
            'subtitle': self.subtitle,
            'summary': self.summary,
            'hero_image_url': self.hero_image_url,
            'start_at': self.start_at.isoformat() if self.start_at else None,
            'end_at': self.end_at.isoformat() if self.end_at else None,
            'timezone': self.timezone,
            'location_label': self.location_label,
            'status': self.status,
            'registration_enabled': self.registration_enabled,
            'livestream_enabled': self.livestream_enabled,
            'livestream_url': self.livestream_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_children:
            data.update({
                'leaders': [l.to_dict() for l in self.leaders],
                'program': [p.to_dict() for p in self.program],
                'faq': [f.to_dict() for f in self.faq],
                'media': [m.to_dict() for m in self.media],
                'news': [n.to_dict() for n in self.news],
            })
        return data

    def __repr__(self):
        return f'<Event {self.slug}>'

class EventLeader(db.Model):
    """Initiator / leader of an event."""

    __tablename__ = 'event_leaders'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role_label = db.Column(db.String(120), nullable=False)
    photo_url = db.Column(db.Text, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'role_label': self.role_label,
            'photo_url': self.photo_url,
            'bio': self.bio,
        }


class EventProgramItem(db.Model):
    """One timeline entry of the event programme."""

    __tablename__ = 'event_program_items'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    time_label = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {'id': self.id, 'time_label': self.time_label, 'title': self.title}


class EventFaq(db.Model):
    """FAQ entry of an event."""

    __tablename__ = 'event_faq'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {'id': self.id, 'question': self.question, 'answer': self.answer}


class EventNews(db.Model):
    """News / actuality published for an event."""

    __tablename__ = 'event_news'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    published_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.String(36), nullable=True)  # optional FK to users/admins table

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'body': self.body,
            'published_at': self.published_at.isoformat() if self.published_at else None,
        }


class EventMedia(db.Model):
    """Photo / video / poster / testimony attached to an event."""

    __tablename__ = 'event_media'
    __table_args__ = (
        db.CheckConstraint("media_type IN ('photo','video','poster','testimony')", name='ck_event_media_type'),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    media_type = db.Column(db.String(20), nullable=False)
    url = db.Column(db.Text, nullable=False)
    caption = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'media_type': self.media_type, 'url': self.url, 'caption': self.caption}



class EventRegion(db.Model):
    """Department / region (e.g. Ouest, Artibonite, Diaspora) for an event."""

    __tablename__ = 'event_regions'
    __table_args__ = (
        db.UniqueConstraint('event_id', 'name', name='uq_event_regions_event_name'),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(120), nullable=False)

    def to_dict(self):
        return {'id': self.id, 'name': self.name}


class EventCoordinator(db.Model):
    """Departmental coordinator. Contact fields are NOT public by default
    (is_public_contact controls their visibility)."""

    __tablename__ = 'event_coordinators'
    __table_args__ = (
        db.CheckConstraint("status IN ('active','pending','inactive')", name='ck_event_coordinators_status'),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    region_id = db.Column(db.String(36), db.ForeignKey('event_regions.id', ondelete='SET NULL'), nullable=True)
    full_name = db.Column(db.String(255), nullable=False)
    org_name = db.Column(db.String(255), nullable=True)
    org_type = db.Column(db.String(30), nullable=True)
    photo_url = db.Column(db.Text, nullable=True)
    phone_professional = db.Column(db.String(40), nullable=True)
    whatsapp = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    approx_participants = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='active')
    is_public_contact = db.Column(db.Boolean, nullable=False, default=False)

    region = db.relationship('EventRegion', lazy='joined')

    def to_dict(self, public_only=True):
        data = {
            'id': self.id,
            'full_name': self.full_name,
            'org_name': self.org_name,
            'org_type': self.org_type,
            'photo_url': self.photo_url,
            'region': self.region.name if self.region else None,
            'city': self.city,
            'address': self.address,
            'approx_participants': self.approx_participants,
            'status': self.status,
            'is_public_contact': self.is_public_contact,
        }
        if not public_only or self.is_public_contact:
            data.update({
                'phone_professional': self.phone_professional,
                'whatsapp': self.whatsapp,
                'email': self.email,
            })
        return data


class EventParticipant(db.Model):
    """Individual registration. IP is stored hashed (never in clear)."""

    __tablename__ = 'event_participants'
    __table_args__ = (
        db.CheckConstraint(
            "role_label IN ('pasteur','responsable','membre','jeune','groupe_de_priere','organisation','autre')",
            name='ck_event_participants_role'),
        db.CheckConstraint(
            "participation_type IN ('individuelle','eglise','mission','organisation','ligue_de_pasteurs','groupe_de_priere')",
            name='ck_event_participants_participation_type'),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    region_id = db.Column(db.String(36), db.ForeignKey('event_regions.id', ondelete='SET NULL'), nullable=True)
    organization_name = db.Column(db.String(255), nullable=True)
    role_label = db.Column(db.String(30), nullable=False, default='membre')
    participation_type = db.Column(db.String(30), nullable=False, default='individuelle')
    consent_public_stats = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_hash = db.Column(db.String(64), nullable=True)

    region = db.relationship('EventRegion', lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'phone': self.phone,
            'email': self.email,
            'city': self.city,
            'region': self.region.name if self.region else None,
            'organization_name': self.organization_name,
            'role_label': self.role_label,
            'participation_type': self.participation_type,
            'consent_public_stats': self.consent_public_stats,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
class EventOrganization(db.Model):
    """Church/organization registration. Status: pending | confirmed | rejected."""

    __tablename__ = 'event_organizations'
    __table_args__ = (
        db.CheckConstraint(
            "org_type IN ('eglise','mission','organisation','ligue_de_pasteurs','groupe_de_priere')",
            name='ck_event_organizations_type',
        ),
        db.CheckConstraint(
            "status IN ('pending','confirmed','rejected')",
            name='ck_event_organizations_status',
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    region_id = db.Column(db.String(36), db.ForeignKey('event_regions.id', ondelete='SET NULL'), nullable=True)
    org_name = db.Column(db.String(255), nullable=False)
    org_type = db.Column(db.String(30), nullable=False, default='eglise')
    contact_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    whatsapp = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    approx_participants = db.Column(db.Integer, nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    consent_public_stats = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_hash = db.Column(db.String(64), nullable=True)

    region = db.relationship('EventRegion', lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'org_name': self.org_name,
            'org_type': self.org_type,
            'contact_name': self.contact_name,
            'phone': self.phone,
            'whatsapp': self.whatsapp,
            'email': self.email,
            'city': self.city,
            'address': self.address,
            'region': self.region.name if self.region else None,
            'approx_participants': self.approx_participants,
            'message': self.message,
            'status': self.status,
            'consent_public_stats': self.consent_public_stats,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EventShare(db.Model):
    """Share-counter row (pure analytics; no personal data)."""

    __tablename__ = 'event_shares'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    event_id = db.Column(db.String(36), db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<EventShare {self.channel}>'


def seed_events():
    """Idempotent bootstrap seed for the SOS ALO LEGLIZ event (published).

    Called from ``create_app()`` after ``db.create_all()``. Safe to re-run.
    """
    from app import db

    event = Event.query.filter_by(slug='sos-alo-legliz').first()
    if event is not None:
        return  # already seeded

    event = Event(
        slug='sos-alo-legliz',
        title='SOS ALO LEGLIZ',
        subtitle='Demi Jounen Jèn Pou Peyi a',
        summary=('SOS ALO LEGLIZ \u2014 Demi Jounen Jèn Pou Peyi a est une mobilisation '
                 'chrétienne consacrée au jeûne, à la prière et à l\u2019intercession en '
                 'faveur d\u2019Haïti. Lancée par l\u2019Apôtre Stanley Désinat et le '
                 'Pasteur Nixon Dieudonnée, l\u2019initiative est coordonnée par ALO '
                 'LEGLIZ, "Yon Mouvman Inite & Sali pou Ayiti".'),
        start_at=datetime(2026, 8, 30, 6, 0),
        end_at=datetime(2026, 8, 30, 12, 0),
        timezone='America/Port-au-Prince',
        location_label='Haïti + Diaspora (en ligne et en Église)',
        status='published',
    )
    db.session.add(event)
    db.session.flush()

    # Leaders
    db.session.add_all([
        EventLeader(event_id=event.id, full_name='Apôtre Stanley Désinat',
                    role_label='Initiateur', display_order=1),
        EventLeader(event_id=event.id, full_name='Pasteur Nixon Dieudonnée',
                    role_label='Initiateur', display_order=2),
        EventLeader(event_id=event.id, full_name='ALO LEGLIZ',
                    role_label='Coordination générale', display_order=3),
    ])

    # Programme
    _program = [
        ('06:00', 'Ouverture', 1), ('06:15', 'Louange / Adoration', 2),
        ('06:45', 'Priere de consecration personnelle', 3), ('07:30', 'Temps de jeûne et méditation', 4),
        ('08:30', 'Prière pour les familles', 5), ('09:30', "Prière pour l'Église", 6),
        ('10:30', 'Intercession nationale', 7), ('11:30', 'Action de grâce', 8),
        ('12:00', 'Clôture', 9),
    ]
    for time_label, title, order in _program:
        db.session.add(EventProgramItem(event_id=event.id, time_label=time_label,
                                        title=title, display_order=order))

    # Régions / départements d'Haïti + Diaspora
    for name in ['Ouest', 'Artibonite', 'Nord', 'Nord-Est', 'Nord-Ouest', 'Centre',
                 'Sud', 'Sud-Est', "Grand'Anse", 'Nippes', 'Diaspora']:
        db.session.add(EventRegion(event_id=event.id, name=name))

    db.session.commit()
