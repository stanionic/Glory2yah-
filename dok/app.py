# -*- coding: utf-8 -*-
"""
Dòk GlorYah - Application Web Médicale
Asistan Sante Entelijan pou Ayiti
"""

from flask import Blueprint, render_template, request, jsonify
import sys
import os

# Ajoute dirèktwa ai nan path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai'))
from model import DokGlorYahAI

# Konfigirasyon Blueprint
dok_bp = Blueprint('dok', __name__, template_folder='templates', static_folder='static', url_prefix='/dok')

# Enstansye modèl IA
ai_model = DokGlorYahAI()

@dok_bp.route('/')
def index():
    """Paj prensipal aplikasyon an"""
    return render_template('index.html')

@dok_bp.route('/analyze', methods=['POST'])
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

@dok_bp.route('/health')
def health():
    """Endpoint pou tcheke si aplikasyon an ap fonksyone"""
    return jsonify({'status': 'ok', 'message': 'Dòk GlorYah ap fonksyone byen!'})
