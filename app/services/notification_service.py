"""
Notification Service Layer
Handles WhatsApp link generation and user notifications
"""
import logging
import urllib.parse
import threading
from flask import url_for, current_app

logger = logging.getLogger(__name__)


def _send_whatsapp_alert(message: str):
    """Send a WhatsApp message to the admin via CallMeBot API (fire-and-forget).
    Register your number once at https://www.callmebot.com/blog/free-api-whatsapp-messages/
    then set CALLMEBOT_APIKEY in .env.
    Falls back silently if not configured.
    """
    import os, requests as _req
    phone = os.environ.get('ADMIN_WHATSAPP', '+50942882076').replace('+', '')
    apikey = os.environ.get('CALLMEBOT_APIKEY', '')
    if not apikey:
        logger.debug('CALLMEBOT_APIKEY not set — WhatsApp alert skipped.')
        return
    try:
        url = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={phone}&text={urllib.parse.quote(message)}&apikey={apikey}"
        )
        _req.get(url, timeout=8)
    except Exception as e:
        logger.warning(f'WhatsApp alert failed: {e}')


def alert_admin(message: str):
    """Fire-and-forget WhatsApp alert to admin. Never blocks the request."""
    threading.Thread(target=_send_whatsapp_alert, args=(message,), daemon=True).start()


class NotificationService:
    """Service for sending notifications (generating WhatsApp links)"""
    
    ADMIN_WHATSAPP = "+50942882076"
    
    @staticmethod
    def generate_whatsapp_link(phone_number, message=""):
        """Generate WhatsApp wa.me link"""
        if not phone_number:
            return None
            
        # Clean phone number
        clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        if not clean_number.startswith('+'):
            clean_number = '+' + clean_number
            
        base_url = f"https://wa.me/{clean_number.replace('+', '')}"
        
        if message:
            encoded_message = urllib.parse.quote(message)
            return f"{base_url}?text={encoded_message}"
            
        return base_url

    @staticmethod
    def notify_admin_new_ad(user_whatsapp, ad_id):
        """Notify admin of new ad submission"""
        message = f"Nouvo piblisite soumèt pa {user_whatsapp}. ID: {ad_id}"
        return NotificationService.generate_whatsapp_link(NotificationService.ADMIN_WHATSAPP, message)

    @staticmethod
    def notify_user_ad_status(user_whatsapp, ad_id, status):
        """Notify user when ad status changes"""
        if status == 'approved':
            message = f"Piblisite w la (ID: {ad_id}) apwouve! Li parèt sou platfòm lan kounye a."
        else:
            message = f"Piblisite w la (ID: {ad_id}) rejte. Tanpri kontakte nou pou plis detay."
            
        return NotificationService.generate_whatsapp_link(user_whatsapp, message)

    @staticmethod
    def notify_seller_new_order(seller_whatsapp, buyer_whatsapp, delivery_id, ad_title):
        """Notify seller of new order/delivery request"""
        try:
            update_url = url_for('delivery.view', delivery_id=delivery_id, _external=True)
        except:
            update_url = f"/delivery/view/{delivery_id}"
            
        message = (
            f"🛒 NOUVO DEMANN LIVREZON\n\n"
            f"📦 Piblisite: {ad_title}\n"
            f"👤 Achte pa: {buyer_whatsapp}\n"
            f"🔗 Klike la a pou mete pri livrezon an: {update_url}"
        )
        return NotificationService.generate_whatsapp_link(seller_whatsapp, message)

    @staticmethod
    def notify_buyer_cost_set(buyer_whatsapp, delivery_id, cost, total):
        """Notify buyer when delivery cost is set"""
        try:
            confirm_url = url_for('delivery.view', delivery_id=delivery_id, _external=True)
        except:
            confirm_url = f"/delivery/view/{delivery_id}"
            
        message = (
            f"🚚 PRI LIVREZON METE AJOU\n\n"
            f"Kou livrezon: {cost} Gkach\n"
            f"Total pou peye: {total} Gkach\n"
            f"🔗 Klike la a pou konfime epi peye: {confirm_url}"
        )
        return NotificationService.generate_whatsapp_link(buyer_whatsapp, message)

    @staticmethod
    def notify_admin_gkach_request(user_whatsapp, amount):
        """Notify admin of Gkach request"""
        message = f"Nouvo demann Gkach: {amount} Gkach pou {user_whatsapp}."
        return NotificationService.generate_whatsapp_link(NotificationService.ADMIN_WHATSAPP, message)
