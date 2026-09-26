# KONFERANS Module - Audit, Bug Fixes & CSS Modernization
## Product Requirements Document

## Overview
- **Summary**: Audit complet du module KONFERANS (visioconférence WebRTC), correction de TOUS les bugs identifiés, et modernisation du CSS pour un look SaaS premium (glassmorphism, ombres douces, micro-animations).
- **Purpose**: Garantir la stabilité, la sécurité et la qualité de l'expérience utilisateur du module de visioconférence qui supporte e-learning, réunions et facturation Gkach.
- **Target Users**: Utilisateurs connectés (créateurs de salles), invités, professeurs e-learning, participants conférences.

## Goals
- Corriger tous les bugs backend (routes, auth, permissions, persistance).
- Corriger tous les bugs frontend (templates cassés, erreurs JS, état incohérent).
- Améliorer le CSS pour respecter la charte SaaS premium: glassmorphism, transitions douces, micro-animations, focus-visible accessible.
- Aucune régression sur les features critiques: WebRTC P2P, billing 45min gratuites + 250 Gkach/h, rappels 10min, partage écran multi-source, switch audio/vidéo sans coupure.

## Non-Goals
- Pas de refonte de l'architecture WebRTC (SimplePeer + SocketIO reste intact).
- Pas de migration de schéma DB hors champs déjà prévus par les migrations idempotentes existantes.
- Pas de changement aux tarifs billing (FREE_MINUTES=45, GKACH_PER_HOUR=250, REMINDER=10min).

