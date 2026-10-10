"""
Mennen M — Transportation Blueprint
Real driver registry + admin approval workflow. Demo mode never debits Gkach.
"""
import os
import re
import uuid
import unicodedata
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import login_required, current_user
from sqlalchemy import or_ as _or, and_ as _and

from app import db, limiter
from app.models.mennem_trip import MennemTrip
from app.models.mennem_driver import MennemDriver
from app.services.gkach_service import GkachService
from app.services.notification_service import NotificationService
from app.utils.validators import (ValidationError, validate_whatsapp,
                                  validate_amount)
from app.utils.security import admin_required

# Create blueprint
mennem_bp = Blueprint('mennem', __name__, template_folder='templates', static_folder='static')

# SECURITY: trips are only possible with ADMIN-APPROVED drivers.
# MENNEM_DEMO_MODE=1 (default) records demo trips WITHOUT debiting real Gkach.
MENNEM_DEMO_MODE = os.environ.get('MENNEM_DEMO_MODE', '1') == '1'

# Platform commission on completed trips (same 2% as MACHE sales, P3).
MENNEM_COMMISSION_RATE = 0.02
# Negotiations with no answer for 24h are auto-cancelled (P3).
MENNEM_NEGOTIATION_TTL_HOURS = 24

ALLOWED_DRIVER_PHOTO_EXTS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

# Main Haitian communes/zones used for lightweight city detection (no geocoding)
HAITI_LOCATIONS = [
    'Port-au-Prince', 'Delmas', 'Pétion-Ville', 'Petion-Ville', 'Carrefour',
    'Tabarre', 'Cité Soleil', 'Croix-des-Bouquets', 'Kafou Fèy', 'Pétion',
    'Jacmel', 'Cap-Haïtien', 'Cap Haitien', 'Gonaïves', 'Les Cayes',
    'Saint-Marc', 'Léogâne', 'Leogane', 'Gressier', 'Kenscoff',
    'Thomassin', 'Bourgdon', 'Turgeau', 'Nazon', 'Canapé-Vert', 'Morne Hercule',
    'Péguy-Ville', 'Diquini', 'Thor', 'Bois-Verna',
]


def _guess_city(address):
    """Best-effort: detect a known Haitian commune/zone inside an address string."""
    if not address:
        return ''
    lower = str(address).lower()
    for loc in HAITI_LOCATIONS:
        if loc.lower() in lower:
            return loc
    return ''


def _allowed_photo(filename):
    return ('.' in filename
            and filename.rsplit('.', 1)[1].lower() in ALLOWED_DRIVER_PHOTO_EXTS)


# ---------------------------------------------------------------------------
# SUGGESTED PRICE MATRIX (market guide for negotiation, MACHE-checkout style)
# ---------------------------------------------------------------------------
# Normalized location -> zone key. Used by suggested_price().
_ZONE_OF = {
    'port au prince': 'pap', 'delmas': 'pap', 'petion ville': 'pap',
    'petion': 'pap', 'carrefour': 'pap', 'tabarre': 'pap',
    'cit soleil': 'pap', 'cite soleil': 'pap', 'croix des bouquets': 'pap',
    'kafou fey': 'pap', 'thomassin': 'pap', 'kenscoff': 'pap',
    'bourgdon': 'pap', 'turgeau': 'pap', 'nazon': 'pap', 'thor': 'pap',
    'bois verna': 'pap', 'canape vert': 'pap', 'morne hercule': 'pap',
    'peguy ville': 'pap', 'diquini': 'pap',
    'gressier': 'gressier', 'leogane': 'leogane',
    'grand goave': 'grandgoave', 'petit goave': 'grandgoave',
    'miragoane': 'miragoane', 'saint marc': 'saintmarc',
    'gonaires': 'gonnaires', 'jacmel': 'jacmel',
    'cap haitien': 'cap', 'caphaitien': 'cap', 'okap': 'cap',
    'les cayes': 'cayes', 'cayes': 'cayes',
}
# Symmetric inter-zone market fares (Gkach)
_ZONE_FARES = {
    frozenset(('pap', 'gressier')): 250,
    frozenset(('pap', 'leogane')): 400,
    frozenset(('pap', 'grandgoave')): 700,
    frozenset(('pap', 'miragoane')): 1500,
    frozenset(('pap', 'saintmarc')): 1200,
    frozenset(('pap', 'gonnaires')): 1500,
    frozenset(('pap', 'cayes')): 2500,
    frozenset(('pap', 'jacmel')): 600,
    frozenset(('pap', 'cap')): 3000,
    frozenset(('jacmel', 'cap')): 3500,
    frozenset(('jacmel', 'cayes')): 3000,
    frozenset(('cap', 'gonnaires')): 2000,
    frozenset(('gonnaires', 'cayes')): 2200,
    frozenset(('leogane', 'jacmel')): 800,
}


