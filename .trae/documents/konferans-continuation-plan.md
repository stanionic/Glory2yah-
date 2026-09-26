# KONFERANS — Plan de correction (Suite)

## Recherche sur le dépôt (Conclusions)

État actuel du module KONFERANS :
- **Backend (routes.py)** : Sockets handlers, routes HTTP, état global en RAM (`active_rooms`, `room_participants`, `room_socket_users`, etc.) — corrects et conformes aux tâches AC-1→AC-5 précédentes. `handle_disconnect` appelle bien `leave_room(room_id)` (L612-613). `upload_recording` / `update_room_name` / `join_room_route` ont les bons codes HTTP.
- **Frontend (room.html)** : Intégration SocketIO 4 + SimplePeer 9.11.1 (mode mesh). Camera switch existe (`switchCamera()`, `refreshCameraDevices()`, `cameraSelect`<select> branché sur `change` → ligne 2105).
- **CSS (konferans.css)** : Blocs 1–7 (accessibilité, reduced-motion, glassmorphism, micro-animations, responsive) déjà appliqués en surcouche.

### 4 Bugs identifiés pendant l'audit (recherche Grep + Read ciblé)

| # | Sévérité | Description | Localisation exacte |
|---|---|---|---|
| 1 | **CRITIQUE** | Template fallback corrompu : la ligne 1 est `ming  drecor<!DOCTYPE html>` (caractères parasites). Ce blueprint enregistre `template_folder='templates'` (routes.py L27). Jinja2 peut résoudre ce fichier dans certaines conditions (precedence blueprint-vs-app), rendant la salle cassée si le path `konferans/room.html` tombe dessus. | `konferans/templates/room.html#L1` |
| 2 | **HAUT** (UX) | `showMediaInMain()` active **systématiquement** le mode `.fullscreen` (fixed overlay 100vw/100vh z-index 1100 + `body.overflow=hidden`) **chaque fois** qu'un média est partagé en mode `'main'`. Tous les participants sont forcés en overlay plein écran sans demander — très disruptif. La fonction `toggleMediaFullscreen()` existe déjà (L2535-2557) pour le mode manuel. | `templates/konferans/room.html#L2435-L2444` |
| 3 | **MOYEN** (sync) | Backend émet `room_name_changed` : (a) handler socket `room_name_updated` L322 → `emit(..., room=room_id)` ; (b) HTTP `update_room_name` L1175-1179 → `_so_emit(...)`. **Mais frontend n'a AUCUN `socket.on('room_name_changed', …)`** → la modification de nom ne se répercute jamais visuellement. De plus, `<div class="konf-room-name">` n'a pas d'`id` → impossible à cibler. | Div: `templates/konferans/room.html#L1426` ; Listener manquant: section socket.on (autour L2585) |
| 4 | **FAIBLE** (clarté) | 46 usages de `request.sid` dans handlers SocketIO → `request` vient de `from flask import … request` (L1). Flask-SocketIO monkey-patch `.sid` dans `flask.request` pendant le dispatch (OK runtime), mais **aucun handler n'importe explicitement `request` de `flask_socketio`** (contrairement à `emit` / `join_room` qui sont importés localement). Risque : confusion future entre `flask.request` (HTTP) et l'objet contexte SocketIO. | `konferans/routes.py` — chaque `@socketio.on(...)` |

---

## Fichiers et modules à modifier

