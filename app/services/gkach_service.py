"""
Gkach Service Layer
Business logic for virtual currency operations
"""
from app import db
from app.models.user_gkach import UserGkach
from app.models.gkach_transaction import GkachTransaction
from app.utils.validators import validate_amount, validate_whatsapp, ValidationError
from sqlalchemy import func
import uuid


class GkachService:
    """Service for Gkach operations"""
    
    @staticmethod
    def get_or_create_account(whatsapp):
        """Get or create Gkach account for user
        P1 FIX: does NOT auto-commit — caller commits. Composable with other writes."""
        whatsapp = validate_whatsapp(whatsapp)

        account = UserGkach.query.filter_by(user_whatsapp=whatsapp).first()
        if not account:
            account = UserGkach(
                user_whatsapp=whatsapp,
                gkach_balance=0
            )
            db.session.add(account)
            db.session.flush()

        return account
    
    @staticmethod
    def get_balance(whatsapp):
        """Get Gkach balance with caching.

        DEFENSIVE GUARD (fixes "connected users can't load ADS"):
          - Called ONLY for logged-in users from inject_global_data / templates.
            validate_whatsapp OR redis OR missing UserGkach columns → any
            uncaught exception bubbles up into Jinja render → route's outer
            except catches it → EMPTY products=[] returned.
          - NEVER raises — always returns an int (default 0).
        """
        try:
            from app.services.redis_service import RedisService
            from app import redis_client

            # 1) Normalize whatsapp with lenient fallback (never raise)
            normalized = None
            try:
                from app.utils.validators import validate_whatsapp
                normalized = validate_whatsapp(whatsapp)
            except Exception:
                # validate_whatsapp refused the format — try a minimal
                # lenient cleanup ourselves instead of aborting.
                if whatsapp:
                    import re as _re
                    digits = _re.sub(r'[^\d+]', '', str(whatsapp))
                    if len(digits.replace('+', '')) >= 7:
                        normalized = digits if digits.startswith('+') else ('+' + digits)
            if not normalized:
                return 0

            redis_service = None
            try:
                redis_service = RedisService(redis_client)
            except Exception:
                redis_service = None

            # 2) Try cache first (ignore errors)
            if redis_service is not None:
                balance = None
                try:
                    balance = redis_service.get_gkach_balance(normalized)
                except Exception:
                    balance = None
                if balance is not None:
                    try:
                        return int(balance)
                    except (ValueError, TypeError):
                        pass

            # 3) Query database (ignore table/column errors)
            balance = 0
            try:
                from app.models.user_gkach import UserGkach
                account = UserGkach.query.filter_by(user_whatsapp=normalized).first()
                if account is not None:
                    raw = getattr(account, 'gkach_balance', 0)
                    balance = int(raw or 0)
            except Exception:
                balance = 0

            # 4) Cache for 5 minutes (ignore write errors)
            if redis_service is not None:
                try:
                    redis_service.set_gkach_balance(normalized, balance, timeout=300)
                except Exception:
                    pass

            return balance
        except Exception:
            return 0
    
    @staticmethod
    def _invalidate_balance_cache(whatsapp):
        """Helper: invalidate gkach cache after mutation (private, called after outer commit)"""
        try:
            from app.services.redis_service import RedisService
            from app import redis_client
            redis_service = RedisService(redis_client)
            redis_service.invalidate_gkach_balance(whatsapp)
        except Exception:
            pass

    @staticmethod
    def add_balance(whatsapp, amount, description='', transaction_type='credit', _commit=True):
        """
        Add Gkach to account
        Thread-safe with database locking.
        P1 FIX: _commit=False by default when used inside compositions.
        """
        whatsapp = validate_whatsapp(whatsapp)
        amount = validate_amount(amount, min_amount=1)

        account = db.session.query(UserGkach).filter_by(
            user_whatsapp=whatsapp
        ).with_for_update().first()

        if not account:
            GkachService.get_or_create_account(whatsapp)
            account = db.session.query(UserGkach).filter_by(
                user_whatsapp=whatsapp
            ).with_for_update().first()

        old_balance = account.gkach_balance
        account.gkach_balance += amount

        transaction = GkachTransaction(
            transaction_id=str(uuid.uuid4()),
            user_whatsapp=whatsapp,
            transaction_type=transaction_type,
            amount=amount,
            old_balance=old_balance,
            new_balance=account.gkach_balance,
            description=description,
            status='completed'
        )
        db.session.add(transaction)

        if _commit:
            db.session.commit()
            GkachService._invalidate_balance_cache(whatsapp)

        return account.gkach_balance

    @staticmethod
    def deduct_balance(whatsapp, amount, description='', transaction_type='debit', _commit=True):
        """
        Deduct Gkach from account
        Thread-safe with database locking.
        P1 FIX: _commit=False by default when used inside compositions.
        """
        whatsapp = validate_whatsapp(whatsapp)
        amount = validate_amount(amount, min_amount=1)

        account = db.session.query(UserGkach).filter_by(
            user_whatsapp=whatsapp
        ).with_for_update().first()

        if not account:
            raise ValidationError("Kont Gkach pa jwenn")

        if account.gkach_balance < amount:
            raise ValidationError(f"Balans ensifisan. Ou gen {account.gkach_balance} Gkach")

        old_balance = account.gkach_balance
        account.gkach_balance -= amount

        transaction = GkachTransaction(
            transaction_id=str(uuid.uuid4()),
            user_whatsapp=whatsapp,
            transaction_type=transaction_type,
            amount=amount,
            old_balance=old_balance,
            new_balance=account.gkach_balance,
            description=description,
            status='completed'
        )
        db.session.add(transaction)

        if _commit:
            db.session.commit()
            GkachService._invalidate_balance_cache(whatsapp)

        return account.gkach_balance

    @staticmethod
    def transfer(from_whatsapp, to_whatsapp, amount, description='', commission_rate=None):
        """
        Transfer Gkach between accounts — ATOMIC (P1 FIX single transaction).
        Optional commission_rate (Decimal 0-1): platform commission deducted from amount,
        so receiver gets amount*(1-commission_rate).
        """
        from_whatsapp = validate_whatsapp(from_whatsapp)
        to_whatsapp = validate_whatsapp(to_whatsapp)
        amount = validate_amount(amount, min_amount=1)

        if from_whatsapp == to_whatsapp:
            raise ValidationError("Pa ka transfere bay tèt ou")

        try:
            platform_whatsapp = '+509PLATFORM'
            commission_amount = 0
            if commission_rate is not None:
                from decimal import Decimal
                commission_amount = int(round(float(amount) * float(commission_rate)))
                if commission_amount < 0:
                    commission_amount = 0

            send_total = amount
            receive_amount = amount - commission_amount

            GkachService.deduct_balance(
                from_whatsapp,
                send_total,
                f"Transfer to {to_whatsapp}: {description}" + (f" (commission {commission_amount} GK)" if commission_amount else ""),
                'transfer_out',
                _commit=False
            )

            if receive_amount > 0:
                GkachService.add_balance(
                    to_whatsapp,
                    receive_amount,
                    f"Transfer from {from_whatsapp}: {description}" + (f" (after commission {commission_amount} GK)" if commission_amount else ""),
                    'transfer_in',
                    _commit=False
                )

            if commission_amount > 0:
                try:
                    GkachService.add_balance(
                        platform_whatsapp,
                        commission_amount,
                        f"Commission 2% on transfer {from_whatsapp}->{to_whatsapp}",
                        'commission',
                        _commit=False
                    )
                except Exception:
                    pass

            db.session.commit()
            GkachService._invalidate_balance_cache(from_whatsapp)
            GkachService._invalidate_balance_cache(to_whatsapp)
            if commission_amount > 0:
                GkachService._invalidate_balance_cache(platform_whatsapp)
            return True
        except Exception as e:
            db.session.rollback()
            raise ValidationError(f"Transfer failed: {str(e)}")
    
    @staticmethod
    def get_transactions(whatsapp, limit=50, offset=0):
        """Get user's transaction history"""
        whatsapp = validate_whatsapp(whatsapp)
        
        transactions = GkachTransaction.query.filter_by(
            user_whatsapp=whatsapp
        ).order_by(
            GkachTransaction.created_at.desc()
        ).limit(limit).offset(offset).all()
        
        return [t.to_dict() for t in transactions]
    
    @staticmethod
    def get_transaction_summary(whatsapp):
        """Get transaction summary"""
        whatsapp = validate_whatsapp(whatsapp)
        
        summary = db.session.query(
            GkachTransaction.transaction_type,
            func.count(GkachTransaction.id).label('count'),
            func.sum(GkachTransaction.amount).label('total')
        ).filter_by(
            user_whatsapp=whatsapp,
            status='completed'
        ).group_by(GkachTransaction.transaction_type).all()
        
        return {
            s.transaction_type: {
                'count': s.count,
                'total': s.total or 0
            }
            for s in summary
        }
    
    @staticmethod
    def process_reward(whatsapp, amount, reason=''):
        """Process reward (ad share, referral, etc.)"""
        return GkachService.add_balance(
            whatsapp,
            amount,
            reason,
            'reward'
        )
    
    @staticmethod
    def process_purchase(buyer_whatsapp, seller_whatsapp, amount, ad_id, delivery_id, donation_amount=0, donation_cause='general'):
        """
        Process purchase transaction with optional charitable donation
        Atomic: deduct from buyer, add to seller, process donation if any
        """
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)
        seller_whatsapp = validate_whatsapp(seller_whatsapp)
        amount = validate_amount(amount, min_amount=1)
        
        # Validate donation amount
        if donation_amount > 0:
            donation_amount = validate_amount(donation_amount, min_amount=1)
            total_to_deduct = amount + donation_amount
        else:
            total_to_deduct = amount
        
        try:
            # Deduct total (purchase + donation) from buyer
            GkachService.deduct_balance(
                buyer_whatsapp,
                total_to_deduct,
                f"Achte piblisite {ad_id}" + (f" + don {donation_amount} Gkach" if donation_amount > 0 else ""),
                'purchase'
            )
            
            # Add purchase amount to seller
            GkachService.add_balance(
                seller_whatsapp,
                amount,
                f"Vann piblisite {ad_id}",
                'sale'
            )
            
            # Process donation if any
            if donation_amount > 0:
                # Get or create charity account
                charity_whatsapp = '+509CHARITY'  # Compte caritatif dédié
                charity_account = UserGkach.query.filter_by(user_whatsapp=charity_whatsapp).first()
                if not charity_account:
                    # Create charity account if not exists
                    from app.models.user import User
                    charity_user = User.query.filter_by(whatsapp=charity_whatsapp).first()
                    if not charity_user:
                        charity_user = User(
                            whatsapp=charity_whatsapp,
                            pseudo='CharityFund',
                            name='Fonds Caritatif Glory2Yah',
                            auth_provider='whatsapp',
                            is_active=True
                        )
                        db.session.add(charity_user)
                        db.session.flush()
                    
                    charity_account = UserGkach(
                        user_id=charity_user.id,
                        user_whatsapp=charity_whatsapp,
                        gkach_balance=0
                    )
                    db.session.add(charity_account)
                    db.session.flush()
                
                # Add donation to charity account (use direct DB ops to avoid premature commit)
                charity_account = db.session.query(UserGkach).filter_by(
                    user_whatsapp=charity_whatsapp
                ).with_for_update().first()
                
                old_balance = charity_account.gkach_balance
                charity_account.gkach_balance += donation_amount
                
                # Log charity donation transaction
                charity_tx = GkachTransaction(
                    transaction_id=str(uuid.uuid4()),
                    user_whatsapp=charity_whatsapp,
                    transaction_type='donation',
                    amount=donation_amount,
                    old_balance=old_balance,
                    new_balance=charity_account.gkach_balance,
                    description=f"Don {donation_cause} from {buyer_whatsapp}",
                    status='completed'
                )
                db.session.add(charity_tx)
                
                # Record donation in CharityDonation model
                from app.models.charity import CharityDonation
                donation = CharityDonation(
                    donation_id=str(uuid.uuid4()),
                    donor_whatsapp=buyer_whatsapp,
                    delivery_id=delivery_id,
                    amount_gkach=donation_amount,
                    cause=donation_cause,
                    status='completed',
                    is_anonymous=False
                )
                db.session.add(donation)
            
            # Update transactions with related data
            buyer_tx = GkachTransaction.query.filter_by(
                user_whatsapp=buyer_whatsapp,
                transaction_type='purchase'
            ).order_by(GkachTransaction.created_at.desc()).first()
            
            if buyer_tx:
                buyer_tx.related_user = seller_whatsapp
                buyer_tx.ad_id = ad_id
                buyer_tx.delivery_id = delivery_id
            
            seller_tx = GkachTransaction.query.filter_by(
                user_whatsapp=seller_whatsapp,
                transaction_type='sale'
            ).order_by(GkachTransaction.created_at.desc()).first()
            
            if seller_tx:
                seller_tx.related_user = buyer_whatsapp
                seller_tx.ad_id = ad_id
                seller_tx.delivery_id = delivery_id
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise ValidationError(f"Tranzaksyon echwe: {str(e)}")

    @staticmethod
    def _is_ip_blocked(ip):
        """Return True if the given client IP is blocked by the Admin.

        Blocked IPs are stored as a comma/newline separated string in
        AdminSettings under the key 'blocked_ips' (managed from the admin panel).
        """
        return str(ip).strip() in GkachService.get_blocked_ips()

    @staticmethod
    def get_blocked_ips():
        """Return the currently blocked IPs as a list (deduplicated)."""
        try:
            from app.models.admin_settings import AdminSettings
            raw = (AdminSettings.get_setting('blocked_ips', '') or '')
            seen = set()
            result = []
            for item in raw.replace('\n', ',').split(','):
                ip = item.strip()
                if ip and ip not in seen:
                    seen.add(ip)
                    result.append(ip)
            return result
        except Exception:
            return []

    @staticmethod
    def set_blocked_ips(ips):
        """Persist the blocked-IP list into AdminSettings as 'blocked_ips'."""
        from app.models.admin_settings import AdminSettings
        clean = [str(x).strip() for x in ips if str(x).strip()]
        AdminSettings.set_setting('blocked_ips', '\n'.join(clean))
        return clean

    @staticmethod
    def track_batch_click(batch_id, referrer_whatsapp, clicker_whatsapp=None, dedup_key=None, clicker_ip=None, clicker_device=None):
        """Track a UNIQUE click on a shared batch and auto-credit the Admin reward.

        Rules:
          - Each click must come from a UNIQUE person: enforced with the
            BatchClick unique constraint on (batch_id, referrer, clicker).
          - Anti-fraud IP limit: at most GKACH_MAX_CLICKS_PER_IP unique clicks
            are accepted from the same IP for a given (batch, referrer).
          - Anti-fraud device limit: at most GKACH_MAX_CLICKS_PER_DEVICE unique
            clicks accepted from the same browser/device (signed cookie).
          - Admin can block an IP outright (stored in AdminSettings 'blocked_ips').
          - The referrer (the user who SHARED the ad link) is paid automatically
            by the platform/Admin: +GKACH_REWARD_AMOUNT (10) Gkach every
            GKACH_CLICKS_REQUIRED (100) UNIQUE clicks.
          - A user cannot earn from his own click (clicker == referrer is ignored).
        """
        from flask import current_app
        from app.models.batch import Batch
        from app.models.batch_click import BatchClick

        batch = Batch.query.filter_by(batch_id=batch_id).first()
        if not batch:
            return False

        # Blocked-IP check (set by Admin in AdminSettings 'blocked_ips')
        if clicker_ip and GkachService._is_ip_blocked(clicker_ip):
            return False

        # Guard: the clicker must not be the referrer (no self-reward)
        if clicker_whatsapp and referrer_whatsapp and str(clicker_whatsapp).strip() == str(referrer_whatsapp).strip():
            return False

        # Determine unique click count for this (batch, referrer)
        query = BatchClick.query.filter_by(
            batch_id=batch_id,
            referrer_whatsapp=referrer_whatsapp,
        )

        if clicker_whatsapp:
            # Only count this click if this exact person has NOT already clicked
            # this batch for this referrer (uniqueness per person).
            already_clicked = query.filter_by(
                clicker_whatsapp=clicker_whatsapp
            ).first()
            if already_clicked:
                return False

            # Anti-fraud IP limit: same IP cannot feed unlimited unique clickers
            if clicker_ip:
                max_per_ip = int(current_app.config.get('GKACH_MAX_CLICKS_PER_IP', 3) or 3)
                ip_clicks = BatchClick.query.filter_by(
                    batch_id=batch_id,
                    referrer_whatsapp=referrer_whatsapp,
                    clicker_ip=clicker_ip,
                ).count()
                if ip_clicks >= max_per_ip:
                    return False

            # Anti-fraud device limit: same browser/device cannot feed multiple icons
            if clicker_device:
                max_per_device = int(current_app.config.get('GKACH_MAX_CLICKS_PER_DEVICE', 1) or 1)
                device_clicks = BatchClick.query.filter_by(
                    batch_id=batch_id,
                    referrer_whatsapp=referrer_whatsapp,
                    clicker_device=clicker_device,
                ).count()
                if device_clicks >= max_per_device:
                    return False

            click = BatchClick(
                batch_id=batch_id,
                referrer_whatsapp=referrer_whatsapp,
                clicker_whatsapp=clicker_whatsapp,
                clicker_ip=clicker_ip,
                clicker_device=clicker_device,
            )
            db.session.add(click)
            # db.session.flush() to make the new row visible to the count below
            db.session.flush()

        # Total UNIQUE clicks earned by this referrer on this batch
        unique_clicks = query.count()

        batch.share_count = unique_clicks

        # Auto-credit by Admin/platform: 10 Gkach every 100 UNIQUE clicks
        required = int(current_app.config.get('GKACH_CLICKS_REQUIRED', 100) or 100)
        reward = int(current_app.config.get('GKACH_REWARD_AMOUNT', 10) or 10)

        if unique_clicks > 0 and unique_clicks % required == 0:
            GkachService.add_balance(
                referrer_whatsapp,
                reward,
                f"Rekonpans Admin: +{reward} Gkach pou {required} klik inik sou batch {batch_id}",
                'reward'
            )
            batch.click_rewards += reward

        db.session.commit()
        return True

