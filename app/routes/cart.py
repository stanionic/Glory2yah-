"""
Cart Routes Blueprint
Shopping cart management
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.services.cart_service import CartService, CartItem
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


@cart_bp.route('/add/<product_id>', methods=['GET', 'POST'])
@login_required
def add(product_id):
    """Add product to cart (supports both GET and POST, JSON for AJAX)"""    
    from app.utils.validators import validate_amount, ValidationError

    try:
        if request.method == 'POST':
            quantity = int(request.form.get('quantity', 1))
        else:
            quantity = 1
            
        CartService.add_to_cart(current_user.id, product_id, quantity)
        
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Content-Type') == 'application/x-www-form-urlencoded':
            return jsonify({'success': True})
            
        flash('Atik ajoute nan panier!', 'success')
        return redirect(url_for('cart.index'))
    except ValidationError as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(str(e), 'error')
        return redirect(url_for('main.index'))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Erè nan ajoute nan panier.'}), 500
        flash('Erè nan ajoute nan panier.', 'error')
        return redirect(url_for('main.index'))


@cart_bp.route('/update/<int:item_id>', methods=['POST'])
@login_required
def update(item_id):
    """Update cart item quantity"""    
    from app.utils.validators import validate_amount, ValidationError

    try:
        quantity = int(request.form.get('quantity', 1))
        CartService.update_quantity(current_user.id, item_id, quantity)
        return jsonify({'success': True})
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Cart update failed user={current_user.id} item={item_id}: {e}")
        return jsonify({'success': False, 'message': 'Erè nan mete ajou kantite atik la.'}), 400


@cart_bp.route('/remove/<int:item_id>', methods=['POST'])
@login_required
def remove(item_id):
    """Remove item from cart"""
    try:
        CartService.remove_item(current_user.id, item_id)
        return jsonify({'success': True})
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Cart remove failed user={current_user.id} item={item_id}: {e}")
        return jsonify({'success': False, 'message': 'Erè nan retire atik nan panier a.'}), 400


@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout process with optional charitable donation"""
    from app.models.charity import CharityCause
    
    items = CartService.get_user_cart(current_user.id)
    if not items:
        flash('Panier ou vid.', 'error')
        return redirect(url_for('main.index'))
    
    # Get active charity causes
    charity_causes = CharityCause.query.filter_by(is_active=True).all()
        
    if request.method == 'POST':
        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from app.services.delivery_service import DeliveryService
            from app.services.gkach_service import GkachService
            from app import db

            totals = CartService.calculate_totals(current_user.id)
            total_price = totals.get('subtotal', 0)

            donation_amount = int(request.form.get('donation_amount', 0) or 0)
            donation_cause = request.form.get('donation_cause', 'general')

            if donation_amount < 0:
                donation_amount = 0

            total_with_donation = total_price + donation_amount

            balance = GkachService.get_balance(current_user.whatsapp)
            if balance < total_with_donation:
                return jsonify({'success': False, 'error': f'Balans ensifisan. Ou bezwen {total_with_donation} Gkach men ou gen {balance} Gkach.'}), 400

            sellers = {}
            for item in items:
                ad = item.ad
                if ad.user_whatsapp not in sellers:
                    sellers[ad.user_whatsapp] = []
                sellers[ad.user_whatsapp].append(item)

            # P1 FIX: single transaction for ALL sellers (atomic multi-seller checkout)
            # P1 FIX: escrow_hold=True — funds to ESCROW account, NOT direct seller (fixes double charge contradiction)
            any_error = None
            try:
                _first_seller = list(sellers.keys())[0] if sellers else None
                donation_applied = False

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

                    delivery = DeliveryService.create_delivery(
                        buyer_whatsapp=current_user.whatsapp,
                        seller_whatsapp=seller_whatsapp,
                        cart_items=cart_data,
                        total_price=seller_total,
                        delivery_address='Pou negosye'
                    )

                    # Only one seller charges the donation (first seller only)
                    this_donation = 0
                    this_cause = donation_cause
                    if (donation_amount > 0) and (not donation_applied) and (seller_whatsapp == _first_seller):
                        this_donation = donation_amount
                        donation_applied = True

                    GkachService.process_purchase(
                        buyer_whatsapp=current_user.whatsapp,
                        seller_whatsapp=seller_whatsapp,
                        amount=seller_total,
                        ad_id=seller_items[0].product_id,
                        delivery_id=delivery.delivery_id,
                        donation_amount=this_donation,
                        donation_cause=this_cause,
                        escrow_hold=True
                    )

                CartService.clear_cart(current_user.id)
                db.session.commit()
                return jsonify({'success': True, 'donation': donation_amount > 0})
            except ValidationError as e:
                db.session.rollback()
                return jsonify({'success': False, 'error': str(e)}), 400
            except Exception as e:
                db.session.rollback()
                any_error = e
                current_app.logger.error(f"Cart AJAX checkout failed user={current_user.id}: {any_error}")
                return jsonify({'success': False, 'error': 'Erè pandan peyman panier la. Tanpri eseye ankò oswa kontakte admin.'}), 500

        # Regular form submission — P1 FIX: correct endpoint name my_deliveries
        flash('Kòmand voye bay vandè yo!', 'success')
        return redirect(url_for('delivery.my_deliveries'))
        
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
        charity_causes=charity_causes,
        current_user=current_user
    )


@cart_bp.route('/api/count')
@login_required
def api_count():
    """API endpoint for cart count (preferred internal path)"""
    try:
        totals = CartService.calculate_totals(current_user.id)
        return jsonify({'count': totals.get('count', 0)})
    except Exception:
        return jsonify({'count': 0})

# Frontend/backward-compat alias: expected path is /api/cart/count
@cart_bp.route('/api/cart/count')
@login_required
def api_cart_count():
    """API endpoint for cart count (compat alias for older frontend calls)"""
    return api_count()
