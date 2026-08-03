"""
Validation Utilities
Input validation and sanitization
"""
import re
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from werkzeug.utils import secure_filename
from flask import current_app


class ValidationError(Exception):
    """Custom validation error"""
    pass


def validate_whatsapp(phone):
    """
    Validate and format WhatsApp number
    Returns: formatted E.164 number or raises ValidationError

    STRICT GUARD (fixes ADS loading corruption bug):
      - Minimum 7 digits of subscriber number after country prefix
      - Inputs like '+509STAN' or '+1' are rejected (not silently truncated)
      - Returns phonenumbers E164 for valid internationals
    """
    if not phone:
        raise ValidationError("Numéro WhatsApp obligatwa")

    original = phone
    cleaned = re.sub(r'[^\d+]', '', phone)

    # Normalize + prefix placement (allow "+509xxx" or "509xxx" with implied +)
    digits_only = cleaned.replace('+', '')

    # Safety: require at least 7 numeric digits for a real subscriber number
    if len(digits_only) < 7:
        raise ValidationError(
            "Nimewo WhatsAapp ou tro kout: min 7 chif. Ou mete: %r" % original
        )

    # If it's pure digits, prepend + for next step (will be normalized)
    if cleaned.isdigit():
        candidate = '+' + cleaned
    elif cleaned.startswith('+'):
        candidate = cleaned
    else:
        candidate = '+' + cleaned

    try:
        parsed = phonenumbers.parse(candidate, None)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    # Not E164-valid: still ACCEPT if the raw digits look long enough (>= 7 digits)
    # This keeps flexibility for unusual local formats while rejecting garbage
    if len(digits_only) >= 7:
        # Preserve the + at the start if user had it, else plain digits
        if candidate.startswith('+'):
            return candidate
        return digits_only

    raise ValidationError(
        "Nimewo WhatsApp invalide (%r). Tanpri antre yon nimewo valid ak 7+ chif." % original
    )


def validate_email_address(email):
    """
    Validate email address
    Returns: normalized email or raises ValidationError
    """
    if not email:
        raise ValidationError("Email obligatwa")
    
    try:
        valid = validate_email(email, check_deliverability=False)
        return valid.email
    except EmailNotValidError as e:
        raise ValidationError(f"Email envalid: {str(e)}")


def validate_password(password):
    """
    Validate password - accepts either 6-digit number OR any password >= 4 characters
    Returns: True or raises ValidationError
    """
    if not password:
        raise ValidationError("Modpas obligatwa")
    
    if len(password) > 128:
        raise ValidationError("Modpas twò long")
    
    # Check if it's exactly 6 digits (PIN-style password)
    if re.fullmatch(r'^\d{6}$', password):
        return True
    
    # For any other password, require at least 4 characters
    if len(password) < 4:
        raise ValidationError("Modpas dwe gen omwen 4 karaktè")
    
    return True


def validate_amount(amount, min_amount=1, max_amount=None):
    """
    Validate numeric amount
    Returns: int amount or raises ValidationError
    """
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValidationError("Kantite dwe yon nonb")
    
    if amount < min_amount:
        raise ValidationError(f"Kantite dwe omwen {min_amount}")
    
    if max_amount and amount > max_amount:
        raise ValidationError(f"Kantite pa ka depase {max_amount}")
    
    return amount


def validate_file_upload(file, allowed_extensions, max_size_mb=50):
    """
    Validate uploaded file
    Returns: secure filename or raises ValidationError
    """
    if not file or not file.filename:
        raise ValidationError("Pa gen dosye chwazi")
    
    # Check extension
    filename = file.filename.lower()
    if '.' not in filename:
        raise ValidationError("Dosye dwe gen yon ekstansyon")
    
    ext = filename.rsplit('.', 1)[1]
    if ext not in allowed_extensions:
        raise ValidationError(f"Tip dosye pa aksepte. Sèlman: {', '.join(allowed_extensions)}")
    
    # Check file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset
    
    max_size = max_size_mb * 1024 * 1024
    if size > max_size:
        raise ValidationError(f"Dosye twò gwo. Maksimòm: {max_size_mb}MB")
    
    if size == 0:
        raise ValidationError("Dosye vid")
    
    # Generate secure filename
    return secure_filename(file.filename)


def sanitize_text(text, max_length=None):
    """
    Sanitize text input
    Returns: cleaned text
    """
    if not text:
        return ''
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Strip whitespace
    text = text.strip()
    
    # Limit length
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text


def validate_pseudo(pseudo):
    """
    Validate username/pseudo
    Returns: cleaned pseudo or raises ValidationError
    """
    if not pseudo:
        raise ValidationError("Pseudo obligatwa")
    
    pseudo = sanitize_text(pseudo)
    
    if len(pseudo) < 3:
        raise ValidationError("Pseudo dwe gen omwen 3 karaktè")
    
    if len(pseudo) > 50:
        raise ValidationError("Pseudo twò long (maksimòm 50 karaktè)")
    
    # Only alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', pseudo):
        raise ValidationError("Pseudo ka sèlman gen lèt, chif, _ ak -")
    
    return pseudo


def validate_url(url):
    """
    Validate URL
    Returns: cleaned URL or raises ValidationError
    """
    if not url:
        raise ValidationError("URL obligatwa")
    
    url = sanitize_text(url)
    
    # Basic URL pattern
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    
    if not url_pattern.match(url):
        raise ValidationError("URL envalid")
    
    return url


def validate_pagination(page, per_page, max_per_page=100):
    """
    Validate pagination parameters
    Returns: (page, per_page) tuple
    """
    try:
        page = int(page) if page else 1
        per_page = int(per_page) if per_page else 20
    except (ValueError, TypeError):
        raise ValidationError("Paramèt paj envalid")
    
    if page < 1:
        page = 1
    
    if per_page < 1:
        per_page = 20
    
    if per_page > max_per_page:
        per_page = max_per_page
    
    return page, per_page
