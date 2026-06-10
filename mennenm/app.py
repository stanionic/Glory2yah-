import os
import math
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable

APP_NAME = "MENNNEN M"
ADMIN_PHONE = "+50942882076"

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join("static", "uploads")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# ======================= MODELE =========================
class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    photo = db.Column(db.String(200))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    active = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

# ======================= OUTILS =========================
def distance(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)

geolocator = Nominatim(user_agent="mennnen_m")

# ======================= ROUTES =========================

@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        address = request.form["address"]
        try:
            location = geolocator.geocode(address + ", Haiti")
        except GeocoderUnavailable:
            return "Service de géolocalisation indisponible. Veuillez réessayer plus tard."

        if not location:
            return "Adresse introuvable"

        client_lat, client_lon = location.latitude, location.longitude

        drivers = Driver.query.filter_by(active=True).all()
        if not drivers:
            return "Aucun chauffeur disponible"

        closest = None
        min_dist = float("inf")

        for d in drivers:
            d_dist = distance(client_lat, client_lon, d.lat, d.lon)
            if d_dist < min_dist:
                min_dist = d_dist
                closest = d

        return render_template(
            "result.html",
            driver=closest,
            client_lat=client_lat,
            client_lon=client_lon
        )

    return render_template("index.html")


@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        address = request.form["address"]
        photo = request.files["photo"]

        location = geolocator.geocode(address + ", Haiti")
        if not location:
            return "Adresse introuvable"

        filename = photo.filename
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo.save(save_path)

        driver = Driver(
            name=name,
            phone=phone,
            photo=filename,
            lat=location.latitude,
            lon=location.longitude,
            active=True
        )

        db.session.add(driver)
        db.session.commit()

        return redirect(url_for("index"))

    return render_template("register_driver.html")


@app.route("/admin/<phone>", methods=["GET","POST"])
def admin(phone):
    if phone != ADMIN_PHONE:
        return "Accès refusé 🚫"

    drivers = Driver.query.all()

    if request.method == "POST":
        driver_id = int(request.form["driver_id"])
        action = request.form["action"]

        d = Driver.query.get(driver_id)
        if d:
            if action == "activate":
                d.active = True
            else:
                d.active = False
            db.session.commit()

        return redirect(url_for("admin", phone=ADMIN_PHONE))

    return render_template("admin.html", drivers=drivers)


if __name__ == "__main__":
    app.run(debug=True)
