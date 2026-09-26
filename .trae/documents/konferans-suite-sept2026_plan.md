# KONFERANS — Suite corrections (Septembre 2026)
## Plan d'implémentation

## Recherche sur le dépôt (Conclusions)

### État actuel — Ce qui est DÉJÀ corrigé (4 bugs du plan précédent — TOUS OK ✅)
Audit Grep/Read du 16 sept 2026 a confirmé:
1. ✅ Bug #1 (Template corrompu blueprint) : Fichiers `konferans/templates/*.html` **supprimés** — `Glob` retourne "No file found". Jinja résout bien `templates/konferans/room.html` global.
2. ✅ Bug #2 (Auto-fullscreen disruptif) : `showMediaInMain()` ligne 2406-2450 — `display.classList.add('showing')` + `display.style.display='block'` inline, AUCUN `.fullscreen` n'est ajouté automatiquement. Seulement le bouton manuel `toggleMediaFullscreen()` active le mode overlay.
3. ✅ Bug #3 (room_name_changed sync manquante) : 
   - Div `<div class="konf-room-name" id="roomNameDisplay">` présente L1436
   - Listener `socket.on('room_name_changed', …)` complet avec `escapeHtml()` + toast Créole L2598-2605
   - Backend emit: routes.py L322 (socket handler) + L1176 (HTTP update_room_name) → OK
4. ✅ Bug #4 (request.sid imports) : Skip confirmé (Preserve-First : 46 occurrences runtime OK via Flask-SocketIO monkey-patch). Surface de risque trop grande.

### 4 NOUVEAUX bugs identifiés lors de la reprise
| # | Sévérité | Catégorie | Description | Localisation exacte |
|---|---|---|---|---|
| **K-1** | MOYEN | Data Integrity + HTTP codes | Route `upload_media` : **aucun pré-check `request.content_length`** avant `file.save()` → contrairement à `upload_recording` (L1087-1092). Retourne aussi 400 sur taille max au lieu du standard **413 Payload Too Large**. | `konferans/routes.py` L1273-1284 |
| **K-2** | ÉLEVÉ (UX Prof) | Camera front/back labels | Dropdown `cameraSelect` affiche labels génériques `"Kamera 1" / "Kamera 2"` SANS heuristique Devan (Front) / Deryè (Back). Professeurs sur mobile ne savent pas quelle caméra choisir. Demande explicite utilisateur mémoire : « caméra frontale/caméra arrière lors des explications ». | `templates/konferans/room.html` L1773-1776 (forEach cameras) + L1777-1785 (selected) |
| **K-3** | ÉLEVÉ (UX Prof) | 1-click flip camera | AUCUN bouton à côté du dropdown pour basculer 1-clic devan↔deryè. Sur mobile, dropdown est petit pour un professeur qui explique debout. | `templates/konferans/room.html` L1545 (après `<select id="cameraSelect">`) |
| **K-4** | MOYEN (Fullscreen) | iframe/PDF fullscreen trop petit | CSS `.konf-media-display.fullscreen .konf-media-display-content` a `img/video` + `audio` styled, MAIS **aucune règle pour `<iframe>`** utilisé par PDF (L2441 showMediaInMain). PDF en mode "toute la fenêtre" reste petit — casse la demande utilisateur mémoire : « affichage des médias partagés sur toute la fenêtre ». | `static/css/konferans.css` L1482-1500 (après règles img/video) |

---

## Fichiers et modules à modifier

1. **`konferans/routes.py`** — Fix K-1 : Ajouter pre-check `request.content_length` sur upload_media (aligné sur upload_recording L1087-1092). Remplacer code HTTP 400 par 413 sur taille dépassée.
2. **`templates/konferans/room.html`** — Fix K-2 + K-3 :
   - K-2 : Fonction helper `_labelCamera(device, detectedFacing, index)` + mise à jour `refreshCameraDevices()` L1773 forEach heuristique label keywords (`front/user` → Devan, `back/rear/environment` → Deryè) + utilisation `track.getSettings?.().facingMode` après obtention du stream.
   - K-3 : Insérer `<button>` flip à côté du `<select id="cameraSelect">` L1545-1547. Ajouter fonction `flipCamera()` qui cycle deviceIds (préfère toggler Devan↔Deryè si identifiés, sinon next device).
3. **`static/css/konferans.css`** — Fix K-4 : Ajouter bloc sélecteurs `iframe` + fallback liens document à la suite de `video` L1490-1500, avec `width:100% / height:100% / min-height: 70vh / border:0 / background:#fff` + marge 24px cohérent avec padding du conteneur.

---

## Étapes d'implémentation (ordre de dépendance)

### Étape K-1 — upload_media : pre-check taille + HTTP 413
Dans `konferans/routes.py`, fonction `upload_media()` L1233-1310 :

