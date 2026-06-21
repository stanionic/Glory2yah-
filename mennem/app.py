from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify

# Create blueprint
mennem_bp = Blueprint('mennem', __name__, template_folder='templates', static_folder='static')

# Routes
@mennem_bp.route('/')
def index():
    return render_template('mennenm/index.html')

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

@mennem_bp.route('/result', methods=['GET', 'POST'])
def result():
    if request.method == 'POST':
        from_location = request.form.get('from')
        to_location = request.form.get('to')
        
        drivers = [
            {'name': 'Jean', 'rating': 4.8, 'price': 150},
            {'name': 'Marie', 'rating': 4.9, 'price': 170},
            {'name': 'Pierre', 'rating': 4.7, 'price': 140},
        ]
        
        return render_template('mennenm/result.html', drivers=drivers, from_location=from_location, to_location=to_location)
    
    return redirect(url_for('mennem.index'))

@mennem_bp.route('/admin')
def admin():
    return render_template('mennenm/admin.html')
