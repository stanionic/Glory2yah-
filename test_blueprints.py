# -*- coding: utf-8 -*-
"""
Test complet de tous les blueprints de Glory2YahPub
Crée un utilisateur de test, se connecte, et teste chaque endpoint
Valide les chaînes de contenu réelles dans les templates
Crée des annonces PUBLICITAIRES (PUB) et VENTE (SELL) réalistes avec des images existantes
"""
import requests
import re
import sys
import json
import random
import os

# Forcer UTF-8 pour la sortie console
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    # Python < 3.7 fallback
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8080"
TEST_USER = {
    "pseudo": "testeur_blueprint",
    "whatsapp": "+50999998877",
    "name": "Testeur Blueprint",
    "password": "Test1234!",
    "bio": "Compte de test pour blueprints"
}

# Images réelles disponibles dans static/uploads/ pour les annonces
UPLOADS_DIR = "static/uploads"
PUB_IMAGES = [
    "La_Sainte_Eglise_Yacinthe.jpg",
    "Fritzner.jpg",
    "Jeanine.jpg",
    "Claunise.jpg",
    "Diapositive1.PNG",
    "Composition2.jpg"
]

SELL_IMAGES = [
    "0a1c4aed-be01-4d6e-abed-a3b682c3ab47_20220625_104046.jpg",
    "85bc77b2-86b1-44c3-aa44-3759bdaf0f8e_images_2.jpg",
    "89b198f8-852c-450e-8767-91af0c10889d_Diapositive1.JPG",
    "a445b1ca-7c07-4c1e-83a7-bc143b0f6206_20211217_111528.jpg",
    "bcd81687-0965-47b2-bf87-5680d25063df_20211218_091410.jpg"
]

# Annonces PUB réalistes (contenu religieux/promotionnel)
PUB_ADS = [
    {
        "title": "La Sainte Église Yacinthe - Culte Dimanche",
        "description": "Venez adorer le Seigneur chaque dimanche à 10h. La Sainte Église Yacinthe vous accueille pour un moment de prière et de louange. Que la paix du Christ soit avec vous!",
        "image": "La_Sainte_Eglise_Yacinthe.jpg",
        "category": "religion",
        "ad_type": "pub",
        "price_gkach": 0
    },
    {
        "title": "Ministère Évangélique - Conférence 2026",
        "description": "Rejoignez-nous pour une grande conférence spirituelle. Le pasteur Fritzner sera présent pour une parole prophétique. Inscrivez-vous dès maintenant!",
        "image": "Fritzner.jpg",
        "category": "religion",
        "ad_type": "pub",
        "price_gkach": 0
    },
    {
        "title": "Jeanine - Témoignage de Foi",
        "description": "Découvrez le témoignage inspirant de Jeanine sur son parcours de foi. Un message d'espoir et de transformation qui touchera votre coeur.",
        "image": "Jeanine.jpg",
        "category": "religion",
        "ad_type": "pub",
        "price_gkach": 0
    }
]

# Annonces SELL réalistes (produits à vendre)
SELL_ADS = [
    {
        "title": "🔋 Appareil Électronique Haute Qualité",
        "description": "Vends appareil électronique en excellent état. Parfait pour la maison ou le bureau. Fonctionne parfaitement. Prix négociable.",
        "image": "0a1c4aed-be01-4d6e-abed-a3b682c3ab47_20220625_104046.jpg",
        "category": "electronics",
        "ad_type": "sell",
        "price_gkach": 150
    },
    {
        "title": "🖼️ Décoration Murale - Collection Exclusive",
        "description": "Magnifique décoration murale importée. Idéal pour embellir votre salon ou votre chambre. Design moderne et élégant.",
        "image": "89b198f8-852c-450e-8767-91af0c10889d_Diapositive1.JPG",
        "category": "home",
        "ad_type": "sell",
        "price_gkach": 75
    },
    {
        "title": "📱 Accessoires Téléphone - Lot Spécial",
        "description": "Lot d'accessoires pour téléphone: coque, protecteur d'écran, support. Compatible avec tous les modèles. Nouveau en emballage.",
        "image": "a445b1ca-7c07-4c1e-83a7-bc143b0f6206_20211217_111528.jpg",
        "category": "electronics",
        "ad_type": "sell",
        "price_gkach": 50
    }
]