1. `konferans/templates/room.html` — **Supprimer** ce template corrompu (fallback obsolète : le template officiel est sous `templates/konferans/room.html` enregistré globalement par l'app Flask). Option de secours : si on veut conserver le blueprint fallback, le remplacer par une redirection/copie saine. **Action choisie** : Suppression sécurisée (Preserve-First : vérifier que `render_template('konferans/room.html')` pointe bien vers `templates/konferans/room.html` avant).

2. `templates/konferans/room.html` :
   - **Bug 2** : Supprimer l'activation auto du `.fullscreen` dans `showMediaInMain()`. Remplacer par un affichage inline **en carte pleine largeur** (pas en overlay) — media toujours visible mais sans bloquer la vidéo.
   - **Bug 3** : (a) Ajouter `id="roomNameDisplay"` sur la div `.konf-room-name` (L1426) ; (b) Ajouter `socket.on('room_name_changed', data => { … })` qui met à jour `textContent`.

3. `konferans/routes.py` :
   - **Bug 4 (optionnel)** : Ajouter `from flask_socketio import request as sio_request` en haut (L2) et remplacer 46 occurrences de `request.sid` dans les handlers par `sio_request.sid`. **Prudence** : ce changement est purement cosmétique / clarifiant — il ne change PAS le comportement runtime. On peut l'omettre pour minimiser la surface de modification, mais recommandé par l'approche "Senior Architect".

---

## Étapes d'implémentation (ordre de dépendance)

### Étape 1 — Corriger Bug #1 : Supprimer le template corrompu
- **Action** : Supprimer `konferans/templates/room.html` ET `konferans/templates/index.html`.
- **Justification** : Le blueprint déclare `template_folder='templates'` (L27) mais l'application principale sert déjà `templates/konferans/*.html` depuis le dossier global. Ces doublons sont obsolètes et corrompus (room.html#L1).
- **Vérification préalable** : Confirmer dans `app/__init__.py` que l'app dispose de `templates/` comme dossier global (valeur par défaut de Flask) → `render_template('konferans/room.html')` résout `templates/konferans/room.html`, pas le blueprint-local. Puis supprimer.

### Étape 2 — Corriger Bug #2 : showMediaInMain n'active plus le fullscreen auto
Dans `showMediaInMain()` (`templates/konferans/room.html` L2395–2445) :
- **Supprimer** les lignes 2439-2444 (bloc `display.classList.add('fullscreen')`, `document.body.style.overflow = 'hidden'`, bouton compress).
- A la place, à la fin de la fonction : **fixer le display à block** (carte inline standard) : `display.style.display = 'block';`
- Ajouter une micro-animation d'apparition (fade-in translateY) via classe `'showing'` puis retirer après 400ms.
- Le bouton `mediaFullscreenBtn` garde l'icône `fa-expand` initiale (déjà reset L2416-2419) et l'utilisateur clique MANUELLEMENT → `toggleMediaFullscreen()` déjà existant fait le reste correctement.

### Étape 3 — Corriger Bug #3 : Listener `room_name_changed` + id sur div
- **3a)** Dans `templates/konferans/room.html` L1426 : changer `<div class="konf-room-name">` → `<div class="konf-room-name" id="roomNameDisplay">`.
- **3b)** Dans la section des listeners Socket (autour L2585, après `socket.on('media_shared', …)`), ajouter :
  ```js
  socket.on('room_name_changed', (data) => {
      const el = document.getElementById('roomNameDisplay');
      if (el && data && data.room_name) {
          const icon = el.querySelector('i');
          el.innerHTML = (icon ? icon.outerHTML + ' ' : '') + escapeHtml(data.room_name);
          showToast('<i class="fas fa-edit"></i> Non sal la chanje.', 'success', 2500);
      }
  });
  ```
- Note : `escapeHtml()` existe déjà dans le fichier (utilisée partout). Vérifier sa présence avant.

