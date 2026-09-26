# KONFERANS — Corrections Live / WhatsApp / Kadr Tite (17 sept 2026)
## Plan + validation

## Recherche sur le dépôt (Conclusions)

### Déjà livré et vérifié ✅ (non retouché)
- **K-1 → K-4** (plan `konferans-suite-sept2026_plan.md`) : `upload_media` pre-check content_length + HTTP 413, labels caméra Devan/Deryè, bouton `flipCameraBtn` + `flipCamera()`, iframe/PDF fullscreen CSS → présents ; `_smoke_konferans_stream.py` = ALL PASSED.
- **Backend live-streaming** : `/api/stream/start|stop|status|platforms`, modèle `KonferansStreamSession` (clé RTMP **jamais** stockée, seulement masquée), migration idempotente `_migrate_konferans_stream.py`, `_smoke_konferans_render.py` = RENDER TEST PASSED.

### 4 bugs résiduels identifiés en relisant le code livré (17 sept, 14h)
| # | Sévérité | Catégorie | Description | Localisation |
|---|---|---|---|---|
| **K-5** | HAUT (UX) | Branche morte JS | `openStreamSetup()` commence par `if (!STREAM_PLATFORMS[platform]) return;` **AVANT** la branche `titleframe`. Or `STREAM_PLATFORMS` (JS) ne contient que `facebook/youtube/tiktok/custom/whatsapp` → l'item de menu **« Kadr Tite (PNG) »** retourne immédiatement : `downloadTitleFramePNG()` n'est **jamais** appelé. | `templates/konferans/room.html` L3290-3296 |
| **K-6** | FAIBLE | SQLAlchemy 2.x | Dernier `Query.get()` legacy du module : `KonferansStreamSession.query.get(...)` (déprécié SQLAlchemy 2.x). Le reste du projet utilise `db.session.get(Model, pk)` (4 usages, 0 `Query.get`). | `konferans/routes.py` L1286 |
| **K-7** | MOYEN (état) | Session fantôme | Si le propriétaire ferme l'onglet / perd la connexion pendant un Live, `room_stream_sessions[room_id]` reste **live en RAM** et la ligne DB reste `status='live'`, `stopped_at=NULL` → bannière rouge **LIVE** collée pour tous, `duration_seconds` perdu, session orpheline. `handle_disconnect` ne faisait aucun nettoyage stream. | `konferans/routes.py` L726-773 |
| **K-8** | MOYEN (robustesse) | null track | `disableTitleFrameOverlay()` appelait `replaceTrackForAll(st.newTrack, st.oldTrack \|\| null, …)` → `SimplePeer.replaceTrack(old, null, stream)` peut lever une `TypeError` (`MediaStream.addTrack(null)`) quand il n'y a pas de caméra d'origine. | `templates/konferans/room.html` L3601 |

---

## Fichiers et modules à modifier

1. **`templates/konferans/room.html`**
   - K-5 : branche `titleframe` déplacée **au-dessus** du garde `STREAM_PLATFORMS`.
   - K-8 : restauration de la track caméra uniquement si `st.oldTrack` existe.
2. **`konferans/routes.py`**
   - K-7 : helper unique `_stop_stream_session(room_id, reason)` (RAM + DB + broadcast), utilisé par la route HTTP **et** par `handle_disconnect`.
   - K-6 : `db.session.get(KonferansStreamSession, id)` dans ce helper.
3. **`_smoke_konferans_fixes.py`** (nouveau) — validations V-K5 → V-K8 + page invité + non-régression.

## Étapes d'implémentation (ordre de dépendance)

### Étape 1 — K-5 (branche morte « Kadr Tite »)
- `titleframe` évalué en premier, garde plateforme ensuite ; le reste de `openStreamSetup` (champs RTMP / WhatsApp / dashboard) est inchangé.

### Étape 2 — K-8 (null track)
- `if (st.oldTrack) replaceTrackForAll(st.newTrack, st.oldTrack, localStream);` ; `st.newTrack.stop()` + remise en place dans `localStream` inchangés.