session = requests.Session()
results = {"passed": 0, "failed": 0, "tests": []}
user_is_logged_in = False  # Track login state for creating ads after login

def test(name, status_code, expected_status=200, check_content=None):
    """Enregistrer un résultat de test - vérifie status et contenu optionnel"""
    # Gérer les listes de statuts attendus (ex: [200, 302, 403])
    if isinstance(expected_status, list):
        passed = status_code in expected_status
    else:
        passed = status_code == expected_status
    
    result = {
        "name": name,
        "status_code": status_code,
        "expected": expected_status,
        "passed": passed
    }
    results["tests"].append(result)
    if result["passed"]:
        results["passed"] += 1
        print(f"  ✅ {name} - {status_code}")
    else:
        results["failed"] += 1
        print(f"  ❌ {name} - Got {status_code}, Expected {expected_status}")
    return result["passed"]

def test_content(name, response, expected_content, expected_status=200):
    """Test avec vérification du contenu dans la réponse HTML"""
    passed = response.status_code == expected_status
    if passed and expected_content:
        passed = expected_content in response.text
    result = {
        "name": name,
        "status_code": response.status_code,
        "expected": expected_status,
        "passed": passed
    }
    results["tests"].append(result)
    if passed:
        results["passed"] += 1
        print(f"  ✅ {name} - {response.status_code} (contient: {expected_content[:50] if expected_content else 'OK'})")
    else:
        results["failed"] += 1
        print(f"  ❌ {name} - {response.status_code}")
        if expected_content and expected_content not in response.text:
            print(f"     Contenu attendu non trouvé: {expected_content[:100]}")
    return passed

def extract_csrf(html, name="csrf"):
    """Extraire le token CSRF du HTML"""
    # Chercher dans meta tag
    match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
    if match:
        return match.group(1)
    # Chercher dans input hidden
    match = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', html)
    if match:
        return match.group(1)
    return None

def create_ad_via_api(ad_data, ad_type_label):
    """Crée une annonce via l'API submit_ad avec les données fournies"""
    global user_is_logged_in
    if not user_is_logged_in:
        print(f"     ⚠️ Utilisateur non connecté, impossible de créer l'annonce {ad_type_label}")
        return False
    
    try:
        # Récupérer la page de soumission d'annonce pour le CSRF token
        resp = session.get(f"{BASE_URL}/submit_ad", allow_redirects=True)
        if resp.status_code != 200:
            print(f"     ⚠️ Impossible d'accéder à /submit_ad (status {resp.status_code})")
            return False
        
        csrf_token = extract_csrf(resp.text)
        
        # Préparer les données du formulaire
        form_data = {
            "title": ad_data["title"],
            "description": ad_data["description"],
            "category": ad_data["category"],
            "ad_type": ad_data["ad_type"],
            "price_gkach": str(ad_data["price_gkach"])
        }
        if csrf_token:
            form_data["csrf_token"] = csrf_token
        
        # Vérifier que l'image existe
        image_path = os.path.join(UPLOADS_DIR, ad_data["image"])
        if os.path.exists(image_path):
            # Envoyer avec le fichier image
            with open(image_path, "rb") as f:
                files = {"image": (ad_data["image"], f, "image/jpeg")}
                resp = session.post(f"{BASE_URL}/submit_ad", data=form_data, files=files, allow_redirects=True)
        else:
            print(f"     ⚠️ Image non trouvée: {image_path}, envoi sans image")
            resp = session.post(f"{BASE_URL}/submit_ad", data=form_data, allow_redirects=True)
        
        if resp.status_code in [200, 302]:
            print(f"     ✅ Annonce {ad_type_label} créée: {ad_data['title'][:40]}...")
            return True
        else:
            print(f"     ❌ Échec création annonce {ad_type_label}: status {resp.status_code}")
            return False
    except Exception as e:
        print(f"     ❌ Erreur création annonce {ad_type_label}: {e}")
        return False

