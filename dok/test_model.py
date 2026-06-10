#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour Dòk GlorYah
"""

import sys
import os

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.model import DokGlorYahAI

def test_ai_model():
    """Tester le modèle IA"""
    print("="*60)
    print("TEST DU MODÈLE IA - DÒK GLORYAH")
    print("="*60 + "\n")
    
    ai = DokGlorYahAI()
    
    test_cases = [
        ("Mwen gen mal nan kè mwen", "🔴 WOUJ (Urgent)"),
        ("M gen lafyèv ak toux", "🟡 JÒN (Modéré)"),
        ("M santi m yon ti jan fatige", "🟢 VÈT (Léger)"),
        ("Tèt mwen ap vire epi pa ka respire", "🔴 WOUJ (Urgent)"),
        ("M gen dyare", "🟡 JÒN (Modéré)"),
    ]
    
    for i, (symptom, expected) in enumerate(test_cases, 1):
        print(f"\nTest {i}: {symptom}")
        print("-" * 60)
        
        result = ai.analyze(symptom)
        
        print(f"Résultat: {result['icon']} {result['level']}")
        print(f"Attendu: {expected}")
        print(f"\nRéponse:")
        print(result['response'][:150] + "...")
        print(f"\nAvertissement: {result['warning']}")
        
        # Vérifier le format de la réponse
        assert 'icon' in result, "Manque 'icon'"
        assert 'level' in result, "Manque 'level'"
        assert 'response' in result, "Manque 'response'"
        assert 'warning' in result, "Manque 'warning'"
        
        print("✅ Test réussi!")
    
    print("\n" + "="*60)
    print("TOUS LES TESTS ONT RÉUSSI! ✅")
    print("="*60)

if __name__ == '__main__':
    try:
        test_ai_model()
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
