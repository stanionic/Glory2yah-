"""
Cart Routes Blueprint
Shopping cart management
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.services.cart_service import CartService
from app.utils.validators import ValidationError


cart_bp = Blueprint('cart', __name__)


@cart_bp.route('/')
@login_required
def index():
    """View cart items"""
    items = CartService.get_user_cart(current_user.id)
    totals = CartService.calculate_totals(current_user.id)
    
    return render_template(
        'cart/index.html',
        cart_items=items,
        subtotal=totals.get('subtotal', 0),
        current_user=current_user
    )


@cart_bp.route('/add/<product_id>', methods=['POST'])
@login_required
def add(product_id):
    """Add product to cart"""
    try:
        quantity = int(request.form.get('quantity', 1))
        CartService.add_to_cart(current_user.id, product_id, quantity)
        flash('Atik ajoute nan panier!', 'success')
        
        return redirect(url_for('cart.index'))
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('main.index'))
    except Exception as e:
        flash('Erè nan ajoute nan panier.', 'error')
        return redirect(url_for('main.index'))


@cart_bp.route('/update/<int:item_id>', methods=['POST'])
@login_required
def update(item_id):
    """Update cart item quantity"""
    try:
        quantity = int(request.form.get('quantity', 1))
        CartService.update_quantity(current_user.id, item_id, quantity)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@cart_bp.route('/remove/<int:item_id>', methods=['POST'])
@login_required
def remove(item_id):
    """Remove item from cart"""
    try:
        CartService.remove_item(current_user.id, item_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout process"""
    items = CartService.get_user_cart(current_user.id)
    if not items:
        flash('Panier ou vid.', 'error')
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                from app.services.delivery_service import DeliveryService
                from app.services.gkach_service import GkachService
                
                # Calculate total
                totals = CartService.calculate_totals(current_user.id)
                total_price = totals.get('subtotal', 0)
                
                # Check balance
                balance = GkachService.get_balance(current_user.whatsapp)
                if balance < total_price:
                    return jsonify({'success': False, 'error': 'Balans ensifisan'}), 400
                
                # Group items by seller
                sellers = {}
                for item in items:
                    ad = item.ad
                    if ad.user_whatsapp not in sellers:
                        sellers[ad.user_whatsapp] = []
                    sellers[ad.user_whatsapp].append(item)
                    
                # Create a delivery for each seller
                for seller_whatsapp, seller_items in sellers.items():
                    seller_total = sum(item.ad.price_gkach * item.quantity for item in seller_items)
                    cart_data = [
                        {
                            'ad_id': item.product_id,
                            'ad_title': item.ad.title,
                            'quantity': item.quantity,
                            'price': item.ad.price_gkach
                        } for item in seller_items
                    ]
                    
                    DeliveryService.create_delivery(
                        buyer_whatsapp=current_user.whatsapp,
                        seller_whatsapp=seller_whatsapp,
                        cart_items=cart_data,
                        total_price=seller_total,
                        delivery_address='Pou negosye'
                    )
                    
                # Clear cart after successful checkout
                CartService.clear_cart(current_user.id)
                
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        # Regular form submission
        flash('Kòmand voye bay vandè yo!', 'success')
        return redirect(url_for('delivery.list'))
        
    # GET request - show checkout page
    totals = CartService.calculate_totals(current_user.id)
    balance = 0
    try:
        from app.services.gkach_service import GkachService
        balance = GkachService.get_balance(current_user.whatsapp)
    except:
        pass
    
    return render_template(
        'cart/checkout.html',
        cart_items=items,
        subtotal=totals.get('subtotal', 0),
        balance=balance,
        current_user=current_user
    )


@cart_bp.route('/api/count')
@login_required
def api_count():
    """API endpoint for cart count"""
    try:
        totals = CartService.calculate_totals(current_user.id)
        return jsonify({'count': totals.get('count', 0)})
    except Exception as e:
        return jsonify({'count': 0})