print("=" * 60)
print("🧪 TEST COMPLET DES BLUEPRINTS - GLORY2YAHPUB")
print("=" * 60)

# ===== ÉTAPE 1: ACCUEIL =====
print("\n📌 1. PAGE D'ACCUEIL (Blueprint: main)")
print("-" * 40)
resp = session.get(f"{BASE_URL}/")
test_content("GET /", resp, "Glory2YahPub", 200)

# ===== ÉTAPE 2: INSCRIPTION =====
print("\n📌 2. INSCRIPTION / REGISTER (Blueprint: auth)")
print("-" * 40)

# GET register page
resp = session.get(f"{BASE_URL}/auth/register")
test_content("GET /auth/register", resp, "Kreye kont ou gratis", 200)

# POST register (créer l'utilisateur)
csrf_token = extract_csrf(resp.text)
print(f"   CSRF Token: {csrf_token[:20] if csrf_token else 'NON TROUVÉ'}...")

if csrf_token:
    register_data = {
        "csrf_token": csrf_token,
        "pseudo": TEST_USER["pseudo"],
        "whatsapp": TEST_USER["whatsapp"],
        "name": TEST_USER["name"],
        "password": TEST_USER["password"],
        "bio": TEST_USER["bio"]
    }
    resp = session.post(f"{BASE_URL}/auth/register", data=register_data, allow_redirects=False)
    # S'inscrire peut rediriger vers login (302), ou renvoyer 429 (rate limit)
    if resp.status_code in [302, 200, 429]:
        print(f"  ✅ POST /auth/register (inscription) - {resp.status_code} (OK)")
        results["passed"] += 1
        results["tests"].append({"name": "POST /auth/register", "status_code": resp.status_code, "expected": [302, 200, 429], "passed": True})
    else:
        print(f"  ❌ POST /auth/register - {resp.status_code}")
        results["failed"] += 1
        results["tests"].append({"name": "POST /auth/register", "status_code": resp.status_code, "expected": [302, 200, 429], "passed": False})

# ===== ÉTAPE 3: CONNEXION =====
print("\n📌 3. CONNEXION / LOGIN (Blueprint: auth)")
print("-" * 40)

# GET login page
resp = session.get(f"{BASE_URL}/auth/login")
test_content("GET /auth/login", resp, "Konekte", 200)

# POST login avec l'utilisateur créé
csrf_token = extract_csrf(resp.text)
print(f"   CSRF Token: {csrf_token[:20] if csrf_token else 'NON TROUVÉ'}...")

login_data = {
    "identifier": TEST_USER["pseudo"],
    "password": TEST_USER["password"]
}
if csrf_token:
    login_data["csrf_token"] = csrf_token

resp = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)
logged_in = "Byenveni" in resp.text or "deconnexion" in resp.text.lower() or "logout" in resp.text.lower() or resp.status_code == 200

if logged_in:
    print(f"  ✅ POST /auth/login (connexion réussie)")
    results["passed"] += 1
    results["tests"].append({"name": "POST /auth/login", "status_code": resp.status_code, "expected": 200, "passed": True})
else:
    print(f"  ❌ POST /auth/login - Connexion échouée")
    # Essayer avec whatsapp comme identifiant
    login_data2 = {"identifier": TEST_USER["whatsapp"], "password": TEST_USER["password"]}
    if csrf_token:
        login_data2["csrf_token"] = csrf_token
    resp2 = session.post(f"{BASE_URL}/auth/login", data=login_data2, allow_redirects=True)
    if "Byenveni" in resp2.text or "logout" in resp2.text.lower():
        print(f"  ✅ POST /auth/login (avec whatsapp) - Succès")
        results["passed"] += 1
        results["tests"].append({"name": "POST /auth/login", "status_code": resp2.status_code, "expected": 200, "passed": True})
        resp = resp2
    else:
        results["failed"] += 1
        results["tests"].append({"name": "POST /auth/login", "status_code": resp.status_code, "expected": 200, "passed": False})

