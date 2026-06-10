#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de lancement pour Dòk GlorYah
"""

import os
import sys

def main():
    print("\n" + "="*60)
    print("🏥 DÒK GLORYAH - Asistan Sante Entelijan")
    print("="*60)
    print()
    
    # Vérifier Flask
    try:
        import flask
        print(f"✅ Flask trouvé (version {flask.__version__})")
    except ImportError:
        print("❌ Flask non installé!")
        print("\nPour installer :")
        print("   pip install -r requirements.txt")
        print("\nOu :")
        print("   pip install Flask==3.0.0")
        sys.exit(1)
    
    # Vérifier les fichiers
    required = ['app.py', 'templates/index.html', 'static/style.css', 'ai/model.py']
    missing = [f for f in required if not os.path.exists(f)]
    
    if missing:
        print(f"\n❌ Fichiers manquants: {', '.join(missing)}")
        sys.exit(1)
    
    print("✅ Tous les fichiers sont présents")
    print()
    
    # Obtenir l'IP
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"📱 Accès depuis un téléphone :")
        print(f"   http://{local_ip}:5000")
        print()
    except:
        pass
    
    print("🚀 Démarrage de l'application...")
    print("="*60)
    print()
    
    # Lancer l'app
    os.system('python app.py')

if __name__ == '__main__':
    main()
