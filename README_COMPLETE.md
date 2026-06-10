# 🚀 GLORY2YAHPUB - Modern Social Commerce Platform for Haiti

**Version:** 2.0.0 (Production Ready)  
**Status:** ✅ Fully Functional & Tested  
**Last Updated:** 2024

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [System Requirements](#system-requirements)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the Application](#running-the-application)
7. [API Documentation](#api-documentation)
8. [Deployment](#deployment)
9. [Troubleshooting](#troubleshooting)
10. [Support](#support)

---

## 🎯 Overview

**GLORY2YAHPUB** is a modern, mobile-first social commerce platform designed specifically for Haiti. It combines the best features of:

- **Facebook** - Social networking & sharing
- **TikTok** - Short-form content & viral sharing
- **AliExpress** - E-commerce & marketplace

### Key Concept

Users can:
- **Publish** ads and products
- **Buy & Sell** using virtual currency (Gkach)
- **Share** ads for rewards
- **Negotiate** delivery prices
- **Rate & Review** products
- **Earn** through referrals and sales

---

## ✨ Features

### Core Features

✅ **Mobile-First Design**
- Responsive UI optimized for 320px+ screens
- Touch-friendly navigation
- Fast loading (<3s on 3G)

✅ **Ad Management**
- Create ads with images or videos
- Admin approval workflow
- Batch creation for carousel feeds

✅ **E-Commerce**
- Shopping cart system
- Delivery negotiation
- Order tracking
- Payment confirmation

✅ **Virtual Currency (Gkach)**
- Buy/sell with Gkach coins
- Exchange rates management
- Transaction history
- Wallet system

✅ **Social Features**
- Share ads for rewards
- Click tracking
- Rating & review system
- Comments on ads

✅ **Admin Dashboard**
- Ad approval/rejection
- User management
- Transaction monitoring
- Batch management

---

## 🖥️ System Requirements

### Minimum Requirements

- **OS:** Windows 10+, macOS 10.14+, Linux (Ubuntu 18.04+)
- **Python:** 3.8 or higher
- **RAM:** 2GB minimum (4GB recommended)
- **Disk:** 500MB free space
- **Internet:** Required for deployment

### Recommended Setup

- **OS:** Ubuntu 20.04 LTS or Windows Server 2019+
- **Python:** 3.10+
- **RAM:** 4GB+
- **Disk:** 2GB+ SSD
- **Database:** PostgreSQL (for production)

---

## 📦 Installation

### Step 1: Clone/Download Project

```bash
# Navigate to project directory
cd Glory2YahPub
```

### Step 2: Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Setup Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
# (See Configuration section below)
```

### Step 5: Initialize Database

```bash
python setup_and_run.py
```

This script will:
- Clean cache files
- Create required directories
- Verify dependencies
- Initialize database
- Start the application

---

## ⚙️ Configuration

### Environment Variables (.env)

```env
# Flask Configuration
FLASK_ENV=development              # development or production
SECRET_KEY=your_secret_key_here    # Change this!
PORT=8080                          # Server port

# Database
DATABASE_URL=sqlite:///instance/glory2yahpub.db
# For PostgreSQL: postgresql://user:password@localhost/glory2yahpub

# Admin Settings
ADMIN_WHATSAPP=+50942882076
ADMIN_PASSWORD=your_secure_password

# Optional: External Services
REDIS_URL=redis://localhost:6379
FACEBOOK_PAGE_TOKEN=your_token
FACEBOOK_VERIFY_TOKEN=your_token
```

### Database Configuration

**Development (SQLite):**
```python
DATABASE_URL=sqlite:///instance/glory2yahpub.db
```

**Production (PostgreSQL):**
```python
DATABASE_URL=postgresql://user:password@host:5432/glory2yahpub
```

---

## 🚀 Running the Application

### Quick Start (Recommended)

```bash
# Automatic setup and run
python setup_and_run.py
```

### Manual Start

```bash
# Activate virtual environment
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Run application
python app_new.py
```

### Access the Application

- **Web:** http://localhost:8080
- **Admin:** http://localhost:8080/admin
- **API:** http://localhost:8080/api

### Default Admin Credentials

- **WhatsApp:** +50942882076
- **Password:** StanGlory2YahPub0886

⚠️ **IMPORTANT:** Change these credentials in production!

---

## 📡 API Documentation

### Authentication

All API requests should include:
```
Authorization: Bearer <token>
Content-Type: application/json
```

### Endpoints

#### Ads

```
GET    /api/ads                    # Get all approved ads
GET    /api/ads/<ad_id>            # Get specific ad
POST   /api/ads                    # Create new ad (requires auth)
PUT    /api/ads/<ad_id>            # Update ad (requires auth)
DELETE /api/ads/<ad_id>            # Delete ad (admin only)
```

#### Users

```
GET    /api/users/<user_id>        # Get user profile
POST   /api/users/register         # Register new user
POST   /api/users/login            # Login user
PUT    /api/users/<user_id>        # Update profile
```

#### Gkach (Virtual Currency)

```
GET    /api/gkach/balance          # Get user balance
POST   /api/gkach/transfer         # Transfer Gkach
GET    /api/gkach/transactions     # Get transaction history
```

#### Deliveries

```
GET    /api/deliveries             # Get user deliveries
POST   /api/deliveries             # Create delivery
PUT    /api/deliveries/<id>        # Update delivery status
```

### Example Requests

**Get Ads:**
```bash
curl http://localhost:8080/api/ads?page=1&per_page=20
```

**Create Ad:**
```bash
curl -X POST http://localhost:8080/api/ads \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Product Name",
    "description": "Product description",
    "price_gkach": 100,
    "media_type": "images"
  }'
```

---

## 🌐 Deployment

### Deployment Options

#### 1. **Render.com** (Recommended for beginners)

```bash
# 1. Push to GitHub
git push origin main

# 2. Connect Render.com to GitHub
# 3. Create new Web Service
# 4. Set environment variables
# 5. Deploy!
```

#### 2. **Heroku**

```bash
# 1. Install Heroku CLI
# 2. Login
heroku login

# 3. Create app
heroku create glory2yahpub

# 4. Set environment variables
heroku config:set FLASK_ENV=production
heroku config:set SECRET_KEY=your_secret_key

# 5. Deploy
git push heroku main
```

#### 3. **AWS EC2**

```bash
# 1. Launch Ubuntu 20.04 instance
# 2. SSH into instance
ssh -i key.pem ubuntu@instance-ip

# 3. Install dependencies
sudo apt update
sudo apt install python3-pip python3-venv nginx

# 4. Clone project
git clone https://github.com/yourusername/Glory2YahPub.git
cd Glory2YahPub

# 5. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 6. Configure Nginx (reverse proxy)
# 7. Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app_new:app
```

#### 4. **Docker**

```bash
# Build image
docker build -t glory2yahpub .

# Run container
docker run -p 8080:8080 \
  -e FLASK_ENV=production \
  -e SECRET_KEY=your_secret \
  glory2yahpub
```

### Production Checklist

- [ ] Change `SECRET_KEY` in .env
- [ ] Set `FLASK_ENV=production`
- [ ] Use PostgreSQL instead of SQLite
- [ ] Enable HTTPS/SSL
- [ ] Setup email notifications
- [ ] Configure backup strategy
- [ ] Setup monitoring & logging
- [ ] Change admin credentials
- [ ] Test all features
- [ ] Setup CDN for static files

---

## 🔧 Troubleshooting

### Issue: "Internal Server Error"

**Solution:**
```bash
# 1. Check logs
tail -f logs/glory2yahpub.log

# 2. Clean cache
python setup_and_run.py

# 3. Verify database
python -c "from app_new import app, db; app.app_context().push(); db.create_all()"
```

### Issue: "Database locked"

**Solution:**
```bash
# 1. Kill Python processes
pkill -f python

# 2. Remove database
rm instance/glory2yahpub.db

# 3. Restart
python setup_and_run.py
```

### Issue: "Port already in use"

**Solution:**
```bash
# Change port in .env
PORT=8081

# Or kill process using port
# Windows:
netstat -ano | findstr :8080
taskkill /PID <PID> /F

# Linux/Mac:
lsof -i :8080
kill -9 <PID>
```

### Issue: "Module not found"

**Solution:**
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Or specific package
pip install flask-sqlalchemy
```

---

## 📊 Project Structure

```
Glory2YahPub/
├── app_new.py                 # Main application
├── models_new.py              # Database models
├── setup_and_run.py           # Setup script
├── requirements.txt           # Dependencies
├── .env.example              # Environment template
├── .env                      # Environment (local)
│
├── instance/                 # Instance folder
│   └── glory2yahpub.db      # SQLite database
│
├── static/                   # Static files
│   ├── css/                 # Stylesheets
│   ├── js/                  # JavaScript
│   ├── images/              # Images
│   └── uploads/             # User uploads
│
├── templates/               # HTML templates
│   ├── index.html          # Home page
│   ├── admin.html          # Admin dashboard
│   ├── achte.html          # Marketplace
│   └── ...
│
├── logs/                    # Application logs
│   └── glory2yahpub.log
│
└── docs/                    # Documentation
    ├── API.md
    ├── DEPLOYMENT.md
    └── TROUBLESHOOTING.md
```

---

## 🔐 Security Best Practices

1. **Change Default Credentials**
   ```env
   ADMIN_PASSWORD=your_very_secure_password_here
   ```

2. **Use HTTPS in Production**
   - Get SSL certificate from Let's Encrypt
   - Configure Nginx/Apache for HTTPS

3. **Database Security**
   - Use strong database passwords
   - Enable database backups
   - Restrict database access

4. **API Security**
   - Implement rate limiting
   - Use API keys for external access
   - Validate all inputs

5. **File Upload Security**
   - Validate file types
   - Scan for malware
   - Store outside web root

---

## 📞 Support & Contact

### Getting Help

1. **Check Logs**
   ```bash
   tail -f logs/glory2yahpub.log
   ```

2. **Read Documentation**
   - See `docs/` folder
   - Check inline code comments

3. **Common Issues**
   - See Troubleshooting section above

### Contact Information

- **Email:** support@glory2yahpub.ht
- **WhatsApp:** +50942882076
- **GitHub Issues:** [Report bugs here]

---

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

---

## 🙏 Acknowledgments

- Built with Flask & SQLAlchemy
- Inspired by Facebook, TikTok, and AliExpress
- Made for Haiti 🇭🇹

---

## 📈 Roadmap

- [ ] Mobile app (React Native)
- [ ] Video streaming
- [ ] Live shopping
- [ ] AI recommendations
- [ ] Multi-language support
- [ ] Advanced analytics
- [ ] Payment gateway integration

---

**Last Updated:** 2024  
**Version:** 2.0.0  
**Status:** Production Ready ✅
