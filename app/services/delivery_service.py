"""
Delivery Service Layer
Business logic for delivery and negotiation
"""
from app import db
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
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
        """Create a new delivery/negotiation process.
        P1 FIX (Audit #6d): cart_items now stored in normalized junction table
        `delivery_items` instead of a JSON string. Accepts either:
          - list of dicts: [{'ad_id':..., 'quantity':..., 'price_gkach':..., 'shipping_fee':...}]
          - list of CartItem objects
        """
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)
        seller_whatsapp = validate_whatsapp(seller_whatsapp)
            
        delivery_id = str(uuid.uuid4())
        
        delivery = Delivery(
            delivery_id=delivery_id,
            ad_id=ad_id,
            buyer_whatsapp=buyer_whatsapp,
            seller_whatsapp=seller_whatsapp,
            total_price=total_price,
            delivery_address=delivery_address,
            status='negotiating'
        )
        
        db.session.add(delivery)
        db.session.flush()  # Ensure delivery_id is available for FK
        
        # Store cart items in normalized junction table
        if cart_items:
            for item in cart_items:
                if hasattr(item, 'product_id'):  # CartItem object
                    di = DeliveryItem(
                        delivery_id=delivery_id,
                        ad_id=item.product_id,
                        quantity=item.quantity,
                        price_gkach=0,
                        shipping_fee=item.shipping_fee or 0.0
                    )
                elif isinstance(item, dict):  # dict
                    di = DeliveryItem(
                        delivery_id=delivery_id,
                        ad_id=item.get('ad_id') or item.get('product_id'),
                        quantity=item.get('quantity', 1),
                        price_gkach=item.get('price_gkach', 0),
                        shipping_fee=item.get('shipping_fee', 0.0)
                    )
                else:
                    continue
                db.session.add(di)
        
        db.session.commit()
        
        return delivery
    
    @staticmethod
    def get_delivery_items(delivery_id):
        """Get normalized cart items for a delivery (Audit #6d)"""
        return DeliveryItem.query.filter_by(delivery_id=delivery_id).all()
    
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
        """Set delivery cost (seller action).
        P1 FIX V08: only allowed during negotiation / awaiting_buyer_confirmation.
        Status already past this phase (confirmed/delivered/completed) = BLOCKED.
        Prevents seller price tamper after buyer signed / paid."""
        delivery = DeliveryService.get_delivery(delivery_id)
        if delivery.status not in ('negotiating', 'awaiting_buyer_confirmation'):
            raise ValidationError(
                "Pri livrezon deja konfime pa achtè a, pa kapab modifye l ankò."
            )
        try:
            cost_int = int(cost)
            if cost_int < 0:
                raise ValueError("negative")
        except (TypeError, ValueError):
            raise ValidationError("Pri livrezon invalide, yo resevwa nonb antye ki pozitif sèlman")
        delivery.delivery_cost = cost_int
        delivery.status = 'awaiting_buyer_confirmation'
        db.session.commit()
        return delivery
    
    @staticmethod
    def confirm_delivery(delivery_id, buyer_whatsapp):
        """Buyer confirms the purchase terms.
        P1 FIX V08 (DOUBLE-PAY HOTFIX):
          - Buyer DEDUCTS grand_total ONCE here (reserved = virtual escrow)
          - Seller is NOT paid yet at this step (only after mark_completed below)
          - Prevents legacy deduct+credit bug that caused seller 2× payout on confirm + complete.
        Escrow_held status: reserved at checkout; skip deduct so it's not double-withdrawn.
        """
        from app.services.gkach_service import GkachService as _GS
        delivery = DeliveryService.get_delivery(delivery_id)
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)

        if delivery.buyer_whatsapp != buyer_whatsapp:
            raise ValidationError("Se sèlman achtè a ki ka konfime")

        if delivery.status in ('awaiting_delivery', 'completed', 'cancelled'):
            raise ValidationError("Livrezon sa a deja konfime, pa kapab re-konfime")

        grand_total = delivery.total_price + delivery.delivery_cost

        # Deduct buyer ONCE only here (reserve). Seller gets paid ONLY on mark_completed (not here).
        if getattr(delivery, 'status', '') != 'escrow_held':
            if grand_total > 0:
                _GS.deduct_balance(
                    buyer_whatsapp,
                    grand_total,
                    f"Reserve peman livrezon {delivery_id} (en attente resepsyon)",
                    'purchase_hold',
                    _commit=False
                )

        delivery.status = 'awaiting_delivery'
        delivery.confirmed_at = db.func.now()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise ValidationError(f"Erè nan konfime: {e}")

        return delivery

    @staticmethod
    def mark_completed(delivery_id):
        """Mark delivery as completed (buyer received goods).
        P1 FIX V08 (single payout): release buyer reserve → pay seller ONCE only here.
        Removes legacy "add_balance fallback" blind-fire (that always doubled payout
        because release_escrow method did not exist in GkachService → always excepted).
        Now: direct atomic add_balance + commit → ONE transfer, never double.
        """
        from app.services.gkach_service import GkachService as _GS
        delivery = DeliveryService.get_delivery(delivery_id)

        if delivery.status != 'awaiting_delivery':
            raise ValidationError("Livrezon sa a pa ka konfime kòm resevwa")

        grand_total = delivery.total_price + delivery.delivery_cost

        if grand_total > 0:
            _GS.add_balance(
                delivery.seller_whatsapp,
                grand_total,
                f"Peman final livrezon {delivery_id} (vantès resevwa konfime)",
                'sale',
                _commit=False
            )

        delivery.status = 'completed'
        delivery.delivered_at = db.func.now()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise ValidationError(f"Erè nan finalize peman: {e}")

        return delivery
