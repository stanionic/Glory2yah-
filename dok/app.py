# -*- coding: utf-8 -*-
"""
Dòk GlorYah - Application Web Médicale
Asistan Sante Entelijan pou Ayiti
"""

from flask import Flask, render_template, request, jsonify
import sys
import os

# Ajoute dirèktwa ai nan path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai'))
from model import DokGlorYahAI

# Konfigirasyon Flask
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # Pou sipòte karaktè kreyòl

# Enstansye modèl IA
ai_model = DokGlorYahAI()

@app.route('/')
def index():
    """Paj prensipal aplikasyon an"""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Endpoint pou analize sentòm yo
    Resevwa: {"symptoms": "tèks sentòm yo"}
    Retounen: {"response": "repons IA a"}
    """
    try:
        data = request.get_json()
        symptoms = data.get('symptoms', '').strip()
        
        if not symptoms:
            return jsonify({
                'error': True,
                'message': 'Tanpri ekri sentòm ou yo'
            }), 400
        
        # Analize sentòm yo ak IA
        response = ai_model.analyze(symptoms)
        
        return jsonify({
            'error': False,
            'response': response
        })
    
    except Exception as e:
        print(f"Erè: {str(e)}")
        return jsonify({
            'error': True,
            'message': 'Gen yon pwoblèm. Tanpri eseye ankò.'
        }), 500

@app.route('/health')
def health():
    """Endpoint pou tcheke si aplikasyon an ap fonksyone"""
    return jsonify({'status': 'ok', 'message': 'Dòk GlorYah ap fonksyone byen!'})

if __name__ == '__main__':
    # Konfigirasyon pou pwoduksyon oswa devlopman
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "="*60)
    print("🏥 DÒK GLORYAH - Asistan Sante Entelijan")
    print("="*60)
    print(f"📱 Aplikasyon an ap kouri sou: http://localhost:{port}")
    print(f"🌐 Pou aksede sou telefòn: http://[IP-ou]:{port}")
    print("="*60 + "\n")
    
    app.run(
        host='0.0.0.0',  # Aksesib sou rezo lokal
        port=port,
        debug=debug_mode
    )
