"""
Cart Service Layer
Business logic for shopping cart operations
"""
from app import db
from app.models.cart import CartItem
from app.models.ad import Ad
from app.utils.validators import ValidationError


class CartService:
    """Service for Cart operations"""
    
    MAX_LINE_QUANTITY = 1000

    # ----------------------------------------------------------- validation
    @staticmethod
    def parse_quantity(raw):
        """Strict integer parsing: 'abc', '1.5', '1e3', 'NaN', '' and bools are refused."""
        if isinstance(raw, bool):
            raise ValidationError("Kantite dwe yon nonb antye")
        if isinstance(raw, int):
            return raw
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            raise ValidationError("Kantite dwe yon nonb antye")

    @staticmethod
    def _same_person(a, b):
        digits = lambda v: ''.join(c for c in str(v or '') if c.isdigit())
        return bool(digits(a)) and digits(a) == digits(b)

    @staticmethod
    def assert_purchasable(ad, user):
        """A listing can be bought only if it is a live SELL ad owned by someone else."""
        if ad is None:
            raise ValidationError("Piblisite pa jwenn")
        if ad.ad_type != 'sell' or ad.admin_status != 'approved' or (ad.price_gkach or 0) <= 0:
            raise ValidationError("Piblisite sa a pa disponib pou vant")
        if user is not None and CartService._same_person(ad.user_whatsapp, user.whatsapp):
            raise ValidationError("Ou pa ka achte pwòp piblisite w")

    @staticmethod
    def check_stock(ad, quantity):
        """``ad.quantity`` None = legacy listing with no stock figure (unlimited)."""
        if quantity < 1:
            raise ValidationError("Kantite dwe omwen 1")
        if quantity > CartService.MAX_LINE_QUANTITY:
            raise ValidationError(f"Kantite pa ka depase {CartService.MAX_LINE_QUANTITY}")
        if ad.quantity is not None and quantity > ad.quantity:
            raise ValidationError(f"Pa gen ase nan stok (rete {max(ad.quantity, 0)})")

    # ---------------------------------------------------------------- cart
    @staticmethod
    def add_to_cart(user_id, product_id, quantity=1):
        """Add item to user's cart (validated: live sell ad, not own, within stock)."""
        from app.models.user import User
        quantity = CartService.parse_quantity(quantity)
        if quantity < 1:
            raise ValidationError("Kantite dwe omwen 1")
        ad = Ad.query.filter_by(ad_id=product_id).first()
        CartService.assert_purchasable(ad, db.session.get(User, user_id))

        item = CartItem.query.filter_by(
            user_id=user_id,
            product_id=product_id,
            negotiation_status='cart'
        ).first()
        CartService.check_stock(ad, (item.quantity if item else 0) + quantity)

        if item:
            item.quantity += quantity
        else:
            item = CartItem(
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                negotiation_status='cart'
            )
            db.session.add(item)

        db.session.commit()
        return item

    @staticmethod
    def get_user_cart(user_id):
        """Get user's active cart items"""
        return CartItem.query.filter_by(
            user_id=user_id,
            negotiation_status='cart'
        ).all()
    
    @staticmethod
    def update_quantity(user_id, item_id, quantity):
        """Update quantity of an OPEN cart line (lines already in negotiation are frozen)."""
        quantity = CartService.parse_quantity(quantity)
        item = CartItem.query.filter_by(id=item_id, user_id=user_id,
                                        negotiation_status='cart').first()
        if not item:
            raise ValidationError("Atik pa jwenn nan panier")

        if quantity <= 0:
            db.session.delete(item)
        else:
            ad = Ad.query.filter_by(ad_id=item.product_id).first()
            if ad is None:
                raise ValidationError("Piblisite pa jwenn")
            CartService.check_stock(ad, quantity)
            item.quantity = quantity

        db.session.commit()
        return True

    @staticmethod
    def remove_item(user_id, item_id):
        """Remove item from cart"""
        item = CartItem.query.filter_by(id=item_id, user_id=user_id).first()
        if item:
            db.session.delete(item)
            db.session.commit()
        return True
    
    @staticmethod
    def clear_cart(user_id, commit=True):
        """Clear all items from cart"""
        CartItem.query.filter_by(
            user_id=user_id,
            negotiation_status='cart'
        ).delete()
        if commit:
            db.session.commit()
        return True
    
    @staticmethod
    def calculate_totals(user_id):
        """Calculate total product price and shipping.

        DEFENSIVE GUARD (fixes "connected users can't load ADS"):
          - Called ONLY for logged-in users from inject_global_data context
            processor. Any uncaught exception (missing cart_items columns, bad
            DB state, broken FK) would bubble up → template render crashes →
            route's outer except returns EMPTY ads list.
          - NEVER raises — always returns a well-formed totals dict with
            count/subtotal defaulted to 0.
        """
        _empty = {
            'subtotal': 0,
            'total_products': 0,
            'total_shipping': 0,
            'grand_total': 0,
            'count': 0,
        }
        try:
            items = CartService.get_user_cart(user_id) or []

            total_products = 0
            total_shipping = 0
            qty_count = 0

            for item in items:
                try:
                    ad = Ad.query.filter_by(ad_id=getattr(item, 'product_id', None)).first()
                    if ad:
                        qty = int(getattr(item, 'quantity', 1) or 1)
                        total_products += int(getattr(ad, 'price_gkach', 0) or 0) * qty
                        qty_count += qty
                    ship_fee = getattr(item, 'shipping_fee', None)
                    if ship_fee is not None:
                        try:
                            total_shipping += float(ship_fee)
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    # Skip a single problematic cart row — never abort the whole list
                    continue

            return {
                'subtotal': total_products,
                'total_products': total_products,
                'total_shipping': int(total_shipping),
                'grand_total': total_products + int(total_shipping),
                'count': qty_count,
            }
        except Exception:
            return dict(_empty)
