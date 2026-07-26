"""App Installation Model - Tracks PWA installations"""
from app import db
from app.models.base import BaseModel


class AppInstallation(BaseModel):
    """Tracks PWA/App installations for analytics"""
    __tablename__ = 'app_installations'

    id = db.Column(db.Integer, primary_key=True)
    user_whatsapp = db.Column(db.String(20), db.ForeignKey('users.whatsapp'), nullable=True, index=True)
    device_type = db.Column(db.String(50))
    platform = db.Column(db.String(50))  # ios, android, web
    install_method = db.Column(db.String(50))  # pwa, direct, referral
    referral_code = db.Column(db.String(50), nullable=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    install_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    uninstall_date = db.Column(db.DateTime, nullable=True)

    @classmethod
    def get_stats(cls):
        """Get PWA installation statistics"""
        from app import db
        total_visitors = cls.query.count()
        prompts_displayed = cls.query.filter(cls.install_prompt_displayed == True).count() if hasattr(cls, 'install_prompt_displayed') else 0
        installs_completed = cls.query.filter(cls.install_completed == True).count() if hasattr(cls, 'install_completed') else 0
        dismissed = cls.query.filter(cls.dismissed == True).count() if hasattr(cls, 'dismissed') else 0
        
        conversion_rate = 0
        if prompts_displayed > 0:
            conversion_rate = round((installs_completed / prompts_displayed) * 100, 1)
        
        return {
            'total_visitors': total_visitors,
            'prompts_displayed': prompts_displayed,
            'installs_completed': installs_completed,
            'dismissed': dismissed,
            'conversion_rate': conversion_rate
        }

    @classmethod
    def record_event(cls, user_id=None, device_type='desktop', browser='unknown', os='unknown', language='ht', install_prompt_displayed=False, install_completed=False, dismissed=False):
        """Record a PWA installation event"""
        record = cls(
            user_whatsapp=user_id,
            device_type=device_type,
            platform=os,
            install_method='pwa',
            user_agent=f'{browser}/{os}',
            is_active=install_completed,
            last_seen=db.func.current_timestamp()
        )
        db.session.add(record)
        db.session.commit()
        return record

    def to_dict(self):
        return {
            'id': self.id,
            'user_whatsapp': self.user_whatsapp,
            'device_type': self.device_type,
            'platform': self.platform,
            'install_method': self.install_method,
            'is_active': self.is_active,
            'install_date': self.install_date.isoformat() if self.install_date else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }
