#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests pour Dòk GlorYah
"""

import sys
import os

# Ajoute le dossier parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_ai_model():
    """Teste le module IA"""
    print("\n" + "="*60)
    print("TEST: Module IA")
    print("="*60)
    
    try:
        from ai.model import DokGlorYahAI
        ai = DokGlorYahAI()
        print("✅ Module IA importé")
        
        # Test urgence
        urgent = ai.analyze("Mwen pa ka respire e pwatrin fè m mal")
        assert "🔴" in urgent or "WOUJ" in urgent
        print("✅ Détection urgence OK")
        
        # Test modéré
        moderate = ai.analyze("Mwen gen lafyèv ak touse")
        assert "🟡" in moderate or "JÒN" in moderate
        print("✅ Détection modéré OK")
        
        # Test léger
        minor = ai.analyze("Tèt fè m yon ti jan mal")
        assert "🟢" in minor or "VÈ" in minor
        print("✅ Détection léger OK")
        
        print("\n✅ Module IA fonctionne")
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        return False

def test_flask_app():
    """Teste l'application Flask"""
    print("\n" + "="*60)
    print("TEST: Application Flask")
    print("="*60)
    
    try:
        import app as flask_app
        print("✅ Module Flask importé")
        
        with flask_app.app.test_client() as client:
            # Test route principale
            response = client.get('/')
            assert response.status_code == 200
            print("✅ Route / accessible")
            
            # Test route health
            response = client.get('/health')
            assert response.status_code == 200
            print("✅ Route /health accessible")
            
            # Test route analyze
            response = client.post('/analyze',
                                  json={'symptoms': 'tèt fè m mal'},
                                  content_type='application/json')
            assert response.status_code == 200
            data = response.get_json()
            assert 'response' in data
            print("✅ Route /analyze fonctionne")
        
        print("\n✅ Application Flask fonctionne")
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        return False

def main():
    """Lance tous les tests"""
    print("\n" + "="*70)
    print("🧪 TESTS - DÒK GLORYAH")
    print("="*70)
    
    results = {
        'Module IA': test_ai_model(),
        'Flask App': test_flask_app(),
    }
    
    print("\n" + "="*70)
    print("📊 RÉSULTATS")
    print("="*70)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20s} : {status}")
    
    print("="*70)
    
    if all(results.values()):
        print("\n🎉 TOUS LES TESTS SONT PASSÉS !")
        print("\n✅ L'application est prête :")
        print("   python app.py\n")
        return 0
    else:
        print("\n⚠️  CERTAINS TESTS ONT ÉCHOUÉ\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