- **K-1a)** Insérer APRÈS extension check (L1272) et AVANT file.save (L1278) un bloc identique à upload_recording L1086-1092 :
  ```python
  max_bytes = _MAX_MEDIA_MB * 1024 * 1024
  cl = request.content_length
  if cl is not None and cl > max_bytes:
      return jsonify({
          'success': False,
          'message': f'Dosye a twò gwo. Maksimòm: {_MAX_MEDIA_MB} MB.'
      }), 413
  ```
- **K-1b)** Modifier le post-save check taille L1281-1284 : changer code `400` → `413`.
- **Note** : `_MAX_MEDIA_MB` est déjà défini L1228 (50MB). Réutiliser variable existante, NE PAS hardcoder 50.

### Étape K-2 — Labels caméra Devan/Deryè heuristique
Dans `templates/konferans/room.html` :

- **K-2a)** Insérer helper APRÈS `cameraVideoConstraints()` (juste avant L1760 `refreshCameraDevices`) :
  ```js
  function _labelCameraByHints(device, index) {
      const raw = (device.label || '').toLowerCase();
      if (/front|user|selfie|avant|devan|fac(e|ing)\s*user/i.test(raw)) {
          return `📱 Kamera Devan — ${device.label || 'Kamera ' + (index+1)}`;
      }
      if (/back|rear|envir|arriere|derye|environment/i.test(raw)) {
          return `📷 Kamera Deryè — ${device.label || 'Kamera ' + (index+1)}`;
      }
      return device.label || `Kamera ${index + 1}`;
  }
  let _cameraFacings = {}; // deviceId -> 'user' | 'environment'
  function _detectFacingAndStore(stream, deviceId) {
      if (!stream || !deviceId) return;
      try {
          const t = stream.getVideoTracks()[0];
          if (!t) return;
          const facing = t.getSettings?.().facingMode;
          if (facing) _cameraFacings[deviceId] = facing;
      } catch(e){}
  }
  ```
- **K-2b)** Modifier `refreshCameraDevices()` L1773 forEach : changer label pour utiliser helper :
  ```js
  cameras.forEach((camera, index) => {
      let label = _labelCameraByHints(camera, index);
      if (_cameraFacings[camera.deviceId] === 'user' && !/Devan/i.test(label))
          label = '📱 ' + label.replace(/^/, 'Kamera Devan — ').replace(/Kamera Devan — Kamera Devan/, 'Kamera Devan');
      if (_cameraFacings[camera.deviceId] === 'environment' && !/Deryè/i.test(label))
          label = '📷 ' + label.replace(/^/, 'Kamera Deryè — ').replace(/Kamera Deryè — Kamera Deryè/, 'Kamera Deryè');
      select.add(new Option(label, camera.deviceId));
  });
  ```
- **K-2c)** Injecter detection facing sur track obtenu : Dans `switchCamera()` L1810, après `localStream.addTrack(newTrack)` et avant refreshDevices, ajouter :
  ```js
  _detectFacingAndStore(newStream, deviceId);
  ```
- **K-2d)** Dans initMedia (après L2063 `addVideoStream('local', localStream, …)`) :
  ```js
  const initCamId = (qualityProfiles[currentQuality]?.video
      ? (localStream.getVideoTracks()[0]?.getSettings?.().deviceId || cameras[0]?.deviceId)
      : null);
  if (initCamId) _detectFacingAndStore(localStream, initCamId);
  ```

### Étape K-3 — Bouton flip caméra 1-click + fonction `flipCamera()`
Dans `templates/konferans/room.html` :

- **K-3a)** Bloc HTML L1545-1547 : INSÉRER bouton APRÈS le select, avant le `</div>` / prochain bouton :
  ```html
  <button type="button" class="konf-mini-btn" id="flipCameraBtn" onclick="flipCamera()" title="Bakoulé kamera devan/deryè" aria-label="Bakoulé kamera">
      <i class="fas fa-sync-alt"></i>
  </button>
  ```
- **K-3b)** Fonction JS à insérer APRÈS `switchCamera()` L1825 :
  ```js
  async function flipCamera() {
      const all = Array.from(document.querySelectorAll('#cameraSelect option'))
          .map(opt => ({ id: opt.value, label: opt.textContent }))
          .filter(o => o.id);
      if (!all.length) return;
      const select = document.getElementById('cameraSelect');
      const curId = select?.value || selectedCameraId || '';
      let nextId;
      // Toggle pref: user<->environment si détecté
      const curFacing = _cameraFacings[curId];
      if (curFacing) {
          const target = curFacing === 'user' ? 'environment' : 'user';
          const pair = all.find(o => _cameraFacings[o.id] === target);
          if (pair) { nextId = pair.id; }
      }
      if (!nextId) {
          // Fallback: index+1 circulaire
          const idx = all.findIndex(o => o.id === curId);
          nextId = all[(idx + 1) % all.length]?.id;
      }
      if (nextId && nextId !== curId) {
          await switchCamera(nextId);
      } else {
          showToast('<i class="fas fa-info-circle"></i> Se sèl kamera ki disponib.', 'info', 2500);
      }
  }
  ```

