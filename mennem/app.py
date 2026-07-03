from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app import db
from app.models.mennem_trip import MennemTrip
from app.services.gkach_service import GkachService
from app.utils.validators import ValidationError

# Create blueprint
mennem_bp = Blueprint('mennem', __name__, template_folder='templates', static_folder='static')

# Routes
@mennem_bp.route('/')
def index():
    return render_template('mennenm/index.html')

@mennem_bp.route('/find', methods=['GET', 'POST'])
def find():
    if request.method == 'POST':
        from_location = request.form.get('from')
        to_location = request.form.get('to')
        
        if not from_location or not to_location:
            flash('Tanpri antre depa ak destinasyon!', 'error')
            return redirect(url_for('mennem.index'))
        
        # Mock drivers for now
        drivers = [
            {'name': 'Jean', 'phone': '+50911111111', 'rating': 4.8, 'price_gkach': 150},
            {'name': 'Marie', 'phone': '+50922222222', 'rating': 4.9, 'price_gkach': 170},
            {'name': 'Pierre', 'phone': '+50933333333', 'rating': 4.7, 'price_gkach': 140},
        ]
        
        return render_template('mennenm/result.html', drivers=drivers, from_location=from_location, to_location=to_location)
    
    return redirect(url_for('mennem.index'))

@mennem_bp.route('/register_driver', methods=['GET', 'POST'])
def register_driver():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        car_model = request.form.get('car_model')
        car_plate = request.form.get('car_plate')
        
        flash('Enskripsyon chofè anrejistre!', 'success')
        return redirect(url_for('mennem.index'))
    
    return render_template('mennenm/register_driver.html')

@mennem_bp.route('/book/<int:driver_index>/<from_loc>/<to_loc>', methods=['GET', 'POST'])
def book(driver_index, from_loc, to_loc):
    # Mock drivers again
    drivers = [
        {'name': 'Jean', 'phone': '+50911111111', 'rating': 4.8, 'price_gkach': 150},
        {'name': 'Marie', 'phone': '+50922222222', 'rating': 4.9, 'price_gkach': 170},
        {'name': 'Pierre', 'phone': '+50933333333', 'rating': 4.7, 'price_gkach': 140},
    ]
    
    driver = drivers[driver_index]
    
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Ou dwe konekte pou resevwa chofè!', 'error')
            return redirect(url_for('auth.login', next=request.url))
        
        try:
            # Deduct Gkach from passenger
            GkachService.deduct_balance(
                current_user.whatsapp,
                driver['price_gkach'],
                f"Voyaj MENNEM M: {from_loc} → {to_loc}",
                'mennem_m'
            )
            
            # Create trip record
            trip = MennemTrip(
                from_location=from_loc,
                to_location=to_loc,
                price_gkach=driver['price_gkach'],
                driver_name=driver['name'],
                driver_phone=driver['phone'],
                driver_rating=driver['rating'],
                passenger_id=current_user.id,
                passenger_whatsapp=current_user.whatsapp,
                status='paid'
            )
            db.session.add(trip)
            db.session.commit()
            
            flash(f'Peman an reyisi! Ou te peye {driver["price_gkach"]} Gkach! Kontakte chofè a sou WhatsApp.', 'success')
            return redirect(url_for('mennem.success', trip_id=trip.id))
        except ValidationError as e:
            flash(str(e), 'error')
            return redirect(url_for('mennem.find'))
        except Exception as e:
            flash(f'Erè nan peman: {str(e)}', 'error')
            return redirect(url_for('mennem.find'))
    
    # GET request: show booking confirmation
    return render_template('mennenm/book.html', driver=driver, from_location=from_loc, to_location=to_loc)

@mennem_bp.route('/success/<int:trip_id>')
@login_required
def success(trip_id):
    trip = MennemTrip.query.get_or_404(trip_id)
    return render_template('mennenm/success.html', trip=trip)

@mennem_bp.route('/admin')
def admin():
    return render_template('mennenm/admin.html')