def _norm_loc(value):
    """Normalize a location string: lowercase, accents stripped, alnum only."""
    s = unicodedata.normalize('NFD', (value or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def suggested_price(from_location, to_location):
    """Best-effort market fare (Gkach) for a route. None if route unknown.

    Guides the MACHE-style negotiation: shown on search results, the booking
    page and the trip page as "pri mache sijere".
    """
    a = _ZONE_OF.get(_norm_loc(from_location))
    b = _ZONE_OF.get(_norm_loc(to_location))
    if not a or not b:
        return None
    if a == b:
        # Intra-zone: metro rides are short-haul, other zones default 400.
        return 150 if a == 'pap' else 400
    return _ZONE_FARES.get(frozenset((a, b)))


def _trip_notify(trip, audience):
    """Contextual WhatsApp deep-link to ping the other party about a trip.

    Follows the codebase convention (NotificationService.generate_whatsapp_link,
    like delivery checkout notifications). Returns (link, label) or (None, None).
    """
    trip_url = url_for('mennem.trip', trip_id=trip.id, _external=True)
    route = f"{trip.from_location} → {trip.to_location}"
    if trip.status == 'negotiating':
        if audience == 'driver':
            msg = (f"🚕 MENNEM M — Nouvo demann vwayaj: {route}. "
                   f"Kliyan an pwopoze {trip.proposed_price} Gk. "
                   f"Reponn isit: {trip_url}")
            label = 'Notifye chofè a (nouvo demann)'
        else:
            msg = (f"🚕 MENNEM M — Chofè a fè yon kontre-pwopozisyon "
                   f"({trip.counter_price} Gk) pou {route}. Reponn isit: {trip_url}")
            label = 'Notifye kliyan an (kontre-pri)'
    elif trip.status == 'accepted':
        msg = (f"🎉 MENNEM M — Pri aksepte: {trip.accepted_price} Gk pou {route}. "
               f"Kliyan an ka konfime peman an isit: {trip_url}")
        label = 'Anonse akò a sou WhatsApp'
    elif trip.status in ('paid', 'demo'):
        msg = (f"💳 MENNEM M — Peman konfime ({trip.accepted_price} Gk) pou {route}. "
               f"Ou ka kontakte lòt pati a kounye a. Detay: {trip_url}")
        label = 'Anonse peman an sou WhatsApp'
    else:
        msg = f"🚕 MENNEM M — Vwayaj {route}. Detay: {trip_url}"
        label = 'Pataje detay vwayaj la'
    phone = trip.driver_phone if audience == 'driver' else trip.passenger_whatsapp
    link = NotificationService.generate_whatsapp_link(phone, msg)
    return (link, label) if link else (None, None)


def _expire_stale_negotiations():
    """Auto-cancel negotiations left unanswered for >24h (P3)."""
    try:
        cutoff = datetime.utcnow() - timedelta(hours=MENNEM_NEGOTIATION_TTL_HOURS)
        stale = MennemTrip.query.filter(
            MennemTrip.status == 'negotiating',
            MennemTrip.created_at < cutoff,
        ).all()
        for trip in stale:
            trip.status = 'cancelled'
            trip.add_history_event(
                'system', 'Negosyasyon an ekspire — pa gen repons nan 24 èdtan.')
        if stale:
            db.session.commit()
            current_app.logger.info(
                f'MENNEM: expired {len(stale)} stale negotiation(s)')
        return len(stale)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'MENNEM expire error: {e}', exc_info=True)
        return 0


def _pending_action_count():
    """Trips waiting for THE logged-in user's next move (in-app badge, P3).

    Client's turn: a counter-offer arrived (negotiating + counter_price set)
    or the deal is accepted and payment is due.
    Driver's turn: a client proposal is open (negotiating + no counter yet).
    """
    if not current_user.is_authenticated:
        return 0
    try:
        client_pending = MennemTrip.query.filter(
            MennemTrip.passenger_id == current_user.id,
            _or(
                MennemTrip.status == 'accepted',
                _and(
                    MennemTrip.status == 'negotiating',
                    MennemTrip.counter_price.isnot(None),
                ),
            ),
        ).count()
        driver_pending = 0
        driver = MennemDriver.query.filter_by(
            whatsapp=current_user.whatsapp).first()
        if driver is not None:
            driver_pending = MennemTrip.query.filter(
                MennemTrip.driver_id == driver.id,
                MennemTrip.status == 'negotiating',
                MennemTrip.counter_price.is_(None),
            ).count()
        return client_pending + driver_pending
    except Exception:
        return 0


def _save_driver_photo(file_storage):
    """Persist a driver photo into UPLOAD_FOLDER. Returns stored filename or None."""
    if file_storage is None or not file_storage.filename:
        return None
    if not _allowed_photo(file_storage.filename):
        raise ValidationError(
            'Fòma foto a pa sipòte. Sèvi ak PNG, JPG, JPEG, WEBP oswa GIF sèlman.'
        )
    upload_dir = current_app.config.get('UPLOAD_FOLDER') or os.path.join('static', 'uploads')
    try:
        os.makedirs(upload_dir, exist_ok=True)
    except Exception:
        pass
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    filename = f'mennem_driver_{uuid.uuid4().hex}.{ext}'
    file_storage.save(os.path.join(upload_dir, filename))
    return filename


# Routes
@mennem_bp.route('/')
def index():
    _expire_stale_negotiations()
    return render_template(
        'mennenm/index.html',
        pending_count=_pending_action_count(),
    )


@mennem_bp.route('/find', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def find():
    if request.method == 'POST':
        from_location = (request.form.get('from') or '').strip()
        to_location = (request.form.get('to') or '').strip()

        if not from_location or not to_location:
            flash('Tanpri antre depa ak destinasyon!', 'error')
            return redirect(url_for('mennem.index'))

        # Real registered drivers: verified + active only
        query = MennemDriver.active().filter(
            MennemDriver.is_verified.is_(True),
            MennemDriver.is_active.is_(True),
        )

        # Lightweight keyword filter against city/address (no geocoding yet)
        keywords = [
            w.strip().strip(',').lower()
            for w in (from_location + ' ' + to_location).split()
            if len(w.strip().strip(',')) >= 3
        ]
        if keywords:
            conditions = [
                _or(
                    MennemDriver.city.ilike(f'%{kw}%'),
                    MennemDriver.address.ilike(f'%{kw}%'),
                )
                for kw in keywords
            ]
            query = query.filter(_or(*conditions))

        drivers = (
            query
            .order_by(MennemDriver.rating.desc(), MennemDriver.trips_count.desc())
            .limit(50)
            .all()
        )

        return render_template(
            'mennenm/result.html',
            drivers=drivers,
            from_location=from_location,
            to_location=to_location,
            suggested=suggested_price(from_location, to_location),
            demo_mode=MENNEM_DEMO_MODE,
        )

    return redirect(url_for('mennem.index'))

@mennem_bp.route('/register_driver', methods=['GET', 'POST'])
@limiter.limit('10 per hour')
def register_driver():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        address = (request.form.get('address') or '').strip()
        try:
            base_fare = int((request.form.get('price') or '').strip() or 150)
        except (TypeError, ValueError):
            base_fare = 150
        photo_file = request.files.get('photo')

        if len(name) < 3:
            flash('Antre non konplè ou (omwen 3 karaktè).', 'error')
            return render_template('mennenm/register_driver.html', form=request.form)

        try:
            whatsapp_clean = validate_whatsapp(phone)
        except ValidationError as e:
            flash(f'Nimewo WhatsApp la pa valid — {e}', 'error')
            return render_template('mennenm/register_driver.html', form=request.form)

        if not address:
            flash('Antre adrès kote ou ye a.', 'error')
            return render_template('mennenm/register_driver.html', form=request.form)

        if base_fare < 50:
            flash('Pri minimòm lan se 50 Gkach.', 'error')
            return render_template('mennenm/register_driver.html', form=request.form)

        try:
            photo_filename = _save_driver_photo(photo_file)
        except ValidationError as e:
            flash(str(e), 'error')
            return render_template('mennenm/register_driver.html', form=request.form)

        existing = MennemDriver.query.filter_by(whatsapp=whatsapp_clean).first()
        if existing is not None and existing.deleted_at is None:
            flash('Yon chofè ak nimewo WhatsApp sa a deja anrejistre.', 'warning')
            return redirect(url_for('mennem.index'))

        driver = MennemDriver(
            name=name,
            whatsapp=whatsapp_clean,
            address=address,
            city=_guess_city(address),
            photo=photo_filename,
            base_fare=base_fare,
            rating=5.0,
            trips_count=0,
            is_active=False,
            is_verified=False,
        )
        db.session.add(driver)
        db.session.commit()
        current_app.logger.info(
            f'MENNEM: new driver registered id={driver.id} whatsapp={whatsapp_clean}'
        )

        # ── ADMIN APPROVAL TRAFFIC ───────────────────────────────────────────
        # A driver starts is_verified=False / is_active=False → the admin must
        # approve the file before the driver becomes visible in searches.
        try:
            from app.services.admin_approval_alerts import alert_driver_registration
            alert_driver_registration(driver)
        except Exception as _alert_err:
            current_app.logger.warning('driver approval alert failed: %s', _alert_err)

        flash(
            '✅ Enskripsyon resevwa! Administratè a ap revize dosye w—'
            'lè li apwouve, w ap parèt nan rechèch la.',
            'success',
        )
        return redirect(url_for('mennem.index'))

    return render_template('mennenm/register_driver.html', form=None)

@mennem_bp.route('/book/<int:driver_id>/<from_loc>/<to_loc>', methods=['GET', 'POST'])
@limiter.limit('20 per minute')
def book(driver_id, from_loc, to_loc):
    """Start a trip request — creates a negotiation (like MACHE checkout).

    The request is stored with status='negotiating' and the client's proposed
    price. NO Gkach is debited here. The driver can accept, counter or refuse.
    """
    driver = MennemDriver.get_by_id(driver_id)
    if driver is None or not driver.is_verified or not driver.is_active:
        flash('Chofè sa a pa disponib ankò.', 'error')
        return redirect(url_for('mennem.find'))

    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Ou dwe konekte pou voye yon demann chofè!', 'error')
            return redirect(url_for('auth.login', next=request.url))

        proposed = request.form.get('price') or driver.base_fare
        try:
            proposed = validate_amount(proposed, min_amount=10)
        except ValidationError as e:
            flash(str(e), 'error')
            return redirect(url_for('mennem.book', driver_id=driver_id,
                                    from_loc=from_loc, to_loc=to_loc))

        # Avoid duplicate open requests for the same route/driver (same passenger)
        existing_open = (
            MennemTrip.active()
            .filter(
                MennemTrip.passenger_id == current_user.id,
                MennemTrip.driver_id == driver.id,
                MennemTrip.status.in_(['negotiating', 'accepted']),
            )
            .first()
        )
        if existing_open is not None:
            flash('Ou gen yon demann ki ankou ou pou chofè sa a. Kontinye negosyasyon an.', 'info')
            return redirect(url_for('mennem.trip', trip_id=existing_open.id))

        trip = MennemTrip(
            from_location=from_loc,
            to_location=to_loc,
            price_gkach=0,  # only set once agreed
            driver_id=driver.id,
            driver_name=driver.name,
            driver_phone=driver.whatsapp,
            driver_rating=driver.rating,
            passenger_id=current_user.id,
            passenger_whatsapp=current_user.whatsapp,
            proposed_price=proposed,
            counter_price=None,
            accepted_price=None,
            status='negotiating',
        )
        trip.add_history_event(
            'client', f'Demann kou: {from_loc} → {to_loc}. Mwen pwopoze {proposed} Gk.',
            price=proposed,
        )
        db.session.add(trip)
        db.session.commit()
        current_app.logger.info(
            f'MENNEM: trip request {trip.id} created for driver {driver.id} '
            f'(client proposes {proposed} Gk)'
        )

        flash('✅ Demann ou voye! Chofè a ap reponn — negosye pri a sou paj la.', 'success')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    # GET request: show booking confirmation with price input
    return render_template(
        'mennenm/book.html',
        driver=driver,
        from_location=from_loc,
        to_location=to_loc,
        suggested=suggested_price(from_loc, to_loc),
        demo_mode=MENNEM_DEMO_MODE,
    )

@mennem_bp.route('/success/<int:trip_id>')
@login_required
def success(trip_id):
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, is_driver = _trip_roles(trip)
    if not (is_client or is_driver or current_user.is_admin):
        _abort_mennem_no_access()
    return render_template('mennenm/success.html', trip=trip)


# ============================================================================
# PRICE NEGOTIATION (MACHE-checkout style)
#   trip detail + prices + accept/counter + pay/cancel
# ============================================================================
def _abort_mennem_no_access():
    from flask import abort as _abort
    _abort(403)


def _trip_roles(trip):
    """Return (is_client, is_driver) booleans based on the logged-in user."""
    if not current_user.is_authenticated:
        return False, False
    is_client = trip.passenger_id == current_user.id
    is_driver = trip.driver is not None and trip.driver.whatsapp == current_user.whatsapp
    return bool(is_client), bool(is_driver)


@mennem_bp.route('/trip/<int:trip_id>')
@login_required
def trip(trip_id):
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))

    is_client, is_driver = _trip_roles(trip)
    if not (is_client or is_driver or current_user.is_admin):
        _abort_mennem_no_access()

    # Contextual WhatsApp notification to the other party (codebase convention)
    notify_link = notify_label = None
    if is_client and trip.driver_phone:
        notify_link, notify_label = _trip_notify(trip, 'driver')
    elif is_driver:
        notify_link, notify_label = _trip_notify(trip, 'client')

    return render_template(
        'mennenm/trip.html',
        trip=trip,
        is_client=is_client,
        is_driver=is_driver,
        suggested=suggested_price(trip.from_location, trip.to_location),
        notify_link=notify_link,
        notify_label=notify_label,
        demo_mode=MENNEM_DEMO_MODE,
    )


