from models import db, Message, Delivery
from datetime import datetime
import json

def send_message(delivery_id, sender_whatsapp, message):
    """
    Send a message between buyer and seller for a delivery.
    """
    # Validate delivery exists
    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if not delivery:
        raise ValueError("Delivery not found")

    # Validate sender is either buyer or seller
    if sender_whatsapp not in [delivery.buyer_whatsapp, delivery.seller_whatsapp]:
        raise ValueError("Unauthorized sender")

    # Create message record
    new_message = Message(
        delivery_id=delivery_id,
        sender_whatsapp=sender_whatsapp,
        message=message.strip(),
        created_at=datetime.utcnow()
    )

    db.session.add(new_message)
    db.session.commit()

    return new_message

def get_messages(delivery_id, user_whatsapp):
    """
    Get all messages for a delivery, but only if user is buyer or seller.
    """
    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if not delivery:
        raise ValueError("Delivery not found")

    if user_whatsapp not in [delivery.buyer_whatsapp, delivery.seller_whatsapp]:
        raise ValueError("Unauthorized access")

    messages = Message.query.filter_by(delivery_id=delivery_id).order_by(Message.created_at).all()

    return [{
        'id': msg.id,
        'sender_whatsapp': msg.sender_whatsapp,
        'message': msg.message,
        'created_at': msg.created_at.isoformat(),
        'is_mine': msg.sender_whatsapp == user_whatsapp
    } for msg in messages]

def get_delivery_participants(delivery_id):
    """
    Get buyer and seller WhatsApp numbers for a delivery.
    """
    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if not delivery:
        raise ValueError("Delivery not found")

    return {
        'buyer_whatsapp': delivery.buyer_whatsapp,
        'seller_whatsapp': delivery.seller_whatsapp
    }
