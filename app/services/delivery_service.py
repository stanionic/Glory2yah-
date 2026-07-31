"""
Delivery Service Layer
Business logic for delivery and negotiation
"""
from app import db
from app.models.delivery import Delivery
from app.models.message import Message
from app.utils.validators import validate_whatsapp, ValidationError
from app.services.gkach_service import GkachService
import uuid
import json


class DeliveryService:
    """Service for Delivery operations"""
    
    @staticmethod
    def create_delivery(buyer_whatsapp, seller_whatsapp, ad_id=None, 
                        cart_items=None, total_price=0, delivery_address=''):
        """Create a new delivery/negotiation process"""
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)
        seller_whatsapp = validate_whatsapp(seller_whatsapp)
        
        # Format cart items to JSON if list
        if isinstance(cart_items, list):
            cart_items = json.dumps(cart_items)
            
        delivery_id = str(uuid.uuid4())
        
        delivery = Delivery(
            delivery_id=delivery_id,
            ad_id=ad_id,
            buyer_whatsapp=buyer_whatsapp,
            seller_whatsapp=seller_whatsapp,
            total_price=total_price,
            cart_items=cart_items,
            delivery_address=delivery_address,
            status='negotiating'
        )
        
        db.session.add(delivery)
        db.session.commit()
        
        return delivery
    
    @staticmethod
    def get_delivery(delivery_id):
        """Get delivery by ID"""
        delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
        if not delivery:
            raise ValidationError("Livrezon pa jwenn")
        return delivery
    
    @staticmethod
    def update_status(delivery_id, status):
        """Update delivery status"""
        delivery = DeliveryService.get_delivery(delivery_id)
        delivery.status = status
        db.session.commit()
        return delivery
    
    @staticmethod
    def add_message(delivery_id, sender_whatsapp, message_text):
        """Add chat message to delivery"""
        delivery = DeliveryService.get_delivery(delivery_id)
        sender_whatsapp = validate_whatsapp(sender_whatsapp)
        
        msg = Message(
            delivery_id=delivery_id,
            sender_whatsapp=sender_whatsapp,
            message=message_text
        )
        db.session.add(msg)
        db.session.commit()
        return msg
    
    @staticmethod
    def get_messages(delivery_id):
        """Get all messages for delivery"""
        return Message.query.filter_by(
            delivery_id=delivery_id
        ).order_by(Message.created_at.asc()).all()
    
    @staticmethod
    def set_delivery_cost(delivery_id, cost):
        """Set delivery cost (seller action)"""
        delivery = DeliveryService.get_delivery(delivery_id)
        delivery.delivery_cost = int(cost)
        delivery.status = 'awaiting_buyer_confirmation'
        db.session.commit()
        return delivery
    
    @staticmethod
    def confirm_delivery(delivery_id, buyer_whatsapp):
        """Buyer confirms the purchase terms (not final pay — escrow already held at checkout per P1 FIX V07)"""
        from app.services.gkach_service import GkachService as _GS
        delivery = DeliveryService.get_delivery(delivery_id)
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)

        if delivery.buyer_whatsapp != buyer_whatsapp:
            raise ValidationError("Se sèlman achtè a ki ka konfime")

        grand_total = delivery.total_price + delivery.delivery_cost

        # P1 FIX V07: if delivery is paid via escrow_hold at checkout, status starts at 'escrow_held'
        # Else legacy path (direct manual delivery): deduct + pay now (old fallback for mixed data).
        if getattr(delivery, 'status', '') != 'escrow_held':
            _GS.deduct_balance(
                buyer_whatsapp,
                grand_total,
                f"Payment for delivery {delivery_id}",
                'purchase'
            )
            _GS.add_balance(
                delivery.seller_whatsapp,
                grand_total,
                f"Payment received for delivery {delivery_id}",
                'sale'
            )

        delivery.status = 'awaiting_delivery'
        delivery.confirmed_at = db.func.now()
        db.session.commit()

        return delivery

    @staticmethod
    def mark_completed(delivery_id):
        """Mark delivery as completed — P1 FIX V07: release escrow hold + pay seller (commission already reserved)"""
        from app.services.gkach_service import GkachService as _GS
        delivery = DeliveryService.get_delivery(delivery_id)

        if delivery.status != 'awaiting_delivery':
            raise ValidationError("Livrezon sa a pa ka konfime kòm resevwa")

        grand_total = delivery.total_price + delivery.delivery_cost

        try:
            _GS.release_escrow(delivery.delivery_id, delivery.seller_whatsapp)
        except Exception as exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            # Fallback: if escrow record missing, direct pay (mixed legacy datasets)
            _GS.add_balance(
                delivery.seller_whatsapp,
                grand_total,
                f"Payment received for delivery {delivery_id} (direct fallback)",
                'sale'
            )

        delivery.status = 'completed'
        delivery.delivered_at = db.func.now()
        db.session.commit()

        return delivery