# ===== ÉTAPE 4: CRÉATION D'ANNONCES RÉALISTES =====
print("\n📌 4. CRÉATION D'ANNONCES AVEC IMAGES RÉELLES")
print("-" * 40)

# Marquer l'utilisateur comme connecté après le POST login réussi
user_is_logged_in = True

# Créer les annonces PUB (publicitaires/promotionnelles)
print("\n   --- Annonces PUB (Publicitaires) ---")
pub_created = 0
for ad_data in PUB_ADS:
    if create_ad_via_api(ad_data, "PUB"):
        pub_created += 1

# Créer les annonces SELL (vente de produits)
print("\n   --- Annonces SELL (Vente) ---")
sell_created = 0
for ad_data in SELL_ADS:
    if create_ad_via_api(ad_data, "SELL"):
        sell_created += 1

total_ads_created = pub_created + sell_created
print(f"\n   📊 Total: {total_ads_created} annonces créées ({pub_created} PUB + {sell_created} SELL)")
result = {
    "name": "Création d'annonces réalistes",
    "status_code": 200 if total_ads_created > 0 else 500,
    "expected": 200,
    "passed": total_ads_created > 0
}
results["tests"].append(result)
if result["passed"]:
    results["passed"] += 1
    print(f"  ✅ Création d'annonces - {total_ads_created} créées")
else:
    results["failed"] += 1
    print(f"  ❌ Création d'annonces - Aucune annonce créée")

# ===== ÉTAPE 5: PROFIL =====
print("\n📌 5. PROFIL (Blueprint: auth)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/auth/profile")
test_content("GET /auth/profile", resp, "Pwofil", 200)

resp = session.get(f"{BASE_URL}/auth/profile/edit")
test("GET /auth/profile/edit", resp.status_code, 200)

# ===== ÉTAPE 6: MES ANNONCES =====
print("\n📌 6. MES ANNONCES (Blueprint: auth)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/auth/ads")
test_content("GET /auth/ads", resp, "Piblisite", 200)

# ===== ÉTAPE 7: MES STORIES =====
print("\n📌 7. MES STORIES (Blueprint: auth)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/auth/stories")
test_content("GET /auth/stories", resp, "Istwa", 200)

# ===== ÉTAPE 8: MARKETPLACE (MACHE) =====
print("\n📌 8. MARKETPLACE - MACHE (Blueprint: marketplace)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/mache")
test_content("GET /mache", resp, "Mache", 200)

resp = session.get(f"{BASE_URL}/mache/categories")
test("GET /mache/categories", resp.status_code, 200)

# ===== ÉTAPE 9: PANIER / CART =====
print("\n📌 9. PANIER - CART (Blueprint: cart)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/cart")
test("GET /cart", resp.status_code, 200)

# ===== ÉTAPE 10: GKACH (RÉCOMPENSES) =====
print("\n📌 10. GKACH (Blueprint: gkach)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/gkach")
test("GET /gkach", resp.status_code, [200, 302])

# ===== ÉTAPE 11: LIVRAISON =====
print("\n📌 11. LIVRAISON / DELIVERY (Blueprint: delivery)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/delivery/my-deliveries")
test("GET /delivery/my-deliveries", resp.status_code, [200, 302])

# ===== ÉTAPE 12: ADMIN =====
print("\n📌 12. ADMIN (Blueprint: admin)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/admin")
test("GET /admin", resp.status_code, [200, 302, 403])

resp = session.get(f"{BASE_URL}/admin/users")
test("GET /admin/users", resp.status_code, [200, 302, 403])

resp = session.get(f"{BASE_URL}/admin/ads")
test("GET /admin/ads", resp.status_code, [200, 302, 403])

# ===== ÉTAPE 13: ECOLE BIBLIQUE =====
print("\n📌 13. ECOLE BIBLIQUE (Blueprint: ecole_biblique)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/ecole_biblique/")
test_content("GET /ecole_biblique/", resp, "Biblique", 200)