## Background & Context
Le module KONFERANS repose sur:
- Modèles DB: [konferans.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/app/models/konferans.py) (KonferansRoom, KonferansRecording)
- Blueprint + SocketIO handlers: [routes.py](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/konferans/routes.py)
- Templates: [index.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/konferans/index.html), [room.html](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/templates/konferans/room.html)
- CSS: [konferans.css](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/static/css/konferans.css)
- Variables design system: [variables.css](file:///c:/Users/Ops/OneDrive/Desktop/dev/Glory2YahPub%20-%20Copy/static/css/variables.css)
- Hard constraints projet (mémoire):
  - Seuls utilisateurs connectés créent des salles (enforcé côté backend avec @login_required + current_user).
  - 45 min gratuites puis 250 Gkach/h, rappel toutes les 10min au propriétaire.
  - Switch audio↔video sans coupure via replaceTrack; partage écran multi-source (monitor/fenêtre/onglet).
  - Création de salle = lien partage + code unique systématiques.

## Functional Requirements

### Bug Fixes Backend
- **FR-B1**: Template index.html doit avoir une balise `{% extends %}` valide (corriger le préfixe "ake it ").
- **FR-B2**: Route `upload_recording` doit:
  - Vérifier que l'utilisateur est authentifié ET propriétaire de la salle OU admin.
  - Appliquer la whitelist `_ALLOWED_RECORDING_EXTS`.
  - Appliquer la limite `_MAX_RECORDING_MB` avant écriture disque.
  - Protéger CSRF via X-CSRFToken header.
- **FR-B3**: Route `update_room_name` doit:
  - Vérifier l'ownership via user_id connecté OU fallback nom exact (même logique que `/room/<code>`).
  - Propager le changement via SocketIO broadcast `room_name_changed` aux participants.
  - Retourner status codes HTTP corrects (404, 403, 200).
- **FR-B4**: Route `join_room_route` doit retourner un status 400/404 en cas d'échec (pas 200 avec success:false).
- **FR-B5**: Socket handler `handle_join` doit:
  - Refuser l'entrée si `len(participants) >= max_participants` via une erreur `join_error`.
  - Appeler `leave_room()` dans `handle_disconnect` pour nettoyer la room SocketIO.
- **FR-B6**: Socket event `room_name_updated` doit persister le changement en DB (pas seulement broadcast).

### Bug Fixes Frontend
- **FR-F1**: Corriger l'erreur de template literal JS dans `billingTick` (manque `}` dans `${FREE_MINUTES minit...`).
- **FR-F2**: Le billing timer côté owner doit:
  - Initialiser `billingElapsedSec` depuis `initialBilling.elapsed_seconds` correctement, sinon 0.
  - Ne PAS planifier `setInterval` si l'utilisateur n'est PAS owner.
- **FR-F3**: Lien WhatsApp share: le fallback `String({{ room.room_name|tojson }})` ne doit pas générer d'erreur JS pour des noms avec caractères spéciaux.
- **FR-F4**: Partage écran: bouton stop item dropdown doit correctement s'afficher quand partage actif; `stopScreenShare` ne doit pas crasher si `originalVideoTrack` est null.

### CSS Modernization
- **FR-C1**: Index page: hero card doit présenter glassmorphism premium (backdrop-filter, border semi-transparent, gradient subtil, animation fade-in).
- **FR-C2**: Boutons formulaire: focus-visible ring accessible, hover lift + soft shadow, active pressée 1px.
- **FR-C3**: Room page controls bar: glassmorphism épuré, espacement régulier, transitions douces (scale/translateY sur hover).
- **FR-C4**: Grille vidéos: wrapper avec border-radius uniforme, hover highlight (border couleur primary glow), label vidéo backdrop-filter.
- **FR-C5**: Sidebar (chat + participants): hauteur flexible, scrollbar stylée subtil, bulles chat avec animation slide-in depuis gauche/droite.
- **FR-C6**: Billing Modal: premium card look (gradient background, icon with soft glow, pricing row with separator, CTA button primary gradient).
- **FR-C7**: Toasts: position top-right, backdrop-filter, border coloré par type (info/success/warn/danger), animation slide-in + fade-out.
- **FR-C8**: Responsive: breakpoint 992px sidebar en grid 2-col; 768px sidebar en colonne unique; 480px controls avec overflow-x scroll icônes-only.
- **FR-C9**: Accessibilité: tous les boutons interactifs ont un `:focus-visible` outline/ring visible; `prefers-reduced-motion` réduit animations.

## Non-Functional Requirements
- **NFR-1**: Sécurité - Toutes routes protégées retournent 401/403 JSON avec message en Créole Haïtien.
- **NFR-2**: Persistance - Aucune modification des colonnes billing DB (gkach_charged_total, credit_bought_minutes) n'est perdue entre redémarrages; écriture DB dans charge_gkach_hour reste.
- **NFR-3**: Performance - CSS ne dépasse pas ~750 lignes; animations GPU-friendly (transform, opacity).
- **NFR-4**: Compatibilité - Pas de breaking change sur les selecteurs CSS déjà référencés par inline styles templates (classes konf-* préservées, extensions seulement).

## Constraints
- **Technique**:
  - Framework: Flask + SocketIO + SimplePeer (inchangés).
  - CSS custom properties (variables.css) comme source de vérité pour couleurs, espacements, radius, shadows.
  - Aucune dépendance npm/CDN nouvelle (socket.io/4.0.1 et simple-peer/9.11.1 gardés).
- **Business**:
  - Messages UI en Créole Haïtien (inchangé sémantiquement, peut corriger typos).
  - Billing: FREE_MINUTES=45, GKACH_PER_HOUR=250, REMINDER=10 (négociables seulement via user approbation).
- **Dépendances**:
  - `app/__init__.py::register_blueprints` → importe `konferans.routes`.
  - `GkachService` pour `get_balance` et `deduct_balance`.
  - CSRF: `csrf.init_app` actif global; routes POST AJAX doivent inclure `X-CSRFToken`.

## Assumptions
- Routes `create_room` et `charge_gkach_hour` sont déjà protégées par `@login_required` (correct).
- Les migrations KONFERANS dans `app/__init__.py` (colonnes billing + e-learning) sont déjà appliquées (code présent).
- Le serveur SocketIO démarre avec `socketio.init_app(app, ...)` comme dans l'init.

## Acceptance Criteria

### AC-1: Template extends index.html valide
- **Type**: `rule`
- **Given**: Fichier `templates/konferans/index.html`
- **When**: Ligne 1 est lue
- **Then**: Elle contient uniquement `{% extends "base.html" %}` sans préfixe parasite
- **Pass Condition**: `head -1 templates/konferans/index.html` retourne exactement la balise extends valide
- **Evidence**: Diff du fichier + py_compile des templates Flask (ou test de render sans exception)

### AC-2: upload_recording sécurisé + limites appliquées
- **Type**: `rule`
- **Given**: Utilisateur non-owner / anonyme POST /konferans/upload_recording/<room_id>
- **When**: Requête est envoyée
- **Then**: Réponse est 401/403 (pas 200), et aucun fichier n'est écrit si extension non-autorisée ou taille > 512MB
- **Pass Condition**: Test avec: (a) user anonyme → 401/403; (b) mauvaise extension → 400; (c) taille > MAX → 413/400
- **Evidence**: Code routes.py vérifiant auth + ext + size + py_compile succès

### AC-3: update_room_name owner-check + broadcast + bons status codes
- **Type**: `rule`
- **Given**: User non-owner POST /konferans/update_room_name avec room_id valide et nouveau nom
- **When**: Requête exécutée
- **Then**: DB unchanged; réponse 403; owner obtient 200 ET message SocketIO reçu par participants
- **Pass Condition**: Routes test: 403 non-owner / 200 owner; handler socket écrit en DB
- **Evidence**: Diff routes.py + capture emit socket

### AC-4: join_room_route retourne bons status HTTP
- **Type**: `rule`
- **Given**: Code de salle invalide ou manquant envoyé à /konferans/join_room
- **When**: Réponse est reçue
- **Then**: Status code != 200 (400/404), frontend `response.ok === false` et error message affiché
- **Pass Condition**: Routes retournent 4xx sur échec, 2xx sur succès
- **Evidence**: Diff routes.py lignes join_room_route + upload + update_room_name status codes

### AC-5: max_participants enforcement + disconnect leave_room
- **Type**: `rule`
- **Given**: Salle configurée max_participants=50 et 50 participants déjà dedans
- **When**: 51ème user émet socket 'join'
- **Then**: Il reçoit 'join_error' avec message; n'apparaît pas dans participants. Et à disconnect: `leave_room(room_id)` appelé
- **Pass Condition**: Code handle_join vérifie len >= max; handle_disconnect appelle leave_room
- **Evidence**: Diff routes.py handle_join + handle_disconnect

### AC-6: Erreur syntaxe JS billingTick corrigée
- **Type**: `rule`
- **Given**: Templates room.html ligne billingTick `${FREE_MINUTES minit...`
- **When**: Browser parse le script
- **Then**: Aucune `SyntaxError` dans console; timer fonctionne jusqu'à FREE_MINUTES
- **Pass Condition**: Fermeture correcte `}` après FREE_MINUTES
- **Evidence**: Diff room.html + test console navigateur sans erreur

### AC-7: CSS SaaS premium quality (rubric composite)
- **Type**: `rubric`
- **Dimension**: Qualité visuelle & UX globale (glassmorphism, micro-animations, accessibilité, responsive)
- **Scale**: 1-5
- **Anchors**:
  - 1 = CSS existant inchangé, aucun glassmorphism
  - 3 = Glassmorphism appliqué aux cards mais peu de transitions, focus outline par défaut
  - 5 = Glassmorphism uniforme cards/controls/modals/toasts; micro-animations hover/active partout; `:focus-visible` ring sur tous éléments; `prefers-reduced-motion` respected; responsive breakpoints 480/768/992 fonctionnels
- **Pass Threshold**: >= 4
- **Evidence**: Visuel rendu de index.html + room.html (screenshot navigateur ou diff CSS)

## Open Questions
- Aucune — toutes les contraintes sont connues via mémoire projet et audit code.
