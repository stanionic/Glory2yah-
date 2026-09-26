import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db
from app.models.user import User
from app.models.ad import Ad
from app.models.user_gkach import UserGkach
from app.services.gkach_service import GkachService


def test_welcome_bonus_is_awarded_once():
    app = create_app("testing")
    with app.app_context():
        user = User(
            whatsapp="+50940000001",
            pseudo="welcome_test_1",
            name="Welcome Tester",
            auth_provider="whatsapp",
            is_active=True,
        )
        user.set_password("StrongPass123!")
        db.session.add(user)
        db.session.commit()

        bal1 = GkachService.issue_welcome_bonus(user.whatsapp)
        bal2 = GkachService.issue_welcome_bonus(user.whatsapp)

        assert bal1 == 50
        assert bal2 == 50
        assert GkachService.get_balance(user.whatsapp) == 50

        txns = db.session.query(GkachService.gkach_transaction_model()).filter_by(
            user_whatsapp=user.whatsapp,
            transaction_type="WELCOME_BONUS",
            status="completed",
        ).all()
        assert len(txns) == 1


def test_welcome_gkach_is_restricted_to_certified_products():
    app = create_app("testing")
    with app.app_context():
        user = User(
            whatsapp="+50940000002",
            pseudo="welcome_cert_test",
            name="Cert Buyer",
            auth_provider="whatsapp",
            is_active=True,
        )
        user.set_password("StrongPass123!")
        db.session.add(user)
        db.session.commit()

        # create account with welcome balance
        account = UserGkach.query.filter_by(user_whatsapp=user.whatsapp).first()
        if account is None:
            account = UserGkach(user_whatsapp=user.whatsapp, gkach_balance=50, welcome_balance=50)
            db.session.add(account)
            db.session.commit()
        else:
            account.gkach_balance = 50
            account.welcome_balance = 50
            db.session.commit()

        certified = Ad(
            ad_id="certified-ad-1",
            user_whatsapp="+50999999999",
            title="Certified Product",
            description="Certified product",
            media_type="images",
            price_gkach=80,
            ad_type="sell",
            admin_status="approved",
            is_certified=True,
            certification_status="CERTIFIED",
        )
        uncertified = Ad(
            ad_id="uncertified-ad-1",
            user_whatsapp="+50999999998",
            title="Uncertified Product",
            description="Uncertified product",
            media_type="images",
            price_gkach=80,
            ad_type="sell",
            admin_status="approved",
            is_certified=False,
            certification_status="NONE",
        )
        db.session.add_all([certified, uncertified])
        db.session.commit()

        assert GkachService.can_use_welcome_gkach_for_purchase(user.whatsapp, certified.ad_id) is True
        assert GkachService.can_use_welcome_gkach_for_purchase(user.whatsapp, uncertified.ad_id) is False
