# KONFERANS STUDIO — Phase 1 : audit et sécurisation

*Document produit avant toute modification fonctionnelle. Aucune ligne du module KONFERANS n'a été
modifiée ; seuls des tests ont été corrigés/ajoutés (voir §5). Rien n'est commité.*

**Légende des preuves** : ✅ vérifié par un test ou une expérience exécutée · 📄 présent dans le code, non exécuté ·
⚠️ risque observé · ❓ non vérifiable depuis cet environnement.

## 1. Périmètre réel du module (mesuré)

| Élément | Mesure |
|---|---|
| Paquet `konferans/` | `routes.py` (~3 400 lignes), `stream_relay.py`, `facebook_live.py`, `subscription.py`, … (~4 200 lignes Python) |
| Modèles (`app/models/konferans.py`) | salles, participants, enregistrements, sessions de diffusion, connexions de plateformes |
| Templates | salle de conférence (5 761 lignes) + pages d'accueil/liste |
| Routes HTTP | **24** |
| Événements Socket.IO | **47** |

### 1.1 Routes HTTP (générées depuis le code)
| Chemin | Méthodes | Fonction |
|---|---|---|
| `/` | GET | `index` |
| `/create_room` | POST | `create_room` |
| `/join_room` | POST | `join_room_route` |
| `/check_room/<room_code>` | GET | `check_room` |
| `/room/<room_code>` | GET,POST | `room` |
| `/api/billing/<room_id>` | GET | `get_billing_state` |
| `/api/subscription/<room_id>` | GET | `get_subscription_state` |
| `/api/subscription/pay` | POST | `pay_subscription` |
| `/api/charge_hour/<room_id>` | POST | `charge_gkach_hour` |
| `/api/invite/<room_id>` | GET | `get_invite` |
| `/facebook/connect/<room_id>` | GET | `facebook_connect` |
| `/facebook/callback` | GET | `facebook_callback` |
| `/api/facebook/status/<room_id>` | GET | `facebook_status` |
| `/api/stream/start/<room_id>` | POST | `start_stream_session` |
| `/api/stream/stop/<room_id>` | POST | `stop_stream_session` |
| `/api/stream/status/<room_id>` | GET | `stream_status` |
| `/api/stream/platforms` | GET | `stream_platforms` |
| `/upload_recording/<room_id>` | POST | `upload_recording` |
| `/api/recording/register` | POST | `register_device_recording` |
| `/api/room/<room_id>/allow_download` | POST | `set_allow_download` |
| `/api/recordings/<room_id>` | GET | `list_room_recordings` |
| `/update_room_name` | POST | `update_room_name` |
| `/download_recording/<filename>` | GET | `download_recording` |
| `/upload_media` | POST | `upload_media` |

### 1.2 Événements Socket.IO par domaine (générés depuis le code)
| Domaine | Nb | Événements |
|---|---|---|
| Autres | 2 | `reject_user`, `room_name_updated` |
| Chat / interaction | 6 | `chat_message`, `lower_hand`, `poll_close`, `poll_create`, `poll_vote`, `raise_hand` |
| Enregistrement / diffusion | 5 | `start_recording`, `stop_recording`, `stream_chunk`, `stream_start`, `stream_stop` |
| Facturation / stats | 2 | `billing_ping`, `connection_stats` |
| Modération / salle | 8 | `admit_all_waiting`, `admit_user`, `breakout_create`, `breakout_return`, `kick_participant`, `mute_remote_audio`, `mute_remote_video`, `update_room_locks` |
| Signalisation / appel | 5 | `breakout_join`, `disconnect`, `join`, `screen_ice_candidate`, `sending_signal` |
| Tableau blanc / médias | 13 | `media_annotation`, `media_annotation_clear`, `media_annotation_remove`, `media_annotation_undo`, `media_view`, `screen_answer`, `screen_offer`, `share_media`, `start_screen_share`, `stop_screen_share`, `whiteboard_clear`, `whiteboard_draw`, `whiteboard_undo` |
| Téléchargements | 6 | `dl_approve`, `dl_cancel`, `dl_chunk`, `dl_complete`, `dl_deny`, `dl_request` |

## 2. Inventaire des fonctionnalités existantes

L'énoncé demandait de ne pas supposer l'existence des fonctions : voici l'état **constaté**.

