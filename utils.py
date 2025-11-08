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

def generate_receipt(delivery_id, buyer_whatsapp, seller_whatsapp, cart_items_data, total_product_price, total_shipping, grand_total, transaction_date=None):
    """
    Generate a formatted receipt text for a completed transaction
    
    Args:
        delivery_id (str): Unique delivery/transaction ID
        buyer_whatsapp (str): Buyer's WhatsApp number
        seller_whatsapp (str): Seller's WhatsApp number
        cart_items_data (list): List of cart items with details
        total_product_price (int): Total price of products
        total_shipping (int): Total shipping cost
        grand_total (int): Grand total (products + shipping)
        transaction_date (datetime, optional): Transaction date
        
    Returns:
        str: Formatted receipt text
    """
    from datetime import datetime
    
    if transaction_date is None:
        transaction_date = datetime.now()
    
    # Format date
    date_str = transaction_date.strftime("%d/%m/%Y %H:%M")
    
    # Build receipt
    receipt = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    receipt += "🧾 RESI TRANZAKSYON\n"
    receipt += "   Glory2yahPub\n"
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    receipt += f"📅 Dat: {date_str}\n"
    receipt += f"🆔 ID Tranzaksyon: {delivery_id[:8]}...\n\n"
    
    receipt += "👤 ENFÒMASYON:\n"
    receipt += f"   Vandè: {seller_whatsapp}\n"
    receipt += f"   Achte: {buyer_whatsapp}\n\n"
    
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    receipt += "📦 ATIK YO:\n"
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, item in enumerate(cart_items_data, 1):
        title = item.get('title', 'N/A')
        quantity = item.get('quantity', 1)
        price = item.get('price', 0)
        subtotal = price * quantity
        
        receipt += f"{idx}. {title}\n"
        receipt += f"   Kantite: {quantity}\n"
        receipt += f"   Pri Inite: {price} Gkach\n"
        receipt += f"   Sou-total: {subtotal} Gkach\n\n"
    
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    receipt += "💰 REZIME:\n"
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    receipt += f"Pri Pwodwi:      {total_product_price} Gkach\n"
    receipt += f"Pri Livrezon:    {total_shipping} Gkach\n"
    receipt += "─────────────────────────────\n"
    receipt += f"TOTAL:           {grand_total} Gkach\n\n"
    
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    receipt += "✅ TRANZAKSYON KONPLETE\n"
    receipt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    receipt += "Mèsi pou biznis ou! 🙏\n"
    receipt += "Glory2yahPub - Platfòm Piblisite #1\n"
    
    return receipt

def generate_pdf_receipt(delivery_id, buyer_whatsapp, seller_whatsapp, cart_items_data, total_product_price, total_shipping, grand_total, transaction_date=None, output_path=None):
    """
    Generate a PDF receipt for a completed transaction
    
    Args:
        delivery_id (str): Unique delivery/transaction ID
        buyer_whatsapp (str): Buyer's WhatsApp number
        seller_whatsapp (str): Seller's WhatsApp number
        cart_items_data (list): List of cart items with details
        total_product_price (int): Total price of products
        total_shipping (int): Total shipping cost
        grand_total (int): Grand total (products + shipping)
        transaction_date (datetime, optional): Transaction date
        output_path (str, optional): Path to save PDF. If None, generates in static/uploads/
        
    Returns:
        str: Path to generated PDF file
    """
    from datetime import datetime
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    
    if transaction_date is None:
        transaction_date = datetime.now()
    
    # Generate filename if not provided
    if output_path is None:
        filename = f"receipt_{delivery_id}.pdf"
        output_path = os.path.join('static', 'uploads', filename)
    
    # Create PDF
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=1  # Center
    )
    
    elements.append(Paragraph("RESI TRANZAKSYON", title_style))
    elements.append(Paragraph("Glory2yahPub", styles['Heading2']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Transaction info
    date_str = transaction_date.strftime("%d/%m/%Y %H:%M")
    info_data = [
        ['Dat:', date_str],
        ['ID Tranzaksyon:', delivery_id],
        ['Vandè:', seller_whatsapp],
        ['Achte:', buyer_whatsapp]
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#7f8c8d')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Items table
    items_data = [['#', 'Atik', 'Kantite', 'Pri Inite', 'Sou-total']]
    
    for idx, item in enumerate(cart_items_data, 1):
        title = item.get('title', 'N/A')
        quantity = item.get('quantity', 1)
        price = item.get('price', 0)
        subtotal = price * quantity
        
        items_data.append([
            str(idx),
            title[:30] + '...' if len(title) > 30 else title,
            str(quantity),
            f"{price} Gkach",
            f"{subtotal} Gkach"
        ])
    
    items_table = Table(items_data, colWidths=[0.5*inch, 2.5*inch, 1*inch, 1.2*inch, 1.2*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Summary table
    summary_data = [
        ['Pri Pwodwi:', f"{total_product_price} Gkach"],
        ['Pri Livrezon:', f"{total_shipping} Gkach"],
        ['TOTAL:', f"{grand_total} Gkach"]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.5*inch))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#27ae60'),
        alignment=1  # Center
    )
    elements.append(Paragraph("✅ TRANZAKSYON KONPLETE", footer_style))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("Mèsi pou biznis ou! 🙏", styles['Normal']))
    elements.append(Paragraph("Glory2yahPub - Platfòm Piblisite #1", styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    
    return output_path
