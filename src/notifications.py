import requests
import logging
from models import Delivery

logger = logging.getLogger(__name__)

def send_whatsapp_message(to_number, message):
    """
    Send WhatsApp message using WhatsApp.me API
    """
    try:
        # WhatsApp.me API endpoint (placeholder - replace with actual API)
        url = "https://api.whatsapp.me/send"

        payload = {
            "to": to_number,
            "message": message
        }

        # Note: You'll need to add your API key to headers
        headers = {
            "Content-Type": "application/json",
            # "Authorization": "Bearer YOUR_API_KEY"  # Add your API key here
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            logger.info(f"WhatsApp message sent successfully to {to_number}")
            return True
        else:
            logger.error(f"Failed to send WhatsApp message: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return False

def notify_admin_new_gkach_request(user_whatsapp, amount, request_id):
    """
    Notify admin of new Gkach purchase request
    """
    admin_number = "+50942882076"
    message = f"Nouvo demann Gkach: {amount} Gkach pou {user_whatsapp}. ID: {request_id}"
    return send_whatsapp_message(admin_number, message)

def notify_admin_balance_change(user_whatsapp, action, amount):
    """
    Notify admin of balance changes (add/edit/delete)
    """
    admin_number = "+50942882076"
    message = f"Chanjman balans Gkach: {action} {amount} Gkach pou {user_whatsapp}"
    return send_whatsapp_message(admin_number, message)

def notify_admin_request_approved(user_whatsapp, amount, request_id):
    """
    Notify admin when a Gkach request is approved
    """
    admin_number = "+50942882076"
    message = f"Demann Gkach apwouve: {amount} Gkach pou {user_whatsapp}. ID: {request_id}"
    return send_whatsapp_message(admin_number, message)

def notify_admin_request_rejected(user_whatsapp, amount, request_id):
    """
    Notify admin when a Gkach request is rejected
    """
    admin_number = "+50942882076"
    message = f"Demann Gkach rejte: {amount} Gkach pou {user_whatsapp}. ID: {request_id}"
    return send_whatsapp_message(admin_number, message)

def notify_admin_new_ad_submission(user_whatsapp, ad_id):
    """
    Notify admin of new ad submission
    """
    admin_number = "+50942882076"
    message = f"Nouvo piblisite soumèt pa {user_whatsapp}. ID: {ad_id}"
    return send_whatsapp_message(admin_number, message)

def notify_admin_payment_proof_uploaded(user_whatsapp, ad_id):
    """
    Notify admin when payment proof is uploaded
    """
    admin_number = "+50942882076"
    message = f"Prèv pèman telechaje pou piblisite {ad_id} pa {user_whatsapp}"
    return send_whatsapp_message(admin_number, message)

def notify_user_ad_approved(user_whatsapp, ad_id):
    """
    Notify user when ad is approved
    """
    message = f"Piblisite w la (ID: {ad_id}) apwouve! Li pral parèt nan gwoup yo byento."
    return send_whatsapp_message(user_whatsapp, message)

def notify_user_ad_rejected(user_whatsapp, ad_id):
    """
    Notify user when ad is rejected
    """
    message = f"Piblisite w la (ID: {ad_id}) rejte. Kontakte administratè pou plis detay."
    return send_whatsapp_message(user_whatsapp, message)

def notify_admin_ad_purchased(user_whatsapp, ad_id, price):
    """
    Notify admin when an ad is purchased
    """
    admin_number = "+50942882076"
    message = f"Piblisite {ad_id} achte pa {user_whatsapp} pou {price} Gkach"
    return send_whatsapp_message(admin_number, message)

def notify_user_ad_purchased(user_whatsapp, ad_id, price):
    """
    Notify user when they purchase an ad
    """
    message = f"Achte avèk siksè! Ou te depanse {price} Gkach pou piblisite {ad_id}."
    return send_whatsapp_message(user_whatsapp, message)

def notify_admin_gkach_approval_uploaded(user_whatsapp, request_id):
    """
    Notify admin when Gkach approval document is uploaded
    """
    admin_number = "+50942882076"
    message = f"Dokiman apwobasyon Gkach telechaje pou demann {request_id} pa {user_whatsapp}"
    return send_whatsapp_message(admin_number, message)

def notify_user_gkach_request_approved(user_whatsapp, amount):
    """
    Notify user when Gkach request is approved
    """
    message = f"Demann Gkach ou a apwouve! {amount} Gkach ajoute nan balans ou."
    return send_whatsapp_message(user_whatsapp, message)

def notify_user_gkach_request_rejected(user_whatsapp, amount):
    """
    Notify user when Gkach request is rejected
    """
    message = f"Demann Gkach ou a ({amount} Gkach) rejte. Kontakte administratè pou plis detay."
    return send_whatsapp_message(user_whatsapp, message)

def notify_user_balance_added(user_whatsapp, amount):
    """
    Notify user when balance is added by admin
    """
    message = f"{amount} Gkach ajoute nan balans ou pa administratè."
    return send_whatsapp_message(user_whatsapp, message)

def notify_admin_traffic_alert(traffic_count):
    """
    Notify admin when traffic exceeds threshold
    """
    admin_number = "+50942882076"
    message = f"Alerte trafik: {traffic_count} demann resevwa nan dènye minit yo."
    return send_whatsapp_message(admin_number, message)

def notify_admin_otp(otp):
    """
    Send OTP to admin for login verification
    """
    admin_number = "+50942882076"
    message = f"Kòd verifikasyon pou koneksyon administratè: {otp}. Kòd sa a ekspire nan 5 minit."
    return send_whatsapp_message(admin_number, message)

def notify_seller_delivery_request(seller_whatsapp, buyer_whatsapp, delivery_address, delivery_id, ad_title, ad_price):
    """
    Notify seller of new delivery request with detailed cart receipt and link to set delivery fees
    """
    set_delivery_url = f"https://yourdomain.com/set_delivery/{delivery_id}"  # Replace with actual domain
    message = f"🛒 NOUVO DEMANN LIVREZON - REÇU PANIER\n\n📦 Piblisite: {ad_title}\n💰 Pri piblisite: {ad_price} Gkach\n👤 Achte pa: {buyer_whatsapp}\n📍 Adrès livrezon: {delivery_address}\n\n📋 Detay:\n- ID Livrezon: {delivery_id}\n- Pri inisyal: {ad_price} Gkach\n- Kou livrezon: TBD\n- Total: TBD\n\n🔗 Klik sou lyen sa a pou mete pri livrezon: {set_delivery_url}\n\n⚠️ Tanpri revize detay yo epi mete pri livrezon ki apwopriye."
    return send_whatsapp_message(seller_whatsapp, message)

def notify_buyer_delivery_updated(buyer_whatsapp, delivery_cost, total_price, delivery_id):
    """
    Notify buyer when seller sets delivery cost with updated cart link
    """
    # Get the delivery to find the ad_id
    delivery = Delivery.query.filter_by(delivery_id=delivery_id).first()
    if delivery:
        updated_cart_url = f"https://yourdomain.com/achte/check_balance/{delivery.ad_id}"  # Link to check balance page
        message = f"Pri livrezon mete ajou! Kou livrezon: {delivery_cost} Gkach, Total: {total_price} Gkach.\n\nKlike sou lyen sa a pou konfime achte: {updated_cart_url}"
    else:
        message = f"Pri livrezon mete ajou! Kou livrezon: {delivery_cost} Gkach, Total: {total_price} Gkach.\n\nKontakte vandè pou konfime achte."
    return send_whatsapp_message(buyer_whatsapp, message)

def notify_buyer_cart_submitted(buyer_whatsapp, ad_title, price, delivery_address, delivery_id):
    """
    Notify buyer when shopping cart is submitted with cart details
    """
    message = f"Panier achte soumèt avèk siksè!\n\nPiblisite: {ad_title}\nPri: {price} Gkach\nAdrès livrezon: {delivery_address}\nID Livrezon: {delivery_id}\n\nVandè a pral mete pri livrezon byento. Ou pral resevwa yon mesaj lè pri a mete ajou."
    return send_whatsapp_message(buyer_whatsapp, message)
