"""
Base Model with Redis caching support
"""
from datetime import datetime
from app import db


class BaseModel(db.Model):
    """Base model with common fields"""
    
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert model to dictionary"""
        try:
            if hasattr(self, '__table__') and self.__table__ is not None:
                return {
                    column.name: getattr(self, column.name)
                    for column in self.__table__.columns
                }
        except Exception:
            pass
        # Fallback: return common fields
        return {
            'id': getattr(self, 'id', None),
            'created_at': getattr(self, 'created_at', None),
            'updated_at': getattr(self, 'updated_at', None)
        }
    
    def save(self):
        """Save model to database"""
        db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Delete model from database"""
        db.session.delete(self)
        db.session.commit()
    
    @classmethod
    def get_by_id(cls, id):
        """Get model by ID (SQLAlchemy 2.0 style — modern db.session.get, no deprecation warning)"""
        return db.session.get(cls, id)
    
    @classmethod
    def get_all(cls):
        """Get all models"""
        return cls.query.all()
    
    @classmethod
    def paginate(cls, page=1, per_page=20):
        """Paginate models"""
        return cls.query.paginate(page=page, per_page=per_page, error_out=False)
