from app import db

class AdminSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setting_name = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<AdminSetting {self.setting_name}: {self.setting_value}>"

    @staticmethod
    def get_setting(name, default=None):
        setting = AdminSettings.query.filter_by(setting_name=name).first()
        if setting:
            return setting.setting_value
        return default

    @staticmethod
    def set_setting(name, value):
        setting = AdminSettings.query.filter_by(setting_name=name).first()
        if setting:
            setting.setting_value = str(value)
        else:
            setting = AdminSettings(setting_name=name, setting_value=str(value))
            db.session.add(setting)
        db.session.commit()

    @staticmethod
    def get_all_settings():
        return {s.setting_name: s.setting_value for s in AdminSettings.query.all()}
