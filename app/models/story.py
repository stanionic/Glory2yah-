from app import db
from app.models.base import BaseModel
import uuid


class Story(BaseModel):
    __tablename__ = 'stories'

    story_id = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    user_whatsapp = db.Column(db.String(20), nullable=False, index=True)
    
    title = db.Column(db.String(200), nullable=False, default="Story")
    description = db.Column(db.Text)
    media_type = db.Column(db.String(10), nullable=False, default='image')  # image or video
    media = db.Column(db.String(255), nullable=False)  # filename in static/uploads
    price_gkach = db.Column(db.Integer, default=0)
    
    admin_status = db.Column(db.String(20), default='approved', index=True)
    
    view_count = db.Column(db.Integer, default=0)
    like_count = db.Column(db.Integer, default=0)
    share_count = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.story_id,
            'story_id': self.story_id,
            'user_whatsapp': self.user_whatsapp,
            'name': self.user_whatsapp,
            'title': self.title,
            'desc': self.description or '',
            'price': self.price_gkach,
            'img': f'/static/uploads/{self.media}' if self.media_type == 'image' else None,
            'video': f'/static/uploads/{self.media}' if self.media_type == 'video' else None,
            'view_count': self.view_count,
            'like_count': self.like_count,
            'share_count': self.share_count
        }

    def get_media_url(self):
        return f'/static/uploads/{self.media}'
