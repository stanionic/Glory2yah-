#!/bin/bash
# MANDEMMAPBAW - Quick Deployment Script for Render/Railway

echo "========================================"
echo "MANDEMMAPBAW - Deployment Setup"
echo "========================================"
echo ""

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "Initializing Git repository..."
    git init
    git branch -M main
fi

# Check if files exist
echo "Creating/checking deployment files..."

# Ensure all deployment files exist
if [ ! -f "render.yaml" ]; then
    echo "✗ render.yaml missing - creating..."
    cat > render.yaml << 'EOF'
services:
  - type: web
    name: mandemmapbaw
    env: python
    buildCommand: "pip install -r requirements-basic.txt"
    startCommand: "gunicorn app:app"
    envVars:
      - key: FLASK_ENV
        value: production
      - key: SECRET_KEY
        generateValue: true
EOF
fi

if [ ! -f "Procfile" ]; then
    echo "web: gunicorn app:app" > Procfile
fi

if [ ! -f ".gitignore" ]; then
    cat > .gitignore << 'EOF'
.venv/
venv/
__pycache__/
*.pyc
*.db
.env
static/generated/images/*.png
static/generated/videos/*.mp4
EOF
fi

echo ""
echo "✓ Deployment files ready!"
echo ""
echo "Next steps:"
echo ""
echo "1. Commit your code:"
echo "   git add ."
echo "   git commit -m 'Deploy MANDEMMAPBAW'"
echo ""
echo "2. Create GitHub repository and push:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/mandemmapbaw.git"
echo "   git push -u origin main"
echo ""
echo "3. Deploy on Render.com:"
echo "   a. Go to https://render.com"
echo "   b. Sign in with GitHub"
echo "   c. New Web Service"
echo "   d. Connect your repo"
echo "   e. Click 'Create Web Service'"
echo ""
echo "4. Your app will be live at:"
echo "   https://mandemmapbaw.onrender.com"
echo ""