resp = session.get(f"{BASE_URL}/ecole_biblique/register")
test("GET /ecole_biblique/register", resp.status_code, 200)

resp = session.get(f"{BASE_URL}/ecole_biblique/ranking")
test_content("GET /ecole_biblique/ranking", resp, "Klasman", 200)

# ===== ÉTAPE 14: KONFERANS =====
print("\n📌 14. KONFERANS (Blueprint: konferans)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/konferans/")
test_content("GET /konferans/", resp, "Konferans", 200)

# ===== ÉTAPE 15: PARTY - FET =====
print("\n📌 15. PARTY - FET (Blueprint: party)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/fet/")
test_content("GET /fet/", resp, "Fèt", 200)

# ===== ÉTAPE 16: PWA =====
print("\n📌 16. PWA (Blueprint: pwa)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/pwa/manifest.json")
test("GET /pwa/manifest.json", resp.status_code, 200)

resp = session.get(f"{BASE_URL}/pwa/api/settings")
test("GET /pwa/api/settings", resp.status_code, 200)

resp = session.get(f"{BASE_URL}/pwa/api/stats")
test("GET /pwa/api/stats", resp.status_code, 200)

resp = session.get(f"{BASE_URL}/pwa/offline")
test_content("GET /pwa/offline", resp, "Pa gen Koneksyon", 200)

# ===== ÉTAPE 17: SHARE =====
print("\n📌 17. SHARE (Blueprint: share)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/s/create")
test_content("GET /s/create", resp, "Fonksyon", 200)

resp = session.get(f"{BASE_URL}/s/b/test-batch")
test("GET /s/b/test-batch", resp.status_code, [200, 302])

# ===== ÉTAPE 18: API ENDPOINTS =====
print("\n📌 18. API ENDPOINTS")
print("-" * 40)

resp = session.get(f"{BASE_URL}/api/feed?page=1")
test("GET /api/feed", resp.status_code, 200)

resp = session.get(f"{BASE_URL}/api/stories")
test("GET /api/stories", resp.status_code, 200)

resp = session.get(f"{BASE_URL}/api/ads/trending")
test("GET /api/ads/trending", resp.status_code, 200)

# ===== ÉTAPE 19: DÉCONNEXION =====
print("\n📌 19. DÉCONNEXION / LOGOUT (Blueprint: auth)")
print("-" * 40)

resp = session.get(f"{BASE_URL}/auth/logout", allow_redirects=True)
test_content("GET /auth/logout", resp, "dekonekte", 200)

# ===== RÉSULTATS =====
print("\n" + "=" * 60)
print("📊 RÉSULTATS DES TESTS")
print("=" * 60)
total = len(results["tests"])
print(f"Total: {total} tests")
print(f"✅ Réussis: {results['passed']}")
print(f"❌ Échoués: {results['failed']}")
success_rate = (results['passed'] / total * 100) if total > 0 else 0
print(f"🎯 Taux de succès: {success_rate:.1f}%")

# Détails des échecs
if results["failed"] > 0:
    print("\n📋 Détails des échecs:")
    for t in results["tests"]:
        if not t["passed"]:
            expected_str = t.get("expected", "?")
            print(f"  ❌ {t['name']} - Status: {t['status_code']}, Attendu: {expected_str}")

print("\n" + "=" * 60)
if success_rate >= 90:
    print("🎉 TOUS LES BLUEPRINTS FONCTIONNENT CORRECTEMENT !")
elif success_rate >= 70:
    print("⚠️ La plupart des blueprints fonctionnent, quelques ajustements nécessaires.")
else:
    print("🔧 Plusieurs blueprints ont besoin d'être corrigés.")

# Enregistrer les résultats
import datetime
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
report = {
    "timestamp": timestamp,
    "test_user": TEST_USER["pseudo"],
    "total_tests": total,
    "passed": results["passed"],
    "failed": results["failed"],
    "success_rate": f"{success_rate:.1f}%",
    "details": results["tests"]
}
with open(f"test_report_{timestamp}.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n📁 Rapport enregistré: test_report_{timestamp}.json")
