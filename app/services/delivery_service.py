"""
Delivery Service Layer
Business logic for delivery and negotiation
"""
from app import db
from app.models.ad import Ad
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.message import Message
from app.utils.validators import validate_whatsapp, ValidationError
from app.services.gkach_service import GkachService
import logging
import uuid
import json

logger = logging.getLogger(__name__)


class DeliveryService:
    """Service for Delivery operations"""
    
    @staticmethod
    def create_delivery(buyer_whatsapp, seller_whatsapp, ad_id=None,
                        cart_items=None, total_price=0, delivery_address='', commit=True):
        """Create a new delivery/negotiation process.
        P1 FIX (Audit #6d): cart_items now stored in normalized junction table
        `delivery_items` instead of a JSON string. Accepts either:
          - list of dicts: [{'ad_id':..., 'quantity':..., 'price_gkach':..., 'shipping_fee':...}]
          - list of CartItem objects

        ``commit=False`` only flushes, so a caller creating several orders (one per
        seller) can commit them together and never leave a half-created checkout.
        """
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)
        seller_whatsapp = validate_whatsapp(seller_whatsapp)
        if buyer_whatsapp == seller_whatsapp:
            raise ValidationError("Ou pa ka achte nan pwòp piblisite w")
        if isinstance(total_price, bool) or not isinstance(total_price, int) or total_price < 0:
            raise ValidationError("Pri total la pa valid")
        for item in cart_items or []:
            qty = item.quantity if hasattr(item, 'product_id') else (
                item.get('quantity', 1) if isinstance(item, dict) else 1)
            if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
                raise ValidationError("Kantite atik la pa valid")

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

        if commit:
            db.session.commit()
        else:
            db.session.flush()

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
    
    # ------------------------------------------------------------------
    # Escrow helpers. Every state change is a COMPARE-AND-SET on the status
    # column (UPDATE ... WHERE status = <expected>): only one of several racing
    # requests can win, so money is never charged / paid / refunded twice. This
    # works on PostgreSQL and SQLite alike and does not depend on row locks.
    # ------------------------------------------------------------------
    @staticmethod
    def _transition(delivery_id, from_statuses, to_status, **extra):
        values = dict(extra, status=to_status)
        n = Delivery.query.filter(
            Delivery.delivery_id == delivery_id,
            Delivery.status.in_(tuple(from_statuses)),
        ).update(values, synchronize_session=False)
        return n == 1

    @staticmethod
    def _items_by_ad(delivery_id):
        totals = {}
        for di in DeliveryItem.query.filter_by(delivery_id=delivery_id).all():
            totals[di.ad_id] = totals.get(di.ad_id, 0) + int(di.quantity or 0)
        return totals

    @staticmethod
    def _reserve_stock(delivery_id):
        """Atomically take the stock for this order; refuse if it is no longer there.
        ``Ad.quantity is None`` = legacy listing without a stock figure (unlimited)."""
        for ad_id, qty in DeliveryService._items_by_ad(delivery_id).items():
            ad = Ad.query.filter_by(ad_id=ad_id).first()
            if ad is None:
                raise ValidationError("Yon piblisite nan kòmand sa a pa egziste ankò")
            if ad.quantity is None:
                continue
            n = Ad.query.filter(Ad.ad_id == ad_id, Ad.quantity >= qty).update(
                {Ad.quantity: Ad.quantity - qty}, synchronize_session=False)
            if n != 1:
                raise ValidationError(f'Pa gen ase nan stok pou "{ad.title}"')

    @staticmethod
    def _release_stock(delivery_id):
        for ad_id, qty in DeliveryService._items_by_ad(delivery_id).items():
            Ad.query.filter(Ad.ad_id == ad_id, Ad.quantity.isnot(None)).update(
                {Ad.quantity: Ad.quantity + qty}, synchronize_session=False)

    @staticmethod
    def _after_money_commit(*whatsapps):
        """Best-effort cache refresh so balances/stock shown are not stale."""
        try:
            for w in whatsapps:
                GkachService._invalidate_balance_cache(w)
        except Exception:
            pass
        try:
            from app import redis_client
            from app.services.redis_service import RedisService
            RedisService(redis_client).invalidate_approved_ads()
        except Exception:
            pass

    @staticmethod
    def confirm_delivery(delivery_id, buyer_whatsapp, expected_total=None):
        """Buyer confirms the purchase terms and the funds are reserved (escrow).

        * only from ``awaiting_buyer_confirmation`` (the seller must have set the
          shipping cost first - the UI never offers it earlier);
        * ``expected_total`` (what the buyer saw on screen) must equal the real
          total, so a seller cannot raise the price right before the click;
        * status change + stock reservation + buyer debit are ONE transaction;
        * a racing second confirmation loses the compare-and-set and charges nothing.
        """
        delivery = DeliveryService.get_delivery(delivery_id)
        buyer_whatsapp = validate_whatsapp(buyer_whatsapp)

        if delivery.buyer_whatsapp != buyer_whatsapp:
            raise ValidationError("Se sèlman achtè a ki ka konfime")

        status = delivery.status
        if status in ('awaiting_delivery', 'completed', 'cancelled'):
            raise ValidationError("Livrezon sa a deja konfime, pa kapab re-konfime")
        if status not in ('awaiting_buyer_confirmation', 'escrow_held'):
            raise ValidationError("Vandè a poko mete frè livrezon an. Tann li fini negosye.")

        grand_total = (delivery.total_price or 0) + (delivery.delivery_cost or 0)
        if expected_total is not None:
            try:
                expected = int(expected_total)
            except (TypeError, ValueError):
                raise ValidationError("Total la pa valid")
            if expected != grand_total:
                raise ValidationError(
                    "Pri a chanje depi ou te wè l. Tcheke nouvo total la epi konfime ankò.")

        try:
            if not DeliveryService._transition(
                    delivery_id, (status,), 'awaiting_delivery', confirmed_at=db.func.now()):
                db.session.rollback()
                raise ValidationError("Livrezon sa a deja konfime, pa kapab re-konfime")
            DeliveryService._reserve_stock(delivery_id)
            # Legacy 'escrow_held' orders were already debited at checkout: skip the debit.
            if status != 'escrow_held' and grand_total > 0:
                GkachService.deduct_balance(
                    buyer_whatsapp,
                    grand_total,
                    f"Reserve peman livrezon {delivery_id} (en attente resepsyon)",
                    'purchase_hold',
                    _commit=False
                )
            db.session.commit()
        except ValidationError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            logger.exception("confirm_delivery failed delivery=%s", delivery_id)
            raise ValidationError("Erè nan konfime kòmand lan. Verifye balans ou epi eseye ankò.")

        DeliveryService._after_money_commit(buyer_whatsapp)
        db.session.expire_all()
        return DeliveryService.get_delivery(delivery_id)

    @staticmethod
    def mark_completed(delivery_id):
        """Buyer received the goods: release the reserved funds to the seller ONCE.

        The compare-and-set from ``awaiting_delivery`` happens BEFORE the credit, in
        the same transaction, so two racing requests cannot both pay the seller.
        """
        delivery = DeliveryService.get_delivery(delivery_id)
        if delivery.status != 'awaiting_delivery':
            raise ValidationError("Livrezon sa a pa ka konfime kòm resevwa")

        grand_total = (delivery.total_price or 0) + (delivery.delivery_cost or 0)
        seller = delivery.seller_whatsapp
        try:
            if not DeliveryService._transition(
                    delivery_id, ('awaiting_delivery',), 'completed', delivered_at=db.func.now()):
                db.session.rollback()
                raise ValidationError("Livrezon sa a pa ka konfime kòm resevwa")
            if grand_total > 0:
                GkachService.add_balance(
                    seller,
                    grand_total,
                    f"Peman final livrezon {delivery_id} (vantès resevwa konfime)",
                    'sale',
                    _commit=False
                )
            db.session.commit()
        except ValidationError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            logger.exception("mark_completed failed delivery=%s", delivery_id)
            raise ValidationError("Erè nan finalize peman. Eseye ankò.")

        DeliveryService._after_money_commit(seller)
        db.session.expire_all()
        return DeliveryService.get_delivery(delivery_id)

    @staticmethod
    def cancel_delivery(delivery_id, actor_whatsapp, is_admin=False):
        """Cancel an order.

        * before payment (negotiating / awaiting_buyer_confirmation): buyer, seller
          or admin; no money moves;
        * after payment (awaiting_delivery): ONLY the seller or an admin (the buyer
          cannot claw back an order the seller is preparing; that is a dispute for
          the admin). The buyer is refunded in full and the stock is restored;
        * completed / cancelled orders are final. Refund happens at most once.
        """
        delivery = DeliveryService.get_delivery(delivery_id)
        actor = validate_whatsapp(actor_whatsapp)
        is_buyer = actor == delivery.buyer_whatsapp
        is_seller = actor == delivery.seller_whatsapp
        status = delivery.status

        if status in ('negotiating', 'awaiting_buyer_confirmation'):
            allowed, funds_held, restock = (is_buyer or is_seller or is_admin), False, False
        elif status in ('awaiting_delivery', 'escrow_held'):
            allowed, funds_held, restock = (is_seller or is_admin), True, status == 'awaiting_delivery'
        else:
            raise ValidationError("Kòmand sa a pa ka anile ankò")
        if not allowed:
            raise ValidationError("Ou pa gen pèmisyon pou anile kòmand sa a")

        grand_total = (delivery.total_price or 0) + (delivery.delivery_cost or 0)
        buyer = delivery.buyer_whatsapp
        try:
            if not DeliveryService._transition(delivery_id, (status,), 'cancelled'):
                db.session.rollback()
                raise ValidationError("Kòmand sa a pa ka anile ankò")
            if restock:
                DeliveryService._release_stock(delivery_id)
            if funds_held and grand_total > 0:
                GkachService.add_balance(
                    buyer,
                    grand_total,
                    f"Rembousman livrezon {delivery_id} (kòmand anile)",
                    'refund',
                    _commit=False
                )
            db.session.commit()
        except ValidationError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            logger.exception("cancel_delivery failed delivery=%s", delivery_id)
            raise ValidationError("Erè nan anile kòmand lan. Eseye ankò.")

        DeliveryService._after_money_commit(buyer)
        db.session.expire_all()
        return DeliveryService.get_delivery(delivery_id)