### Étape K-4 — iframe/PDF 100% en fullscreen media
Dans `static/css/konferans.css`, APRÈS règle `.fullscreen … content audio` L1497-1500 et AVANT commentaire `/* ===== Media Position Controls =====` L1502 :

```css
.konf-media-display.fullscreen .konf-media-display-content iframe {
    width: 100%;
    height: 100%;
    min-height: 70vh;
    border: 0;
    border-radius: 4px;
    background: #ffffff;
    box-shadow: 0 8px 40px rgba(0,0,0,0.5);
}
.konf-media-display.fullscreen .konf-media-display-content .konf-media-file-link {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    padding: 24px 32px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 16px;
    font-size: 1.15rem;
    color: #ffffff;
    margin-top: 24px;
}
.konf-media-display.fullscreen .konf-media-display-content .konf-media-file-link i {
    font-size: 2rem;
    color: var(--g2y-primary-light);
}
```

---

## Dépendances et considérations

- **0 nouvelles dépendances**. Purement modifications sur fichiers existants.
- **Preserve-First garanti**: 
  - Routes.py : SEULEMENT ajouter pre-check + changer 400 → 413. Pas d'altération du workflow save/DB/media_type.
  - room.html : HELPER ajoutés en amont, modifications des forEach + ajout 1 balise `<button>` + 1 fonction, AUCUNE modification de SimplePeer / Socket handlers existants.
  - konferans.css : EXTENSION de règles existantes fullscreen. AUCUNE règle existante altérée.
- **Compatibilité mobile iOS/Safari**: `track.getSettings().facingMode` supporté iOS ≥15; fallback sur label heuristique si indisponible. `navigator.mediaDevices.enumerateDevices` labels vides avant getUserMedia sur certains navigateurs (mesure anti-fingerprint) → la 1ère acquisition remplira `_cameraFacings` via `_detectFacingAndStore`, puis `await refreshCameraDevices()` post-switch affichera bien Devan/Deryè labels.
- **upload_media HTTP 413**: Frontend `showToast` générique sur `success:false` → pas de changement frontend nécessaire. Message error body en Créole déjà prêt.

---

## Validation

| Test | Commande / Action | Critère d'acceptation |
|---|---|---|
| **V-K1** py_compile backend | `python -m py_compile konferans/routes.py` | Exit 0 |
| **V-K2** request.content_length check présent | `grep -n "request.content_length.*_MAX_MEDIA_MB" konferans/routes.py` | 1+ match (pre-check ajouté) |
| **V-K3** 413 sur upload_media taille | `grep -n "'413\|413'" konferans/routes.py \| grep -i media` | 2 matchs (pre + post) |
| **V-K4** _labelCamera helper présent | `grep -n "_labelCameraByHints\|_cameraFacings\|_detectFacing" templates/konferans/room.html` | 3+ matchs |
| **V-K5** flipCamera btn + fn présent | (a) `grep -n 'id="flipCameraBtn"' templates/konferans/room.html` → 1 match; (b) `grep -n "async function flipCamera" templates/konferans/room.html` → 1 match | 2 ok |
| **V-K6** iframe fullscreen CSS | `grep -n "\.fullscreen .*iframe\|fullscreen.*konf-media-file-link" static/css/konferans.css` | 2 matchs |
| **V-K7** Smoke GET /konferans/room | `create_app().test_client().get('/konferans/')` → HTTP 200; `…get('/konferans/room/dummy123')` → 302/404 sans Jinja TemplateNotFound | Pas d'exception |
| **V-K8** Rendu visuel room.html | Capture écran page salle via browser intégré → dropdown camera label correct, bouton flip caméra visible, section media display présente | OK visuel |

---

## Risques et gestion

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| upload_media pre-check content_length None sur multipart chunked (navigateurs anciens) | Faible | Faible | Garde post-save getsize + delete + 413 (L1280-1284). Pre-check ne bloque QUE si cl est explicite et >max. None → passe. |
| Camera heuristique Devan/Deryè labels dupliqués "Kamera Devan — Kamera Devan" sur certaines combinaisons | Moyenne | Très faible | Chaînes de remplacement anti-redondance dans refreshCameraDevices L1773 bloc modifié. |
| iOS Safari getUserMedia refuse track.replaceTrack() switch camera | Moyenne | Moyen | switchCamera déjà try/catch + rollback selectedCameraId/select.value (L1819-1823). flipCamera délègue purement à switchCamera, garde safety. |
| iframe fullscreen brise contenus non-PDF (site web externe sandbox) | Faible | Faible | showMediaInMain ne génère iframe QUE pour `/.pdf$/i` (L2441). Autres extensions utilisent `.konf-media-file-link` lien; CSS nouvelle règle file-link fullscreen est safe. |
