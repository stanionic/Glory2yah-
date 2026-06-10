"""
Database models for MANDEMMAPBAW
NOTE: This is a placeholder file. 
Full implementation needed - see INSTALL.md
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ChatHistory(db.Model):
    """Historique des conversations"""
    __tablename__ = 'chat_history'
    
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False, index=True)
    response = db.Column(db.Text, nullable=False)
    mode = db.Column(db.String(20), default='chat', index=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'prompt': self.prompt,
            'response': self.response,
            'mode': self.mode,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class ImageGeneration(db.Model):
    """Générations d'images"""
    __tablename__ = 'image_generation'
    
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False, index=True)
    filename = db.Column(db.String(200), nullable=False, unique=True)
    filepath = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    file_size = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'prompt': self.prompt,
            'filename': self.filename,
            'filepath': self.filepath,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'file_size': self.file_size
        }

class VideoGeneration(db.Model):
    """Générations de vidéos"""
    __tablename__ = 'video_generation'
    
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False, index=True)
    filename = db.Column(db.String(200), nullable=False, unique=True)
    filepath = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    file_size = db.Column(db.Integer, default=0)
    duration = db.Column(db.Float, default=0.0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'prompt': self.prompt,
            'filename': self.filename,
            'filepath': self.filepath,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'file_size': self.file_size,
            'duration': self.duration
        }

class CodeGeneration(db.Model):
    """Générations de code"""
    __tablename__ = 'code_generation'
    
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False, index=True)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), index=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'prompt': self.prompt,
            'code': self.code,
            'language': self.language,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
