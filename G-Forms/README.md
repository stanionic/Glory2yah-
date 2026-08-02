# Glory2YahPub Forms — prototype d'interface

Prototype UI/UX complet (React + Tailwind + lucide-react) du module de création de
formulaires d'inscription intelligents pour Glory2YahPub.

## Contenu

- Tableau de bord principal
- Création de formulaire en 4 étapes (informations, constructeur drag & drop,
  paramètres avancés, partage/publication)
- Gestion des réponses (recherche, filtres, export, présence)
- Statistiques
- Paramètres du module et intégrations Glory2YahPub
- Assistant IA (simulation de génération de formulaire)
- Mode clair / sombre, responsive mobile / tablette / desktop

## Installation

```bash
npm install
npm run dev
```

Puis ouvrez l'URL indiquée par Vite (par défaut http://localhost:5173).

## Build de production

```bash
npm run build
npm run preview
```

## Structure

```
glory2yahpub-forms/
├── index.html
├── package.json
├── tailwind.config.js
├── postcss.config.js
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx        # Écrans + logique du prototype
    └── index.css
```

## Notes d'intégration

`App.jsx` est un prototype front-end autonome, avec des données de démonstration
(`SAMPLE_FORMS`, `SAMPLE_RESPONSES`). Pour une intégration réelle à Glory2YahPub,
remplacer :

- les tableaux de démonstration par des appels API,
- l'assistant IA (simulation `setTimeout`) par un appel réel au moteur IA,
- les boutons de partage/export par les intégrations réelles (paiement,
  diffusion, certificats, gestion communautaire).