### Étape 3 — K-7 (session fantôme)
- `_stop_stream_session(room_id, reason='manual')` : (1) `pop` RAM ; (2) `db.session.get()` → `status='stopped'`, `stopped_at`, `duration_seconds` (rollback silencieux) ; (3) `_so_emit_stream('streaming_stopped', payload)` avec `stopped_reason`.
- `/api/stream/stop/<room_id>` délègue entièrement au helper → **404** si rien de live (comportement du smoke #8 préservé).
- `handle_disconnect` : mémorise `was_owner` avant `pop`, puis auto-stop si `was_owner` **ou** salle vide (`'owner_disconnect'` / `'room_empty'`).
- **Preserve-First** : aucune autre ligne de `handle_disconnect` modifiée (screen share, mains levées, breakouts intacts).

### Étape 4 — Validation
- `py_compile` + smoke live-stream existant + render existant + nouveau `_smoke_konferans_fixes.py`.

---

## Dépendances et considérations

- **0 nouvelle dépendance** (Python/JS) ; aucune migration DB supplémentaire (`status`, `stopped_at`, `duration_seconds` existent déjà).
- Le helper est appelé uniquement en contexte requête/socket → `db.session` disponible ; erreurs DB avalées (`rollback`) pour ne jamais casser un `disconnect`.
- `_so_emit_stream` est déjà protégé (try/except) : un échec de broadcast ne remonte pas dans le handler `disconnect`.

## Validation

| Test | Commande / Action | Critère |
|---|---|---|
| **V-K5a** ordre des branches | `_smoke_konferans_fixes.py` — `titleframe` trouvé avant le garde dans `openStreamSetup` | OK |
| **V-K5b** page owner | `_smoke_konferans_render.py` | RENDER TEST PASSED |
| **V-K6** legacy SQLAlchemy | `grep -c "\.query\.get(" konferans/routes.py` | 0 |
| **V-K6b** `db.session.get` présent | `grep -c "db.session.get(" konferans/routes.py` | ≥ 1 |
| **V-K7a** helper présent | `grep -n "_stop_stream_session" konferans/routes.py` | 3 (déf + route + disconnect) |
| **V-K7b** auto-stop fonctionnel | start Live (owner) → `_stop_stream_session(ROOM_ID, 'owner_disconnect')` → RAM vidée + ligne DB `stopped` + `stopped_at` + `duration_seconds` + `stopped_reason` | OK |
| **V-K7c** 404 si rien de live | `/api/stream/stop` après nettoyage | 404 |
| **V-K7d** idempotence | 2ᵉ appel `_stop_stream_session` | `None`, pas de broadcast |
| **V-K8** garde oldTrack | `grep -n "if (st.oldTrack) replaceTrackForAll"` | 1 |
| **V-K8b** JS équilibré | tokenizer `_dbg_js_balance.check_js_balance` (page rendue) | OK |
| **V-Guest** page invité | aucun marqueur owner (`streamMenuBtn`, `streamModal`, `stopStreamItem`, `openStreamSetup`, `startWhatsAppSave`, `buyTimeBtn`) + `konf-live-banner` + `liveStatus` présents | OK |
| **V-Reg** non-régression | `_smoke_konferans_stream.py` + `_smoke_konferans_render.py` | PASSED |
| **V-Compile** | `python -m py_compile konferans/routes.py app/models/konferans.py` | exit 0 |

## Risques et gestion

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| L'auto-stop sur `disconnect` coupe un Live lors d'un simple reload de la page owner | Moyenne | Faible | Comportement attendu : la capture navigateur s'arrête aussi au reload, et le propriétaire relance d'un clic (menu Live immédiat). Durée + statut sont persistés (aucune donnée perdue). |
| Double appel `_stop_stream_session` (stop HTTP puis disconnect) | Haute | Nul | `pop` atomique → le 2ᵉ appel renvoie `None` sans broadcast ni écriture DB (vérifié V-K7d). |
| `db.session.get` indisponible (SQLAlchemy < 1.4) | Très faible | Moyen | Le projet est déjà en SQLAlchemy 2.x (`db.session.get` utilisé 4× ailleurs, `Query.get` = 0). |
| Le test statique K-5 dépend du formatage du template | Faible | Faible | Le regex cible la signature exacte de `openStreamSetup` ; toute modification future qui casse l'extraction fait échouer le test explicitement (`K-5 openStreamSetup extractable`). |