@mennem_bp.route('/trip/<int:trip_id>/propose', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def trip_propose(trip_id):
    """Client proposes a new price (or a first counter if status still open)."""
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, _ = _trip_roles(trip)
    if not (is_client or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status not in ('negotiating',):
        flash('Negosyasyon an fèmen — ou pa ka pwopoze pri ankò.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    try:
        price = validate_amount(request.form.get('price'), min_amount=10)
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    trip.proposed_price = price
    trip.counter_price = None
    trip.add_history_event('client', f'Kliyan pwopoze {price} Gk.', price=price)
    db.session.commit()
    flash('Pri ou anrejistre. Chofè a ap fè yon repons.', 'success')
    return redirect(url_for('mennem.trip', trip_id=trip.id))


@mennem_bp.route('/trip/<int:trip_id>/counter', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def trip_counter(trip_id):
    """Driver makes a counter-offer."""
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    _, is_driver = _trip_roles(trip)
    if not (is_driver or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status not in ('negotiating',):
        flash('Negosyasyon an fèmen — ou pa ka fè kontreè.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    try:
        price = validate_amount(request.form.get('price'), min_amount=10)
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    trip.counter_price = price
    trip.proposed_price = None
    trip.add_history_event('driver', f'Chofè kontre-pwopoze {price} Gk.', price=price)
    db.session.commit()
    flash('Kontreè ou anrejistre. Kliyan an ka aksepte oswa fè yon lòt pri.', 'success')
    return redirect(url_for('mennem.trip', trip_id=trip.id))


@mennem_bp.route('/trip/<int:trip_id>/accept', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def trip_accept(trip_id):
    """Accept the latest proposed/counter price -> status 'accepted'."""
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, is_driver = _trip_roles(trip)
    if not (is_client or is_driver or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status != 'negotiating':
        flash('Pa gen negosyasyon ki louvri kounye a.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    # The other side's current price is the one being accepted
    accepted = None
    if is_client:
        accepted = trip.counter_price          # client accepts driver's counter
        history_note = f'Kliyan aksepte {accepted} Gk.'
    elif is_driver:
        accepted = trip.proposed_price          # driver accepts client's proposal
        history_note = f'Chofè aksepte {accepted} Gk.'
    else:  # admin
        accepted = trip.counter_price or trip.proposed_price
        history_note = f'Admin fikse pri a {accepted} Gk.'

    if not accepted:
        flash('Pa gen pri pou aksepte — fè yon pwopozisyon anvan.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    trip.accepted_price = accepted
    trip.price_gkach = accepted
    trip.status = 'accepted'
    trip.add_history_event('system', history_note, price=accepted)
    db.session.commit()
    flash(f'🎉 Pri aksepte: {accepted} Gk. Kliyan an ka konfime peman an now.', 'success')
    return redirect(url_for('mennem.trip', trip_id=trip.id))


@mennem_bp.route('/trip/<int:trip_id>/pay', methods=['POST'])
@login_required
@limiter.limit('5 per minute')
def trip_pay(trip_id):
    """Client confirms & pays the agreed price (ONE debit, à la MACHE)."""
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, _ = _trip_roles(trip)
    if not (is_client or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status != 'accepted':
        flash('Pri a pa aksepte ankò — kliyan an dwe konfime pri a anvan peman.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    agreed = trip.accepted_price or trip.price_gkach
    if not agreed:
        flash('Pa gen pri aksepte.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    try:
        if MENNEM_DEMO_MODE:
            trip.status = 'demo'  # demo: recorded, no debit
            trip.add_history_event(
                'system',
                f'DEMO: kliyan konfime {agreed} Gk (pa gen debi an demomòd).',
                price=agreed,
            )
            db.session.commit()
            if trip.driver:
                trip.driver.trips_count = (trip.driver.trips_count or 0) + 1
                db.session.commit()
            flash(f'✅ DEMO: akò konfime a {agreed} Gk. Pa gen Gkach debite (demo).', 'success')
        else:
            GkachService.deduct_balance(
                current_user.whatsapp,
                agreed,
                f'Voyaj MENNEM M: {trip.from_location} → {trip.to_location}',
                'mennem_payment',
            )
            trip.status = 'paid'
            trip.add_history_event(
                'system', f'Kliyan peye {agreed} Gk.', price=agreed,
            )
            db.session.commit()
            if trip.driver:
                trip.driver.trips_count = (trip.driver.trips_count or 0) + 1
                db.session.commit()
            flash(f'💳 Peman {agreed} Gk konfime! Chofè a ap vin pran ou.', 'success')
    except ValidationError as e:
        db.session.rollback()
        current_app.logger.error(f'MENNEM pay validation: {e}', exc_info=True)
        flash(str(e), 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'MENNEM pay error: {e}', exc_info=True)
        flash(f'Erè nan peman: {str(e)}', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    return redirect(url_for('mennem.success', trip_id=trip.id))


@mennem_bp.route('/trip/<int:trip_id>/cancel', methods=['POST'])
@login_required
def trip_cancel(trip_id):
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, is_driver = _trip_roles(trip)
    if not (is_client or is_driver or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status in ('completed', 'cancelled'):
        flash('Voyaj la deja fèmen.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    agreed = trip.accepted_price or trip.price_gkach
    try:
        if trip.status == 'paid' and not MENNEM_DEMO_MODE and agreed:
            # Real mode: the client already paid -> refund them.
            GkachService.add_balance(
                trip.passenger_whatsapp,
                agreed,
                f'Remanbourseman voyaj MENNEM M anile: '
                f'{trip.from_location} → {trip.to_location}',
                'mennem_refund',
            )
            trip.add_history_event(
                'system', f'Remanbourseman {agreed} Gk voye bay kliyan an.',
                price=agreed,
            )
            flash(f'↩️ Voyaj anile. {agreed} Gk remanbourse.', 'warning')
        else:
            trip.add_history_event('system', 'Voyaj la anile.')
            flash('Voyaj la anile.', 'warning')
        trip.status = 'cancelled'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'MENNEM cancel error: {e}', exc_info=True)
        flash(f'Erè pandan anilasyon an: {str(e)}', 'error')
    return redirect(url_for('mennem.trip', trip_id=trip.id))


@mennem_bp.route('/trip/<int:trip_id>/complete', methods=['POST'])
@login_required
def trip_complete(trip_id):
    """Client marks the trip as completed (driver gets paid in real mode)."""
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, _ = _trip_roles(trip)
    if not (is_client or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status not in ('paid', 'demo'):
        flash('Voyaj la pa peye ankò.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    agreed = trip.accepted_price or trip.price_gkach
    was_paid = trip.status == 'paid'
    try:
        if was_paid and not MENNEM_DEMO_MODE and agreed and trip.driver_phone:
            # Real mode: release the fare to the driver, minus the platform
            # commission (same 2% split as MACHE's process_purchase).
            commission = int(round(agreed * MENNEM_COMMISSION_RATE))
            payout = agreed - commission
            GkachService.add_balance(
                trip.driver_phone,
                payout,
                f'Peman voyaj MENNEM M konplete: '
                f'{trip.from_location} → {trip.to_location}',
                'mennem_payout',
            )
            if commission > 0:
                try:
                    GkachService.add_balance(
                        '+509PLATFORM',
                        commission,
                        f'Komisyon {int(MENNEM_COMMISSION_RATE * 100)}% voyaj '
                        f'MENNEM M #{trip.id}',
                        'commission',
                    )
                except Exception:
                    pass  # platform account may not validate — never block payout
            trip.add_history_event(
                'system',
                f'{payout} Gk vire bay chofè a (komisyon platfòm: '
                f'{commission} Gk).',
                price=payout,
            )
            flash(f'✅ Voyaj konplete — {payout} Gk vire bay chofè a. Mèsi!',
                  'success')
        else:
            trip.add_history_event('system', 'Voyaj la konplete.')
            flash('✅ Voyaj konplete. Mèsi!', 'success')
        trip.status = 'completed'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'MENNEM complete error: {e}', exc_info=True)
        flash(f'Erè pandan konplètman an: {str(e)}', 'error')
    return redirect(url_for('mennem.trip', trip_id=trip.id))


@mennem_bp.route('/trip/<int:trip_id>/rate', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def trip_rate(trip_id):
    """Client rates the driver 1-5 after completion (updates driver's avg)."""
    trip = MennemTrip.get_by_id(trip_id)
    if trip is None:
        flash('Voyaj sa pa jwenn.', 'error')
        return redirect(url_for('mennem.index'))
    is_client, _ = _trip_roles(trip)
    if not (is_client or current_user.is_admin):
        _abort_mennem_no_access()

    if trip.status != 'completed':
        flash('Ou ka nòte chofè a sèlman apre vwayaj la konplete.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))
    if trip.client_rating() is not None:
        flash('Ou deja nòte vwayaj sa a.', 'warning')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    try:
        rating = int(request.form.get('rating') or 0)
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        flash('Nòt la dwe ant 1 ak 5 etwal.', 'error')
        return redirect(url_for('mennem.trip', trip_id=trip.id))

    trip.add_history_event('client', f'Kliyan nòte chofè a {rating}/5 ⭐.', rating=rating)
    driver = trip.driver
    if driver is not None:
        n = driver.trips_count or 0
        old = driver.rating or 5.0
        if n > 1:
            driver.rating = round(((old * (n - 1)) + rating) / n, 2)
        else:
            driver.rating = float(rating)
    db.session.commit()
    flash(f'⭐ Mèsi! Nòt ou ({rating}/5) anrejistre.', 'success')
    return redirect(url_for('mennem.trip', trip_id=trip.id))


@mennem_bp.route('/my-trips')
@login_required
def my_trips():
    """List trips where the user is client OR driver (MACHE my-deliveries style)."""
    _expire_stale_negotiations()
    trips = (
        MennemTrip.active()
        .filter(
            _or(
                MennemTrip.passenger_id == current_user.id,
                MennemTrip.driver_phone == current_user.whatsapp,
            )
        )
        .order_by(MennemTrip.created_at.desc())
        .all()
    )
    return render_template(
        'mennenm/trips.html',
        trips=trips,
        pending_count=_pending_action_count(),
        is_client_trip=(lambda t: bool(t.passenger_id == current_user.id)),
    )


# ---------------------------------------------------------------------------
# ADMIN — approve (verify) / activate / deactivate registered drivers
# ---------------------------------------------------------------------------
@mennem_bp.route('/admin')
@login_required
@admin_required
def admin():
    drivers = (
        MennemDriver.active()
        .order_by(MennemDriver.is_verified.asc(), MennemDriver.created_at.desc())
        .all()
    )
    return render_template(
        'mennenm/admin.html',
        drivers=drivers,
        total=len(drivers),
        verified_count=sum(1 for d in drivers if d.is_verified),
        active_count=sum(1 for d in drivers if d.is_active),
    )


@mennem_bp.route('/admin/driver/<int:driver_id>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle(driver_id):
    """Verify + activate, or deactivate a driver in one call."""
    driver = MennemDriver.get_by_id(driver_id)
    if driver is None:
        flash('Chofè sa pa jwenn nan baz done.', 'error')
        return redirect(url_for('mennem.admin'))

    action = request.form.get('action', '')
    if action == 'activate':
        driver.is_verified = True
        driver.is_active = True
        db.session.commit()
        current_app.logger.info(f'MENNEM ADMIN: driver {driver.id} verified+activated')
        flash(f'✅ Chofè {driver.name} verifye ak aktive.', 'success')
    elif action == 'deactivate':
        driver.is_active = False
        db.session.commit()
        current_app.logger.info(f'MENNEM ADMIN: driver {driver.id} deactivated')
        flash(f'⛔ Chofè {driver.name} dezaktive.', 'warning')
    else:
        flash('Aksyon enkoni.', 'error')
    return redirect(url_for('mennem.admin'))
