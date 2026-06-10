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
    
    @staticmethod
    def add_to_cart(user_id, product_id, quantity=1):
        """Add item to user's cart"""
        ad = Ad.query.filter_by(ad_id=product_id).first()
        if not ad:
            raise ValidationError("Piblisite pa jwenn")
            
        # Check if already in cart
        item = CartItem.query.filter_by(
            user_id=user_id,
            product_id=product_id,
            negotiation_status='cart'
        ).first()
        
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
        """Update item quantity in cart"""
        item = CartItem.query.filter_by(id=item_id, user_id=user_id).first()
        if not item:
            raise ValidationError("Atik pa jwenn nan panier")
            
        if quantity <= 0:
            db.session.delete(item)
        else:
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
    def clear_cart(user_id):
        """Clear all items from cart"""
        CartItem.query.filter_by(
            user_id=user_id,
            negotiation_status='cart'
        ).delete()
        db.session.commit()
        return True
    
    @staticmethod
    def calculate_totals(user_id):
        """Calculate total product price and shipping"""
        items = CartService.get_user_cart(user_id)
        
        total_products = 0
        total_shipping = 0
        
        for item in items:
            ad = Ad.query.filter_by(ad_id=item.product_id).first()
            if ad:
                total_products += ad.price_gkach * item.quantity
                total_shipping += item.shipping_fee
                
        return {
            'total_products': total_products,
            'total_shipping': total_shipping,
            'grand_total': total_products + total_shipping,
            'count': sum(item.quantity for item in items)
        }
