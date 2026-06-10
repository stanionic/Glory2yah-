from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import secrets
import sys
import os

# Add parent directory to path to import from main app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db as main_db, UserGkach, GkachTransaction

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
# Use same database as main app for Gkach integration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'glory2yahpub.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Use the same db as main app
db = main_db

bcrypt = Bcrypt(app)

# Database Models (local to this app)
class Student(db.Model):
    __tablename__ = 'ecole_students_local'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False, unique=True)
    birth_date = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    address = db.Column(db.Text, nullable=False)
    course_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='EN ATTENTE')  # EN ATTENTE, CONFIRMÉ, REFUSÉ
    gkach_amount = db.Column(db.Integer, default=0)  # Amount paid in Gkach
    payment_status = db.Column(db.String(20), default='pending')  # pending, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Course(db.Model):
    __tablename__ = 'ecole_courses_local'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    duration = db.Column(db.String(50), nullable=False)
    fee_gkach = db.Column(db.Integer, nullable=False)  # Fee in Gkach
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    __tablename__ = 'ecole_admin_local'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Routes
@app.route('/')
def home():
    courses = Course.query.all()
    return render_template('home.html', courses=courses)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Check if WhatsApp number already exists
        existing_student = Student.query.filter_by(whatsapp=request.form['whatsapp']).first()
        if existing_student:
            flash('Nime WhatsApp sa deja enskri. Tanpri itilize yon lòt.', 'danger')
            return redirect(url_for('register'))

        # Create new student
        student = Student(
            full_name=request.form['full_name'],
            whatsapp=request.form['whatsapp'],
            birth_date=datetime.strptime(request.form['birth_date'], '%Y-%m-%d').date(),
            gender=request.form['gender'],
            address=request.form['address'],
            course_id=request.form['course_id']
        )

        db.session.add(student)
        db.session.commit()

        # Get course info for payment
        course = Course.query.get(student.course_id)
        
        flash(f'Enskripsyon ou anrejistre avèk siksè! Price: {course.fee_gkach} Gkach. Kounye a, fè peman an.', 'success')
        return redirect(url_for('payment', student_id=student.id))

    courses = Course.query.all()
    return render_template('register.html', courses=courses)

@app.route('/payment/<int:student_id>', methods=['GET', 'POST'])
def payment(student_id):
    student = Student.query.get_or_404(student_id)
    course = Course.query.get(student.course_id)

    if request.method == 'POST':
        # Gkach payment - check user's balance
        whatsapp = request.form.get('whatsapp', '').strip()
        amount_gkach = int(request.form.get('amount_gkach', 0))
        
        if not whatsapp:
            flash('Nime WhatsApp obligatwa pou verification.', 'danger')
            return redirect(url_for('payment', student_id=student_id))
        
        # Format WhatsApp number
        if not whatsapp.startswith('+'):
            whatsapp = '+' + whatsapp
        
        # Check if user has enough Gkach balance
        user_gkach = UserGkach.query.filter_by(user_whatsapp=whatsapp).first()
        
        if not user_gkach:
            flash(f'Ou pa gen kont Gkach. Achte Gkach dabò sou: {url_for("achte_gkach", _external=True)}', 'danger')
            return redirect(url_for('payment', student_id=student_id))
        
        if user_gkach.gkach_balance < amount_gkach:
            flash(f'Ou pa gen ase Gkach. Ou bezwen {amount_gkach} Gkach men ou gen {user_gkach.gkach_balance} Gkach. Achte plis Gkach.', 'danger')
            return redirect(url_for('payment', student_id=student_id))
        
        # Deduct Gkach from user's balance
        old_balance = user_gkach.gkach_balance
        user_gkach.gkach_balance -= amount_gkach
        
        # Update student payment status
        student.gkach_amount = amount_gkach
        student.payment_status = 'completed'
        student.status = 'CONFIRMÉ'  # Auto-confirm after payment
        
        # Create transaction record
        transaction_id = str(secrets.token_hex(16))
        transaction = GkachTransaction(
            transaction_id=transaction_id,
            user_whatsapp=whatsapp,
            transaction_type='ecole_payment',
            amount=amount_gkach,
            old_balance=old_balance,
            new_balance=user_gkach.gkach_balance,
            description=f'Ecole payment for {course.name}'
        )
        db.session.add(transaction)
        db.session.commit()

        flash(f'Peman avèk siksè! {amount_gkach} Gkach debouche. Ou resevwa konfimasyon.', 'success')
        return redirect(url_for('confirmation', student_id=student_id))

    return render_template('payment.html', student=student, course=course)

@app.route('/confirmation/<int:student_id>')
def confirmation(student_id):
    student = Student.query.get_or_404(student_id)
    course = Course.query.get(student.course_id)
    return render_template('confirmation.html', student=student, course=course)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        admin = Admin.query.filter_by(username=request.form['username']).first()
        if admin and bcrypt.check_password_hash(admin.password_hash, request.form['password']):
            session['admin_id'] = admin.id
            flash('Koneksyon admin avèk siksè!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Non itilizatè oswa modpas sa pa kòrèk.', 'danger')

    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    students = Student.query.all()
    courses = Course.query.all()

    return render_template('admin_dashboard.html',
                         students=students,
                         courses=courses)

@app.route('/admin/student/<int:student_id>/validate', methods=['POST'])
def validate_student(student_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    student = Student.query.get_or_404(student_id)
    action = request.form['action']

    if action == 'confirm':
        student.status = 'CONFIRMÉ'
    elif action == 'reject':
        student.status = 'REFUSÉ'

    db.session.commit()
    flash(f'Etidyan {student.full_name} te {action}ed.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/course/add', methods=['GET', 'POST'])
def add_course():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        course = Course(
            name=request.form['name'],
            description=request.form['description'],
            duration=request.form['duration'],
            fee_gkach=int(request.form['fee_gkach'])  # Fee in Gkach
        )

        db.session.add(course)
        db.session.commit()

        flash('Kou ajoute avèk siksè!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('add_course.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    flash('Dekoneksyon avèk siksè.', 'info')
    return redirect(url_for('home'))

@app.route('/check_balance/<whatsapp>')
def check_balance(whatsapp):
    """API to check user's Gkach balance"""
    if not whatsapp.startswith('+'):
        whatsapp = '+' + whatsapp
    
    user_gkach = UserGkach.query.filter_by(user_whatsapp=whatsapp).first()
    if user_gkach:
        return {'balance': user_gkach.gkach_balance, 'whatsapp': whatsapp}
    return {'balance': 0, 'whatsapp': whatsapp}

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Create default admin if not exists
        if not Admin.query.filter_by(username='admin').first():
            hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = Admin(username='admin', password_hash=hashed_password)
            db.session.add(admin)
            db.session.commit()

    app.run(debug=True, host='0.0.0.0', port=5001)
