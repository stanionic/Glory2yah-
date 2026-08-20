"""EVENTS (SOS ALO LEGLIZ) blueprint — Flask/SQLAlchemy port of the
framework-agnostic module in ``events/backend`` (see API-REFERENCE.md).

Public blueprint ``events_bp`` built around ``/events``:
    GET  /events                     -> list of published events
    GET  /events/<slug>              -> landing page (hero, leaders, programme,
                                        FAQ, regions, registration forms)
    POST /events/<slug>              -> form_type=participant|organization
    POST /events/<slug>/shares       -> share counter (JSON)

Admin blueprint ``admin_events_bp`` (login_required + admin_required):
    GET  /admin/events                        -> events + status + counts
    GET  /admin/events/<slug>/participants    -> paginated participant list
    GET  /admin/events/<slug>/organizations   -> org list w/ status
    POST /admin/events/<slug>/organizations/<oid>/status -> set status
"""
import hashlib
import re

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   jsonify, request, abort)
from flask_login import login_required

from app import db
from app.models.events import (Event, EventLeader, EventProgramItem, EventFaq,
                               EventRegion, EventParticipant, EventOrganization,
                               EventShare)
from app.utils.security import admin_required

events_bp = Blueprint('events', __name__)
admin_events_bp = Blueprint('admin_events', __name__)

ROLE_LABELS = {'pasteur', 'responsable', 'membre', 'jeune',
               'groupe_de_priere', 'organisation', 'autre'}
PARTICIPATION_TYPES = {'individuelle', 'eglise', 'mission', 'organisation',
                       'ligue_de_pasteurs', 'groupe_de_priere'}
ORG_TYPES = {'eglise', 'mission', 'organisation', 'ligue_de_pasteurs',
             'groupe_de_priere'}
SHARE_CHANNELS = {'whatsapp', 'facebook', 'messenger', 'x', 'telegram', 'link'}


def _hash_ip(ip):
    return hashlib.sha256(str(ip).encode('utf-8')).hexdigest()


def _clean(value, limit=2000):
    if not isinstance(value, str):
        return None
    return re.sub(r'<[^>]*>', '', value).strip()[:limit]


def _is_valid_phone(v):
    return isinstance(v, str) and bool(re.match(r'^[+0-9()\-.\s]{7,20}$', v.strip()))


# ---------------------------------------------------------------------------
# Public: list + landing
# ---------------------------------------------------------------------------
@events_bp.route('/events')
def index():
    evts = (Event.query
            .filter_by(status='published')
            .order_by(Event.start_at.desc())
            .all())
    return render_template('events/index.html', events=evts)


@events_bp.route('/events/<slug>', methods=['GET', 'POST'])
def landing(slug):
    event = Event.query.filter_by(slug=slug, status='published').first_or_404()

    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'participant':
            _register_participant(event)
        elif form_type == 'organization':
            _register_organization(event)
        else:
            abort(400)
        return redirect(url_for('events.landing', slug=slug))

    leaders = EventLeader.query.filter_by(event_id=event.id).all()
    program = EventProgramItem.query.filter_by(event_id=event.id).all()
    faq = EventFaq.query.filter_by(event_id=event.id).all()
    regions = EventRegion.query.filter_by(event_id=event.id).all()
    participants_count = event.participants.count()
    orgs_count = event.organizations.count()

    return render_template(
        'events/landing.html',
        event=event, leaders=leaders, program=program, faq=faq,
        regions=regions, participants_count=participants_count,
        orgs_count=orgs_count,
        ROLE_LABELS=sorted(ROLE_LABELS),
        PARTICIPATION_TYPES=sorted(PARTICIPATION_TYPES),
        ORG_TYPES=sorted(ORG_TYPES),
    )


def _register_participant(event):
    body = request.form
    errors = []
    if not body.get('full_name'):
        errors.append('full_name invalide')
    if not _is_valid_phone(body.get('phone')):
        errors.append('phone invalide')
    role = body.get('role_label') or 'membre'
    ptype = body.get('participation_type') or 'individuelle'
    if role not in ROLE_LABELS:
        errors.append('role_label invalide')
    if ptype not in PARTICIPATION_TYPES:
        errors.append('participation_type invalide')
    if body.get('website'):  # honeypot
        errors.append('spam détecté')
    if errors:
        flash('Verifye enfòmasyon yo: ' + ', '.join(errors), 'error')
        return

    region = None
    if body.get('region'):
        region = EventRegion.query.filter_by(event_id=event.id,
                                             name=body.get('region')).first()
    db.session.add(EventParticipant(
        event_id=event.id,
        full_name=_clean(body.get('full_name'), 255),
        phone=_clean(body.get('phone'), 40),
        email=_clean(body.get('email'), 255),
        city=_clean(body.get('city'), 120),
        region_id=region.id if region else None,
        organization_name=_clean(body.get('organization_name'), 255),
        role_label=role,
        participation_type=ptype,
        consent_public_stats=bool(body.get('consent_public_stats')),
        ip_hash=_hash_ip(request.remote_addr),
    ))
    db.session.commit()


