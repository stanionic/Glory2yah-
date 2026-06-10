"""
Training data models for MANDEMMAPBAW
Allows users to submit examples to improve the AI
"""

from datetime import datetime
from .models import db

class TrainingImage(db.Model):
    """User-submitted images for training"""
    __tablename__ = 'training_images'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False, unique=True)
    filepath = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(500))
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    file_size = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'description': self.description,
            'tags': self.tags,
            'approved': self.approved,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class TrainingVideo(db.Model):
    """User-submitted videos for training"""
    __tablename__ = 'training_videos'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False, unique=True)
    filepath = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(500))
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    file_size = db.Column(db.Integer, default=0)
    duration = db.Column(db.Float, default=0.0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'description': self.description,
            'tags': self.tags,
            'approved': self.approved,
            'duration': self.duration,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class TrainingConversation(db.Model):
    """User-submitted conversation examples"""
    __tablename__ = 'training_conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False, index=True)
    expected_response = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), index=True)
    language = db.Column(db.String(20), default='kreyol', index=True)
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    used_count = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_message': self.user_message,
            'expected_response': self.expected_response,
            'category': self.category,
            'language': self.language,
            'approved': self.approved,
            'used_count': self.used_count,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class TrainingCode(db.Model):
    """User-submitted code examples"""
    __tablename__ = 'training_code'
    
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False, index=True)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.Text)
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    used_count = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'prompt': self.prompt,
            'code': self.code,
            'language': self.language,
            'description': self.description,
            'approved': self.approved,
            'used_count': self.used_count,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