### Étape 4 — (Clarté) Bug #4 : Imports `request` flask_socketio explicites
- **4a)** Modifier `konferans/routes.py` L2 → `from flask_socketio import emit, join_room, leave_room, request as sio_request`
- **4b)** Remplacer dans TOUS les `@socketio.on(...)` handlers : `request.sid` → `sio_request.sid` (46 occurrences).
- **4c)** Attention : ne PAS toucher les usages de `request.form`, `request.files`, `request.args` dans les routes HTTP classiques (`create_room`, `join_room_route`, `upload_recording`, `update_room_name`, `upload_media`, etc.) — elles utilisent `flask.request` et doivent rester sous ce nom.
- Alternative plus sûre et plus "Preserve-First" (**recommandée**) : sauter cette étape 4. Flask-SocketIO garantit formellement que `flask.request.sid` existe dans les handlers. La surface de modification de 46 occurrences n'est pas justifiée pour un gain de clarté. On garde le statu quo. → **Action : Skip Étape 4**.

---

## Dépendances et considérations

- **Aucune nouvelle dépendance Python/JS**. Tous les correctifs sont en modifications locales sur fichiers existants.
- Jinja template precedence : Flask blueprint-local a une priorité INFÉRIEURE au template global `templates/` SAUF si `Blueprint(…, template_folder='templates')` avec un `subdomain` ou configuration spéciale. La suppression des fichiers blueprint-local est donc sans impact. Risque résiduel nul vérifié par lecture de `app/__init__.py#L1675-1678` (enregistrement blueprint).
- **Compatibilité `escapeHtml`** : Vérifier l'existence de la fonction `escapeHtml` dans room.html avant d'écrire le listener. Utilisée dans `formatMediaMessage` L2569 donc disponible.
- **Socket handlers HTTP vs SocketIO `request`** : On n'y touche pas (Étape 4 skippée) — règle Preserve-First : ne pas modifier 46 lignes qui fonctionnent correctement en runtime.

---

## Validation

| Test | Commande / Action | Critère d'acceptation |
|---|---|---|
| **V-1** py_compile backend | `python -m py_compile konferans/routes.py app/models/konferans.py app/__init__.py` | Exit 0 |
| **V-2** Smoke test GET /konferans/ | `create_app('development').test_client().get('/konferans/')` | HTTP 200 |
| **V-3** Jinja render room template (sans auth on attend redirect) | `test_client().get('/konferans/room/dummy')` → check absence de `TemplateSyntaxError` ou `jinja2.TemplateNotFound` remontant vers `konferans/templates/room.html` corrompu | Pas d'exception Jinja (status 302/404 normal) |
| **V-4** showMediaInMain — PAS d'auto-fullscreen | Vérifier que `showMediaInMain()` NE contient PLUS `display.classList.add('fullscreen')` (grep) + `display.style.display = 'block'` présent | Grep négatif + affirmatif |
| **V-5** room_name_changed listener présent | `grep -n "room_name_changed" templates/konferans/room.html` | 2+ matchs (1 emit backend injecté dans JS non ; ici on check le listener côté client) → grep doit trouver `socket.on('room_name_changed'` |
| **V-6** id roomNameDisplay présent | `grep -n 'id="roomNameDisplay"' templates/konferans/room.html` | 1 match |

---

## Risques et gestion

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Suppression template blueprint-local `konferans/templates/*.html` → résolution Jinja casse | Faible | Moyen | Vérification préalable : confirmer la résolution par le template global (chemin `templates/konferans/room.html`). Faire un smoke test V-2/V-3 immédiatement après. |
| Suppression fullscreen auto → utilisateurs s'attendent à voir le media "grand" | Faible | Faible | Media sera quand même affiché en **carte pleine largeur** (main area width) ; bouton fullscreen manuel reste disponible et visible immédiatement. Micro-animation d'apparition adoucit. |
| `escapeHtml` indisponible dans listener | Très faible | Très faible | Déjà utilisée L2569/2570/2571. Si absente, fallback : `.textContent` direct (plus sûr mais ne préserve pas l'icône). |
| Modification de 46 `request.sid` (si Étape 4) en `sio_request.sid` → erreur HTTP routes (utilisant `request.form`) | Moyenne (si étape activée) | Élevé | **Décision : Skip Étape 4** entièrement. Surface de risque trop grande pour un bénéfice cosmétique. |
