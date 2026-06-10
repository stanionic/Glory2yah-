"""
Delivery Routes Blueprint
Delivery tracking and negotiation
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.services.delivery_service import DeliveryService
from app.utils.validators import ValidationError


delivery_bp = Blueprint('delivery', __name__)


@delivery_bp.route('/my-deliveries')
@login_required
def my_deliveries():
    """View user's deliveries (buyer or seller)"""
    from app.models.delivery import Delivery
    from sqlalchemy import or_
    
    # Get deliveries where user is buyer or seller
    deliveries = Delivery.query.filter(
        or_(
            Delivery.buyer_whatsapp == current_user.whatsapp,
            Delivery.seller_whatsapp == current_user.whatsapp
        )
    ).order_by(Delivery.created_at.desc()).all()
    
    return render_template(
        'delivery/list.html',
        deliveries=deliveries,
        current_user=current_user
    )


@delivery_bp.route('/view/<delivery_id>')
@login_required
def view(delivery_id):
    """View specific delivery detail and chat"""
    try:
        delivery = DeliveryService.get_delivery(delivery_id)
        
        # Check permission
        if current_user.whatsapp not in [delivery.buyer_whatsapp, delivery.seller_whatsapp] and not current_user.is_admin:
            flash('Ou pa gen pèmisyon pou wè livrezon sa a.', 'error')
            return redirect(url_for('delivery.my_deliveries'))
            
        messages = DeliveryService.get_messages(delivery_id)
        
        return render_template(
            'delivery/detail.html',
            delivery=delivery,
            messages=messages,
            current_user=current_user
        )
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('delivery.my_deliveries'))


@delivery_bp.route('/set-cost/<delivery_id>', methods=['POST'])
@login_required
def set_cost(delivery_id):
    """Seller sets the delivery cost"""
    try:
        delivery = DeliveryService.get_delivery(delivery_id)
        
        if current_user.whatsapp != delivery.seller_whatsapp:
            flash('Se sèlman vandè a ki ka mete pri livrezon an.', 'error')
            return redirect(url_for('delivery.view', delivery_id=delivery_id))
            
        cost = int(request.form.get('cost', 0))
        DeliveryService.set_delivery_cost(delivery_id, cost)
        
        flash('Pri livrezon mete ajou!', 'success')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))
    except Exception as e:
        flash('Erè nan mete pri livrezon.', 'error')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))


@delivery_bp.route('/confirm/<delivery_id>', methods=['POST'])
@login_required
def confirm(delivery_id):
    """Buyer confirms and pays"""
    try:
        DeliveryService.confirm_delivery(delivery_id, current_user.whatsapp)
        flash('Peman konfime! Vandè a ap prepare livrezon ou an.', 'success')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))
    except Exception as e:
        flash('Erè nan konfime livrezon.', 'error')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))


@delivery_bp.route('/complete/<delivery_id>', methods=['POST'])
@login_required
def complete(delivery_id):
    """Buyer marks delivery as completed (received)"""
    try:
        delivery = DeliveryService.get_delivery(delivery_id)
        
        if current_user.whatsapp != delivery.buyer_whatsapp:
            flash('Se sèlman achtè a ki ka konfime resepsyon.', 'error')
            return redirect(url_for('delivery.view', delivery_id=delivery_id))
            
        DeliveryService.mark_completed(delivery_id)
        
        flash('Resepsyon livrezon konfime! Vandè a resevwa peman l.', 'success')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))
    except ValidationError as e:
        flash(str(e), 'error')
        return redirect(url_for('delivery.view', delivery_id=delivery_id))


@delivery_bp.route('/message/<delivery_id>', methods=['POST'])
@login_required
def message(delivery_id):
    """Add message to delivery chat"""
    try:
        msg_text = request.form.get('message', '').strip()
        if msg_text:
            DeliveryService.add_message(delivery_id, current_user.whatsapp, msg_text)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Mesaj vid.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
