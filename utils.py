"""
Utility functions for Glory2yahPub
"""
import re
import bleach
from werkzeug.utils import secure_filename

def format_whatsapp_number(whatsapp):
    """
    Format WhatsApp number to standard international format: +[country_code][number]
    
    Args:
        whatsapp (str): Raw WhatsApp number input
        
    Returns:
        str: Formatted WhatsApp number with + prefix
    """
    if not whatsapp:
        return None
    
    # Remove all non-digit characters except +
    clean_number = ''.join(c for c in whatsapp if c.isdigit() or c == '+')
    
    # If already has +, return as is (after cleaning)
    if clean_number.startswith('+'):
        return clean_number
    
    # If no +, add it
    return '+' + clean_number

def sanitize_input(text, max_length=None):
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        text (str): Raw user input
        max_length (int, optional): Maximum allowed length
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    
    # Remove potentially dangerous HTML/JavaScript
    cleaned = bleach.clean(text, tags=[], strip=True)
    
    # Trim to max length if specified
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    
    return cleaned.strip()

def validate_file_upload(file, allowed_extensions, max_size_mb=100):
    """
    Validate uploaded file
    
    Args:
        file: FileStorage object from request.files
        allowed_extensions (set): Set of allowed file extensions
        max_size_mb (int): Maximum file size in MB
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not file or not file.filename:
        return False, "Pa gen dosye chwazi"
    
    # Check file extension
    if '.' not in file.filename:
        return False, "Non dosye envalid"
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return False, f"Tip dosye pa aksepte. Sèlman: {', '.join(allowed_extensions)}"
    
    # Check file size (if we can)
    try:
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset to beginning
        
        max_size_bytes = max_size_mb * 1024 * 1024
        if size > max_size_bytes:
            return False, f"Dosye twò gwo. Maksimòm: {max_size_mb}MB"
    except:
        pass  # If we can't check size, continue
    
    return True, None

def generate_secure_filename(original_filename):
    """
    Generate a secure filename with UUID prefix
    
    Args:
        original_filename (str): Original filename from upload
        
    Returns:
        str: Secure filename with UUID prefix
    """
    import uuid
    secure_name = secure_filename(original_filename)
    return f"{uuid.uuid4()}_{secure_name}"

def validate_whatsapp_number(whatsapp):
    """
    Validate WhatsApp number format
    
    Args:
        whatsapp (str): WhatsApp number to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not whatsapp:
        return False
    
    # Should be in format +509xxxxxxxx (12 characters total)
    pattern = r'^\+509\d{8}$'
    return bool(re.match(pattern, whatsapp))

def calculate_cart_total(cart_items):
    """
    Calculate total price for cart items including shipping
    
    Args:
        cart_items (list): List of CartItem objects
        
    Returns:
        dict: Dictionary with product_total, shipping_total, and grand_total
    """
    product_total = 0
    shipping_total = 0
    
    for item in cart_items:
        if hasattr(item, 'ad') and item.ad:
            product_total += item.ad.price_gkach * item.quantity
            shipping_total += item.shipping_fee
    
    return {
        'product_total': product_total,
        'shipping_total': shipping_total,
        'grand_total': product_total + shipping_total
    }
