# 📚 DOCUMENTATION TECHNIQUE - Dòk GlorYah

## 🎯 Vue d'ensemble

Dòk GlorYah est une application web médicale légère utilisant :
- **Backend** : Python 3.7+ avec Flask
- **Frontend** : HTML5, CSS3, JavaScript (Vanilla)
- **IA** : Système basé sur des règles (rule-based AI)
- **Design** : Mobile-first, responsive, optimisé pour connexions lentes

## 🏗️ Architecture

```
┌──────────────────────────────────────────┐
│           Interface Utilisateur          │
│        (HTML + CSS + JavaScript)         │
└────────────────┬─────────────────────────┘
                 │ HTTP/JSON
┌────────────────▼─────────────────────────┐
│         Application Flask (app.py)       │
│  - Route /: Page principale              │
│  - Route /analyze: Analyse IA            │
│  - Route /health: Health check           │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│       Moteur IA (ai/model.py)            │
│  - DokGlorYahAI class                    │
│  - Analyse par mots-clés                 │
│  - Classification 3 niveaux              │
└──────────────────────────────────────────┘
```

## 📦 Modules

### 1. app.py (Application Flask)

**Responsabilités :**
- Servir l'interface web
- Router les requêtes
- Interfacer avec le module IA
- Gérer les erreurs

**Routes :**
- `GET /` → Page principale (index.html)
- `POST /analyze` → Analyse des symptômes
- `GET /health` → Vérification d'état

**Format de requête /analyze :**
```json
{
  "symptoms": "Description des symptômes en créole ou français"
}
```

**Format de réponse :**
```json
{
  "error": false,
  "response": "🟢 **Nivo Ijans: VÈ - PA GRAV**..."
}
```

### 2. ai/model.py (Moteur IA)

**Classe : DokGlorYahAI**

**Méthodes principales :**

#### `__init__()`
- Initialise les listes de mots-clés
- Définit les templates de réponse
- Configure les niveaux d'urgence

#### `normalize_text(text: str) -> str`
- Convertit en minuscules
- Retire les caractères spéciaux
- Préserve les caractères créoles

#### `detect_urgency_level(text: str) -> str`
- Analyse le texte normalisé
- Cherche les patterns de mots-clés
- Retourne : 'urgent', 'moderate', 'minor', ou 'unclear'

#### `generate_response(symptoms: str) -> Dict`
- Détecte le niveau d'urgence
- Génère le conseil approprié
- Retourne un dictionnaire structuré

#### `analyze(symptoms: str) -> str`
- Méthode publique principale
- Formatte la réponse finale
- Ajoute les avertissements

**Algorithme de classification :**

```python
1. Normaliser le texte
2. Chercher patterns urgents
   → SI trouvé : URGENT (🔴)
3. Compter patterns modérés
   → SI ≥ 2 : MODÉRÉ (🟡)
   → SI = 1 : vérifier patterns légers
     → SI trouvé : LÉGER (🟢)
     → SINON : MODÉRÉ (🟡)
4. SI aucun pattern : LÉGER (🟢)
```

### 3. templates/index.html (Interface)

**Sections principales :**

- **Header** : Logo et titre
- **Instructions** : Guide utilisateur
- **Formulaire** : Saisie des symptômes
- **Zone de réponse** : Affichage IA
- **WhatsApp** : Bouton de contact
- **Footer** : Avertissements

**Fonctionnalités JavaScript :**

- Compteur de caractères (max 1000)
- Auto-resize du textarea
- Validation du formulaire
- Appel API asynchrone (fetch)
- Animation de chargement
- Formatage de la réponse
- Scroll automatique

### 4. static/style.css (Design)

**Variables CSS :**
```css
--primary: #00a67e;        /* Couleur principale */
--primary-dark: #008563;   /* Variante foncée */
--accent: #ff6b35;         /* Couleur d'accent */
```

**Breakpoints responsives :**
- Mobile : < 480px
- Tablette : 480px - 768px
- Desktop : > 768px

