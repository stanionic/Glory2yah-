from app.models.base import BaseModel
from app import db
from datetime import datetime

class KonferansRoom(BaseModel):
    __tablename__ = 'konferans_rooms'
    
    room_id = db.Column(db.String(128), unique=True, nullable=False)
    room_code = db.Column(db.String(10), unique=True, nullable=False)
    room_name = db.Column(db.String(255), nullable=False)
    creator_name = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    creator_whatsapp = db.Column(db.String(30), nullable=True)
    
    # Relationship
    user = db.relationship('User', backref='konferans_rooms', lazy=True)


class KonferansRecording(BaseModel):
    __tablename__ = 'konferans_recordings'
    
    room_id = db.Column(db.String(128), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
