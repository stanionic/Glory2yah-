"""
Transaction logging module for Gkach transactions
Logs all Gkach transactions to database for audit trail and reporting
"""

import json
import uuid
from datetime import datetime

# Import models - handle both relative and absolute imports
try:
    from ..models import db, GkachTransaction
except (ImportError, ValueError):
    from models import db, GkachTransaction

# Import logger
try:
    from .logger import setup_logger
except (ImportError, ValueError):
    from src.logger import setup_logger

logger = setup_logger()

def log_gkach_transaction(user_whatsapp, transaction_type, amount, old_balance=None, new_balance=None, 
                          related_user=None, delivery_id=None, ad_id=None, description=None, 
                          status='completed', metadata=None):
    """
    Log a Gkach transaction to the database
    
    Args:
        user_whatsapp: WhatsApp number of user involved in transaction
        transaction_type: Type of transaction (purchase, payment_received, balance_add, etc.)
        amount: Amount of Gkach involved
        old_balance: User's balance before transaction
        new_balance: User's balance after transaction
        related_user: Other party in transaction (if applicable)
        delivery_id: Reference to delivery if applicable
        ad_id: Reference to ad if applicable
        description: Human readable description
        status: Transaction status (completed, pending, failed)
        metadata: Additional data as dict (will be converted to JSON)
    
    Returns:
        GkachTransaction object or None if error
    """
    try:
        transaction_id = str(uuid.uuid4())
        
        # Convert metadata to JSON if provided
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata)
        
        transaction = GkachTransaction(
            transaction_id=transaction_id,
            user_whatsapp=user_whatsapp,
            transaction_type=transaction_type,
            amount=amount,
            old_balance=old_balance,
            new_balance=new_balance,
            related_user=related_user,
            delivery_id=delivery_id,
            ad_id=ad_id,
            description=description,
            status=status,
            metadata=metadata_json,
            created_at=datetime.utcnow()
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        logger.info(f"Logged transaction: {transaction_id} - {transaction_type} for {user_whatsapp}")
        return transaction
        
    except Exception as e:
        logger.error(f"Error logging Gkach transaction: {str(e)}")
        db.session.rollback()
        return None


def log_purchase_transaction(buyer_whatsapp, seller_whatsapp, delivery_id, amount, 
                             buyer_old_balance, buyer_new_balance, ad_title=None, ad_id=None):
    """
    Log a purchase transaction (buyer pays for ad)
    
    Args:
        buyer_whatsapp: Buyer's WhatsApp number
        seller_whatsapp: Seller's WhatsApp number
        delivery_id: Delivery ID
        amount: Purchase amount
        buyer_old_balance: Buyer's balance before purchase
        buyer_new_balance: Buyer's balance after purchase
        ad_title: Title of ad purchased
        ad_id: ID of ad purchased
    
    Returns:
        GkachTransaction object
    """
    description = f"Achte piblisite pa {seller_whatsapp} pou {amount} Gkach"
    if ad_title:
        description = f"Achte '{ad_title}' pa {seller_whatsapp} pou {amount} Gkach"
    
    metadata = {
        'seller_whatsapp': seller_whatsapp,
        'delivery_id': delivery_id,
        'ad_title': ad_title
    }
    
    return log_gkach_transaction(
        user_whatsapp=buyer_whatsapp,
        transaction_type='purchase',
        amount=amount,
        old_balance=buyer_old_balance,
        new_balance=buyer_new_balance,
        related_user=seller_whatsapp,
        delivery_id=delivery_id,
        ad_id=ad_id,
        description=description,
        metadata=metadata
    )


def log_payment_received_transaction(seller_whatsapp, buyer_whatsapp, delivery_id, amount,
                                     seller_old_balance, seller_new_balance, ad_title=None, ad_id=None):
    """
    Log a payment received transaction (seller gets paid)
    
    Args:
        seller_whatsapp: Seller's WhatsApp number
        buyer_whatsapp: Buyer's WhatsApp number
        delivery_id: Delivery ID
        amount: Payment amount
        seller_old_balance: Seller's balance before payment
        seller_new_balance: Seller's balance after payment
        ad_title: Title of ad sold
        ad_id: ID of ad sold
    
    Returns:
        GkachTransaction object
    """
    description = f"Peman resevwa pou vann piblisite bay {buyer_whatsapp} - {amount} Gkach"
    if ad_title:
        description = f"Peman pou vann '{ad_title}' bay {buyer_whatsapp} - {amount} Gkach"
    
    metadata = {
        'buyer_whatsapp': buyer_whatsapp,
        'delivery_id': delivery_id,
        'ad_title': ad_title
    }
    
    return log_gkach_transaction(
        user_whatsapp=seller_whatsapp,
        transaction_type='payment_received',
        amount=amount,
        old_balance=seller_old_balance,
        new_balance=seller_new_balance,
        related_user=buyer_whatsapp,
        delivery_id=delivery_id,
        ad_id=ad_id,
        description=description,
        metadata=metadata
    )


def log_balance_addition(user_whatsapp, amount, old_balance, new_balance, reason='manual_add'):
    """
    Log a balance addition (admin adds Gkach to user)
    
    Args:
        user_whatsapp: User's WhatsApp number
        amount: Amount added
        old_balance: Balance before addition
        new_balance: Balance after addition
        reason: Reason for addition (default: manual_add)
    
    Returns:
        GkachTransaction object
    """
    description = f"Administratè ajoute {amount} Gkach - {reason}"
    metadata = {'reason': reason}
    
    return log_gkach_transaction(
        user_whatsapp=user_whatsapp,
        transaction_type='balance_add',
        amount=amount,
        old_balance=old_balance,
        new_balance=new_balance,
        description=description,
        metadata=metadata
    )


def log_balance_edit(user_whatsapp, amount, old_balance, new_balance, reason='manual_edit'):
    """
    Log a balance edit (admin edits user's Gkach balance)
    
    Args:
        user_whatsapp: User's WhatsApp number
        amount: New balance amount
        old_balance: Balance before edit
        new_balance: Balance after edit
        reason: Reason for edit
    
    Returns:
        GkachTransaction object
    """
    change = new_balance - old_balance
    description = f"Administratè modifye balans - {change:+d} Gkach (Te gen: {old_balance}, Kounye a: {new_balance})"
    metadata = {'reason': reason, 'old_balance': old_balance, 'new_balance': new_balance}
    
    return log_gkach_transaction(
        user_whatsapp=user_whatsapp,
        transaction_type='balance_edit',
        amount=abs(change),
        old_balance=old_balance,
        new_balance=new_balance,
        description=description,
        metadata=metadata
    )


def log_gkach_request_approved(user_whatsapp, amount, old_balance, new_balance, request_id):
    """
    Log when a Gkach request is approved
    
    Args:
        user_whatsapp: User's WhatsApp number
        amount: Amount approved
        old_balance: Balance before approval
        new_balance: Balance after approval
        request_id: ID of the Gkach request
    
    Returns:
        GkachTransaction object
    """
    description = f"Demann Gkach apwouve - {amount} Gkach ajoute"
    metadata = {'request_id': request_id}
    
    return log_gkach_transaction(
        user_whatsapp=user_whatsapp,
        transaction_type='gkach_request_approved',
        amount=amount,
        old_balance=old_balance,
        new_balance=new_balance,
        description=description,
        metadata=metadata
    )


def get_user_transactions(user_whatsapp, limit=50, offset=0, transaction_type=None):
    """
    Get all transactions for a user
    
    Args:
        user_whatsapp: User's WhatsApp number
        limit: Number of transactions to return
        offset: Number of transactions to skip
        transaction_type: Filter by transaction type (optional)
    
    Returns:
        List of GkachTransaction objects
    """
    try:
        query = GkachTransaction.query.filter_by(user_whatsapp=user_whatsapp)
        
        if transaction_type:
            query = query.filter_by(transaction_type=transaction_type)
        
        transactions = query.order_by(GkachTransaction.created_at.desc()).limit(limit).offset(offset).all()
        return transactions
        
    except Exception as e:
        logger.error(f"Error retrieving transactions for {user_whatsapp}: {str(e)}")
        return []


def get_delivery_transactions(delivery_id):
    """
    Get all transactions related to a delivery
    
    Args:
        delivery_id: Delivery ID
    
    Returns:
        List of GkachTransaction objects
    """
    try:
        transactions = GkachTransaction.query.filter_by(delivery_id=delivery_id).order_by(
            GkachTransaction.created_at.asc()
        ).all()
        return transactions
        
    except Exception as e:
        logger.error(f"Error retrieving transactions for delivery {delivery_id}: {str(e)}")
        return []


def get_all_transactions(limit=100, offset=0, transaction_type=None, status=None):
    """
    Get all transactions (admin view)
    
    Args:
        limit: Number of transactions to return
        offset: Number of transactions to skip
        transaction_type: Filter by transaction type (optional)
        status: Filter by transaction status (optional)
    
    Returns:
        List of GkachTransaction objects
    """
    try:
        query = GkachTransaction.query
        
        if transaction_type:
            query = query.filter_by(transaction_type=transaction_type)
        
        if status:
            query = query.filter_by(status=status)
        
        transactions = query.order_by(GkachTransaction.created_at.desc()).limit(limit).offset(offset).all()
        return transactions
        
    except Exception as e:
        logger.error(f"Error retrieving all transactions: {str(e)}")
        return []


def get_transaction_summary(start_date=None, end_date=None):
    """
    Get summary statistics of transactions
    
    Args:
        start_date: Start date for summary (optional)
        end_date: End date for summary (optional)
    
    Returns:
        Dictionary with transaction statistics
    """
    try:
        query = GkachTransaction.query
        
        if start_date:
            query = query.filter(GkachTransaction.created_at >= start_date)
        
        if end_date:
            query = query.filter(GkachTransaction.created_at <= end_date)
        
        total_transactions = query.count()
        
        # Group by transaction type
        by_type = db.session.query(
            GkachTransaction.transaction_type,
            db.func.count(GkachTransaction.id),
            db.func.sum(GkachTransaction.amount)
        ).filter(query).group_by(GkachTransaction.transaction_type).all()
        
        summary = {
            'total_transactions': total_transactions,
            'by_type': {
                item[0]: {
                    'count': item[1],
                    'total_amount': item[2]
                } for item in by_type
            }
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generating transaction summary: {str(e)}")
        return {}
