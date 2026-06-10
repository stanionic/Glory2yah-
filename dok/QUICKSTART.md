# 🚀 GUIDE DE DÉMARRAGE RAPIDE - Dòk GlorYah

## Installation et Lancement en 3 étapes

### Étape 1: Vérifier Python
```bash
python3 --version
# Doit afficher Python 3.8 ou supérieur
```

### Étape 2: Installer Flask (si nécessaire)
```bash
pip install Flask --break-system-packages
```

### Étape 3: Lancer l'application
```bash
cd dok_gloryah
python3 app.py
```

## Accéder à l'application

### Sur ordinateur:
Ouvrir: `http://localhost:5000`

### Sur téléphone (même réseau WiFi):
1. Trouver l'adresse IP de l'ordinateur:
   - **Windows**: `ipconfig` → Chercher "IPv4"
   - **Mac/Linux**: `ifconfig` → Chercher "inet"
   
2. Ouvrir: `http://[ADRESSE_IP]:5000`
   Exemple: `http://192.168.1.100:5000`

## Test Rapide

Une fois l'app lancée, testez avec:
- "Mwen gen mal nan kè mwen" → Devrait donner 🔴 WOUJ (Urgent)
- "M gen lafyèv" → Devrait donner 🟡 JÒN (Modéré)
- "M santi m fatige" → Devrait donner 🟢 VÈT (Léger)

## Personnalisation

### Changer le numéro WhatsApp:
Éditer `templates/index.html` ligne ~113:
```html
<a href="https://wa.me/50942882076" ...>
```
Remplacer `50942882076` par votre numéro.

### Changer le port:
```bash
PORT=8080 python3 app.py
```

## Structure du Projet

```
dok_gloryah/
├── app.py              ← Application Flask principale
├── ai/
│   └── model.py        ← Intelligence artificielle locale
├── templates/
│   └── index.html      ← Interface utilisateur
├── static/
│   └── style.css       ← Styles et design
└── requirements.txt    ← Dépendances
```

## Résolution de Problèmes

### Problème: "Module flask not found"
**Solution**: 
```bash
pip install Flask --break-system-packages
```

### Problème: "Port already in use"
**Solution**: Utiliser un autre port
```bash
PORT=8080 python3 app.py
```

### Problème: Impossible d'accéder depuis le téléphone
**Solutions**:
1. Vérifier que l'ordinateur et le téléphone sont sur le même WiFi
2. Désactiver le pare-feu temporairement
3. Utiliser l'adresse IP correcte (pas 127.0.0.1 ou localhost)

## Support

Pour toute question:
- WhatsApp: +509 4288-2076
- Consulter le README.md pour plus de détails

---
**Bon Lancement! 🎉**