| Fonctionnalité | Fichier / module | État constaté | Action |
|---|---|---|---|
| Salles virtuelles (création, accès, propriétaire) | `konferans/routes.py`, modèles | 📄 présent | Préserver |
| Signalisation WebRTC (maillage pair-à-pair) | `sending_signal`, `returning_signal` | ✅ relais livré aux membres de la même salle, jamais aux étrangers (test client réel) | Préserver |
| Chat, mains levées, sondages | événements `chat_*`, `hand_*`, `poll_*` | 📄 présent | Préserver |
| Modération (muet, exclusion, verrous, salle d'attente, ateliers) | événements dédiés | 📄 présent ; autorisations de base ✅ (tests existants) | Préserver |
| Tableau blanc, annotation de médias | `whiteboard_*`, `media_*` | ✅ un socket non joint ne peut pas modifier le tableau | Préserver |
| Partage d'écran | événements `screen_*` | 📄 présent | Préserver |
| Enregistrement + téléchargement | `upload_recording`, `download_recording` | 📄 présent (extensions autorisées, 512 Mo max, `secure_filename`) | Préserver |
| Octrois de téléchargement (`dl_*`) | 6 événements | ✅ un socket étranger ne peut pas annuler l'octroi d'autrui | Préserver |
| Facturation (accès gratuit/payant) | `_billing_gate` | 📄 décision **côté serveur** | Préserver, ne pas toucher |
| Diffusion Facebook Live (RTMP) | `stream_relay.py`, `facebook_live.py` | 📄 un processus FFmpeg **par salle**, **une seule destination** ; clé jamais stockée (forme masquée), jeton Facebook chiffré | Préserver puis étendre |
| YouTube Live, TikTok Live | modèle `KonferansPlatformConnection`, références | ❓ références présentes, **fonctionnement non vérifié** (aucun compte réel) | À vérifier avant d'y toucher |
| Multistream (plusieurs destinations simultanées) | — | **absent** (1 destination/salle) | À construire (phase 6) |
| Éditeur vidéo, habillage, assistant IA | — | **absents** | À construire (phases 4, 5, 7) |

## 3. Risques identifiés (classés)

### R1 — ÉLEVÉ, reproduit : serveur web incompatible avec le temps réel
`render.yaml` / `Procfile` démarrent gunicorn avec **4 workers `sync`**. Socket.IO tourne en mode *threading*
(aucun `eventlet`/`gevent`/`simple-websocket` dans `requirements.txt`) donc en *long-polling* uniquement.
Expérience (`tools/konferans_realtime_probe.py`, 8 clients, sans Redis, local) :

| Configuration | Clients connectés | Requêtes HTTP ordinaires pendant ce temps |
|---|---|---|
| 1 worker `gthread` (témoin) | **8 / 8** | instantanées |
| **4 workers `sync` (commande du dépôt)** | **2 / 8** (un des deux s'est ensuite déconnecté) | **2 requêtes sur 6 expirent (6 s)** |

Deux causes cumulées : (a) une session Engine.IO appartient à un seul processus, or les requêtes suivantes
d'un même client peuvent arriver sur un autre worker ; (b) chaque long-polling occupe un worker `sync`, donc
quelques participants suffisent à bloquer **tout le site**. ❓ À confirmer contre la configuration réellement
déployée sur Render (non consultable ici) ; la file de messages Redis du déploiement corrige la diffusion entre
workers mais pas l'affinité de session ni l'occupation des workers.
**Pourquoi c'est bloquant pour le Studio** : le relais FFmpeg et le multistream gardent leur état dans un
dictionnaire **propre au processus** ; les fragments vidéo d'un navigateur doivent donc toujours atteindre le
processus qui possède FFmpeg.
**Options** (décision requise) : A) service Web séparé pour `/socket.io` (1 worker `gthread`/`eventlet`),
le site garde ses 4 workers ; B) 1 seul worker `gthread` (≥ 64 threads) pour toute l'application ;
C) plusieurs workers avec affinité de session (non établie sur l'hébergement actuel).
**À valider par la sonde sur un environnement de test avant tout déploiement.**

### R2 — MOYEN : stockage
Disque persistant Render de **1 Go** partagé (envois, enregistrements, sessions). Les fichiers sont servis sous
`static/` : accessibles par simple URL, ce qui contredit l'exigence « projets privés ». Un éditeur vidéo et des
exports MP4 dépasseront 1 Go très vite ⇒ stockage objet compatible S3 (ou disque plus grand) + accès contrôlé.

### R3 — MOYEN : charge CPU du multistream
Le navigateur envoie du WebM (VP8/VP9 + Opus) ; RTMP exige H.264/AAC ⇒ **un transcodage** est inévitable.
Conception retenue : **un seul encodage** puis diffusion vers N destinations (`tee`/sorties multiples), jamais
un encodage par plateforme. La capacité du plan Render actuel n'a pas été mesurée ❓.

### R4 — FAIBLE : URL d'ingestion
Le serveur n'exige que le préfixe `rtmp://` ou `rtmps://` : aucune liste d'hôtes autorisés, aucun blocage des
adresses privées ⇒ un utilisateur autorisé peut faire ouvrir au serveur des connexions sortantes arbitraires.
Correctif prévu avec le multistream : liste d'hôtes des plateformes + refus des plages privées.

### R5 — INFORMATIF
* TikTok : l'accès au direct et la clé de diffusion dépendent des règles de TikTok et du compte ❓ ; rien n'est
  supposé identique à Facebook/YouTube.
* Redis (Render « keyvalue », plan gratuit) : adapté à la file de messages/cache, pas au stockage de médias.
* FFmpeg : binaire statique via `imageio-ffmpeg` en production (pas de FFmpeg système sur Render).
* Facturation : décision côté serveur ; aucune modification prévue.

## 4. Base de non-régression

| Suite | Résultat |
|---|---|
| Tests d'autorisation Socket.IO existants (3) | ✅ 3/3 |
| **Nouveaux** tests temps réel sur serveur vivant (3) | ✅ 3/3 |
| Suite complète du dépôt | voir rapport de livraison |
| Non couvert | médias WebRTC réels dans un navigateur, exécution FFmpeg du relais, YouTube/TikTok, mobile |

## 5. Corrections apportées en Phase 1 (démontrées uniquement)

1. **Test faussement rouge** `test_signaling_requires_both_sockets_in_same_room` : il échouait depuis le début.
   Cause : avec `python-socketio 5.9` + `Flask-SocketIO 5.3.4`, le client de test en processus **ne capture pas**
   les émissions ciblant une salle (même un `socketio.emit(room=sid)` direct) ; la livraison réelle fonctionne
   (prouvé avec de vrais clients). Le test enregistre maintenant ce que le gestionnaire émet, avec des
   assertions *plus strictes* (destinataire exact, expéditeur, nom). Les deux autres tests du fichier sont
   inchangés (octet pour octet).
2. **Nouveau** `tests/test_konferans_realtime_live.py` : 3 tests sur serveur vivant (connexion, livraison aux
   membres / jamais aux étrangers, rejet de l'auto-signalisation et des destinataires inconnus).
3. **Nouveau** `tools/konferans_realtime_probe.py` : sonde reproductible (R1).
*Incident évité* : ma première réécriture du fichier de test avait supprimé deux tests voisins ; détecté,
restauré depuis git et vérifié identique avant de poursuivre.

## 6. Sauvegarde et retour arrière (à appliquer avant la Phase 2)

* Code : tout est non commité ⇒ créer une branche dédiée (`git switch -c konferans-studio`) et un tag de
  restauration sur l'état actuel de `main`.
* Base de données : `pg_dump` de la base Render **avant** toute migration (❓ je n'ai pas accès à la base).
* Migrations : **additives uniquement** (nouvelles tables `studio_*`), aucune colonne existante modifiée.
* Interrupteur : toute nouvelle section derrière une variable d'environnement (`KONFERANS_STUDIO_ENABLED`) ⇒
  retour arrière = désactiver la variable, sans redéploiement de l'ancien code.

## 7. Plan et décisions requises

| Phase | Contenu | Dépend de |
|---|---|---|
| 2 | Stabiliser : trancher R1 (A/B/C), valider par la sonde en test | **Décision A/B/C** |
| 3 | Centre de contrôle (navigation, rôles) en simple ajout, interrupteur | — |
| 4 | Frame Studio : modèles, aperçu, export d'image/vidéo d'habillage | stockage (R2) |
| 5 | Éditeur de projets (canvas/timeline) + médiathèque + export FFmpeg en tâche de fond | stockage (R2), file de tâches |
| 6 | Multistream : encodage unique, N sorties, surveillance, reconnexion, liste d'hôtes (R4) | R1 réglé |
| 7 | Assistant IA facultatif (sans dépendance obligatoire) | clé API optionnelle |
| 8 | Tests finaux, documentation, déploiement | — |