def _register_organization(event):
    body = request.form
    otype = body.get('org_type') or 'eglise'
    if not body.get('org_name') or otype not in ORG_TYPES:
        flash('Verifye enfòmasyon òganizasyon an.', 'error')
        return
    if not _is_valid_phone(body.get('phone')):
        flash('Telefòn envalid.', 'error')
        return
    if body.get('website'):
        flash('Spam détecté.', 'error')
        return
    region = None
    if body.get('region'):
        region = EventRegion.query.filter_by(event_id=event.id,
                                             name=body.get('region')).first()
    approx = body.get('approx_participants')
    try:
        approx = int(approx) if approx else None
    except (TypeError, ValueError):
        approx = None
    db.session.add(EventOrganization(
        event_id=event.id,
        region_id=region.id if region else None,
        org_name=_clean(body.get('org_name'), 255),
        org_type=otype,
        contact_name=_clean(body.get('contact_name') or body.get('org_name'), 255),
        phone=_clean(body.get('phone'), 40),
        whatsapp=_clean(body.get('whatsapp'), 40),
        email=_clean(body.get('email'), 255),
        city=_clean(body.get('city'), 120),
        address=_clean(body.get('address'), 255),
        approx_participants=approx,
        message=_clean(body.get('message'), 2000),
        consent_public_stats=bool(body.get('consent_public_stats')),
        ip_hash=_hash_ip(request.remote_addr),
    ))
    db.session.commit()


@events_bp.route('/events/<slug>/nearby-locations')
def nearby_locations(slug):
    """Return confirmed enrolled churches and organizations by city."""
    event = Event.query.filter_by(slug=slug, status='published').first_or_404()
    city = _clean(request.args.get('city'), 120)
    region = _clean(request.args.get('region'), 120)

    city_key = city.casefold() if city else ''
    region_key = region.casefold() if region else ''
    locations = []
    for organization in (EventOrganization.query
                          .filter_by(event_id=event.id, status='confirmed')
                          .all()):
        organization_city = (organization.city or '').casefold()
        organization_region = (organization.region.name if organization.region else '').casefold()
        city_match = bool(city_key and organization_city == city_key)
        region_match = bool(region_key and organization_region == region_key)
        if (city_key or region_key) and not city_match and not region_match:
            continue
        locations.append(organization)

    locations.sort(key=lambda organization: (
        not bool((organization.city or '').strip()),
        (organization.city or '').casefold(),
        (organization.org_name or '').casefold(),
    ))
    return jsonify({
        'locations': [{
            'name': organization.org_name,
            'city': organization.city,
            'region': organization.region.name if organization.region else None,
            'address': organization.address,
            'phone': organization.phone,
            'whatsapp': organization.whatsapp,
        } for organization in locations],
        'message': None if locations else 'Pa gen lokal konfime pou zòn sa a ankò.',
    })


# ---------------------------------------------------------------------------
# Share counter (analytics)
# ---------------------------------------------------------------------------
@events_bp.route('/events/<slug>/shares', methods=['POST'])
def share(slug):
    event = Event.query.filter_by(slug=slug).first()
    if not event:
        return jsonify({'error': 'introuvable'}), 404
    data = request.get_json(silent=True) or {}
    channel = data.get('channel') or request.form.get('channel')
    if channel not in SHARE_CHANNELS:
        return jsonify({'error': 'channel invalide'}), 400
    db.session.add(EventShare(event_id=event.id, channel=channel))
    db.session.commit()
    return ('', 204)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@admin_events_bp.route('/admin/events')
@login_required
@admin_required
def admin_events():
    items = Event.query.order_by(Event.start_at.desc()).all()
    stats = {}
    for evt in items:
        stats[evt.id] = {
            'participants': evt.participants.count(),
            'organizations': evt.organizations.count(),
            'regions': evt.regions.count(),
        }
    return render_template('events/admin.html', events=items, stats=stats)


@admin_events_bp.route('/admin/events/<slug>/participants')
@login_required
@admin_required
def admin_participants(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)
    query = (EventParticipant.query
             .filter_by(event_id=event.id)
             .order_by(EventParticipant.created_at.desc()))
    pagination = query.paginate(page=page, per_page=50, error_out=False)
    return render_template('events/admin_participants.html',
                           event=event, pagination=pagination)


@admin_events_bp.route('/admin/events/<slug>/organizations')
@login_required
@admin_required
def admin_organizations(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    orgs = (EventOrganization.query
            .filter_by(event_id=event.id)
            .order_by(EventOrganization.created_at.desc())
            .all())
    return render_template('events/admin_organizations.html',
                           event=event, orgs=orgs)


@admin_events_bp.route('/admin/events/<slug>/organizations/<oid>/status',
                       methods=['POST'])
@login_required
@admin_required
def admin_org_status(slug, oid):
    if request.form.get('status') not in {'pending', 'confirmed', 'rejected'}:
        flash('Statut envalid.', 'error')
        return redirect(url_for('admin_events.admin_organizations', slug=slug))
    org = EventOrganization.query.filter_by(id=oid).first_or_404()
    org.status = request.form.get('status')
    db.session.commit()
    flash('Statut mete ajou.', 'success')
    return redirect(url_for('admin_events.admin_organizations', slug=slug))