**Optimisations :**
- CSS Grid et Flexbox
- Transitions CSS natives
- Media queries
- Mode sombre (@prefers-color-scheme)
- Réduction mouvement (@prefers-reduced-motion)

## 🔍 Mots-clés IA

### Urgents (🔴)
- Respiratoires : "pa ka respire", "souf kout", "etoufe"
- Cardiaques : "doulè nan pwatrin", "kè fè mal"
- Neurologiques : "paralizi", "pèdi konesans", "konvilsyon"
- Hémorragies : "san nan piki", "vomi san"
- Traumatismes : "aksidan", "zo kase"

### Modérés (🟡)
- Fièvre : "lafyèv", "chalè", "cho"
- Douleurs : "doulè", "fè mal"
- Digestifs : "vant fè mal", "dyare", "vomi"
- Infections : "grip", "touse", "kouri nen"
- Cutanés : "po graje", "bouton"

### Légers (🟢)
- "yon ti doulè"
- "yon ti grip"
- "graj", "gratel"
- "fatige"

## 🔐 Sécurité

### Données
- Pas de stockage des symptômes
- Pas de base de données
- Pas d'authentification requise
- Session-less (stateless)

### Validation
- Limite de caractères (1000)
- Validation côté client et serveur
- Sanitization des entrées
- CORS configuré

### Avertissements
- Affichage systématique du disclaimer
- Ne jamais donner de diagnostic
- Ne jamais recommander de médicaments
- Toujours encourager la consultation

## 🚀 Déploiement

### Développement
```bash
python app.py
```

### Production (avec Gunicorn)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Production (avec uWSGI)
```bash
pip install uwsgi
uwsgi --http :5000 --wsgi-file app.py --callable app
```

### Docker (optionnel)
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

## 📊 Performance

### Métriques
- **Temps de réponse IA** : < 100ms
- **Taille HTML** : ~8 KB
- **Taille CSS** : ~12 KB
- **Total (sans images)** : ~20 KB
- **Requêtes HTTP** : 3 (HTML, CSS, JSON)

### Optimisations
- CSS inlining possible
- Minification assets
- Compression gzip
- Cache navigateur
- CDN pour fonts

## 🧪 Tests

### Exécuter les tests
```bash
python test_app.py
```

### Tests couverts
- Import module IA
- Détection urgence
- Détection modéré
- Détection léger
- Routes Flask
- Analyse JSON

### Tests manuels
```bash
# Test IA directement
python -c "from ai.model import DokGlorYahAI; ai = DokGlorYahAI(); print(ai.analyze('tèt fè m mal'))"

# Test Flask
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symptoms":"tèt fè m mal"}'
```

## 🔧 Maintenance

### Ajouter des symptômes
1. Éditer `ai/model.py`
2. Ajouter regex dans les listes appropriées
3. Tester avec `test_app.py`

### Modifier les conseils
1. Éditer `advice_templates` dans `model.py`
2. Respecter le format créole
3. Tester la cohérence

### Mettre à jour le design
1. Modifier `static/style.css`
2. Tester sur mobile et desktop
3. Vérifier le mode sombre

## 📝 Logs

### Activer les logs détaillés
```python
# Dans app.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Format des logs
```
2026-01-28 10:30:45 - INFO - Application démarrée
2026-01-28 10:31:02 - DEBUG - Analyse: tèt fè m mal
2026-01-28 10:31:02 - DEBUG - Niveau détecté: minor
```

## 🌍 Internationalisation

### Ajouter une langue
1. Dupliquer les templates de réponse
2. Traduire les mots-clés
3. Ajouter un sélecteur de langue
4. Utiliser Flask-Babel (optionnel)

## 📞 Support

Pour toute question technique :
- Consulter README.md
- Lire QUICKSTART.md
- Vérifier test_app.py
- Examiner les logs

---

**Version** : 1.0  
**Date** : Janvier 2026  
**Auteur** : Dòk GlorYah Project
