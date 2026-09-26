"""Create an owned room + user for the media-upload diagnostic."""
import uuid
from datetime import datetime
from app import create_app, db
from app.models.user import User
from app.models.konferans import KonferansRoom

app = create_app('development')
with app.app_context():
    u = User.query.filter_by(pseudo='diaguser').first()
    if not u:
        u = User(name='Diag User', pseudo='diaguser', whatsapp='50900000001',
                 auth_provider='whatsapp', is_active=True)
        db.session.add(u)
    u.set_password('DiagPass123!')
    u.is_active = True
    db.session.commit()

    r = KonferansRoom.query.filter_by(room_code='DIAG02').first()
    if not r:
        r = KonferansRoom(room_id=str(uuid.uuid4()), room_code='DIAG02',
                          room_name='Diag Upload Room', room_type='classic',
                          creator_name=u.name, user_id=u.id, max_participants=50)
        db.session.add(r)
    r.creator_name = u.name
    r.user_id = u.id
    r.is_active = True
    r.started_at = datetime.utcnow()
    db.session.commit()
    print(f'user_id={u.id} room_code={r.room_code} room_id={r.room_id}')
