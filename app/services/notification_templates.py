"""
Notification Templates (i18n catalogue)
=======================================
Instead of storing only a final sentence, every notification stores its
`type` (+ optional `data_json` context). This module renders the title/message
in the recipient's language (ht / fr / en) and also provides the grouped
("12 personnes ont aimé…") variant used by the anti-spam aggregation.

Adding a NEW notification kind = adding ONE entry here. No schema change.
"""
from datetime import datetime, timezone

DEFAULT_LANG = 'ht'
SUPPORTED_LANGS = ('ht', 'fr', 'en')

# Categories a user can mute (spec §20/§21). Default = everything enabled.
CATEGORY_DEFAULTS = {
    'follows': True,
    'likes': True,
    'comments': True,
    'shares': True,
    'messages': True,
    'orders': True,
    'gkach': True,
    'ads': True,
    'events': True,
    'match': True,
    'system': True,
    'security': True,
    'admin': True,
}

CATEGORY_LABELS = {
    'follows': {'ht': 'Koneksyon', 'fr': 'Connexions', 'en': 'Connections'},
    'likes': {'ht': 'Renmen', 'fr': 'Likes', 'en': 'Likes'},
    'comments': {'ht': 'Kòmantè', 'fr': 'Commentaires', 'en': 'Comments'},
    'shares': {'ht': 'Pataje', 'fr': 'Partages', 'en': 'Shares'},
    'messages': {'ht': 'Mesaj', 'fr': 'Messages', 'en': 'Messages'},
    'orders': {'ht': 'Kòmand', 'fr': 'Commandes', 'en': 'Orders'},
    'gkach': {'ht': 'GKACH', 'fr': 'GKACH', 'en': 'GKACH'},
    'ads': {'ht': 'Piblisite', 'fr': 'Publicités', 'en': 'Ads'},
    'events': {'ht': 'Evennman', 'fr': 'Événements', 'en': 'Events'},
    'match': {'ht': 'MATCH', 'fr': 'MATCH', 'en': 'MATCH'},
    'system': {'ht': 'Sistèm', 'fr': 'Système', 'en': 'System'},
    'security': {'ht': 'Sekirite', 'fr': 'Sécurité', 'en': 'Security'},
    'admin': {'ht': 'Administrasyon', 'fr': 'Administration', 'en': 'Administration'},
}

# Kinds that must NEVER be aggregated away nor auto-deleted (spec §25/§41).
PROTECTED_CATEGORIES = ('orders', 'gkach', 'security', 'admin')


def _T(icon, category, priority, url, ht, fr, en, group=None):
    """Compact template factory.

    ht/fr/en = (title, message) tuples. `group` = optional
    (ht, fr, en) tuples of (title, message) used when aggregate_count > 1.
    """
    return {
        'icon': icon,
        'category': category,
        'priority': priority,
        'url': url,
        'langs': {'ht': ht, 'fr': fr, 'en': en},
        'group': dict(zip(SUPPORTED_LANGS, group)) if group else None,
    }


TEMPLATES = {
    # ────────────────────────── USERS (spec §4) ──────────────────────────
    'new_follower': _T('👤', 'follows', 'normal', '/profile/{actor_id}',
        ('Nouvo koneksyon', '{actor} ap swiv ou kounye a.'),
        ('Nouvelle connexion', '{actor} vous suit maintenant.'),
        ('New connection', '{actor} is now following you.')),
    'new_connection': _T('👤', 'follows', 'normal', '/profile/{actor_id}',
        ('Nouvo koneksyon', 'Ou gen yon nouvo koneksyon ak {actor}.'),
        ('Nouvelle connexion', 'Vous avez une nouvelle connexion avec {actor}.'),
        ('New connection', 'You have a new connection with {actor}.')),
    'welcome': _T('🎉', 'system', 'low', '/',
        ('Byenveni nan Glory2YahPub !', 'Kont ou pare. Dekouvri mache a ak GKACH ou.'),
        ('Bienvenue sur Glory2YahPub !', 'Votre compte est prêt. Découvrez le marché et vos GKACH.'),
        ('Welcome to Glory2YahPub!', 'Your account is ready. Explore the market and your GKACH.')),

    # ────────────────────────── POSTS / INTERACTIONS (§5) ──────────────────────────
    'post_like': _T('❤️', 'likes', 'low', '/post/{entity_id}',
        ('Nouvo renmen', '{actor} renmen piblikasyon ou.'),
        ('Nouveau like', '{actor} a aimé votre publication.'),
        ('New like', '{actor} liked your post.'),
        (('❤️ Plizyè moun renmen', '{actor} ak {count} lòt moun renmen piblikasyon ou.'),
         ('❤️ Plusieurs likes', '{actor} et {count} autres personnes ont aimé votre publication.'),
         ('❤️ More likes', '{actor} and {count} others liked your post.'))),
    'post_comment': _T('💬', 'comments', 'normal', '/post/{entity_id}',
        ('Nouvo kòmantè', '{actor} kòmante piblikasyon ou.'),
        ('Nouveau commentaire', '{actor} a commenté votre publication.'),
        ('New comment', '{actor} commented on your post.'),
        (('💬 Plizyè kòmantè', '{actor} ak {count} lòt moun kòmante piblikasyon ou.'),
         ('💬 Plusieurs commentaires', '{actor} et {count} autres personnes ont commenté votre publication.'),
         ('💬 More comments', '{actor} and {count} others commented on your post.'))),
    'comment_reply': _T('💬', 'comments', 'normal', '/post/{entity_id}',
        ('Repons a kòmantè', '{actor} reponn kòmantè ou.'),
        ('Réponse à votre commentaire', '{actor} a répondu à votre commentaire.'),
        ('Reply to your comment', '{actor} replied to your comment.')),
    'post_share': _T('🔄', 'shares', 'normal', '/post/{entity_id}',
        ('Piblikasyon pataje', '{actor} pataje piblikasyon ou.'),
        ('Publication partagée', '{actor} a partagé votre publication.'),
        ('Post shared', '{actor} shared your post.'),
        (('🔄 Plizyè pataje', '{actor} ak {count} lòt moun pataje piblikasyon ou.'),
         ('🔄 Plusieurs partages', '{actor} et {count} autres ont partagé votre publication.'),
         ('🔄 More shares', '{actor} and {count} others shared your post.'))),
    'post_save': _T('🔖', 'shares', 'low', '/post/{entity_id}',
        ('Piblikasyon anrejistre', '{actor} anrejistre piblikasyon ou.'),
        ('Publication enregistrée', '{actor} a enregistré votre publication.'),
        ('Post saved', '{actor} saved your post.')),
    'post_click': _T('👆', 'shares', 'low', '/post/{entity_id}',
        ('Nouvo klik', '{actor} klike sou piblikasyon ou.'),
        ('Nouveau clic', '{actor} a cliqué sur votre contenu.'),
        ('New click', '{actor} clicked your content.')),
    # ────────────────────────── MARKETPLACE (§6) ──────────────────────────
    'order_created': _T('🛍️', 'orders', 'high', '/delivery/view/{entity_id}',
        ('Nouvo kòmand resevwa', '{actor} fè yon kòmand pou pwodwi ou.'),
        ('Nouvelle commande reçue', '{actor} a passé une commande pour votre produit.'),
        ('New order received', '{actor} placed an order for your product.')),
    'cart_updated': _T('🛒', 'orders', 'normal', '/delivery/view/{entity_id}',
        ('Panier modifye', 'Achtè a modifye panier kòmand lan.'),
        ('Panier modifié', "L'acheteur a modifié le panier de la commande."),
        ('Cart updated', 'The buyer updated the order cart.')),
    'buyer_message': _T('💬', 'messages', 'high', '/delivery/view/{entity_id}',
        ('Mesaj achtè', '{actor} voye yon mesaj sou kòmand lan.'),
        ('Message acheteur', "L'acheteur vous a envoyé un message sur la commande."),
        ('Buyer message', 'The buyer sent you a message about the order.')),
    'payment_received': _T('💰', 'orders', 'high', '/delivery/view/{entity_id}',
        ('Peman resevwa', 'Peman {amount} GK resevwa pou kòmand ou.'),
        ('Paiement reçu', 'Paiement de {amount} GK reçu pour votre commande.'),
        ('Payment received', 'Payment of {amount} GK received for your order.')),
    'order_confirmed': _T('🛒', 'orders', 'normal', '/delivery/view/{entity_id}',
        ('Kòmand konfime', '{actor} konfime kòmand lan. Vandè a ka prepare livrezon an.'),
        ('Commande confirmée', "{actor} a confirmé la commande. Le vendeur peut préparer la livraison."),
        ('Order confirmed', '{actor} confirmed the order. The seller can now prepare delivery.')),
    'order_preparing': _T('📦', 'orders', 'normal', '/delivery/view/{entity_id}',
        ('Kòmand an preparasyon', 'Vandè a ap prepare kòmand ou an.'),
        ('Commande en préparation', 'Le vendeur prépare votre commande.'),
        ('Order being prepared', 'The seller is preparing your order.')),
    'order_shipped': _T('🚚', 'orders', 'normal', '/delivery/view/{entity_id}',
        ('Kòmand an livrezon', 'Kòmand ou an nan wout livrezon.'),
        ('Commande en livraison', 'Votre commande est en cours de livraison.'),
        ('Order shipped', 'Your order is on its way.')),
    'order_delivered': _T('✅', 'orders', 'high', '/delivery/view/{entity_id}',
        ('Kòmand livre', 'Kòmand ou livre. Tanpri konfime resepsyon.'),
        ('Commande livrée', 'Votre commande a été livrée. Merci de confirmer la réception.'),
        ('Order delivered', 'Your order was delivered. Please confirm receipt.')),
    'order_delivered_seller': _T('✅', 'orders', 'high', '/delivery/view/{entity_id}',
        ('Livrezon fini', 'Achtè a konfime resepsyon. Peman {amount} GK lage pou ou.'),
        ('Livraison terminée', "L'acheteur a confirmé la réception. Paiement {amount} GK libéré."),
        ('Delivery completed', 'The buyer confirmed receipt. {amount} GK released to you.')),
    'order_cancelled': _T('❌', 'orders', 'high', '/delivery/view/{entity_id}',
        ('Kòmand anile', 'Kòmand lan anile.'),
        ('Commande annulée', 'La commande a été annulée.'),
        ('Order cancelled', 'The order was cancelled.')),

    # ────────────────────────── GKACH (§7) ──────────────────────────
    'gkach_credit': _T('💰', 'gkach', 'normal', '/gkach',
        ('Kont ou kredite', '＋{amount} GK · {description}'),
        ('Compte crédité', '+{amount} GK · {description}'),
        ('Account credited', '+{amount} GK · {description}')),
    'gkach_debit': _T('📉', 'gkach', 'normal', '/gkach',
        ('Kont ou debite', '－{amount} GK · {description}'),
        ('Compte débité', '-{amount} GK · {description}'),
        ('Account debited', '-{amount} GK · {description}')),
    'gkach_reward': _T('🎁', 'gkach', 'normal', '/gkach',
        ('Felisitasyon !', 'Ou resevwa yon rekonpans {amount} GK. {description}'),
        ('Félicitations !', 'Vous avez reçu une récompense de {amount} GK. {description}'),
        ('Congratulations!', 'You received a {amount} GK reward. {description}')),
    'gkach_commission': _T('🏦', 'gkach', 'normal', '/gkach',
        ('Kòmisyon resevwa', '＋{amount} GK kòmisyon. {description}'),
        ('Commission reçue', '+{amount} GK de commission. {description}'),
        ('Commission received', '+{amount} GK commission. {description}')),
    'gkach_transfer': _T('🔁', 'gkach', 'high', '/gkach',
        ('Transfè GKACH', '{amount} GK · {description}'),
        ('Transfert GKACH', '{amount} GK · {description}'),
        ('GKACH transfer', '{amount} GK · {description}')),
    'gkach_bonus': _T('🎉', 'gkach', 'normal', '/gkach',
        ('Bonis GKACH', '＋{amount} GK bonis ! {description}'),
        ('Bonus GKACH', '+{amount} GK de bonus ! {description}'),
        ('GKACH bonus', '+{amount} GK bonus! {description}')),
    'gkach_cashback': _T('💸', 'gkach', 'normal', '/gkach',
        ('Cashback GKACH', '＋{amount} GK cashback. {description}'),
        ('Cashback GKACH', '+{amount} GK de cashback. {description}'),
        ('GKACH cashback', '+{amount} GK cashback. {description}')),
    'gkach_transaction_failed': _T('⚠️', 'gkach', 'urgent', '/gkach',
        ('Tranzaksyon echwe', 'Tranzaksyon {amount} GK echwe. {description}'),
        ('Transaction échouée', 'La transaction de {amount} GK a échoué. {description}'),
        ('Transaction failed', 'Your {amount} GK transaction failed. {description}')),
    # ────────────────────────── ADS (§8) ──────────────────────────
    'ad_approved': _T('✅', 'ads', 'high', '/my-ads',
        ('Piblisite apwouve', 'Piblisite ou "{title}" apwouve e vizib pou tout moun.'),
        ('Publicité approuvée', 'Votre publicité « {title} » est approuvée et visible.'),
        ('Ad approved', 'Your ad "{title}" was approved and is now visible.')),
    'ad_rejected': _T('❌', 'ads', 'high', '/my-ads',
        ('Piblisite refize', 'Piblisite "{title}" refize. Rezon : {reason}'),
        ('Publicité refusée', 'Votre publicité « {title} » a été refusée. Raison : {reason}'),
        ('Ad rejected', 'Your ad "{title}" was rejected. Reason: {reason}')),
    'ad_started': _T('🚀', 'ads', 'normal', '/my-ads',
        ('Piblisite kòmanse', 'Piblisite "{title}" kòmanse kounye a.'),
        ('Publicité lancée', 'Votre publicité « {title} » est lancée.'),
        ('Ad started', 'Your ad "{title}" has started.')),
    'ad_expired': _T('⏳', 'ads', 'normal', '/my-ads',
        ('Piblisite ekspire', 'Piblisite "{title}" ekspire. Ou ka renouvle li.'),
        ('Publicité expirée', 'Votre publicité « {title} » a expiré. Vous pouvez la renouveler.'),
        ('Ad expired', 'Your ad "{title}" expired. You can renew it.')),
    'ad_interaction': _T('👀', 'ads', 'low', '/my-ads',
        ('Nouvo entèraksyon', 'Piblisite ou resevwa {count} nouvo entèraksyon.'),
        ('Nouvelles interactions', 'Votre publicité a reçu {count} nouvelles interactions.'),
        ('New interactions', 'Your ad received {count} new interactions.')),
    'ad_sale': _T('💵', 'ads', 'high', '/my-ads',
        ('Vant jeneri', 'Piblisite ou jere yon vant : {amount} GK.'),
        ('Vente générée', 'Votre publicité a généré une vente : {amount} GK.'),
        ('Sale generated', 'Your ad generated a sale: {amount} GK.')),
    # ────────────────────────── ADMIN (§9) ──────────────────────────
    'admin_new_user': _T('🆕', 'admin', 'low', '/admin',
        ('Nouvo itilizatè', '{actor} enskri sou Glory2YahPub.'),
        ('Nouvel utilisateur', "{actor} vient de s'inscrire sur Glory2YahPub."),
        ('New user', '{actor} just registered on Glory2YahPub.')),
    'admin_new_post': _T('📝', 'admin', 'normal', '/admin',
        ('Nouvo piblikasyon', 'Yon piblikasyon bezwen apwobasyon.'),
        ('Nouvelle publication', 'Une publication attend une approbation.'),
        ('New post', 'A post is awaiting approval.')),
    'admin_new_ad': _T('📢', 'admin', 'high', '/admin',
        ('Nouvo piblisite', '{actor} soumèt yon nouvo piblisite : {title}.'),
        ('Nouvelle publicité', '{actor} a soumis une nouvelle publicité : {title}.'),
        ('New ad submitted', '{actor} submitted a new ad: {title}.')),
    'admin_new_seller': _T('🏪', 'admin', 'normal', '/admin',
        ('Nouvo vandè', '{actor} vin yon vandè.'),
        ('Nouveau vendeur', '{actor} est devenu vendeur.'),
        ('New seller', '{actor} became a seller.')),
    'admin_new_product': _T('📦', 'admin', 'normal', '/admin',
        ('Nouvo pwodwi', 'Nouvo pwodwi sou mache a : {title}.'),
        ('Nouveau produit', 'Nouveau produit sur le marché : {title}.'),
        ('New product', 'New product on the market: {title}.')),
    'admin_new_order': _T('🛍️', 'admin', 'high', '/admin',
        ('Nouvo kòmand', 'Nouvo kòmand {amount} GK (achtè {actor}).'),
        ('Nouvelle commande', 'Nouvelle commande de {amount} GK (acheteur {actor}).'),
        ('New order', 'New order of {amount} GK (buyer {actor}).')),
    'admin_payment': _T('💰', 'admin', 'high', '/admin',
        ('Peman sou platfòm', 'Peman {amount} GK · {description}'),
        ('Paiement plateforme', 'Paiement de {amount} GK · {description}'),
        ('Platform payment', 'Payment of {amount} GK · {description}')),
    'admin_validation_request': _T('🔎', 'admin', 'normal', '/admin',
        ('Demann validasyon', '{actor} mande yon validasyon : {description}'),
        ('Demande de validation', '{actor} demande une validation : {description}'),
        ('Validation request', '{actor} requested a validation: {description}')),
    'admin_system_issue': _T('⚠️', 'admin', 'urgent', '/admin',
        ('Pwoblèm sistèm', '{description}'),
        ('Problème système', '{description}'),
        ('System issue', '{description}')),
    'admin_report': _T('🚩', 'admin', 'high', '/admin',
        ('Nouvo siyalman', 'Siyalman : {description}'),
        ('Nouveau signalement', 'Signalement : {description}'),
        ('New report', 'Report: {description}')),
    'admin_suspicious_transaction': _T('🚨', 'admin', 'urgent', '/admin',
        ('Tranzaksyon sispèk', 'Tranzaksyon sispèk {amount} GK · {description}'),
        ('Transaction suspecte', 'Transaction suspecte de {amount} GK · {description}'),
        ('Suspicious transaction', 'Suspicious transaction of {amount} GK · {description}')),
    # ────────────────────────── MATCH / STREAMING (§10) ──────────────────────────
    'match_starting_soon': _T('⚽', 'match', 'high', '/gadematch',
        ('Match la prèske kòmanse', '{title} kòmanse nan {when}.'),
        ('Le match commence bientôt', '{title} commence dans {when}.'),
        ('Match starting soon', '{title} starts in {when}.')),
    'match_available': _T('📺', 'match', 'high', '/gadematch',
        ('Match disponib', '{title} disponib kounye a. Klike pou gade.'),
        ('Match disponible', '{title} est maintenant disponible. Cliquez pour regarder.'),
        ('Match available', '{title} is now available. Click to watch.')),
    'match_free_expiring': _T('⏰', 'match', 'high', '/gadematch',
        ('Aksè gratis ap ekspire', 'Aksè gratis ou ekspire nan {when}.'),
        ('Accès gratuit bientôt expiré', 'Votre accès gratuit expire dans {when}.'),
        ('Free access expiring', 'Your free access expires in {when}.')),
    'match_payment_required': _T('💰', 'match', 'urgent', '/gadematch',
        ('Peman obligatwa', 'Ou dwe peye pou kontinye gade {title}.'),
        ('Paiement requis', 'Vous devez payer pour continuer à regarder {title}.'),
        ('Payment required', 'You must pay to continue watching {title}.')),

    # ────────────────────────── MESSAGING (§11) ──────────────────────────
    'new_message': _T('💬', 'messages', 'high', '/messages?to={entity_id}',
        ('Nouvo mesaj', '{actor} voye yon mesaj : {preview}'),
        ('Nouveau message', '{actor} vous a envoyé un message : {preview}'),
        ('New message', '{actor} sent you a message: {preview}'),
        (('💬 Nouvo mesaj', 'Ou gen {count} nouvo mesaj.'),
         ('💬 Nouveaux messages', 'Vous avez {count} nouveaux messages.'),
         ('💬 New messages', 'You have {count} new messages.'))),
    'unread_messages': _T('📬', 'messages', 'normal', '/messages',
        ('Mesaj pa li', 'Ou gen {count} mesaj ki pa li.'),
        ('Messages non lus', 'Vous avez {count} messages non lus.'),
        ('Unread messages', 'You have {count} unread messages.')),
    'conversation_request': _T('➕', 'messages', 'normal', '/messages?to={entity_id}',
        ('Demann konvèsasyon', '{actor} vle kòmanse yon konvèsasyon avèk ou.'),
        ('Demande de conversation', '{actor} souhaite démarrer une conversation avec vous.'),
        ('Conversation request', '{actor} wants to start a conversation with you.')),

    # ────────────────────────── SYSTEM / EVENTS ──────────────────────────
    'system_announcement': _T('📣', 'system', 'normal', '/',
        ('Anons', '{description}'),
        ('Annonce', '{description}'),
        ('Announcement', '{description}')),
    'security_alert': _T('🛡️', 'security', 'urgent', '/profile',
        ('Alèt sekirite', '{description}'),
        ('Alerte de sécurité', '{description}'),
        ('Security alert', '{description}')),
    'event_reminder': _T('📅', 'events', 'normal', '/events',
        ('Evennman byento', '{title} kòmanse nan {when}.'),
        ('Événement bientôt', '{title} commence dans {when}.'),
        ('Event soon', '{title} starts in {when}.')),




}


# ═══════════════════════════ rendering engine ═══════════════════════════

class _SafeDict(dict):
    """dict that renders missing {keys} as '' instead of raising KeyError."""

    def __missing__(self, key):
        return ''


def _fmt(text, context):
    if not text:
        return ''
    try:
        return str(text).format_map(_SafeDict(context or {}))
    except Exception:
        return str(text)


def get_template(notification_type):
    return TEMPLATES.get(notification_type)


def default_categories():
    """Copy of the per-category defaults (never share the module dict)."""
    return dict(CATEGORY_DEFAULTS)


def resolve_category(notification_type, fallback='system'):
    tpl = get_template(notification_type)
    return (tpl or {}).get('category') or fallback


def resolve_priority(notification_type, fallback='normal'):
    tpl = get_template(notification_type)
    return (tpl or {}).get('priority') or fallback


def resolve_icon(notification_type, fallback='🔔'):
    tpl = get_template(notification_type)
    return (tpl or {}).get('icon') or fallback


def resolve_url(notification_type, context):
    """Build the clickable destination (spec §22) — '' when not applicable."""
    tpl = get_template(notification_type)
    url = (tpl or {}).get('url') if tpl else None
    if not url:
        return (context or {}).get('url') or ''
    return _fmt(url, context)


def is_protected(category):
    """Financial / security kinds are never aggregated away nor auto-deleted."""
    return category in PROTECTED_CATEGORIES


def render(notification_type, context=None, lang=DEFAULT_LANG, count=1,
           title=None, message=None, icon=None):
    """Render a notification in `lang`.

    Returns:
        dict(title, message, icon, category, priority, url)

    Callers may force `title`/`message` (raw text) when no template matches;
    otherwise unknown types degrade to the generic payload message.
    """
    context = dict(context or {})
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    tpl = get_template(notification_type) or {}
    langs = tpl.get('langs') or {}

    use_group = (count or 1) > 1 and tpl.get('group')
    if use_group:
        pair = tpl['group'].get(lang) or tpl['group'].get(DEFAULT_LANG)
    else:
        pair = langs.get(lang) or langs.get(DEFAULT_LANG)

    ctx = dict(context)
    ctx.setdefault('count', count or 1)

    if pair:
        tpl_title, tpl_message = pair
        r_title = _fmt(tpl_title, ctx)
        r_message = _fmt(tpl_message, ctx)
    else:
        r_title = title or ''
        r_message = message or ctx.get('description') or ''

    # Anti-spam: keep the grouped counter visible even on a custom render.
    if use_group and (count or 1) > 1 and '{count}' not in (r_message or ''):
        r_message = f'{r_message} (+{int(count) - 1})'

    return {
        'title': (title or r_title or '')[:160],
        'message': r_message or (message or ''),
        'icon': icon or tpl.get('icon') or '🔔',
        'category': tpl.get('category') or context.get('category') or 'system',
        'priority': tpl.get('priority') or context.get('priority') or 'normal',
        'url': resolve_url(notification_type, ctx),
    }


def humanize_delta(dt, lang=DEFAULT_LANG, now=None):
    """Relative time label used by the notification centre."""
    if not dt:
        return ''
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        seconds = (now - dt.replace(tzinfo=None)).total_seconds()
    except Exception:
        return ''
    if seconds < 60:
        return {'ht': 'kounye a', 'fr': "à l'instant", 'en': 'just now'}.get(lang, 'just now')
    minutes = int(seconds // 60)
    if minutes < 60:
        return {'ht': f'{minutes} min', 'fr': f'il y a {minutes} min', 'en': f'{minutes} min ago'}.get(lang)
    hours = minutes // 60
    if hours < 24:
        return {'ht': f'{hours} èdtan', 'fr': f'il y a {hours} h', 'en': f'{hours} h ago'}.get(lang)
    days = hours // 24
    return {'ht': f'{days} jou', 'fr': f'il y a {days} j', 'en': f'{days} d ago'}.get(lang)

