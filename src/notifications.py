import logging
from flask import url_for

# Handle both relative and absolute imports for compatibility
try:
    from ..models import Delivery
except (ImportError, ValueError):
    from models import Delivery

logger = logging.getLogger(__name__)

ADMIN_WHATSAPP = "+50942882076"

def generate_whatsapp_link(phone_number, message=""):
    """
    Generate WhatsApp Click-to-Chat link (wa.me format)
    Format: https://wa.me/<PhoneNumber>
    Example: https://wa.me/50948592888
    """
    try:
        # Clean phone number - remove any non-numeric characters except +
        clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')

        # Ensure it starts with +
        if not clean_number.startswith('+'):
            clean_number = '+' + clean_number

        # Create wa.me link
        base_url = f"https://wa.me/{clean_number.replace('+', '')}"

        if message:
            # URL encode the message
            import urllib.parse
            encoded_message = urllib.parse.quote(message)
            return f"{base_url}?text={encoded_message}"

        return base_url

    except Exception as e:
        logger.error(f"Error generating WhatsApp link for {phone_number}: {str(e)}")
        return None

def pair_buyer_seller(buyer_whatsapp, seller_whatsapp, ad_title, delivery_id):
    """
    Create WhatsApp contact links for buyer-seller communication
    Returns a dictionary with contact links for both parties
    """
    try:
        # Message for buyer to contact seller
        buyer_message = f"Bonjou! Mwen achte piblisite '{ad_title}' epi mwen ap tann pou w mete pri livrezon an. ID Livrezon: {delivery_id}"

        # Message for seller to contact buyer
        seller_message = f"Bonjou! Ou resevwa yon nouvo demann livrezon pou piblisite '{ad_title}'. Tanpri mete pri livrezon an. ID Livrezon: {delivery_id}"

        buyer_contact_link = generate_whatsapp_link(seller_whatsapp, buyer_message)
        seller_contact_link = generate_whatsapp_link(buyer_whatsapp, seller_message)

        return {
            'buyer_contact_link': buyer_contact_link,
            'seller_contact_link': seller_contact_link,
            'buyer_number': buyer_whatsapp,
            'seller_number': seller_whatsapp
        }

    except Exception as e:
        logger.error(f"Error pairing buyer {buyer_whatsapp} with seller {seller_whatsapp}: {str(e)}")
        return None

def send_whatsapp_message(to_number, message):
    """
    Legacy function - now returns WhatsApp link instead of sending message
    """
    logger.warning("send_whatsapp_message is deprecated. Use generate_whatsapp_link instead.")
    return generate_whatsapp_link(to_number, message)

def pair_user_chat(user_whatsapp):
    """
    Create a chat pairing for admin to communicate with user
    """
    try:
        admin_number = ADMIN_WHATSAPP
        pairing_message = f"Chat pairing established with user {user_whatsapp}. You can now communicate directly."
        return generate_whatsapp_link(admin_number, pairing_message)
    except Exception as e:
        logger.error(f"Error pairing user chat: {str(e)}")
        return None

def notify_admin_new_gkach_request(user_whatsapp, amount, request_id):
    """
    Notify admin of new Gkach purchase request
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Nouvo demann Gkach: {amount} Gkach pou {user_whatsapp}. ID: {request_id}"
    return generate_whatsapp_link(admin_number, message)

def notify_admin_balance_change(user_whatsapp, action, amount):
    """
    Notify admin of balance changes (add/edit/delete)
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Chanjman balans Gkach: {action} {amount} Gkach pou {user_whatsapp}"
    return generate_whatsapp_link(admin_number, message)

def notify_admin_request_approved(user_whatsapp, amount, request_id):
    """
    Notify admin when a Gkach request is approved
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Demann Gkach apwouve: {amount} Gkach pou {user_whatsapp}. ID: {request_id}"
    return generate_whatsapp_link(admin_number, message)

def notify_admin_request_rejected(user_whatsapp, amount, request_id):
    """
    Notify admin when a Gkach request is rejected
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Demann Gkach rejte: {amount} Gkach pou {user_whatsapp}. ID: {request_id}"
    return generate_whatsapp_link(admin_number, message)

def notify_admin_new_ad_submission(user_whatsapp, ad_id):
    """
    Notify admin of new ad submission
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Nouvo piblisite soumèt pa {user_whatsapp}. ID: {ad_id}"
    return generate_whatsapp_link(admin_number, message)

def notify_admin_payment_proof_uploaded(user_whatsapp, ad_id):
    """
    Notify admin when payment proof is uploaded
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Prèv pèman telechaje pou piblisite {ad_id} pa {user_whatsapp}"
    return generate_whatsapp_link(admin_number, message)

def notify_user_ad_approved(user_whatsapp, ad_id):
    """
    Notify user when ad is approved
    """
    message = f"Piblisite w la (ID: {ad_id}) apwouve! Li pral parèt nan gwoup yo byento."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_user_ad_rejected(user_whatsapp, ad_id):
    """
    Notify user when ad is rejected
    """
    message = f"Piblisite w la (ID: {ad_id}) rejte. Kontakte administratè pou plis detay."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_admin_ad_purchased(user_whatsapp, ad_id, price):
    """
    Notify admin when an ad is purchased
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Piblisite {ad_id} achte pa {user_whatsapp} pou {price} Gkach"
    return generate_whatsapp_link(admin_number, message)

def notify_user_ad_purchased(user_whatsapp, ad_id, price):
    """
    Notify user when they purchase an ad
    """
    message = f"Achte avèk siksè! Ou te depanse {price} Gkach pou piblisite {ad_id}."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_admin_gkach_approval_uploaded(user_whatsapp, request_id):
    """
    Notify admin when Gkach approval document is uploaded
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Dokiman apwobasyon Gkach telechaje pou demann {request_id} pa {user_whatsapp}"
    return generate_whatsapp_link(admin_number, message)

def notify_user_gkach_request_approved(user_whatsapp, amount):
    """
    Notify user when Gkach request is approved
    """
    message = f"Demann Gkach ou a apwouve! {amount} Gkach ajoute nan balans ou."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_user_gkach_request_rejected(user_whatsapp, amount):
    """
    Notify user when Gkach request is rejected
    """
    message = f"Demann Gkach ou a ({amount} Gkach) rejte. Kontakte administratè pou plis detay."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_user_balance_added(user_whatsapp, amount):
    """
    Notify user when balance is added by admin
    """
    message = f"{amount} Gkach ajoute nan balans ou pa administratè."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_admin_traffic_alert(traffic_count):
    """
    Notify admin when traffic exceeds threshold
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Alerte trafik: {traffic_count} demann resevwa nan dènye minit yo."
    return generate_whatsapp_link(admin_number, message)

def notify_admin_otp(otp):
    """
    Send OTP to admin for login verification
    """
    admin_number = ADMIN_WHATSAPP
    message = f"Kòd verifikasyon pou koneksyon administratè: {otp}. Kòd sa a ekspire nan 5 minit."
    return generate_whatsapp_link(admin_number, message)

def notify_seller_delivery_request(seller_whatsapp, buyer_whatsapp, delivery_address, delivery_id, ad_title, ad_price):
    """
    Notify seller of new delivery request with detailed cart receipt and link to update cart
    """
    try:
        # Generate the actual URL using Flask's url_for
        from flask import current_app
        with current_app.app_context():
            update_cart_url = url_for('seller_update_cart', delivery_id=delivery_id, _external=True)
    except Exception as e:
        logger.error(f"Error generating URL for delivery {delivery_id}: {str(e)}")
        update_cart_url = f"https://yourdomain.com/seller_update_cart/{delivery_id}"  # Fallback

    message = f"🛒 NOUVO DEMANN LIVREZON - REÇU PANIER\n\n📦 Piblisite: {ad_title}\n💰 Pri piblisite: {ad_price} Gkach\n👤 Achte pa: {buyer_whatsapp}\n📍 Adrès livrezon: {delivery_address}\n\n📋 Detay:\n- ID Livrezon: {delivery_id}\n- Pri inisyal: {ad_price} Gkach\n- Kou livrezon: TBD\n- Total: TBD\n\n🔗 Klik sou lyen sa a pou mete ajou panier an: {update_cart_url}\n\n⚠️ Tanpri revize detay yo epi mete ajou pri ak adrès livrezon si nesesè."
    return generate_whatsapp_link(seller_whatsapp, message)

def notify_buyer_delivery_updated(buyer_whatsapp, delivery_cost, total_price, delivery_id):
    """
    Notify buyer when seller sets delivery cost with updated cart link
    """
    # Get the delivery to find the ad_id
    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if delivery:
        try:
            # Generate the actual URL using Flask's url_for
            from flask import current_app
            with current_app.app_context():
                updated_cart_url = url_for('check_balance', ad_id=delivery.ad_id, _external=True)
        except Exception as e:
            logger.error(f"Error generating URL for balance check {delivery.ad_id}: {str(e)}")
            updated_cart_url = f"https://yourdomain.com/achte/check_balance/{delivery.ad_id}"  # Fallback
        message = f"Pri livrezon mete ajou! Kou livrezon: {delivery_cost} Gkach, Total: {total_price} Gkach.\n\nKlike sou lyen sa a pou konfime achte: {updated_cart_url}"
    else:
        message = f"Pri livrezon mete ajou! Kou livrezon: {delivery_cost} Gkach, Total: {total_price} Gkach.\n\nKontakte vandè pou konfime achte."
    return generate_whatsapp_link(buyer_whatsapp, message)

def notify_buyer_cart_submitted(buyer_whatsapp, ad_title, price, delivery_address, delivery_id):
    """
    Notify buyer when shopping cart is submitted with cart details
    """
    message = f"Panier achte soumèt avèk siksè!\n\nPiblisite: {ad_title}\nPri: {price} Gkach\nAdrès livrezon: {delivery_address}\nID Livrezon: {delivery_id}\n\nVandè a pral mete pri livrezon byento. Ou pral resevwa yon mesaj lè pri a mete ajou."
    return generate_whatsapp_link(buyer_whatsapp, message)

def notify_buyer_add_to_cart(user_whatsapp, ad_title, quantity):
    """
    Notify buyer when an item is added to cart
    """
    message = f"Piblisite '{ad_title}' ajoute nan panier ou! Kantite: {quantity}"
    return generate_whatsapp_link(user_whatsapp, message)

def notify_buyer_shipping_set(user_whatsapp, ad_title, shipping_fee):
    """
    Notify buyer when shipping fee is set for an item
    """
    message = f"Pri livrezon pou '{ad_title}' mete ajou a {shipping_fee} Gkach."
    return generate_whatsapp_link(user_whatsapp, message)

def notify_buyer_checkout(user_whatsapp, total_gkach, delivery_ids):
    """
    Notify buyer when checkout is completed
    """
    delivery_ids_str = ', '.join(delivery_ids)
    message = f"Achte avèk siksè! Ou te depanse {total_gkach} Gkach. ID Livrezon: {delivery_ids_str}"
    return generate_whatsapp_link(user_whatsapp, message)

def notify_seller_cart_update_request(seller_whatsapp, buyer_whatsapp, ad_title, total_price, shipping_price, delivery_address, update_url):
    """
    Notify seller when buyer submits cart with shipping proposal
    """
    message = f"🛒 NOUVO DEMANN LIVREZON - ACHTE PANIER\n\n📦 Piblisite: {ad_title}\n💰 Pri pwodwi: {total_price} Gkach\n👤 Achte pa: {buyer_whatsapp}\n📍 Adrès livrezon: {delivery_address}\n💸 Pri livrezon pwopoze: {shipping_price} Gkach\n\n📋 Detay:\n- Pri total pwopoze: {total_price + shipping_price} Gkach\n\n🔗 Klik sou lyen sa a pou mete ajou pri livrezon an: {update_url}\n\n⚠️ Tanpri revize epi mete ajou pri livrezon an si nesesè."
    return generate_whatsapp_link(seller_whatsapp, message)

def notify_buyer_shipping_updated(buyer_whatsapp, ad_title, updated_shipping, total_price, update_url):
    """
    Notify buyer when seller updates shipping price
    """
    message = f"Pri livrezon mete ajou pa vandè!\n\nPiblisite: {ad_title}\nPri livrezon nouvo: {updated_shipping} Gkach\nTotal: {total_price} Gkach\n\nKlike sou lyen sa a pou konfime achte oubyen refize: {update_url}"
    return generate_whatsapp_link(buyer_whatsapp, message)

def notify_seller_cart_declined(seller_whatsapp, buyer_whatsapp, ad_title):
    """
    Notify seller when buyer declines the cart
    """
    message = f"Achte a refize pa {buyer_whatsapp} pou piblisite '{ad_title}'. Panier an efase."
    return generate_whatsapp_link(seller_whatsapp, message)

def notify_seller_purchase_confirmed(seller_whatsapp, buyer_whatsapp, delivery_id, total_price):
    """
    Notify seller when buyer confirms purchase
    """
    message = f"✅ ACHA KONFIME!\n\nAchte a konfime acha a pou {total_price} Gkach.\n\n👤 Achte: {buyer_whatsapp}\n🆔 ID Livrezon: {delivery_id}\n\n📦 Tanpri livre pwodwi a bay achte a. Lè achte a resevwa livrezon an, li pral konfime epi ou pral resevwa Gkach ou."
    return generate_whatsapp_link(seller_whatsapp, message)

def notify_seller_purchase_declined(seller_whatsapp, buyer_whatsapp, delivery_id):
    """
    Notify seller when buyer declines purchase
    """
    message = f"❌ ACHA REFIZE\n\nAchte a refize acha a.\n\n👤 Achte: {buyer_whatsapp}\n🆔 ID Livrezon: {delivery_id}"
    return generate_whatsapp_link(seller_whatsapp, message)

def notify_seller_delivery_confirmed(seller_whatsapp, buyer_whatsapp, delivery_id, total_price):
    """
    Notify seller when buyer confirms delivery receipt and payment is released
    """
    message = f"💰 PEMAN RESEVWA!\n\nAchte a konfime resepsyon livrezon an. {total_price} Gkach kredite nan balans ou.\n\n👤 Achte: {buyer_whatsapp}\n🆔 ID Livrezon: {delivery_id}\n\n✅ Tranzaksyon konplete!"
    return generate_whatsapp_link(seller_whatsapp, message)

def notify_buyer_awaiting_delivery(buyer_whatsapp, seller_whatsapp, delivery_id, total_price):
    """
    Notify buyer that purchase is confirmed and awaiting delivery
    """
    message = f"✅ ACHA KONFIME!\n\nAcha ou a konfime pou {total_price} Gkach.\n\n👤 Vandè: {seller_whatsapp}\n🆔 ID Livrezon: {delivery_id}\n\n📦 Vandè a pral livre pwodwi a. Lè ou resevwa livrezon an, tanpri konfime resepsyon pou finaliz tranzaksyon an."
    return generate_whatsapp_link(buyer_whatsapp, message)

def notify_admin_delivery_completed(buyer_whatsapp, seller_whatsapp, delivery_id, total_price):
    """
    Notify admin when delivery is completed and payment is released
    """
    admin_number = ADMIN_WHATSAPP
    message = f"📦 LIVREZON KONPLETE\n\nAchte: {buyer_whatsapp}\nVandè: {seller_whatsapp}\nID: {delivery_id}\nTotal: {total_price} Gkach\n\n✅ Peman voye bay vandè."
    return generate_whatsapp_link(admin_number, message)

def notify_admin_gkach_transaction_started(buyer_whatsapp, seller_whatsapp, ad_title, total_price, delivery_id):
    """
    Notify admin when a new Gkach transaction (purchase) is started
    """
    admin_number = ADMIN_WHATSAPP
    message = f"💳 NOUVO TRANZAKSYON GKACH KÒMANSE\n\n👤 Achte: {buyer_whatsapp}\n🏪 Vandè: {seller_whatsapp}\n📦 Piblisite: {ad_title}\n💰 Montan: {total_price} Gkach\n🆔 ID Livrezon: {delivery_id}\n\n⏳ Tann pou konfirmassyon achte..."
    return generate_whatsapp_link(admin_number, message)

def notify_admin_gkach_payment_released(buyer_whatsapp, seller_whatsapp, delivery_id, total_price, ad_title):
    """
    Notify admin when Gkach payment is released to seller after delivery confirmation
    """
    admin_number = ADMIN_WHATSAPP
    message = f"💰 PEMAN GKACH LAGE\n\n👤 Achte: {buyer_whatsapp}\n🏪 Vandè: {seller_whatsapp}\n📦 Piblisite: {ad_title}\n💵 Montan: {total_price} Gkach\n🆔 ID Livrezon: {delivery_id}\n\n✅ Balans vandè a mete ajou."
    return generate_whatsapp_link(admin_number, message)

def notify_admin_gkach_balance_updated(user_whatsapp, action_type, amount, new_balance):
    """
    Notify admin when a user's Gkach balance is updated (add, edit, purchase, etc.)
    """
    admin_number = ADMIN_WHATSAPP
    action_text = {
        'purchase': 'ACHA',
        'receive': 'RESEVWA',
        'add': 'AJOUTE',
        'edit': 'MODIFYE',
        'delete': 'EFASE',
        'refund': 'REMBOURSAY'
    }.get(action_type, action_type.upper())
    
    message = f"🔄 BALANS GKACH METE AJOU\n\n👤 Itilizatè: {user_whatsapp}\n🔴 Aksyon: {action_text}\n💵 Montà: {amount} Gkach\n📊 Balans Nouvo: {new_balance} Gkach"
    return generate_whatsapp_link(admin_number, message)

def notify_admin_gkach_purchase_confirmed(buyer_whatsapp, seller_whatsapp, ad_title, total_price, delivery_id):
    """
    Notify admin when buyer confirms a Gkach purchase (payment deducted from buyer)
    """
    admin_number = ADMIN_WHATSAPP
    message = f"✅ ACHA GKACH KONFIME\n\n👤 Achte: {buyer_whatsapp}\n🏪 Vandè: {seller_whatsapp}\n📦 Piblisite: {ad_title}\n💰 Montan: {total_price} Gkach\n🆔 ID: {delivery_id}\n\n📦 Tann pou livrezon..."
    return generate_whatsapp_link(admin_number, message)

def notify_admin_insufficient_gkach(buyer_whatsapp, required_amount, current_balance):
    """
    Notify admin when a user tries to make purchase but has insufficient Gkach
    """
    admin_number = ADMIN_WHATSAPP
    message = f"⚠️ BALANS GKACH ENSIFIZAN\n\n👤 Itilizatè: {buyer_whatsapp}\n💰 Montan Bezwen: {required_amount} Gkach\n💵 Balans Aktwel: {current_balance} Gkach\n📉 Diferans: {required_amount - current_balance} Gkach\n\nItilizatè a dwe achte plis Gkach."
    return generate_whatsapp_link(admin_number, message)

def notify_party_participants(party_name, party_date, party_location, participants, custom_message=None):
    """
    Generate WhatsApp links for all party participants to send group messages.
    Returns a list of WhatsApp links for each participant.
    
    Args:
        party_name: Name of the party
        party_date: Date of the party
        party_location: Location of the party
        participants: List of PartyParticipant objects
        custom_message: Optional custom message from the party owner
    
    Returns:
        List of dictionaries with participant info and WhatsApp link
    """
    import urllib.parse
    from datetime import datetime
    
    # Format date for message
    if isinstance(party_date, datetime):
        date_str = party_date.strftime('%d/%m/%Y')
    else:
        date_str = str(party_date)
    
    # Build the message
    base_message = f"📢 MESAJ POU FÈT - {party_name}\n\n"
    base_message += f"📅 Dat: {date_str}\n"
    if party_location:
        base_message += f"📍 Lye: {party_location}\n\n"
    
    if custom_message:
        base_message += f"💬 Mesaj: {custom_message}\n\n"
    
    base_message += "Mèsi pou patisipasyon ou!"
    
    results = []
    
    for participant in participants:
        try:
            # Create personalized message for each participant
            personalized_message = f"👋 Bonjou {participant.name}!\n\n" + base_message
            
            # Generate WhatsApp link
            whatsapp_link = generate_whatsapp_link(participant.whatsapp, personalized_message)
            
            results.append({
                'name': participant.name,
                'whatsapp': participant.whatsapp,
                'whatsapp_link': whatsapp_link,
                'food_choice': participant.food_choice,
                'drink_choice': participant.drink_choice
            })
        except Exception as e:
            logger.error(f"Error generating WhatsApp link for participant {participant.name}: {str(e)}")
            continue
    
    return results

def notify_party_participant_individual(participant, party_name, party_date, party_location, message):
    """
    Send an individual message to a specific party participant.
    
    Args:
        participant: PartyParticipant object
        party_name: Name of the party
        party_date: Date of the party
        party_location: Location of the party  
        message: Custom message to send
    
    Returns:
        WhatsApp link for the participant
    """
    from datetime import datetime
    
    # Format date for message
    if isinstance(party_date, datetime):
        date_str = party_date.strftime('%d/%m/%Y')
    else:
        date_str = str(party_date)
    
    # Build the message
    full_message = f"📢 MESAJ POU FÈT - {party_name}\n\n"
    full_message += f"📅 Dat: {date_str}\n"
    if party_location:
        full_message += f"📍 Lye: {party_location}\n\n"
    full_message += f"💬 Mesaj: {message}\n\n"
    full_message += "Mèsi!"
    
    return generate_whatsapp_link(participant.whatsapp, full_message)
