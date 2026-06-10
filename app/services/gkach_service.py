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
        """Get or create Gkach account for user"""
        whatsapp = validate_whatsapp(whatsapp)
        
        account = UserGkach.query.filter_by(user_whatsapp=whatsapp).first()
        if not account:
            account = UserGkach(
                user_whatsapp=whatsapp,
                gkach_balance=0
            )
            db.session.add(account)
            db.session.commit()
        
        return account
    
    @staticmethod
    def get_balance(whatsapp):
        """Get Gkach balance with caching"""
        from app.services.redis_service import RedisService
        from app import redis_client
        
        whatsapp = validate_whatsapp(whatsapp)
        redis_service = RedisService(redis_client)
        
        # Try cache first
        balance = redis_service.get_gkach_balance(whatsapp)
        if balance is not None:
            return balance
        
        # Query database
        account = UserGkach.query.filter_by(user_whatsapp=whatsapp).first()
        balance = account.gkach_balance if account else 0
        
        # Cache for 5 minutes
        redis_service.set_gkach_balance(whatsapp, balance, timeout=300)
        
        return balance
    
    @staticmethod
    def add_balance(whatsapp, amount, description='', transaction_type='credit'):
        """
        Add Gkach to account
        Thread-safe with database locking
        """
        whatsapp = validate_whatsapp(whatsapp)
        amount = validate_amount(amount, min_amount=1)
        
        # Use database-level locking
        account = db.session.query(UserGkach).filter_by(
            user_whatsapp=whatsapp
        ).with_for_update().first()
        
        if not account:
            account = GkachService.get_or_create_account(whatsapp)
            account = db.session.query(UserGkach).filter_by(
                user_whatsapp=whatsapp
            ).with_for_update().first()
        
        old_balance = account.gkach_balance
        account.gkach_balance += amount
        
        # Log transaction
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
        db.session.commit()
        
        # Invalidate cache
        from app.services.redis_service import RedisService
        from app import redis_client
        redis_service = RedisService(redis_client)
        redis_service.invalidate_gkach_balance(whatsapp)
        
        return account.gkach_balance
    
    @staticmethod
    def deduct_balance(whatsapp, amount, description='', transaction_type='debit'):
        """
        Deduct Gkach from account
        Thread-safe with database locking
        """
        whatsapp = validate_whatsapp(whatsapp)
        amount = validate_amount(amount, min_amount=1)
        
        # Use database-level locking
        account = db.session.query(UserGkach).filter_by(
            user_whatsapp=whatsapp
        ).with_for_update().first()
        
        if not account:
            raise ValidationError("Kont Gkach pa jwenn")
        
        if account.gkach_balance < amount:
            raise ValidationError(f"Balans ensifisan. Ou gen {account.gkach_balance} Gkach")
        
        old_balance = account.gkach_balance
        account.gkach_balance -= amount
        
        # Log transaction
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
        db.session.commit()
        
        # Invalidate cache
        from app.services.redis_service import RedisService
        from app import redis_client
        redis_service = RedisService(redis_client)
        redis_service.invalidate_gkach_balance(whatsapp)
        
        return account.gkach_balance
    
    @staticmethod
    def transfer(from_whatsapp, to_whatsapp, amount, description=''):
        """
        Transfer Gkach between accounts
        Atomic transaction
        """
        from_whatsapp = validate_whatsapp(from_whatsapp)
        to_whatsapp = validate_whatsapp(to_whatsapp)
        amount = validate_amount(amount, min_amount=1)
        
        if from_whatsapp == to_whatsapp:
            raise ValidationError("Pa ka transfere bay tèt ou")
        
        try:
            # Deduct from sender
            GkachService.deduct_balance(
                from_whatsapp,
                amount,
                f"Transfer to {to_whatsapp}: {description}",
                'transfer_out'
            )
            
            # Add to receiver
            GkachService.add_balance(
                to_whatsapp,
                amount,
                f"Transfer from {from_whatsapp}: {description}",
                'transfer_in'
            )
            
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
    def process_purchase(buyer_whatsapp, seller_whatsapp, amount, ad_id, delivery_id):
        """
        Process purchase transaction
        Atomic: deduct from buyer, add to seller
        """
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)
        seller_whatsapp = validate_whatsapp(seller_whatsapp)
        amount = validate_amount(amount, min_amount=1)
        
        try:
            # Deduct from buyer
            GkachService.deduct_balance(
                buyer_whatsapp,
                amount,
                f"Achte piblisite {ad_id}",
                'purchase'
            )
            
            # Add to seller
            GkachService.add_balance(
                seller_whatsapp,
                amount,
                f"Vann piblisite {ad_id}",
                'sale'
            )
            
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
    def track_batch_click(batch_id, referrer_whatsapp):
        """Track click on shared batch and reward if milestone reached"""
        from app.models.batch import Batch
        from app.models.user import User
        
        batch = Batch.query.filter_by(batch_id=batch_id).first()
        if not batch:
            return False
            
        batch.share_count += 1
        
        # Reward logic: 10 Gkach per 100 clicks
        if batch.share_count % 100 == 0:
            reward_amount = 10
            GkachService.add_balance(
                referrer_whatsapp,
                reward_amount,
                f"Reward for 100 clicks on batch {batch_id}",
                'reward'
            )
            batch.click_rewards += reward_amount
            
        db.session.commit()
        return True
